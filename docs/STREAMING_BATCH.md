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
3. Drive quota is checked **after each product has been processed**, using the
   exact bytes of the files we will retain and upload: the full-lossless
   `*.science.h5` archive, manifests and evidence, plus derived GeoTIFF/CSV
   outputs. The raw source HDF5 is never in the upload allowlist. The uploader
   calculates actual file sizes and the bytes genuinely new in Drive, checks
   available quota before uploading those files, then verifies each remote
   file's size and MD5. We do not block the run using a full-run storage guess
   derived from the raw-download estimates. The final ZIP/report/receipts also
   get the same actual-size check when they are created.
4. Keep `validation-pilot` for the first real run. It picks one GUNW and one
   GOFF that fall inside your selected window. Both families must have at least
   one baseline product in that window. The retained products are checked and
   uploaded to Drive, and the single-reader CSV rows are compared with the
   committed baseline.
5. After the pilot passes, choose `full-source-baseline` to process every
   committed baseline product inside the selected window. A window containing
   all **15 GUNW + 18 GOFF = 33** pinned products uses the full-baseline
   downstream comparison. A narrower window is recorded as
   `time-window-selection`: it validates selected product rows and exports but
   intentionally does not claim a full-network time-series/bound equivalence
   comparison. `max-parallel: 1` keeps raw HDF5 processing sequential.
6. After remote retention succeeds, the workflow deletes only the temporary
   runner copies of the raw HDF5 and retained local archive. It writes a
   `local-cleanup-receipt.json`, uploads and checksum-verifies that receipt in
   the same versioned Drive folder, and the final aggregation gate validates
   one cleanup receipt for every product before reporting PASS.
7. Open the `sarguardian-streaming-run-*` artifact and inspect
   `batch-equivalence-report.json`. The final Drive bundle is uploaded only
    when the applicable product-level checks (and, for the full baseline, the
   regenerated downstream results and all cleanup receipts) pass. The JSON
   report's `retention_storage_accounting` section totals actual verified
   remote file sizes by product (retained archive vs ancillary evidence), plus
   unique remote files and net-new bytes. The final run ZIP/report are uploaded
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
