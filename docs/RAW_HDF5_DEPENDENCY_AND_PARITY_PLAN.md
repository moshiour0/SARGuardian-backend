# SARGuardian raw-HDF5 dependency and parity plan

Status: implementation in progress.
Baseline authority: the user-supplied SARGuardian-main.zip, especially REPRODUCE_RESULTS.md, src/, and committed outputs/*_source.csv.
Operational repository: moshiour0/SARGuardian-backend.
Safety rule: do not delete a temporary raw HDF5 until required raw-dependent outputs and provenance are validated, uploaded, and remotely verified. Do not start the full 33-product run until the two-product pilot passes.

## 1. Dependency inventory

### Direct HDF5 readers
- src/gunw_reader.py / read_gunw(): opens GUNW HDF5 and reads unwrapped phase, matching coherence, connected components, mask, ionosphere phase screen, x/y coordinates, projection and wavelength. It performs quality/AOI/reference logic and emits statistics and clipped GeoTIFF through --read / --batch.
- src/goff_reader.py / read_goff(): opens GOFF HDF5 and reads range/azimuth offsets, correlation, SNR, variance, coordinate axes and projection. It applies quality/AOI/reference/deramp logic and emits statistics and clipped GeoTIFF.
- src/timeseries.py --dir: discovers raw .h5 and calls read_gunw/read_goff again. A merged stats CSV alone is not equivalent to this path; time-series replay must preserve per-product raster precision, product identity and the documented reference/inversion options.
- src/geometry_merge.py / los_from_product(): opens GUNW metadata/radarGrid LOS unit vectors, incidence angle, coordinates/projection and identification/lookDirection. It is a direct raw dependency for product-native LOS queries. The documented source-AOI bound chain does not call it, so derived-only retention must not claim arbitrary future LOS queries remain available unless a compact equivalent is exported or an archive is retained.

### Raster/CSV downstream stages
- src/troposphere.py consumes exported GeoTIFF and DEM; source-ZIP baselines: outputs/troposphere_gunw_source.csv and outputs/troposphere_goff_source.csv.
- src/local_floor.py consumes exported GeoTIFF plus candidate CSV; baseline outputs include local_floor_candidates.csv and local_floor_phase_candidates.csv.
- src/common_ref.py consumes GOFF GeoTIFF and candidate metadata; baseline common_ref_summer.csv.
- src/bound.py consumes previously derived source CSVs; baseline bound_source.csv.
- src/inverse_velocity.py consumes reconstructed GOFF time series and GOFF floors; event cutoff must be 2026-08-26.
- Candidate-4 common-datum time-series must be reconstructed using the fixed-lattice exports and common-reference logic, not per-pair auto-reference values.
Any newly added output that calls a raw-HDF5 helper must be added to this map before cleanup can be approved.

## 2. Baseline facts

- gunw_stats_source.csv has 15 rows / 15 unique GUNW products.
- goff_stats_source.csv has 18 rows / 18 unique GOFF products (HH/layer2; includes routine and urgent-response products).
- Product-level validation must compare the complete relevant CSV row with the matching source-ZIP baseline, including fields and row identity. Only GDAL-sensitive export_mb gets a documented relaxed tolerance.
- Available downstream baselines include ts_goff_source.csv, both troposphere CSVs, local_floor_candidates.csv, local_floor_phase_candidates.csv, common_ref_summer.csv, ts_goff_cand4_common.csv and bound_source.csv.
- The supplied ZIP has no ts_gunw_source.csv baseline. If generated, it must be labeled generated / no committed baseline, not counted as source-ZIP parity PASS.
- Historical exported GeoTIFFs are not committed in the ZIP. Validate completeness, readability, source tags, bands, CRS, affine transform, dimensions, nodata/valid pixels and common fixed-lattice invariants; do not claim pixel-for-pixel comparison against a raster that is absent.

## 3. Required order and deletion gate

1. Pin and record the exact science commit and validate its product CSV inventory before downloading any granule.
2. Download one raw product at a time; record original bytes and SHA-256, run AOI grid preflight and inventory all source datasets/attributes.
3. Run the original single-product GUNW or GOFF reader with the matching batch settings. Export every raster needed by the declared downstream chain.
4. Before deletion, compare this product's CSV row to its exact source-ZIP baseline row; verify every export is present/readable and has expected grid, CRS, bands, source identity and valid data. Write a machine-readable validation report.
5. If a declared result depends on raw-only information (including product-native LOS geometry), export a validated compact representation or retain an explicit archive for that product. Never silently drop a dependency.
6. Upload derived files, inventory, preflight, source hash, parameters and validation evidence to the product-specific Drive run folder. Verify remote sizes/checksums and ensure all required exports are represented in receipts.
7. Only after all checks pass, delete the runner's raw HDF5. For full-lossless mode, independently verify the remote archive and then delete the temporary archive. Upload and verify the post-cleanup receipt.
8. Aggregate all product artifacts in original baseline row order. Fail closed on missing/duplicate products or exports.
9. Re-run the combined downstream chain from compact outputs: GOFF/GUNW time series as required, inverse-velocity event cutoff, both troposphere reports, both candidate-floor tables, summer common-reference table, candidate-4 common-datum series and final bound.
10. Compare every available source-ZIP baseline with schema, identity, missing/extra row and numeric checks. Report PASS, FAIL, and SKIP_NO_COMMITTED_BASELINE distinctly. A full run must not pass when a required baseline comparison is missing/skipped.
11. Upload the final bundle, command logs, report, manifest, all product/cleanup receipts and actual Drive byte accounting. Separate product outputs from optional archive and run-level report storage.

## 4. Retention modes

- derived-only: do not retain .science.h5. Only the documented output chain and explicit compact sidecars are preserved; arbitrary future access to original HDF5 datasets is not preserved.
- full-lossless: retain a logically lossless HDF5 dataset-tree archive, compare raw/archive reader results, and still retain all derived outputs. The archive consumes near-raw storage and must remain an explicit option, not be confused with derived-only output.

Storage accounting must be policy-aware: derived-only cleanup must require all derived files and their remote checksums, not an archive.

## 5. Known current workflow gaps

- Streaming Batch currently always creates/uploads a full-lossless .science.h5 although aggregate replay reads derived outputs.
- Product-vs-baseline checks mostly occur later in aggregation, after the raw cleanup; this must move into the pre-deletion gate.
- Current BASELINE_DOWNSTREAM omits both troposphere CSVs and downstream replay does not invoke troposphere.py.
- ts_gunw_source.csv is generated without a committed baseline in the supplied ZIP; its status must stay explicit.
- The workflow's scientific commit must match the declared baseline; stale commit guards must fail before processing.
- Earlier run #15 failed on a stale science-commit guard. Run #19 GUNW succeeded but GOFF Drive upload got HTTP 502. Neither proves full baseline parity.

## 6. Acceptance gates before processing all 33 products

- Representative GUNW and GOFF product-level validations pass against source-ZIP baselines before cleanup.
- derived-only passes without a .science.h5 in the upload receipt and refuses cleanup for missing/wrong validation, exports or remote checksums.
- full-lossless remains independently supported with the raw/archive equivalence test.
- Aggregation handles archive-present/absent policies and measures Drive storage from verified receipts.
- Both troposphere outputs are regenerated and compared; every available required baseline is compared.
- Full-source run covers all 15 GUNW + 18 GOFF products, all required comparisons pass, and all 33 product/cleanup receipts verify before the final report can say PASS.

## 7. Change log

- [x] Re-open supplied source ZIP and map direct raw-HDF5 readers.
- [x] Confirm 15 GUNW + 18 GOFF baseline entries and inspect downstream outputs.
- [x] Re-read current streaming workflow and aggregate code.
- [x] Add this plan to the backend branch.
- [x] Add pre-cleanup per-product CSV/raster validation.
- [x] Add derived-only and full-lossless retention modes with policy-aware cleanup.
- [x] Update storage accounting and downstream parity, including both troposphere CSVs and candidate-4 floors.
- [x] CI/static validation on draft PR #28: 129 passed, 2 skipped in the backend suite; 42 passed in the retention suite; workflow YAML and Python syntax checks passed.
- [ ] Run the two-product live validation pilot with `derived-only` retention; verify Drive receipts and cleanup gates before any full run.
- [ ] Run all 33 only after the live pilot passes and every required source-ZIP downstream parity gate passes.
