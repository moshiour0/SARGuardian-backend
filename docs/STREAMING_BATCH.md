# SARGuardian streaming batch run

This workflow processes the exact Nepal source-AOI manifest committed in
moshiour0/SARGuardian at science commit
ab547ecc82bcc4d6ccef545a59852536c2beacc6. It does not substitute the
Langtang or Lhende polygons.

## Run it safely

1. Live processing is manual by design: open **Actions → SARGuardian Streaming
   Batch (source AOI) → Run workflow**. Ordinary code pushes run regression
   tests only; they do not automatically start large downloads or consume Drive
   storage.
2. Choose the inclusive `start_date` and `end_date` inputs in `YYYY-MM-DD`
   format. The window is applied to each baseline granule's **secondary
   acquisition date** (the third timestamp in the NISAR granule name). The
   default `2025-01-01` through `2026-12-31` covers the currently pinned
   products. The `source` AOI is fixed by the scientific project; there is no
   AOI input and its polygon is not changed.
3. Choose `retention_profile=derived-only` by default to save Drive space. It
   uploads the validated CSV/GeoTIFF products, source inventory, source SHA-256,
   preflight and validation receipts without creating or retaining a
   `*.science.h5` archive. Choose `full-lossless` only when future unrestricted
   HDF5 reprocessing is worth retaining a near-source-size archive. Quota is
   checked against actual files and each remote file's size/MD5 is verified.
   Final ZIP/report/receipts are checked separately; no raw-download-size guess
   is used as the retained-output estimate.
4. Keep `validation-pilot` for the first real run. It picks one GUNW and one
   GOFF within the selected window. Each reader's complete product row is
   compared against the pinned `gunw_stats_source.csv` or
   `goff_stats_source.csv` baseline before deletion, and every required TIFF
   must be present/readable with valid grid, CRS, band layout and source identity.
5. After the pilot passes, choose `full-source-baseline` to process every
   committed baseline product inside the selected window. A window containing
   all **15 GUNW + 18 GOFF = 33** pinned products uses the full-baseline
   downstream comparison. A narrower window is recorded as
   `time-window-selection`: it validates selected product rows and exports but
   intentionally does not claim a full-network time-series/bound equivalence
   comparison. `max-parallel: 1` keeps raw HDF5 processing sequential.
6. Each product's cleanup gate checks the baseline-validation report and remote
   receipt, requires all expected CSV/GeoTIFF outputs to appear in the verified
   Drive receipt, and checks that the archive presence matches the selected
   retention profile. Only then may the temporary raw HDF5 (and, in
   `full-lossless` mode, the temporary local archive) be deleted. The uploaded
   cleanup receipt records the policy and deletion evidence.
7. Open the `sarguardian-streaming-run-*` artifact and inspect
   `batch-equivalence-report.json`. The final Drive bundle is uploaded only
    when the applicable product-level checks (and, for the full baseline, the
   regenerated downstream results and all cleanup receipts) pass. The JSON
   report's `retention_storage_accounting` section totals actual verified
   remote file sizes by product (archive bytes are zero under `derived-only`),
   plus unique remote files and net-new bytes. The final run ZIP/report are uploaded
   afterward and are quota-checked/logged separately, so they are not folded
   into the product-retention total.

**Scope:** the selectable window filters the 33 products in the committed
source-AOI baseline. It does not yet discover additional granules outside those
committed CSVs; the live catalog discovery path has been returning upstream
ASF errors. The AOI remains the original fixed `source` polygon either way.

## Per-product sequence and retention rules

For each granule the workflow does the following:

1. Load the pinned `science-source/src/nisar_acquisition.py` and set its canonical `source` AOI. Because the baseline already supplies the exact granule name and maturity, form the documented NISAR direct HTTPS path `https://nisar.asf.earthdatacloud.nasa.gov/NISAR/{NISAR_L2_TYPE_MATURITY_V1}/{GRANULE}/{GRANULE}.h5`; probe its HTTP status and size, then download through the same authenticated `build_session()` and `asf_search.download_url()` used by the source project. This avoids the ASF catalog endpoint, which returned wrapped CMR HTTP 500/502 errors on live runs. The separate raster AOI preflight still verifies that the downloaded HDF5 grid intersects the original source polygon before science processing or Drive retention.
2. Run the AOI-grid preflight for `source`.
3. Inventory every source dataset/attribute.
4. By default, run in `derived-only`: do not create an HDF5 archive. An
   optional `full-lossless` archive is built only when that retention profile is
   selected.
5. Run the original per-product GUNW/GOFF reader, exporting each baseline
   GeoTIFF and its statistics CSV. Verify the single-reader row against the
   pinned source-ZIP row **before deletion**, then validate export readability,
   grid/CRS/bands, dimensions and valid-pixel consistency. If `full-lossless`
   was selected, also compare raw and archived reads with the science engine.
6. Upload outputs, source inventory/attributes, source SHA-256, AOI preflight,
   validation report and download manifest into the granule-specific Drive
   folder. `full-lossless` adds the archive, archive manifest and reader
   equivalence report. Remote byte-size/MD5 checks and manifest-specific file
   checks must pass.
7. Delete runner-local raw HDF5 only after every required derived output is
   uploaded and verified. Delete the temporary archive as well if one was made.
   Store and verify the cleanup receipt. In `derived-only`, arbitrary future
   raw-dataset queries such as a new product-native LOS geometry analysis are
   not preserved unless a compact equivalent was explicitly exported.

A failed upload or failed verification never reaches the explicit `rm` step.
GitHub-hosted runners are disposable; if a run fails before retention succeeds,
rerun that granule from its exact ID. The manifest is deterministic and the
Drive uploader refuses to overwrite a same-name file with different content.

## What is regenerated in full-source-baseline

- `gunw_stats_source.csv` and `goff_stats_source.csv`: merged in the committed
  baseline row order and compared against every expected row/value.
- AOI-clipped `export_src` and `export_goff_src` GeoTIFFs, collected from each
  product artifact.
- GOFF and GUNW summary time series built from the per-pair AOI GeoTIFFs. The finite-pixel median is recomputed at full raster precision and every PR/UR granule is kept as a graph edge, matching the pinned `--dir` path; the rounded statistics CSV and its PR/UR deduplication helper are deliberately not used for this baseline replay.
- Pre-event inverse-velocity check with the explicit 2026-08-26 event cutoff.
- Both `troposphere_gunw_source.csv` and `troposphere_goff_source.csv`, using
  the committed options (GOFF filtered to `layer2`).
- Candidate GOFF and GUNW local floors, summer common-reference table, and
  `bound_source.csv`.
- Candidate-4 local floors (`local_floor_cand4.csv` and
  `local_floor_cand4_as_floors.csv`) plus its common-datum inverse-velocity gate.
- `ts_goff_cand4_common.csv`: this point-level common-datum time series is
  reassembled from the fixed-lattice GOFF GeoTIFF exports, with the same
  `common_mask`, target buffer, `rereference`, window median and time-series
  inversion functions as the pinned science engine. The raw stack is not
  re-downloaded or kept on the aggregation runner.

The report records each table comparison. Float comparisons use a small
explicit tolerance for the float32 AOI-raster representation and rounded CSV
outputs; file identity, row identity, required fields, export sets and
missing/extra rows are checked too. The supplied source ZIP has no
`ts_gunw_source.csv` baseline, so that table is labeled generated/unbaselined
rather than claimed as a parity PASS. GeoTIFFs are not in the ZIP; the workflow
validates raster structure and product statistics, but cannot claim historical
pixel-for-pixel parity against absent TIFF files.
The output bundle is not marked PASS if any required table differs or any
product artifact is missing.

Independent experiments such as detectability/revisit sweeps, terrain/dam
rankings or map-only products that do not form this documented raw
GUNW/GOFF → bound chain are not claimed to have been recalculated by this
workflow; their committed versions remain in the pinned source repository.
If a later project result depends on another raw HDF5 dataset, use the Drive
full-lossless archive and add an equivalence-gated stage before enabling its
source deletion.

## Drive layout

Single-granule assets are isolated per workflow run:

`SARGuardian-DataArchive/{GUNW|GOFF}/{BETA|PROVISIONAL}/NISAR_L2_.../Runs/<run-id>-<attempt>/`

Aggregate run-level output remains separate:

`SARGuardian-DataArchive/Runs/SARGuardian-<run-id>-<attempt>/`

Each folder contains checksummed receipts. Identical content is reused within
the same run folder; a later run gets a new folder rather than overwriting a
previous archive with the same filename. Filename/content conflicts and
insufficient Drive quota still fail closed. This intentionally retains older
archives; do not delete them merely to make space. Raw .h5 source files are
excluded from uploads; only explicitly named `*.science.h5` retained archives
are accepted by the upload helper.

## Required Actions secrets

The workflow needs the same secrets as the existing retention pilot:

- `EARTHDATA_USERNAME`
- `EARTHDATA_PASSWORD`
- `GOOGLE_DRIVE_OAUTH_CLIENT_JSON`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_PARENT_FOLDER_ID`

No credentials should be put into committed files or workflow inputs.


## Resuming a failed full-baseline run

To continue a run after a transient network/authentication failure, select the branch that contains the retry/resume changes and run the SARGuardian Streaming Batch (source AOI) workflow from Actions. Choose full-source-baseline, keep the same date range and retention mode, and enter the failed run's numeric ID in resume_from_run_id.

The workflow downloads the prior manifest, product artifacts and cleanup receipts. It rejects reuse if the AOI, pinned science commit, dates, retention mode or ordered product identities differ. A checkpoint is reusable only when the derived-output baseline validation and remote-retention receipt pass, required local export/provenance files are present, and the cleanup receipt has been remotely verified. Every incomplete/ambiguous product is processed again.

The aggregation job combines the prior checkpoint artifacts with results from the new attempt. A failed retry's diagnostics-only artifact cannot replace a previously verified product checkpoint. Use this for transient infrastructure failures, not to bypass a scientific parity failure. The final run must still reproduce all required baseline rows, downstream tables and receipt/accounting gates. The retry/resume implementation needs one live resumed run before being treated as operationally proven.
