# lab-data-fetch

Download scripts for the climate data used by the M.Sc. projects of the Atmospheric Pollution and Climate Research Unit, School of Energy and Environment, University of Phayao. Everything runs on GitHub Actions, so no personal computer is needed: each job downloads source files, keeps only the Thailand area, and uploads the result to Hugging Face. This repository holds code only, never data or credentials.

## NEX-GDDP-CMIP6, Thailand

Workflow: `.github/workflows/nexgddp-thailand.yml` · Script: `nexgddp.py` · Output: Hugging Face dataset `smalltee2UPSEEN/nexgddp-cmip6-thailand`

The workflow first lists the models on NASA's public bucket (`s3://nex-gddp-cmip6`), then runs one job per model and scenario (up to 10 at a time). Each job fetches the yearly global files, clips them to latitude 5.375–20.875° N and longitude 97.125–105.875° E, joins the years into one NetCDF per variable, and uploads them in one commit. Files already on Hugging Face are skipped, so a failed job can be re-run without repeating finished work.

Run it from the Actions tab (Run workflow) or with `gh workflow run nexgddp-thailand.yml`. Defaults: all models; `historical ssp245 ssp585`; variables `tasmax tasmin tas hurs sfcWind rsds rlds pr`. For a quick test, enter one or two model names in the `models` field.

Required secret: `HF_TOKEN`, a Hugging Face token with write access to the `smalltee2UPSEEN` organization (Settings → Secrets and variables → Actions, or `gh secret set HF_TOKEN`).

Source data: Thrasher et al. (2022), NASA Global Daily Downscaled Projections, CMIP6, *Scientific Data* 9, 262, https://doi.org/10.1038/s41597-022-01393-4.

## Lab monitor

Workflow: `.github/workflows/lab-monitor.yml` · Code: `monitor/` · Output: private Hugging Face Space `smalltee2/lab-monitor`

Every 15 minutes the workflow reads the three student repositories (commits, issues and their checkbox progress, pull requests, the latest `docs/PROGRESS.md` entry), the runs of the data workflows, and the Hugging Face datasets, then publishes `data.json` and the dashboard page to the private Space. Only the Space owner can open it. Secrets: `GH_MONITOR_TOKEN` (GitHub fine-grained token, read-only) and `HF_TOKEN`.
