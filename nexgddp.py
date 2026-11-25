"""Fetch NEX-GDDP-CMIP6 daily data, clip to Thailand, and push to a Hugging Face dataset.

Runs on GitHub Actions (no personal machine). Two sub-commands:

    python nexgddp.py plan  --scenarios historical ssp245 ssp585 [--models A B]
        lists models on the public S3 bucket, creates/updates the HF dataset and card,
        and prints a JSON job matrix (one job per model x scenario).

    python nexgddp.py fetch --model ACCESS-CM2 --scenario ssp245 --variables tas pr ...
        downloads every yearly file for that model/scenario/variable, keeps only the
        Thailand box, joins the years into one NetCDF per variable, and uploads all
        variables of the job to Hugging Face in a single commit. Files already on
        Hugging Face are skipped, so a failed or cancelled run can simply be re-run.

Source: NASA NEX-GDDP-CMIP6 on AWS Open Data, s3://nex-gddp-cmip6 (anonymous access).
Reference: Thrasher et al. (2022) Sci. Data 9, 262, doi:10.1038/s41597-022-01393-4.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BUCKET = "nex-gddp-cmip6/NEX-GDDP-CMIP6"
# Thailand bounding box with a half-cell margin; NEX-GDDP longitudes run 0-360,
# which equals degrees east here because Thailand lies at 97-106 E.
LAT = (5.375, 20.875)
LON = (97.125, 105.875)
FNAME = re.compile(r"^(?P<var>[A-Za-z]+)_day_(?P<model>.+?)_(?P<scen>[a-z0-9]+)_(?P<member>r\d+i\d+p\d+f\d+)_"
                   r"(?P<grid>g[a-z0-9]+)_(?P<year>\d{4})(?:_v(?P<vmaj>\d+)\.(?P<vmin>\d+))?\.nc$")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def s3():
    import s3fs
    return s3fs.S3FileSystem(anon=True, default_block_size=32 * 2**20)


def pick_latest(paths):
    """For each (grid, year) keep the file with the highest version suffix (no suffix = v0.0)."""
    best = {}
    for p in paths:
        m = FNAME.match(os.path.basename(p))
        if not m:
            continue
        ver = (int(m["vmaj"] or 0), int(m["vmin"] or 0))
        key = (m["grid"], int(m["year"]))
        if key not in best or ver > best[key][0]:
            best[key] = (ver, p, m["member"])
    by_grid = {}
    for (grid, year), (ver, p, member) in sorted(best.items()):
        by_grid.setdefault(grid, []).append((year, ver, p, member))
    return by_grid


def out_name(var, model, scen, member, grid, y0, y1):
    return f"data/{scen}/{var}/{var}_day_{model}_{scen}_{member}_{grid}_THA_{y0}-{y1}.nc"


def clip_one(fs, path, tmpdir):
    import xarray as xr
    local = Path(tmpdir) / os.path.basename(path)
    for attempt in range(4):
        try:
            fs.get(path, str(local))
            break
        except Exception as e:  # network hiccup: retry with backoff
            log("  retry", attempt + 1, os.path.basename(path), type(e).__name__)
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"download failed: {path}")
    try:  # keep model calendars (noleap, 360_day) intact
        kw = {"decode_times": xr.coders.CFDatetimeCoder(use_cftime=True)}
    except AttributeError:
        kw = {"use_cftime": True}
    with xr.open_dataset(local, engine="h5netcdf", **kw) as ds:
        lat = slice(*LAT) if ds.lat[0] < ds.lat[-1] else slice(LAT[1], LAT[0])
        sub = ds.sel(lat=lat, lon=slice(*LON)).sortby("lat").load()
    if sub.sizes.get("lat", 0) == 0 or sub.sizes.get("lon", 0) == 0:
        raise RuntimeError(f"empty Thailand subset in {path}: check lat/lon coordinates")
    local.unlink()
    return sub


def build_variable(fs, files, tmpdir, threads):
    import xarray as xr
    with ThreadPoolExecutor(threads) as ex:
        parts = list(ex.map(lambda f: clip_one(fs, f[2], tmpdir), files))
    ds = xr.concat(parts, dim="time").sortby("time")
    ds.attrs.update({
        "title": "NEX-GDDP-CMIP6 clipped to Thailand",
        "source_files": " ".join(os.path.basename(f[2]) for f in files),
        "source_versions": " ".join(f"{f[0]}:v{f[1][0]}.{f[1][1]}" for f in files),
        "processing": f"Subset lat {LAT}, lon {LON} (degrees east); years concatenated; values unchanged.",
        "source": "NASA NEX-GDDP-CMIP6, s3://nex-gddp-cmip6 (CC0 since Sept 2022 per NCCS Tech Note)",
        "references": "Thrasher et al. (2022) Sci. Data 9, 262, doi:10.1038/s41597-022-01393-4",
    })
    return ds


def write_nc(ds, path):
    enc = {}
    for v in ds.data_vars:
        chunks = tuple(min(n, c) for n, c in zip(ds[v].shape, (366, 64, 64)))
        enc[v] = {"zlib": True, "complevel": 4, "shuffle": True, "dtype": "float32", "chunksizes": chunks}
    ds.to_netcdf(path, engine="h5netcdf", encoding=enc)


def existing_files(api, repo):
    try:
        return set(api.list_repo_files(repo, repo_type="dataset"))
    except Exception:
        return set()


def cmd_plan(a):
    from huggingface_hub import HfApi
    fs = s3()
    models = sorted(os.path.basename(p) for p in fs.ls(BUCKET) if fs.isdir(p))
    if a.models:
        models = [m for m in models if m in set(a.models)]
    log("models found:", len(models), " ".join(models))
    token = os.environ.get("HF_TOKEN")
    if token:
        api = HfApi(token=token)
        api.create_repo(a.hf_repo, repo_type="dataset", private=False, exist_ok=True)
        card = Path(__file__).with_name("dataset_card.md").read_text()
        card = card.replace("{{MODELS}}", ", ".join(models)).replace("{{SCENARIOS}}", ", ".join(a.scenarios))
        api.upload_file(path_or_fileobj=card.encode(), path_in_repo="README.md", repo_id=a.hf_repo,
                        repo_type="dataset", commit_message="Update dataset card")
    matrix = {"include": [{"model": m, "scenario": s} for m in models for s in a.scenarios]}
    out = json.dumps(matrix)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"matrix={out}\n")
    print(out)


def cmd_fetch(a):
    from huggingface_hub import HfApi, CommitOperationAdd
    fs, api = s3(), HfApi(token=os.environ["HF_TOKEN"])
    done = existing_files(api, a.hf_repo)
    scen_dir = f"{BUCKET}/{a.model}/{a.scenario}"
    if not fs.exists(scen_dir):
        log("no", a.scenario, "for", a.model, "- nothing to do")
        return
    members = sorted(os.path.basename(p) for p in fs.ls(scen_dir))
    member_dir = f"{scen_dir}/{members[0]}"
    if len(members) > 1:
        log("several members", members, "- using", members[0])
    work = Path(tempfile.mkdtemp(prefix="nex_"))
    ops, skipped, missing = [], [], []
    for var in a.variables:
        vdir = f"{member_dir}/{var}"
        if not fs.exists(vdir):
            missing.append(var)
            continue
        for grid, files in pick_latest(fs.ls(vdir)).items():
            y0, y1, member = files[0][0], files[-1][0], files[0][3]
            target = out_name(var, a.model, a.scenario, member, grid, y0, y1)
            if target in done:
                skipped.append(var)
                continue
            log(f"{a.model} {a.scenario} {var} {grid}: {len(files)} files {y0}-{y1}")
            ds = build_variable(fs, files, work, a.threads)
            local = work / os.path.basename(target)
            write_nc(ds, local)
            log(f"  wrote {local.name} {local.stat().st_size / 2**20:.1f} MB, shape {dict(ds.sizes)}")
            ops.append(CommitOperationAdd(path_in_repo=target, path_or_fileobj=str(local)))
    if missing:
        log("variables not provided by this model:", " ".join(missing))
    if skipped:
        log("already on Hugging Face:", " ".join(skipped))
    if ops:
        for attempt in range(4):
            try:
                api.create_commit(a.hf_repo, ops, repo_type="dataset",
                                  commit_message=f"Add {a.model} {a.scenario} ({len(ops)} variables)")
                break
            except Exception as e:
                log("  commit retry", attempt + 1, type(e).__name__, str(e)[:200])
                time.sleep(30 * (attempt + 1))
        else:
            sys.exit(f"upload failed for {a.model} {a.scenario}")
        log("uploaded", len(ops), "files")
    shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--scenarios", nargs="+", default=["historical", "ssp245", "ssp585"])
    p.add_argument("--models", nargs="*")
    p.add_argument("--hf-repo", default="smalltee2UPSEEN/nexgddp-cmip6-thailand")
    f = sub.add_parser("fetch")
    f.add_argument("--model", required=True)
    f.add_argument("--scenario", required=True)
    f.add_argument("--variables", nargs="+", default=["tasmax", "tasmin", "tas", "hurs", "sfcWind", "rsds", "rlds", "pr"])
    f.add_argument("--hf-repo", default="smalltee2UPSEEN/nexgddp-cmip6-thailand")
    f.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    cmd_plan(a) if a.cmd == "plan" else cmd_fetch(a)


if __name__ == "__main__":
    main()
