# Know Place Analysis — Isolated Runbook

This guide applies only to branch `feat/know-place-analysis`. Do not run the existing source-AOI workflow as a substitute and do not merge these files to `main`.

## Current phase

The pure kernels, strict raw-HDF5 reader, metadata-cube interpolation, separate WKT box/crown geometry, five-pair orchestration and synthetic integration tests are implemented. The code is an **exploratory paper-method path**, not a validated landslide detector. No analysis of real HDF5 inputs is considered a paper reproduction until exact crown geometry, product variant identity and author golden outputs have been verified.

## Five-pair product candidates observed in Dynamic AOI Run 39942529304

The last Dynamic AOI run manifest selected the following GOFF products for the five target date intervals. These names are **available candidate IDs**, not yet confirmed against the paper's original supplementary inputs. The 20 June–2 July pair was listed as CRID X05026 with ASF PROVISIONAL evidence, while the other four pairs selected P05023. Do not silently substitute variants or call them paper-identical.

| Reference → secondary | Granule identifier without `.h5` | Previous run ID |
|---|---|---|
| 2026-06-20 → 2026-07-02 | `NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_X05026_N_F_J_001` | GOFF-003 |
| 2026-07-02 → 2026-07-14 | `NISAR_L2_PR_GOFF_024_098_A_016_025_4000_SH_20260702T233920_20260702T233955_20260714T233920_20260714T233954_P05023_F_F_J_001` | GOFF-007 |
| 2026-07-14 → 2026-07-26 | `NISAR_L2_PR_GOFF_025_098_A_016_026_4000_SH_20260714T233920_20260714T233954_20260726T233919_20260726T233954_P05023_N_F_J_001` | GOFF-011 |
| 2026-07-26 → 2026-08-19 | `NISAR_L2_PR_GOFF_026_098_A_016_028_4000_SH_20260726T233919_20260726T233954_20260819T233918_20260819T233953_P05023_N_F_J_001` | GOFF-015 |
| 2026-08-19 → 2026-08-31 | `NISAR_L2_PR_GOFF_028_098_A_016_029_4000_SH_20260819T233918_20260819T233953_20260831T233918_20260831T233952_P05023_N_F_J_001` | GOFF-019 |

All five must be the correct ascending T098, L-SAR HH, PR GOFF layer2 products. The analysis checks identity from the filename; it records ASF maturity evidence supplied in the manifest but does not independently contact ASF. Before interpreting scientific results, save the exact source checksums and confirm each variant against the author's supplementary input list, if available.

## Reference box and crown

Reference box (the user's GEE polygon):

```text
POLYGON ((85.500000 28.265000, 85.565000 28.265000, 85.565000 28.318000, 85.500000 28.318000, 85.500000 28.265000))
```

The paper's published crown bounding coordinates do not identify its exact irregular polygon. This rectangle is a **bounding-box approximation**, only for exploratory testing:

```text
POLYGON ((85.5245 28.2847, 85.5400 28.2847, 85.5400 28.2970, 85.5245 28.2970, 85.5245 28.2847))
```

Do not label the rectangle `author-supplement-geometry`. The report must keep `paper_reproduction_status` blocked until exact polygon/source provenance and author reference values are independently verified.

## Input manifest

Store the raw HDF5 files locally in a private/untracked folder. Do not commit raw NISAR products, Earthdata credentials, Drive tokens or secrets. Create `know-place-inputs.json` beside that folder and use a relative or absolute path to each verified local file:

```json
{
  "schema_version": "know-place-analysis-inputs/1.0",
  "reference_box_wkt": "POLYGON ((85.500000 28.265000, 85.565000 28.265000, 85.565000 28.318000, 85.500000 28.318000, 85.500000 28.265000))",
  "crown_wkt": "POLYGON ((85.5245 28.2847, 85.5400 28.2847, 85.5400 28.2970, 85.5245 28.2970, 85.5245 28.2847))",
  "crown_geometry_kind": "bounding-box-approximation",
  "crown_geometry_source": "Published crown bounds, manually encoded; not the exact author polygon",
  "geometry_height_m": 5151.0,
  "control_seed": 260826,
  "control_draws": 1000,
  "coherence_minimum_valid_cells": 1,
  "coherence_neighbour_policy": "primary minimum 1 because the preprint does not specify a minimum valid neighbour count; outputs include 1/5/10/15/20/25 sensitivity",
  "products": [
    {
      "path": "raw/<exact-local-file-1>.h5",
      "expected_granule_name": "<exact-local-file-1>.h5",
      "catalog_maturity": "PROVISIONAL",
      "catalog_maturity_evidence": "<ASF dataMaturity filter + collection response and query timestamp>"
    },
    {
      "path": "raw/<exact-local-file-2>.h5",
      "expected_granule_name": "<exact-local-file-2>.h5",
      "catalog_maturity": "PROVISIONAL",
      "catalog_maturity_evidence": "<ASF evidence>"
    },
    {
      "path": "raw/<exact-local-file-3>.h5",
      "expected_granule_name": "<exact-local-file-3>.h5",
      "catalog_maturity": "PROVISIONAL",
      "catalog_maturity_evidence": "<ASF evidence>"
    },
    {
      "path": "raw/<exact-local-file-4>.h5",
      "expected_granule_name": "<exact-local-file-4>.h5",
      "catalog_maturity": "PROVISIONAL",
      "catalog_maturity_evidence": "<ASF evidence>"
    },
    {
      "path": "raw/<exact-local-file-5>.h5",
      "expected_granule_name": "<exact-local-file-5>.h5",
      "catalog_maturity": "PROVISIONAL",
      "catalog_maturity_evidence": "<ASF evidence>"
    }
  ]
}
```

Replace every placeholder before running. The script must stop on filename, pair-date, track, direction, polarization, layer, CRS, grid, metadata, source-file identity or quality-schema mismatches. Catalog maturity statements above are examples only.

## Run locally

From the checked-out feature branch, install the analysis dependencies already used by the isolated CI:

```bash
python -m pip install -r requirements-dev.txt numpy h5py scipy pyproj
python -m py_compile tools/know_place/*.py
python -m pytest -q --confcutdir=tools/tests tools/tests/test_know_place_*.py
python -m tools.know_place.analyze --config path/to/know-place-inputs.json --out path/to/know-place-output
```

The runner first inspects only the five files' grid axes and metadata, checks they have matching 80 m EPSG:32645 grids, and then opens one raw HDF5 at a time to read the box window. It records a SHA-256 of each full source file. The raw offset reader does not consume the existing reader's auto-referenced or deramped rasters.

## Output interpretation

- `KNOW_PLACE_ANALYSIS_STATUS=SCIENTIFIC_METRICS_COMPUTED` means all five pairs produced the explicitly labelled exploratory metrics. It does **not** mean paper reproduction.
- `STRUCTURAL_STATUS=PASS` covers input identity/schema, outputs and provenance gates. An individual pair can still have insufficient pixels or reference support.
- `PAPER_REPRODUCTION_STATUS=BLOCKED_...` is expected with the current crown rectangle and without author golden output parity.
- `HAZARD_DETECTION_STATUS=NOT_EVALUATED` is intentional. No hazard alarm is produced.
- Circular size-matched controls are currently an explicitly exploratory procedure. Do not quote them as the author's exact null distribution until the author algorithm has been recovered and parity tested.
- A displacement magnitude close to 0.96 m alone is not scientific reproduction. The crown metric, background correction, quality gates, direction/coherence, per-product identity and comparison statistics must all be comparable.
