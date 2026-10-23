# Know Place Analysis — Isolated Runbook

This guide applies only to branch `feat/know-place-analysis`. Do not run the existing source-AOI workflow as a substitute and do not merge these files to `main`.

## Current phase

The pure kernels, strict raw-HDF5 reader, metadata-cube interpolation, five-pair orchestration and synthetic integration tests are implemented. The supplied paper and Supplementary Information now establish the crown bounds and exact five author granule IDs. This remains an **exploratory paper-method path**, not a validated landslide detector: the historical raw replay's first pair is X05026 rather than author P05023, and the separate Zenodo code/output archive is now hash-verified. However, source HDF5 payloads are not in the archive and exact author-method parity has not been implemented; this remains an exploratory path, not a validated detector.

## Five-pair product candidates observed in Dynamic AOI Run 39942529304

The table below records the **historical raw replay inputs** from Dynamic AOI Run 39942529304, not the author-exact five-product manifest. Supplementary Table 1 specifies P05023 for every pair; the first historic input is X05026. Keep that source/hash as historical evidence and do not silently substitute or relabel it as the author input. Exact five author IDs and published scalar results are transcribed in [`docs/know-place/reference/author_benchmark_v1.json`](know-place/reference/author_benchmark_v1.json).

| Reference → secondary | Granule identifier without `.h5` | Previous run ID |
|---|---|---|
| 2026-06-20 → 2026-07-02 | `NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_X05026_N_F_J_001` | GOFF-003 |
| 2026-07-02 → 2026-07-14 | `NISAR_L2_PR_GOFF_024_098_A_016_025_4000_SH_20260702T233920_20260702T233955_20260714T233920_20260714T233954_P05023_F_F_J_001` | GOFF-007 |
| 2026-07-14 → 2026-07-26 | `NISAR_L2_PR_GOFF_025_098_A_016_026_4000_SH_20260714T233920_20260714T233954_20260726T233919_20260726T233954_P05023_N_F_J_001` | GOFF-011 |
| 2026-07-26 → 2026-08-19 | `NISAR_L2_PR_GOFF_026_098_A_016_028_4000_SH_20260726T233919_20260726T233954_20260819T233918_20260819T233953_P05023_N_F_J_001` | GOFF-015 |
| 2026-08-19 → 2026-08-31 | `NISAR_L2_PR_GOFF_028_098_A_016_029_4000_SH_20260819T233918_20260819T233953_20260831T233918_20260831T233952_P05023_N_F_J_001` | GOFF-019 |

The author series uses ascending T098, L-SAR HH, PR GOFF layer2 products. The archived TableS1 manifest confirms five exact P05023 IDs, but the archive does not contain their raw HDF5 bytes. The isolated live-catalog check confirmed four trusted collection routes and returned NOT_FOUND for the first P05023 pair. Do not relabel historical X05026 as P05023; keep raw replay blocked until exact source bytes are pinned.

## Reference box and crown

Reference box (the user's GEE polygon):

```text
POLYGON ((85.500000 28.265000, 85.565000 28.265000, 85.565000 28.318000, 85.500000 28.318000, 85.500000 28.265000))
```

The paper and Supplementary Fig. 2 specify these crown bounds, area 2.07 km²; the same rectangular bounds are used in the current WKT. This resolves the coordinate-geometry uncertainty. Exact raster mask inclusion / pixel-centre and edge rules must still be checked against the author golden raster; the historic target-pair replay has 296 valid crown cells whereas Supplementary Table 4 reports 298:

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


## Completed first raw replay and R-policy reanalysis (2026-10-24)

- Raw-input analysis: [Run 40006999011](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40006999011). All five candidate GOFF HDF5 file sizes and SHA-256 values matched the historically inspected source objects; all five intervals produced metrics.
- Saved-array coherence reanalysis: [Run 40015023621](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015023621). This downloaded only the previous derived-only run artifact; no raw HDF5 was downloaded. All five NPZ diagnostic-array checksums matched the source report. The reanalysis report and summary passed Drive remote verification.
- Scientific comparison: for 26 July–19 August, crown median horizontal magnitude was 0.966 m, mean-vector magnitude 1.722 m, azimuth 277.79°. On the pointwise 0.17–2.75 m window, R was 0.869 for 150 crown centres; the preprint reports about 0.869 for 147 centres. Background R/count and control statistics remain different.
- The original min-25-valid-neighbours condition is no longer the primary R rule: the preprint does not specify it. The primary result uses at least one valid vector and emits sensitivity for min valid counts 1/5/10/15/20/25.
- The current circular-control result (median ~0.128 m; ~96.08th percentile) is **not comparable** with the paper's ~0.14 m / 94.7th percentile because exact crown geometry, source variants and author control sampling are not verified. It must not trigger an alarm.
- Current gate is `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; `HAZARD_DETECTION_STATUS=NOT_EVALUATED`. The Zenodo archive payload is integrity-verified; see `know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md`. Evidence table, raw/source hashes, R-policy comparison and acceptance gaps: [RAW_REPLAY_40006999011_R_POLICY_AUDIT.md](know-place/evidence/RAW_REPLAY_40006999011_R_POLICY_AUDIT.md).
- Validation: [Run 40015371603](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015371603) passed 46 tests, parsed all three isolated workflows and passed actionlint. All files remain on `feat/know-place-analysis`; `main` was not changed.


## Generic polygon + date-range engine and dashboard

A separate arbitrary-AOI path now lives in `tools/know_place/aoi_request.py`, `series.py`, `aoi_runner.py`, `dashboard.py`, and `uncertainty.py`. It is a different interface from the five-pair paper-reproduction command above.

### GitHub Actions UI

Open the repository's **Actions** tab on `feat/know-place-analysis` and choose **Know Place AOI analysis — polygon/date-range**:

[Workflow file](../.github/workflows/know-place-aoi-analysis.yml)

1. Enter one closed WGS84 polygon WKT, inclusive UTC start/end dates, polarization, and optional track/direction. You may supply an external reference/background polygon. If omitted, the runner uses component-wise median correction from a 2 km local context outside the AOI; explicitly setting `reference.policy=none` disables correction. The local-context approach assumes most background pixels are stable and must be inspected.
2. Leave `execute_downloads=false` first. The dry run queries ASF and writes the exact candidate inventory and separate pair/processing chains, but downloads no raw product.
3. Inspect `catalog-manifest.json`, `series-plan.json` and the request hash in the run artifact. The plan deliberately separates tracks, direction, polarization, product maturity and CRID/release. Same-pair release ambiguity fails closed; no preferred variant is silently chosen.
4. Set `execute_downloads=true` only after reviewing the dry-run selection and confirming Earthdata and Drive secrets are configured. The workflow downloads one selected pair at a time, checks bytes/SHA-256/receipt, calculates metrics, writes GeoTIFF/NPZ/CSV, produces `visuals/dashboard.html`, and uploads a derived-only ZIP to central Google Drive. The upload receipt records the local and downloaded-remote SHA-256 checksums.
5. Raw HDF5 files and their receipts are deleted from the workflow's ephemeral cache immediately after each pair finishes; the result manifest keeps source filename, size and SHA-256. This avoids filling the GitHub runner disk, but it means a later run reacquires raw source unless a separately configured persistent verified cache is used.

The runner caps a single download job at 30 selected products. A larger window is not silently truncated: split it into explicit date windows and preserve the resulting run manifests, keeping overlapping pair intervals separate. This is an initial bounded execution limit, not a NISAR mission limit.

### Local use

Install the dedicated runtime rather than relying on the legacy five-pair environment:

```bash
python -m pip install -r tools/know_place/requirements.txt
python -m py_compile tools/know_place/*.py
python -m pytest -q --confcutdir=tools/tests tools/tests/test_know_place_*.py
python -m tools.know_place.aoi_runner --request tools/know_place/examples/bhote_koshi_candidate_request.json --out ./know-place-results --dry-run
```

For a credentialed download/measurement run, omit `--dry-run` and set `EARTHDATA_TOKEN` or `EARTHDATA_USERNAME`/`EARTHDATA_PASSWORD`. Use a private `--cache-dir`. Add `--ephemeral-source-cache` when raw HDF5 should be deleted after processing rather than retained for future local reuse.

### Motion-dynamics features

Each measured pair's exact source acquisition start/end timestamps are reduced to reference/secondary acquisition midpoints. The pair's median horizontal displacement magnitude and mean horizontal vector are divided by the midpoint separation, producing separate **interval-average rates** in m/day. These are not instantaneous velocity and do not localize motion onset inside the interval.

The result also records `motion_dynamics` features. Changes in mean-vector rate and the corresponding descriptive rate-change magnitude (m/day) and acceleration-like feature (m/day²) are calculated only if both pairs have actual metrics, are in the same release/maturity chain, the pair intervals are contiguous, projected grid lattices match, and neither interval crosses a registered mission gap. Otherwise the rate-change field is null with an explicit block reason. No risk score or operational alarm is emitted.

`motion_dynamics.status` distinguishes complete, partial, and insufficient feature coverage. `risk_score` remains null and `hazard_detection_status=NOT_EVALUATED` until a separate model is trained/calibrated and tested on independently labelled event/non-event sites. Rate changes are candidate research features, not evidence of an impending collapse.

### Dashboard outputs and scientific status

- `visuals/dashboard.html`: offline HTML, no CDN; contains displacement trend, interval-average rates, gap-aware motion-dynamics table, AOI outline over a downsampled raster preview, source IDs/SHA-256, valid AOI pixel support, uncertainty interval and status gates. It is not a basemap or a substitute for full-resolution GIS rasters.
- `maps/*_displacement.tif`: native-grid east/north/magnitude/coherence/valid-mask/high-magnitude-review flag/uncorrected-magnitude bands.
- `diagnostics/*_arrays.npz`: derived arrays and AOI/reference masks for numerical reanalysis.
- `timeseries.csv`: pairwise displacement metrics and interval-average magnitude rate. `motion-features.csv`: same-chain rates, gap/grid comparability, rate-change features, blocked reasons and the explicit uncalibrated risk-score status. `result.json` and `manifest.json` record request hash, runtime package versions, source checksums and derived-file checksums.
- `paper_reproduction_status=NOT_EVALUATED_GENERIC_AOI` and `hazard_detection_status=NOT_EVALUATED` are expected. The generic runner measures movement and does not issue alarms.
- Generic mode preserves and flags displacement above the configurable review threshold by default because rapid failures can be real high-magnitude motion. The Bhote Koshi paper-method example explicitly chooses `reject_above_threshold`; that method-specific setting must never be adopted as a universal “real movement” rule.
- Constant HAE is still an approximation, not DEM-derived per-pixel terrain height. Operational monitoring remains blocked until terrain-dependent geometry and independent validation are implemented and tested.

For event-level thresholds and a separate multi-event holdout strategy see [MULTI_EVENT_VALIDATION_PLAN.md](know-place/validation/MULTI_EVENT_VALIDATION_PLAN.md). Current author-supplement and method-parity blockers are documented in [AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md](know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md) and the later [Zenodo archive/method audit](know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md).
