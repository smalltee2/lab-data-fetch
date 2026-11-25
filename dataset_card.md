---
pretty_name: NEX-GDDP-CMIP6 daily, clipped to Thailand
license: cc-by-4.0
language:
  - en
tags:
  - climate
  - cmip6
  - downscaling
  - thailand
  - southeast-asia
---

# NEX-GDDP-CMIP6 daily, clipped to Thailand

Daily bias-corrected, statistically downscaled CMIP6 projections from NASA NEX-GDDP-CMIP6 (0.25°), clipped to a box around Thailand (latitude 5.375–20.875° N, longitude 97.125–105.875° E). Values are unchanged from the source files; only the spatial subset was taken and the yearly files were joined into one file per model, scenario and variable.

Prepared by the Atmospheric Pollution and Climate Research Unit, School of Energy and Environment, University of Phayao, for graduate research on heat exposure and compound climate extremes in Thailand. Download code: https://github.com/smalltee2/lab-data-fetch

## Contents

Scenarios: {{SCENARIOS}}. Historical runs cover 1950–2014 and SSP runs 2015–2100.

Variables requested: `tasmax`, `tasmin`, `tas` (K), `hurs` (%), `sfcWind` (m s⁻¹), `rsds`, `rlds` (W m⁻²), `pr` (kg m⁻² s⁻¹). Not every model provides every variable; a variable missing from the source is missing here.

Models: {{MODELS}}.

Layout: `data/<scenario>/<variable>/<variable>_day_<model>_<scenario>_<member>_<grid>_THA_<start>-<end>.nc`. Where NASA released more than one version of a yearly file, the highest version was used; the exact source files and versions are listed in each file's `source_files` and `source_versions` attributes.

## Use

```python
from huggingface_hub import hf_hub_download
import xarray as xr

path = hf_hub_download("smalltee2UPSEEN/nexgddp-cmip6-thailand", repo_type="dataset",
                       filename="data/ssp245/tasmax/<file name>.nc")
ds = xr.open_dataset(path)
```

## Source, licence and citation

Source: NASA Earth Exchange Global Daily Downscaled Projections (NEX-GDDP-CMIP6), AWS Open Data `s3://nex-gddp-cmip6`, and NCCS (https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6). According to the NCCS technical note, all NEX-GDDP-CMIP6 outputs have been released under a blanket Creative Commons Zero (CC0) licence since September 2022; this subset is shared under CC BY 4.0, asking users to credit the original source as below.

Please cite the original dataset:

Thrasher, B., Wang, W., Michaelis, A., Melton, F., Lee, T., & Nemani, R. (2022). NASA Global Daily Downscaled Projections, CMIP6. *Scientific Data*, 9, 262. https://doi.org/10.1038/s41597-022-01393-4

and acknowledge the CMIP6 modelling groups whose output underlies the downscaled data.
