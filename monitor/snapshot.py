"""Collect a read-only snapshot of the lab's GitHub repos and Hugging Face datasets
and publish it, with the dashboard page, to a private static Hugging Face Space.

Runs every 5 minutes on GitHub Actions (.github/workflows/lab-monitor.yml).
Needs two secrets: GH_MONITOR_TOKEN (GitHub, read-only) and HF_TOKEN (Hugging Face, write).
Nothing secret is written to data.json.
"""
import base64
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

import requests
from huggingface_hub import HfApi

OWNER = "smalltee2"
HF_ORG = "smalltee2UPSEEN"
SPACE = os.environ.get("MONITOR_SPACE", "smalltee2/lab-monitor")
PROJECTS = [
    # Student usernames are kept in students.json inside the private Space (written by invite.py),
    # not in this public repository.
    {"key": "msc1", "label": "ป.โท1 · Heat exposure", "repo": "msc1-heat-exposure-th", "dataset": "msc1-heat-exposure-th",
     "student": {}},
    {"key": "msc2", "label": "ป.โท2 · Compound extreme", "repo": "msc2-compound-extreme-th", "dataset": "msc2-compound-extreme-th",
     "student": {}},
    {"key": "msc3", "label": "ป.โท3 · PM2.5 downscaling", "repo": "msc3-pm25-downscaling-th", "dataset": "msc3-pm25-downscaling-th",
     "student": {}},
]
PIPELINES = [{"repo": "lab-data-fetch", "workflow": "nexgddp-thailand.yml", "dataset": "nexgddp-cmip6-thailand",
              "label": "NEX-GDDP-CMIP6 Thailand"}]
BOARD_URL = f"https://github.com/users/{OWNER}/projects/1"
REFRESH_URL = f"https://github.com/{OWNER}/lab-data-fetch/actions/workflows/lab-monitor.yml"
INVITE_URL = f"https://github.com/{OWNER}/lab-data-fetch/actions/workflows/invite-student.yml"
# Commits by the supervisor (or made on his behalf) are not student activity.
SUPERVISOR = {"smalltee2", "Teerachai Amnuaylojaroen", "teerachai.am@up.ac.th"}
NOW = dt.datetime.now(dt.timezone.utc)

gh = requests.Session()
gh.headers.update({"Authorization": f"Bearer {os.environ['GH_MONITOR_TOKEN']}",
                   "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
hf = HfApi(token=os.environ["HF_TOKEN"])
errors = []


def get(path, **params):
    r = gh.get(f"https://api.github.com/{path}", params=params, timeout=30)
    if r.status_code >= 400:
        errors.append(f"GitHub {path}: HTTP {r.status_code}")
        return None
    return r.json()


def checkbox_progress(body):
    done = len(re.findall(r"^\s*[-*] \[[xX]\]", body or "", re.M))
    todo = len(re.findall(r"^\s*[-*] \[ \]", body or "", re.M))
    return done, done + todo


def last_progress_entry(repo):
    f = get(f"repos/{OWNER}/{repo}/contents/docs/PROGRESS.md")
    if not f or "content" not in f:
        return None
    text = base64.b64decode(f["content"]).decode("utf-8", "replace")
    parts = re.split(r"^## ", text, flags=re.M)
    entries = [p for p in parts[1:] if not p.startswith("YYYY")]
    return ("## " + entries[-1]).strip()[:1200] if entries else None


def github_project(p):
    repo = p["repo"]
    info = {"repo": repo, "url": f"https://github.com/{OWNER}/{repo}"}
    since = (NOW - dt.timedelta(days=7)).isoformat()
    commits = get(f"repos/{OWNER}/{repo}/commits", per_page=50) or []

    def who(c):
        return (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]

    def is_supervisor(c):
        return who(c) in SUPERVISOR or c["commit"]["author"].get("email") in SUPERVISOR

    def brief(c):
        return {"date": c["commit"]["author"]["date"], "message": c["commit"]["message"].split("\n")[0][:140],
                "author": who(c), "url": c["html_url"]}

    student = [c for c in commits if not is_supervisor(c)]
    recent = [c for c in student if c["commit"]["author"]["date"] >= since[:19]]
    info["last_commit"] = brief(student[0]) if student else None
    info["last_any_commit"] = brief(commits[0]) if commits else None
    info["commits_7d"] = len(recent)
    info["authors_7d"] = sorted({who(c) for c in recent})
    issues = get(f"repos/{OWNER}/{repo}/issues", state="all", per_page=50) or []
    info["issues"] = []
    info["pulls_open"] = 0
    for i in issues:
        if "pull_request" in i:
            info["pulls_open"] += i["state"] == "open"
            continue
        done, total = checkbox_progress(i.get("body"))
        info["issues"].append({"number": i["number"], "title": i["title"], "state": i["state"], "url": i["html_url"],
                               "done": done, "total": total, "comments": i["comments"], "updated": i["updated_at"],
                               "assignees": [a["login"] for a in i.get("assignees", [])]})
    info["issues"].sort(key=lambda x: (x["state"] != "open", x["number"]))
    info["progress_entry"] = last_progress_entry(repo)
    return info


def hf_dataset(name):
    repo = f"{HF_ORG}/{name}"
    out = {"id": repo, "url": f"https://huggingface.co/datasets/{repo}"}
    try:
        files = [f for f in hf.list_repo_tree(repo, repo_type="dataset", recursive=True) if hasattr(f, "size")]
        data = [f for f in files if not f.path.endswith((".gitkeep", ".gitattributes", "README.md"))]
        out["files"] = len(data)
        out["bytes"] = sum(f.size or 0 for f in data)
        top = {}
        for f in data:
            parts = f.path.split("/")
            k = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
            top[k] = top.get(k, 0) + 1
        out["folders"] = dict(sorted(top.items()))
        models = {f.path.split("_day_")[1].split("_")[0] for f in data if "_day_" in f.path}
        if models:
            out["models"] = sorted(models)
        commits = hf.list_repo_commits(repo, repo_type="dataset")
        if commits:
            out["last_update"] = commits[0].created_at.isoformat()
            out["last_message"] = commits[0].title
        out["private"] = hf.dataset_info(repo).private
    except Exception as e:
        errors.append(f"Hugging Face {repo}: {type(e).__name__}: {str(e)[:150]}")
    return out


def hf_members():
    r = requests.get(f"https://huggingface.co/api/organizations/{HF_ORG}/members",
                     headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}, timeout=30)
    if r.status_code >= 400:
        errors.append(f"Hugging Face members: HTTP {r.status_code}")
        return []
    out = []
    for m in r.json():
        out.append({"user": m.get("user") or m.get("name"), "name": m.get("fullname") or "",
                    "role": m.get("role") or ""})
    return out


def pipeline(pl):
    runs = (get(f"repos/{OWNER}/{pl['repo']}/actions/workflows/{pl['workflow']}/runs", per_page=5) or {}).get("workflow_runs", [])
    out = {"label": pl["label"], "url": f"https://github.com/{OWNER}/{pl['repo']}/actions", "runs": []}
    for r in runs:
        jobs = (get(f"repos/{OWNER}/{pl['repo']}/actions/runs/{r['id']}/jobs", per_page=100) or {}).get("jobs", [])
        count = lambda pred: sum(1 for j in jobs if pred(j))
        out["runs"].append({
            "id": r["id"], "url": r["html_url"], "status": r["status"], "conclusion": r["conclusion"],
            "started": r["run_started_at"], "updated": r["updated_at"],
            "jobs_total": len(jobs), "jobs_done": count(lambda j: j["status"] == "completed"),
            "jobs_failed": count(lambda j: j["conclusion"] == "failure"),
            "jobs_running": count(lambda j: j["status"] == "in_progress"),
            "failed_names": [j["name"] for j in jobs if j["conclusion"] == "failure"][:20],
        })
    ds = hf_dataset(pl["dataset"])
    out["dataset"] = ds
    return out


def load_students():
    """students.json in the private Space: {"msc1": {"gh": ..., "hf": ..., "name": ...}, ...}."""
    from huggingface_hub import hf_hub_download
    try:
        path = hf_hub_download(SPACE, "students.json", repo_type="space", token=os.environ["HF_TOKEN"])
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def student_name(st, members):
    """Display name: configured name, else Hugging Face full name, else GitHub name, else username."""
    if st.get("name"):
        return st["name"]
    for m in members:
        if st.get("hf") and (m.get("user") or "").lower() == st["hf"].lower() and m.get("name"):
            return m["name"]
    if st.get("gh"):
        u = get(f"users/{st['gh']}")
        if u and u.get("name"):
            return u["name"]
        return st["gh"]
    return ""


def main():
    snap = {"generated": NOW.isoformat(), "board": BOARD_URL, "refresh": REFRESH_URL, "invite": INVITE_URL, "projects": [], "pipelines": []}
    members = hf_members()
    snap["hf_members"] = members
    students = load_students()
    for p in PROJECTS:
        st = {**p.get("student", {}), **students.get(p["key"], {})}
        entry = {"key": p["key"], "label": p["label"], "student": student_name(st, members),
                 "student_gh": st.get("gh", ""), "student_hf": st.get("hf", ""),
                 "github": github_project(p), "data": hf_dataset(p["dataset"])}
        snap["projects"].append(entry)
    snap["pipelines"] = [pipeline(pl) for pl in PIPELINES]
    private = sum(x["data"].get("bytes", 0) for x in snap["projects"] if x["data"].get("private", True))
    snap["private_storage"] = {"bytes": private, "quota_bytes": 100 * 10**9}
    snap["errors"] = errors

    here = Path(__file__).parent
    out = here / "site"
    out.mkdir(exist_ok=True)
    (out / "data.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    for f in ("index.html",):
        (out / f).write_text((here / f).read_text())
    (out / "README.md").write_text((here / "space_README.md").read_text())
    if "--no-upload" in sys.argv:
        print("wrote", out)
        return
    hf.create_repo(SPACE, repo_type="space", space_sdk="static", private=True, exist_ok=True)
    hf.upload_folder(repo_id=SPACE, repo_type="space", folder_path=str(out),
                     commit_message=f"Snapshot {NOW:%Y-%m-%d %H:%M} UTC")
    print("published", SPACE, "errors:", len(errors))
    for e in errors:
        print("  ", e)


if __name__ == "__main__":
    main()
