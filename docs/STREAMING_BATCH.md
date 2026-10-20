# SARGuardian streaming batch run

This workflow processes the exact Nepal source-AOI manifest committed in
moshiour0/SARGuardian at science commit
ab547ecc82bcc4d6ccef545a59852536c2beacc6. It does not substitute the
Langtang or Lhende polygons.

## Run it safely

1. Open **Actions → SARGuardian Streaming Batch (source AOI) → Run workflow**.
2. Keep `validation-pilot` for the first real run. It downloads one GUNW and
   one GOFF from the committed baseline, verifies each against its full-lossless
   retained HDF5 copy, uploads both retained products and their small derived
   outputs to Drive, and compares the single-reader CSV rows against the
   committed batch rows.
3. Only after the pilot reports `BATCH_EQUIVALENCE_STATUS=PASS`, run
   `full-source-baseline`. The pinned `outputs/*_stats_source.csv` files define
   **15 GUNW + 18 GOFF = 33 product jobs**. `max-parallel: 1` makes the jobs
   sequential, so only one source HDF5 is processed on a runner at a time.
4. Open the `sarguardian-streaming-run-*` artifact and inspect
   `batch-equivalence-report.json`. The final Drive bundle is uploaded only
   when the product-level CSVs and regenerated downstream results pass their
   comparison gates.

## Per-product sequence and retention rules

For each granule the workflow does the following:

1. Load the pinned `science-source/src/nisar_acquisition.py` and set its canonical `source` AOI. Because the baseline already supplies the exact granule name and maturity, form the documented NISAR direct HTTPS path `https://nisar.asf.earthdatacloud.nasa.gov/NISAR/{NISAR_L2_TYPE_MATURITY_V1}/{GRANULE}/{GRANULE}.h5`; probe its HTTP status and size, then download through the same authenticated `build_session()` and `asf_search.download_url()` used by the source project. This avoids the ASF catalog endpoint, which returned wrapped CMR HTTP 500/502 errors on live runs. The separate raster AOI preflight still verifies that the downloaded HDF5 grid intersects the original source polygon before science processing or Drive retention.
2. Run the AOI-grid preflight for `source`.
3. Inventory every source dataset/attribute.
4. Create a `full-lossless` HDF5 retained copy; do not use `engine-ready` for
   this full-baseline workflow.
5. Run the actual pinned SARGuardian reader equivalence test on raw versus
   retained HDF5. A `PASS_NO_VALID_AOI_PIXELS` means the two readers agree but
   the product supplies no valid science pixels in the AOI; it is not treated
   as a valid measurement.
6. Run one original single-product reader with the same source-AOI settings as
   the batch reader; save the per-product CSV and AOI-clipped GeoTIFF exports.
7. Upload the full-lossless archive, exports, CSV, inventory, preflight,
   reader-equivalence report, download manifest and processing metadata into
   the granule-specific Drive folder. The uploader verifies remote size and
   MD5; the full original source SHA-256 is retained in provenance.
8. Delete the runner's raw and archive copies only after verified remote upload,
   and after the small evidence artifact has been written. The original raw
   HDF5 itself is not uploaded; its full-lossless HDF5 dataset tree is preserved
   in Drive for future readers and analysis. This archive has the same source
   dataset paths/values/attributes needed by the scientific reader but is not
   promised to be byte-identical to the source container; source SHA-256 proves
   which original file was processed.

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
- Candidate GOFF and GUNW local floors, summer common-reference table, and
  `bound_source.csv`.
- `ts_goff_cand4_common.csv`: this point-level common-datum time series is
  reassembled from the fixed-lattice GOFF GeoTIFF exports, with the same
  `common_mask`, target buffer, `rereference`, window median and time-series
  inversion functions as the pinned science engine. The raw stack is not
  re-downloaded or kept on the aggregation runner.

The report records each table comparison. Float comparisons use a small
explicit tolerance for the float32 AOI-raster representation and rounded CSV
outputs; file identity, row identity, required fields, export sets and
missing/extra rows are checked too.
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

Single-granule assets:

`SARGuardian-DataArchive/{GUNW|GOFF}/{BETA|PROVISIONAL}/NISAR_L2_.../`

Run-level output:

`SARGuardian-DataArchive/Runs/SARGuardian-<run-id>-<attempt>/`

Each folder contains checksummed receipts; identical remote content is reused,
while filename/content conflicts and insufficient Drive quota fail closed.
Raw .h5 source files are excluded from uploads; only explicitly named
`*.science.h5` retained archives are accepted by the upload helper.

## Required Actions secrets

The workflow needs the same secrets as the existing retention pilot:

- `EARTHDATA_USERNAME`
- `EARTHDATA_PASSWORD`
- `GOOGLE_DRIVE_OAUTH_CLIENT_JSON`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_PARENT_FOLDER_ID`

No credentials should be put into committed files or workflow inputs.
