# Backend science audit: `tools/run_export_science_diagnostics.py`

**Backend dashboard source pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `1814e5dc0c96229fd4fc54314a0d497b5b0ce9ed`  
**Find Displacements use:** called by `aggregate_aoi_run.py` against retained clipped exports.

## Current behaviour

- Resolves the exact AOI in the pinned science code and builds diagnostics from exported GUNW raster layers.
- Runs the science `pixel_stack.py` diagnostic in two modes: default pair-median/common-mode removal and `--keep-common-mode` sensitivity mode.
- Preserves logs and output status.
- Runs the named-AOI `candidate_check.py` only under its supported policy; a custom WKT AOI is explicitly marked skipped rather than silently mapped to `source`, `langtang` or `lhende`.

## Scientific assessment

The two common-mode variants are a sound sensitivity practice because pair-wise scene median removal can erase a broad real deformation signal, while retaining it may preserve atmospheric/orbit common mode. Neither output is an absolute ground-motion reference. The pixel-stack algorithm requires a compatible contiguous PR chain and at least two intervals/three epochs; partial support is not filled as zero.

The stack writes per-pixel LOS velocity and residual sigma GeoTIFFs, plus observed pair count and longest contiguous support. These outputs are diagnostic and relative. They are currently not automatically inserted into `prepare_web_assets.py`'s public layer list.

## Tests and evidence

`tools/tests/test_run_export_science_diagnostics.py` checks exact export identity handling, prevents hazard-confirmation wording, tests source-mask fallback scope and verifies both common-mode variants are invoked.

**Verdict:** PASS for execution policy and dual common-mode diagnostic; PARTIAL for uncertainty calibration and map publication.
