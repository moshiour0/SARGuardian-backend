# Know Place Analysis — Engineering & Scientific Checklist

**Rule:** items are not marked complete without inspectable evidence. This file is on `feat/know-place-analysis`; no item authorizes a merge to `main`.

## Milestone 0 — Freeze and inspect baseline

- [x] Create isolated branch `feat/know-place-analysis` from the existing science-integration branch.
- [x] Freeze the last Dynamic AOI run ID, workflow commit, orchestration commit, scientific engine commit, WKT and artifact IDs.
- [x] Download and inspect manifest, processing report, summary, per-product records and pixel-stack diagnostics.
- [x] Confirm actual input start date (2026-06-17) differs from the intended paper window (2026-06-20) and document impact.
- [x] Confirm selected inventory mixes target ASC T098 pairs with descending D048 and extra pairs; isolate only the five paper-matched GOFF granules.
- [x] Record current GOFF-015 outputs and make clear they are not paper-equivalent crown magnitude.
- [x] Record zero complete GUNW series pixels and the custom-AOI candidate-check skip.
- [x] Record that raw HDF5 was removed after derived-only retention; reprocessing needs verified re-download.
- [x] Save the baseline run URL, artifact IDs, downloaded-archive SHA-256 values and findings under `docs/know-place/evidence/BASELINE_RUN_39942529304.md`.

## Milestone 1 — Lock method and provenance contract

- [x] Write blueprint with geometry roles, five exact pair dates, equations, filtering, background correction and known limitations.
- [x] Write this evidence-based checklist.
- [x] Receive and SHA-256 record the paper PDF, Supplementary Information, 101-zone CSV, and separate Zenodo code/output archive; archive byte integrity and manifest payload checks are recorded in `docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md`. The Zenodo ZIP itself does not contain the raw GOFF HDF5 payloads; the subsequent exact-author download and source-byte hashes are tracked separately below.
- [x] Resolve the five exact author P05023 IDs through NASA CMR, then download/hash/validate the exact HDF5 payloads in [run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362). Catalog identities 5/5; payloads downloaded 5/5; SHA-256 pins 5/5; grid validations 5/5. Evidence: `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`. X05026 is not a substitute.
- [x] Validate the five exact HDF5 identities and common source grid (4311 × 4230, EPSG:32645, 80 m posting) during run 40114703362. [ ] Finish parity checks for geometry-axis interpretation, units/sign conventions, exact crown mask and author golden outputs.
- [x] Define a versioned input/output JSON schema and separate structural / method-reproduction / interpretation statuses.
- [x] Define separate WKT masks for the reference box, crown and box-minus-crown; the supplied paper fixes the crown bounds at 85.5245–85.5400° E and 28.2847–28.2970° N (2.07 km²), and the reference box bounds. [ ] Verify pixelwise crown-mask parity on the original GOFF source grid. **Count-estimand correction (2026-10-24):** exported displacement-valid counts `[283, 294, 296, 292, 195]` match `tables/nisar_pot_series.json` key `n`; separately recomputed R-valid crown counts `[302, 299, 302, 298, 202]` match `tables/polygon_null.json` key `n_px`. The earlier 296-versus-298 comparison mixed estimands. Aggregate count parity does not prove pixelwise source-grid mask parity.
- [x] Define and record deterministic exploratory control parameters (seed, draw count, PRNG, reject/accept accounting and quantile convention). The archived post-hoc polygon-null algorithm was independently replayed from all five processed TIFFs using the archived crown-slice and sampling policy; 45/45 table metrics matched at stored precision. See `docs/know-place/evidence/AUTHOR_ARCHIVE_POLYGON_NULL_REPLAY_20261025.md`. This is exported-field/output parity only, not full paper-method or raw-source-grid parity.

## Milestone 2 — Implement pure scientific kernels (no downloads in unit tests)

- [x] Unit-test horizontal dE/dN projection against hand-computed vectors including sign checks.
- [x] Unit-test quality gate order, SNR ≥ 5, magnitude ≤ 10 m, reject-not-clip behavior, and per-gate rejection counts.
- [x] Unit-test component-wise background median correction on synthetic arrays with known bias.
- [x] Unit-test crown median magnitude, mean-vector magnitude/azimuth, and day-normalized descriptive rate as distinct statistics.
- [x] Test 5×5 mean resultant length using uniform/opposed vectors and expose 1/5/10/15/20/25-neighbour sensitivity in the report.
- [x] Add explicit corner/edge and missing-centre-vector regression cases as current-kernel policy tests; these do not claim author-method parity.
- [x] Add independently labelled validation/test registry schemas, validation-only threshold selection, content-addressed frozen policies, and test-only scoring that rejects mixed-split registries.
- [x] Add deterministic event-level precision/recall/specificity/F1, coverage/NO_RESULT accounting, AOI-month false-alarm rates, lead/delay summaries and site-cluster bootstrap with a minimum-site gate; synthetic known-answer tests only. The evaluator also rejects cross-split site/exact-geometry leakage, contradictory/out-of-window alarms, model-policy hash drift, and per-case source-product SHA-256 mismatches; schemas v1.1 are documented in the multi-event plan. This checks declared cross-file provenance, not trusted execution attestation.
- [x] Add exact acquisition-midpoint interval-average rates and gate rate-change features on contiguous pairs, same processing chain, grid compatibility, valid measurements and mission-data gaps.
- [x] Export the descriptive features to `motion-features.csv`; dashboard/result/manifest state the status and keep risk score null.
- [x] Unit-test deterministic size-matched control sampling, accepted/rejected draw accounting and empirical percentile.
- [x] Unit-test missing/finite/nodata behavior and explicit failure when background/crown support is empty; test HDF5 attribute and creation-property fill handling without mistaking a default zero for nodata.
- [x] Unit-test missing or duplicate products, wrong track/direction, invalid geometry, unit/CRS mismatches and ambiguous metadata fail closed.

## Milestone 3 — Strict raw GOFF HDF5 reader

- [x] Read exact layer2 AT, SR, SNR, correlation, coordinate vectors, CRS/projection and per-product radar geometry from all five candidate raw HDF5 inputs.
- [x] Implement geometry metadata interpolation with explicit cube selection, axis/unit/CRS checks and no extrapolation; synthetic schema tests pass. Actual five-product metadata verification remains pending.
- [x] Confirm the paper's distinction: site series uses one crown-local radar geometry throughout; footprint screen interpolates geometry at per-pixel Copernicus GLO-90 elevation. [x] Inspect archived author code: site-series geometry is the median of each geometry component along height at the radarGrid sample nearest the crown. [ ] Implement and test this author-specific estimator; current per-pixel fixed-height site-series sampling is not equivalent.
- [x] Refuse ambiguous geometry groups, missing fields, non-finite geometry, unit mismatches and out-of-domain interpolation. Confirm actual product sign convention from the five raw files before scientific use.
- [x] Validate all five candidate products against the common EPSG:32645 80 m native grid; the strict reader fails closed on grid mismatches.
- [x] Implement source SHA-256 and record granule name, catalog maturity evidence, CRID, exact pair dates, track, direction, polarization and layer in the report.

## Milestone 4 — Paper-method analysis

- [x] Produce per-pair raw quality-gate counts, crown/background support counts and source SHA-256 evidence.
- [x] Produce corrected dE/dN/magnitude outputs and hash-recorded NPZ diagnostic arrays on the source grid.
- [x] Produce 5×5 R from unit vectors, with valid-centre counts, an explicit minimum-neighbour policy and sensitivity outputs.
- [x] Calculate crown and box/background R and crown displacement/vector metrics with distinct, provenance-labelled masks.
- [x] Create an explicitly labelled exploratory deterministic circular-control distribution for magnitude and R; accepted/rejected draws and percentiles are recorded. - [ ] Verify author-exact spatial-control sampling before comparing published percentiles.
- [x] Screen 19–31 Aug separately: crown R is lower than its surrounding box and the report does not treat its displacement magnitude as an alarm.
- [x] Process all five required intervals separately, without pooling ascending/descending tracks or selecting only a target-positive interval.
## Milestone 4B — Footprint-wide candidate screen (separate method path)

- [x] Extract the archived wide_screen.py array equations into tools/know_place/footprint_screen.py, with attribution and source SHA-256 records: per-pixel AT/SR projection coefficients, SNR >= 5 and magnitude <= 10 m gates, 41-pixel local anomaly, 5x5 residual R, z >= 4, anomaly >= 0.50 m, R >= 0.75, at least 2 of the 5 prescribed intervals, and four-connected components >= 10 cells.
- [x] Add synthetic known-answer parity tests for the archived screen formulas, mask/interval rejection, persistence and connected-component behavior. Wire the module and test file into the explicit CI lists. Geometry→screen integration is also explicitly tested. Latest CI: 176 tests passed in [run 40050020868](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40050020868).
- [x] Add an array-only author geometry-coefficient builder in `tools/know_place/footprint_geometry.py` with synthetic interpolation, Y-axis normalization, median-fill/clipping, extrapolation-count, nonfinite coefficient, CRS/affine and geometry→projection→screen integration tests.
- [x] Require explicit target/geometry/DEM horizontal EPSGs, matching target/DEM affine transforms, and declared DEM/geometry vertical-reference strings. A declared mismatch fails by default; only an explicit source-reproduction override can pass the source's direct-use behavior through, with `vertical_transformation_applied=false` in the result.
- [x] Download and SHA-256-pin the 16 current public Copernicus GLO-90 tiles for the source terrain bbox, validate raster profiles, and replay the archived `terrain/elev_m.tif` mosaic/warp. The archived grid matches 18,235,529/18,235,530 Float32 cells exactly and the entire finite mask matches. This verifies current public tile raster-value parity, not original author tile-byte identity. See `docs/know-place/evidence/COPERNICUS_GLO90_SOURCE_TILE_REPLAY_20261024.md`.
- [x] Run a separate vertical-datum sensitivity using the public PROJ/NGA EGM2008 2.5-arc-minute grid and formal EPSG:9518 → EPSG:4979 conversion. Median ellipsoidal-minus-EGM2008 offset is −30.1587 m across the target grid and −31.7705 m in the 323-cell crown mask. No correction was applied to the author-reproduction path. See `docs/know-place/evidence/EGM2008_VERTICAL_DATUM_SENSITIVITY_20261024.md`.
- [ ] Obtain the author's original 16 terrain input files or verified source receipts to prove byte-level source identity; current public mirror copies are not proven identical.
- [x] Acquire and SHA-256 pin the five exact author-published P05023 GOFF HDF5 payloads, validate HDF5 identities and the common 4311 × 4230 EPSG:32645 80 m grid, and verify source bytes in [run 40128950105](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40128950105). The five raw files were deleted only after derived-only Google Drive retention and post-delete receipt verification. [ ] Re-run the source-acquisition step after explicit consent when the newly integrated full-footprint runner is to be exercised; do not substitute X05026. Full-grid coefficient/output parity remains pending until that runner produces direct comparison evidence.
- [ ] Resolve remaining source/datum provenance uncertainty with independent author input evidence; the current public GLO-90 replay and formal height transformation quantify the issue but do not prove what exact source tile bytes the author used or make the existing paper replay equivalent.
- [ ] Run exact author-pinned raw GOFF inputs on the documented 4230 x 4311 grid, regenerate five per-pair footprint maps and candidate vector outputs, and compare with archived screening rasters. Raw GOFF bytes/full per-pair rasters remain absent; catalog identity is not source-byte identity.
- [ ] Recreate the separate post-hoc downslope attribution/control test from candidate_attributes.py. This must not be folded into the screen or relabel a movement candidate as an event detection.
- [x] Keep HAZARD_DETECTION_STATUS=NOT_EVALUATED. The screen detects candidate moving surfaces, not impending failure; see docs/know-place/evidence/AUTHOR_FOOTPRINT_SCREEN_KERNEL_AUDIT_20261024.md.
- [ ] Keep core diagnostic separate and state its selection bias if implemented.

## Milestone 5 — Golden comparison and interpretation

- [x] Compare the 26 Jul–19 Aug crown median (0.966 m), mean-vector magnitude (1.722 m) and azimuth (277.79°) to rounded paper targets; residual geometry/mask/input-variant differences are documented.
- [x] Compare R on the common 0.17–2.75 m pointwise window (0.869 at 150 crown centres) to the published ~0.869 at 147 centres; document background R/count mismatch and non-equivalent controls.
- [x] Retrieve and inspect archived site-series and polygon-null code and compare all five published TableS4 values to the benchmark fixture. [x] Recompute the archive's five post-hoc polygon-null distributions from the processed fields using the archived algorithm (shared RNG seed 20260907, unique candidate centres, disk edge/support rejection, strict quantile inequalities, 60% acceptance rule): 45/45 stored metrics match. See `docs/know-place/evidence/AUTHOR_ARCHIVE_POLYGON_NULL_REPLAY_20261025.md`. This does not establish a published-paper metric or original source-grid parity.
- [x] Recompute same-estimand statistics from all five exported author field GeoTIFFs and compare `nisar_pot_series.json`, `polygon_null.json` and Table S4: 120/120 comparison checks passed at archived table precision. Results and source-table hashes: `docs/know-place/evidence/AUTHOR_PROCESSED_FIELD_TABLE_PARITY_20261024.md`. This is exported-field/table parity only; exact source-grid mask and raw-GOFF parity remain blocked.
- [x] Record the paper’s interpretation and explicitly avoid describing this analysis as an early-warning detector.
- [x] Keep full author-method reproduction blocked/partial rather than overclaiming: exact raw P05023 bytes and native grid were verified in runs 40114703362/40128950105; the derived 6-km dE/dN/R fields match 15/15 channels and the selected site/polygon metric checks pass. The exact full-footprint pipeline is now integrated but has not yet run on the verified inputs, and displacement-null parity is still blocked because the supplied archive lacks the draw-level generator/distribution. See `docs/know-place/evidence/AUTHOR_EXACT_RUN_40128950105_AUDIT_20261025.md` and `docs/know-place/evidence/TABLE_S4_COVERAGE_REGISTER_20261025.md`.
- [ ] Complete independent scientific review before claiming reproduction; code-level method parity, exact raw-source hashes, full-footprint raster regeneration and pixelwise mask/output parity remain unverified.
- [x] Keep geometry policy explicit: crown-local constant geometry for the site series; per-pixel Copernicus GLO-90 geometry for the footprint screen. The exact datum/query behind the current 5151.0 m value remains unverified; do not tune it to scalar paper targets.
- [x] Add blind split enforcement so threshold calibration only accepts validation-only labels and held-out scoring requires a separate test-only registry plus a hash-matched validation registry.

## Milestone 6 — Operational isolation and review

- [x] Keep the legacy expensive replay workflow gated; add a separate exact-author P05023 workflow with manual-dispatch-only raw access and an exact `[run-know-place]` input, so ordinary pushes never launch the raw download.
- [x] Verify compact CSV/JSON, NPZ diagnostics, source/array hashes, quality-gate accounting, scientific caveats and separate reanalysis artifacts; the latest reanalysis report and summary were remotely verified in Drive.
- [x] Run automated scientific tests, YAML parsing and `actionlint` with author-data integrity and offline ASF-gate tests included: **122 tests passed** in [validation run 40035193088](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40035193088). The historical-candidate gate passed; the separate author-exact gate recorded 4/5 exact P05023 IDs confirmed and the first ID NOT_FOUND, with zero raw downloads. A blocked science input is recorded in the artifact rather than misreported as a passing source match.
- [x] Historical isolated validation after adding the footprint-screen module and explicitly adding its test file to the CI lists: [run 40049074686](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40049074686), commit `5740407c3a477b24453c7c9728aef380869ca3f3`: **164 tests passed**, four workflow YAML files parsed, actionlint v1.7.12 checksum verified and semantic workflow validation passed. The ASF job downloaded zero source products and still records first author P05023 NOT_FOUND. [Raw replay run 40049074681](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40049074681) skipped five-pair analysis because `[run-know-place]` was absent.
- [x] Historical branch validation after event/provenance hardening: [run 40047359607](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40047359607), commit `a0c41e721a9158d47d6ebb1505451d109ab33a23`: **150 tests passed**, four workflow YAML files parsed, actionlint v1.7.12 checksum and semantic validation passed. ASF source downloads were zero; first author P05023 remains NOT_FOUND. [Raw replay run 40047359560](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40047359560) skipped five-pair analysis due to missing `[run-know-place]`.
- [x] Historical validation: [run 40056005969](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005969), commit `80016cfb591a6e6d7715bb36440c949cb1ca5654`: 191 tests passed; six workflow YAMLs and actionlint passed; first P05023 identity was confirmed by CMR. No payload was downloaded. [Raw replay run 40056005985](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005985) skipped because `[run-know-place]` was absent.
- [x] Keep every Know Place Analysis commit on `feat/know-place-analysis`; no `main` changes or merge were made.
- [ ] Do not merge to `main`. Any later integration requires explicit review and approval.

## Current gate status (updated 2026-10-24)

- **Milestone 0:** complete. Baseline run, source/dashboard artifacts, array/report checksums and findings are saved under `docs/know-place/evidence/`.
- **Milestone 1:** blueprint, method contract and provenance implemented. The Zenodo archive itself lacks raw GOFF payloads, but the later author-exact replay downloaded and SHA-256-pinned five exact P05023 HDF5 products. Author-method parity remains unverified because exact crown geometry/control sampling and full-footprint golden outputs are not confirmed. See `docs/know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md`, `docs/know-place/evidence/CMR_AUTHOR_P05023_EXACT_CATALOG_RESOLUTION_20261024.md` and `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- **Milestone 2:** scientific kernels, strict synthetic HDF5/geometry/integration tests, blind-split evaluator and threshold-selector tests, motion dynamics, author benchmark integrity, offline author-catalog handling and CSV bundle contract passed **122 tests** in [validation run 40035193088](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40035193088). The same run's YAML and actionlint checks passed. Live catalog identity is reported separately from code/test status; the author-exact source gate remains BLOCKED. Edge/missing-centre tests are current-kernel policy tests only, not author-method parity.
- **Milestone 3:** five raw candidate GOFF HDF5 products were fetched one at a time during [raw replay Run 40006999011](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40006999011); all five historical file-size/SHA-256 identity checks passed, and all five metric records were produced. The later saved-array reanalysis also verified the five NPZ hashes against the source report before computing any new R values.
- **Milestone 4:** per-pair gates, corrected dE/dN/magnitude metrics, 5x5 R and spatial-control diagnostics have been computed. The original run used a too-strict 25/25 neighbour rule; the separate [saved-array R sensitivity reanalysis, Run 40015023621](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015023621), computes the 1/5/10/15/20/25 sensitivity and does not modify the original run report.
- **Milestone 5 (updated after exact-source replay):** the target pair's initial exploratory result remains only numerical similarity, not reproduction. A later author-compatible run checked five exact P05023 products; its exported 6-km dE/dN/coherence rasters matched all 15 channels at ≤1e-6 absolute error. The P1/polygon workflow has 65 selected checks, but those are not all 95 Table S4 cells. The halo-aware P2 path has been added and synthetic-tested, but its 15 P2 comparisons still require a new raw replay. The 15 core-scale values match conditionally using the author's already-supplied screen-selected candidate geometry; this is not independent full-screen recovery. Displacement-null parity and source-grid pixelwise crown-mask parity remain unresolved. No detection claim.
- **Milestone 6:** isolated raw and saved-array workflows are branch-only; saved-array result/summary retention has passed remote Drive verification. The AOI result bundle includes `timeseries.csv`, `motion-features.csv`, native-grid GeoTIFF placeholders in synthetic tests / real geotiffs in actual measurement runs, NPZ diagnostics, result, dashboard, and checksummed manifest; ephemeral-source manifests now state whether raw HDF5 was deleted or retained. All new commits remain on `feat/know-place-analysis`; no merge or edit to `main` was performed.
- **Paper reproduction:** `PARTIAL_AUTHOR_SITE_SERIES_METRICS_MATCH_FULL_FOOTPRINT_SCREEN_NOT_REPRODUCED`. Five exact P05023 raw payloads and hashes were verified and retained-derived-only/cleanup receipts passed; selected site-series and post-hoc controls match the processed archive. The P2 metrics still need a new raw replay, the three displacement-null columns are blocked by missing draw-level source evidence, and the full-footprint runner's numeric comparison has not yet been executed. Hazard detection remains `NOT_EVALUATED`.
- **Hazard detection:** `NOT_EVALUATED`. Do not report an operational landslide alarm from these results.


- [x] Add isolated archived-author kernels and synthetic regression cases in `tools/know_place/author_parity.py` and `tools/tests/test_know_place_author_parity.py`. These are not yet wired into the exploratory runner; end-to-end golden comparison remains pending.


## Latest exact-author acquisition workflow status — 2026-10-24

- [x] Add the exact-author acquisition runner and direct CMR HDF5 URL resolver. The resolver requires exact P05023 producer identity, the pinned CMR collection, trusted ASF/earthdatacloud hosts, the exact expected HDF5 path/name and exactly one data link per product.
- [x] Preserve failure manifests in the derived output area, bind config provenance to the source-manifest SHA-256, fail closed unless the analysis exit code is zero and all five scientific metrics are complete, and validate all five raw grids against the expected 4311 x 4230 EPSG:32645 / 80 m grid with identical coordinate axes.
- [x] Add offline acquisition-contract tests and wire them explicitly into the validation workflow. Latest validation [run 40058988024](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988024), branch head 2fddad5fbd3d66fc9ade40da41ce829bfabf7610: **204 passed in 4.87 s**, seven workflow YAML parses, actionlint v1.7.12 checksum and semantic validation passed.
- [x] Live CMR/data-link check: AUTHOR_CMR_CATALOG_GATE=PASS; AUTHOR_EXACT_PRODUCTS_CONFIRMED=5/5; AUTHOR_EXACT_CMR_DATA_URLS_CONFIRMED=5. Source payload downloads=0 and raw source SHA-256 pins=0. Evidence artifact [know-place-author-exact-live-cmr-access-evidence](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988024) (artifact digest SHA-256 b81e1d2b1ba4c78a90753ed84fd1ff1da0ff72c886bf46f31ffdd99928a1c4e9).
- [x] Register the exact-author raw workflow as manual-dispatch-only with an exact `[run-know-place]` consent input and credential preflight. Push registration run [40058988016](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988016) did not run the raw job; legacy run [40058988057](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988057) also skipped analysis.
- [x] Exact-author dispatch and data replay completed in [run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362) using the exact consent input. Five payloads were hashed/grid-validated, the analyzer ran, and Drive receipts passed remote verification.
- **Status contract:** source byte identity PASS (5/5); paper reproduction remains `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; hazard detection remains `NOT_EVALUATED`; no merge/change to main.

- [x] Latest full code/test validation before this evidence-pointer refresh: [run 40092715120](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40092715120), commit `e0268bf891329cae4698da0bef8611606da69a4e`: **204 tests passed in 4.55 s**, seven workflow YAML files parsed, actionlint v1.7.12 checksum and semantic checks passed. The live CMR artifact ZIP (ID `12559850649`) was independently downloaded and integrity/hash checked (SHA-256 `e2d62d5b955e76083c90b64ace06f7e69109da628f7a5f37f62f15d37519377f`); exact P05023 IDs/URLs are 5/5, payload downloads 0/5.

## Milestone 7 — Run Workflow launcher and independent multi-site protocol (2026-10-24)

- [x] Add a feature-branch copy of `.github/workflows/sarguardian-aoi-wkt-dispatcher.yml` so the existing default-branch Run Workflow entry point can be opened on branch `feat/know-place-analysis` without changing `main`.
- [x] Add two explicit profiles: `author-exact-p05023` (five exact author products) and `generic-aoi-date` (arbitrary WKT + inclusive date window).
- [x] Make both child workflows reusable and pass all request inputs through typed `workflow_call` contracts.
- [x] Require the exact `[run-know-place]` consent input at the dispatcher before either raw-download path; repeat the guard in each child workflow. Generic catalog-only dry runs default to no raw downloads.
- [x] Preflight Earthdata and Drive secrets before download. Preserve derived bundle and receipts in Drive, verify remote receipts before deleting raw temporary HDF5.
- [x] Expose analysis mode metadata, optional constant HAE sensitivity input and 5x5 coherence-neighbour sensitivity in the generic AOI workflow. These are request parameters, not proof of independent validation or operational readiness.
- [x] Register a six-site benchmark inventory in `docs/know-place/reference/multi_site_benchmark_v1.json`: Bhote Koshi author-method target; four IIRS/ITS_LIVE glacier-flow measurement controls; and Budhi Gandaki as a separate GUNW no-precursor challenge. Exact AOIs, data IDs and source-byte hashes for the independent sites remain pending.
- [x] Document the run instructions, source/measurement/hazard status separation, per-pixel DEM/vertical-datum requirements, blind test protocol and site-specific limitations in `docs/know-place/REPRODUCIBLE_ENGINE_AND_MULTI_SITE_VALIDATION_20261024.md`.
- [x] Add offline multi-site registry integrity tests. They assert that pending site inputs cannot be marked as scored detections, the five Bhote Koshi P05023 intervals match the author fixture, and GUNW is not scored as GOFF.
- [x] Isolated validation passed on commit `b1768ba0ab6d8b19e0803e88a19f9d494339b867`: [run 40102852943](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40102852943) reported **213 tests passed in 5.10 s**, all eight workflow YAML files parsed, and the pinned actionlint v1.7.12 checksum plus semantic workflow validation passed. This confirms the consent-gated launcher, reusable workflow contracts and multi-site registry tests; raw source downloads remained zero.
- [x] Used Actions → `SARGuardian AOI WKT E2E (safe branch dispatcher)` on `feat/know-place-analysis` → profile `author-exact-p05023`, with exact consent `[run-know-place]`; [run 40114703362] completed raw acquisition and analysis.
- [x] Reviewed all five byte counts/SHA-256 hashes, HDF5 identity/grid checks, pair metrics, output bundle and both remote Drive receipts. See `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- [ ] Verify exact author crown geometry/control sampling and full-footprint mask/golden-output parity.
- [ ] Only after the Bhote Koshi run, freeze AOI/source identities for Samudra Tapu and Bara Shigri; then validate Hubbard/Malaspina and the distinct Budhi Gandaki GUNW case. Do not tune using the final holdout.
- [ ] Do not claim paper parity, movement-detector validation or hazard detection until each distinct gate has its own evidence.

**Status rule:** Exact author raw byte identity is verified (5/5 P05023 payloads, hashes and grid checks) in run 40114703362. Metrics remain exploratory; `PAPER_REPRODUCTION_STATUS=BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; `HAZARD_DETECTION_STATUS=NOT_EVALUATED`. This feature branch remains isolated; no merge/change to `main`.


## Latest follow-up status — 2026-10-24

- [x] Downloaded and ZIP-integrity-checked the live CMR catalog artifact from validation run [40102959304](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40102959304). SHA-256: `65e65ae2c4dec384c50ca5a8877e69b705a1861c1e85312026d62512c5dd9386`, matching the GitHub artifact digest.
- [x] Independently inspected the manifest: exact author P05023 CMR identities 5/5 and direct HDF5 URLs 5/5; source payload downloads remain 0/5 and source SHA-256 hashes 0/5.
- [ ] Execute the branch Run Workflow dispatcher with profile `author-exact-p05023`, explicit consent `[run-know-place]`, and configured Earthdata + Google Drive secrets. The available GitHub connection does not expose a workflow-dispatch action, so this step has not been launched from the assistant session.
- [ ] Review raw HDF5 hashes/grid validation, scientific output metrics, and verified Drive-retention receipts after the run. Do not mark paper reproduction or hazard detection complete merely because acquisition succeeds.


## Follow-up — dispatcher consent mismatch (2026-10-24)

- [x] Audited failed dispatcher run [40107037642](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40107037642). Actual input was run-know-place, but raw-source consent requires exact [run-know-place] including both square brackets. The consent job failed before any raw download, processing, or Drive upload; the measurement and exact-author analysis jobs were skipped.
- [x] Improved the gate error and GitHub step summary to state the exact required value; added an automated regression test that rejects the unbracketed near-match.
- [ ] Re-dispatch the branch workflow with profile author-exact-p05023, exact consent input [run-know-place], and valid Earthdata + Drive secrets. Do not start raw acquisition until the exact input is supplied.
- [ ] After an authorized run, verify five source HDF5 byte counts/SHA-256 hashes, grid/identity checks, scientific outputs and both Drive-retention receipts. Do not mark paper reproduction or hazard detection complete merely because acquisition works.


- [x] Audit the latest author-exact live run [40107851266](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40107851266): authenticated download reached the full first HDF5 size of 1,090,519,040 bytes, then was falsely rejected because the validator compared a parser filename with `.h5` against CMR's extension-free granule ID. Fix the filename/stem contract; record source byte count/SHA-256 separately from grid validation; only retry transient transfer failures once with a separate `retry-1` phase. Do not count this failed run as source-hash verification because no hash receipt was preserved by the old code.
- [x] Re-ran isolated CI after the exact-filename/byte-receipt correction: [run 40112528293](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112528293) passed **217 tests in 4.85 s**, all eight workflow YAMLs and pinned actionlint checks. Its live CMR artifact was downloaded and independently verified: SHA-256 `ab1dc5ce3e237649b9c5e404d4c92e6b87c3dae3bf1565dde28e55f66dfe9a49`, matching GitHub's digest; exact P05023 identities/URLs 5/5, raw downloads 0/5. Raw source acquisition still requires explicit `[run-know-place]` dispatch.


- [x] Audit main's last pipeline merge and retry-policy commits; reuse its Earthdata/Drive secret names, pinned science SHA, version/run labels, source-byte expectation, one-attempt-per-worker policy, and bounded receipt-aware `retry-1` handling. No four-attempt large-file retry was introduced.
- [x] Fix raw GOFF false rejection where parser name includes `.h5` but CMR granule name does not. Hash/byte receipts are now saved before HDF5/grid validation, and counts separate downloaded+hashed products from grid-valid products.
- [x] Validate the correction in [run 40109347836](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347836): 217 tests passed, eight workflow YAML files parsed, and pinned actionlint validation passed. The catalog-only job confirmed exact P05023 IDs/URLs 5/5 with raw downloads 0.
- [ ] With explicit `[run-know-place]` authorization only, run the exact-author source workflow again; inspect each of the five actual payload byte counts/SHA-256 hashes, HDF5 identity/grid receipts, derived metrics, and both Drive receipts. Keep paper-method parity BLOCKED until true author implementation parity is demonstrated; do not substitute X05026.


## Latest follow-up — 2026-10-24 (CI 40112528293)

- [x] Validation [40112528293](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112528293), code/test/workflow/docs commit `cce3052af83d39aa6988301ea5b96b6fd776c82a`: 217 tests passed in 4.85 s; eight workflow YAMLs parsed; pinned actionlint v1.7.12 checksum and semantic checks passed.
- [x] Downloaded and independently verified `know-place-author-exact-live-cmr-access-evidence` (artifact ID `12566734581`, 4,117 bytes), SHA-256 `ab1dc5ce3e237649b9c5e404d4c92e6b87c3dae3bf1565dde28e55f66dfe9a49`, matching GitHub's digest. Manifest: CMR identities 5/5, data URLs 5/5, blocking products 0, raw downloads 0, source hashes 0/5. Evidence: `docs/know-place/evidence/LATEST_CMR_ARTIFACT_INTEGRITY_20261024.md`.
- [x] Confirmed exact-author run [40109347847](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347847) and legacy run [40112528294](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112528294) skipped raw acquisition because exact `[run-know-place]` consent was absent.
- [ ] Manually dispatch `SARGuardian AOI WKT E2E (safe branch dispatcher)` on branch `feat/know-place-analysis`, profile `author-exact-p05023`, exact consent `[run-know-place]`, and configured Earthdata + Drive secrets. The connected GitHub tools do not expose workflow dispatch, so raw acquisition was not launched from this session.
- [ ] After consented acquisition, inspect all five byte counts/SHA-256, HDF5 identity/grid receipts, analysis outputs and both verified Drive receipts. Keep paper parity BLOCKED and hazard detection NOT_EVALUATED until distinct scientific evidence supports them.

- [x] Latest CMR artifact integrity evidence refreshed to run 40112528293; metadata confirms exact author identities/URLs 5/5, raw source downloads 0/5 and source SHA-256 pins 0/5.

## Latest exact-author raw replay — 2026-10-24

- [x] [Run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362) downloaded five exact P05023 GOFF HDF5 products (5,473,566,720 bytes total), verified SHA-256 5/5, HDF5 identity 5/5 and grid validation 5/5 (4311 × 4230, EPSG:32645, 80 m posting). Drive-derived bundle and both receipt uploads report remote verification PASS; raw payloads were not uploaded and temporary raw files were removed after remote retention verification.
- [x] Target pair 2026-07-26 → 2026-08-19 metrics: crown median 0.966063 m; mean vector 1.722246 m at 277.793°; median rate 0.040253 m/day; R=0.852850. These are numerical similarities, not reproduction: crown is a bounding-box approximation and controls are not author-supplement verified. Report status: `NOT_COMPARABLE_EXACT_CROWN_GEOMETRY_UNVERIFIED`.
- [x] Corrected the wrapper's stale status overwrite: after source bytes are pinned, source identity is `FIVE_EXACT_AUTHOR_SOURCE_HASHES_PINNED`; paper reproduction is `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`. The historical artifact retains its pre-fix label. Validation [40115947045](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40115947045) passed 217 tests, eight YAML parses and actionlint checks.
- [ ] Verify author-supplement crown geometry and control sampling, compare golden tables/masks, resolve terrain vertical-datum provenance, and run full-footprint screen parity. Hazard detection remains `NOT_EVALUATED`.

## Latest follow-up — 2026-10-25 (validation 40120575317)

- [x] Independently downloaded and SHA-256-verified author-exact derived artifact from run [40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362): artifact ID 12567509703, 830,510 bytes, SHA-256 `d49b6aa10da27138de6b8b8f2af6a4b5d3ffd86a8ccb87cef7765e3c597a0b59`; it contains diagnostic NPZ/CSV/reports/manifests/receipts and no raw HDF5.
- [x] Five exact P05023 source SHA-256s and grid validations are present in the source manifest; target-pair exploratory metrics are preserved in `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- [!] Historical run's two Drive upload receipts are pre-cleanup and say `raw_source_deleted=false`; do not treat them as post-delete proof. Current workflow now emits, uploads, and validates a separate `author-exact-raw-cleanup-receipt.json` after rehashing all five raw files and confirming zero remain.
- [x] Validation [40120575317](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40120575317), commit `60dcde7cb3b3895d419b14b689201b6d00d3eb07`: **224 tests passed**, eight workflows plus dispatcher parsed, actionlint checksum/semantic checks passed, live exact-author CMR links 5/5, payload downloads 0.
- [ ] A fresh explicitly consented manual replay is still required to test the new post-cleanup receipt end-to-end; latest runs [40120575271](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40120575271) and [40120575285](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40120575285) correctly skipped raw acquisition without `[run-know-place]`.
- Paper reproduction remains `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; hazard detection `NOT_EVALUATED`. Main remains unchanged; no merge.


## 23. Independent artifact recheck and latest validation — 2026-10-25

- [x] Re-downloaded artifact `know-place-author-exact-40114703362-1` (ID `12567509703`); independently recomputed SHA-256 `d49b6aa10da27138de6b8b8f2af6a4b5d3ffd86a8ccb87cef7765e3c597a0b59`, matching GitHub's digest. No raw HDF5 is in the artifact or its derived bundle.
- [x] Independently verified the five manifest entries are exact `P05023`, all download/hash/HDF5 identity/grid checks pass, and total source bytes are 5,473,566,720. Grid: 4311 × 4230, EPSG:32645, 80 m posting. See `docs/know-place/evidence/AUTHOR_EXACT_ARTIFACT_INDEPENDENT_RECHECK_20261025.md` for all five hashes and per-pair counts.
- [!] Both historical Drive receipts say `raw_source_deleted=false`; they prove remote verification of the derived bundle/receipt copy, not post-delete cleanup. The new post-cleanup receipt path was added later but is not yet exercised end-to-end.
- [x] Latest validation [40121243012](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40121243012), commit `56ef9f52977a7ac6a0c314b8560bfe4ff27743b0`: **224 tests passed in 2.58 s**, eight workflow YAMLs plus branch dispatcher parsed, pinned actionlint checksum/semantic validation passed; live CMR/data links confirmed 5/5 and raw downloads stayed 0.
- [x] Latest legacy run [40121243034](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40121243034) skipped acquisition because the exact consent marker was absent. No new raw products were downloaded in that run.
- [ ] Manually dispatch the author-exact workflow with exact `[run-know-place]` and configured Earthdata/Drive secrets to test post-cleanup receipt; do not infer consent from a prior request.
- Paper reproduction remains `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; hazard detection remains `NOT_EVALUATED`. Main remains `2218dfeb73353080d8d94bd733d9e7bd9a848886`; do not merge or write to main.


## Independent archive polygon-null replay — 2026-10-25

- [x] Independently recomputed R from east/north bands in the five exported site-field TIFFs, replayed the archive's `code/polygon_null.py` sampling algorithm in chronological pair order, and compared all nine stored metrics for each pair against `tables/polygon_null.json`: **45/45 exact matches at archive rounding, zero mismatches**. Evidence: `docs/know-place/evidence/AUTHOR_ARCHIVE_POLYGON_NULL_REPLAY_20261025.md`.
- [x] Confirmed the exact post-hoc control analysis is reproducible from the archive's derived fields. This is not the paper's published method, does not prove raw-GOFF-to-field parity, and does not close the full-footprint screen gate.
- The separate post-cleanup Drive receipt still needs a fresh explicitly consented manual run. Paper reproduction remains `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; hazard detection remains `NOT_EVALUATED`. No merge or write to `main`.


## Author-compatible raw site-series path — 2026-10-25

- [x] Added a separate tools/know_place/author_raw_site_series.py; it uses the author's nearest-crown radar-grid cell and height-axis median geometry, the archived SNR >= 5 / magnitude <= 10 m mask (no added correlation gate), conditional outside-AOI reference correction only when more than 200 valid ring pixels exist, and separate P1/site-series versus polygon-null coherence estimands.
- [x] Added unit tests for the author geometry estimator, quality/reference policy, deterministic null sampling, fixed author WKT bounds and 65 benchmark comparisons. Added compile/test coverage to .github/workflows/know-place-analysis-validation.yml.
- [x] Integrated the separate profile into author_exact_acquisition.py so it processes the same five already downloaded raw products after the exploratory run; no second acquisition is performed. The final raw-replay gate requires all five pairs and 65/65 Table S4 archive-metric comparisons. A mismatch leaves the report and retention receipts available, but fails the workflow rather than forcing a match.
- [x] Validation [40126196592](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40126196592), commit 20c7d7b5c43d8b60b0361726ce605a65376936ac: **229 tests passed**, all eight workflow YAMLs plus the branch launcher parsed, pinned actionlint semantic validation passed, and live exact-author CMR preflight confirmed five P05023 links without downloading raw payloads.
- [x] On this commit, both raw replay workflows correctly passed their no-consent gates and skipped the expensive acquisition jobs; **new raw downloads = 0**. This is not an end-to-end raw replay result.
- [ ] Run the new author-compatible profile against the five pinned P05023 HDF5 files on an explicitly consented manual dispatch; examine all 65 comparisons and the independently generated site-series CSV/NPZs. The exact consent input [run-know-place] has not been given in this turn.
- [ ] Complete the independent full-footprint pixelwise screen comparison and terrain/vertical-reference sensitivity. No hazard-detection performance claim.
- Global paper reproduction remains unverified until the consented source-level run actually matches; hazard detection remains NOT_EVALUATED. Main remains 2218dfeb73353080d8d94bd733d9e7bd9a848886; no merge or write to main.


## Processed-field site-series cross-check — 2026-10-25

- [x] Independently recomputed five site-series rows from the archive's five cropped field TIFFs and compared exact valid-crown counts plus displacement median, daily rate, P1 crown R and P1 scene R to the original tables: **25/25 matches, zero mismatches**. Evidence: docs/know-place/evidence/AUTHOR_ARCHIVE_SITE_SERIES_REPLAY_20261025.md.
- [x] Separate post-hoc polygon-null replay remains 45/45 at stored precision: docs/know-place/evidence/AUTHOR_ARCHIVE_POLYGON_NULL_REPLAY_20261025.md. These checks are from processed fields, not direct replay from raw GOFF.
- [ ] Run raw-source author-compatible site series on the exact five P05023 HDF5 files and require 65/65 Table S4 metric comparisons before marking the site-series table matched. This is not authorized in the absence of explicit [run-know-place] consent.
- [ ] Keep full-footprint screening raster parity and hazard-detection validation as separate incomplete gates.


## Latest status addendum — 2026-10-25 (commit `f56db40f6f82b4ff2769b77023ff5a3d5a051fbd`)

- [x] Verified latest isolated CI: [run 40133358388](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40133358388) passed **238 tests**, eight workflow YAML parses and pinned actionlint v1.7.12 semantic validation. Live ASF identity checks passed without downloading raw payloads.
- [x] Corrected the workflow shell line continuations flagged by actionlint/shellcheck. The archive download uses an exact SHA-256 gate; three extracted terrain rasters are each hash-pinned.
- [x] Integrated `tools/know_place/author_footprint_replay.py` into `.github/workflows/know-place-author-exact-replay.yml`: after a newly consented run it will reprocess all five exact P05023 native grids using author-compatible per-pixel geometry and screening; compare the three full-footprint golden rasters and the 101-zone directional inventory; retain the replay report and derived maps through the existing private Drive upload/receipt flow; then delete raw GOFF only after verified derived retention.
- [x] The full-footprint gate is fail-closed: it requires 3/3 aggregate raster matches, 101/101 directional inventory match, and 106 components before directional filtering / 101 after. This is a code and CI integration gate only; **the actual full-footprint replay has not yet run**.
- [x] `main` remains unchanged at `2218dfeb73353080d8d94bd733d9e7bd9a848886`; all changes remain isolated on `feat/know-place-analysis`.
- [ ] Re-dispatch the author-exact workflow only with explicit `[run-know-place]` consent to reacquire the five raw files and run P2 + full-footprint parity. Without this marker the raw acquisition step is skipped.
- [ ] Resolve displacement-null parity from source script/draw-level controls if obtainable. The supplied Zenodo package contains summary values but not the generator needed to independently recreate those three Table S4 columns.
- [ ] Keep hazard-detection performance unevaluated until independent event-level controls, precision/recall, false-alarm and lead-time analysis exist.

Current scientific status: `PAPER_REPRODUCTION_STATUS=PARTIAL_AUTHOR_SITE_SERIES_METRICS_MATCH_FULL_FOOTPRINT_SCREEN_NOT_REPRODUCED`; `HAZARD_DETECTION_STATUS=NOT_EVALUATED`.


## Score-contract integrity follow-up — 2026-10-25

- [x] Inspected the deposited `inventory/candidates_attributed.csv` and the exact archived `code/wide_screen.py` without raw downloads. The archive has 106 candidate rows / 101 `quality=True` rows; the shipped script assigns `score = n_epochs * anom_m * R`, but **0/106** deposited scores match that expression, while **106/106** match `n_epochs * anom_m * R_res`.
- [x] Evidence: `docs/know-place/evidence/AUTHOR_CANDIDATE_SCORE_CONTRACT_AUDIT_20261025.md`. A zero-download regression test now ensures the full-footprint parity audit reports this contract conflict instead of silently replacing the source-script formula.
- [x] Corrected the full-footprint comparison target count: compare the full 106-row `inventory/candidates_attributed.csv` including its quality flag, separately compare the 101 directional/quality-passing candidate metrics with `tables/TableS7_all_validated_zones.csv`, and preserve a distinct score-contract diagnostic.
- [x] CI including the updated candidate-score diagnostic and strict final report path passed in [run 40134175029](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40134175029): both scientific tests and live ASF identity checks succeeded without raw acquisition.
- [ ] Do not launch another 5.47 GB raw replay merely to obtain a green badge while this upstream code/output score discrepancy is unresolved. A future authorized run will preserve the score-contract mismatch in the report and fail the final scientific gate if the raster/zone evidence matches but the score conflict remains. Verified derived outputs and cleanup receipts must still be retained and checked before raw deletion.
- [ ] Resolve which scoring convention is authoritative (the archived screen source code or the deposited candidate inventory/output-generation convention) before claiming full candidate-ranking reproduction. Do not silently change the score formula.
- Hazard detection remains `NOT_EVALUATED`; `main` remains `2218dfeb73353080d8d94bd733d9e7bd9a848886`.
