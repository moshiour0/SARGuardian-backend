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
- [x] Receive and SHA-256 record the paper PDF, Supplementary Information, 101-zone CSV, and separate Zenodo code/output archive; archive byte integrity and manifest payload checks are recorded in `docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md`. [ ] Retrieve and SHA-256 pin exact raw author GOFF payloads; source HDF5 files are not included in the archive.
- [x] Pin the five exact author GOFF IDs and P05023 release from Supplementary Table 1. Run direct ASF exact-ID, AOI/date, and wildcard searches, then NASA CMR collection-scoped exact queries. CMR confirmed all five exact P05023 producer IDs in collection `C2854341702-ASF`; the latest live CMR evidence confirms all five exact P05023 identities and data URLs. Catalog identity is 5/5, but source bytes/hashes remain unverified; X05026 is not a substitute. Evidence: `docs/know-place/evidence/CMR_AUTHOR_P05023_EXACT_CATALOG_RESOLUTION_20261024.md`.
- [ ] Confirm GOFF HDF5 paths, units, sign convention, metadata-grid coordinates and unit-vector sampling against the exact five files and product specification.
- [x] Define a versioned input/output JSON schema and separate structural / method-reproduction / interpretation statuses.
- [x] Define separate WKT masks for the reference box, crown and box-minus-crown; the supplied paper fixes the crown bounds at 85.5245–85.5400° E and 28.2847–28.2970° N (2.07 km²), and the reference box bounds. [ ] Verify pixelwise crown-mask parity on the original GOFF source grid. **Count-estimand correction (2026-10-24):** exported displacement-valid counts `[283, 294, 296, 292, 195]` match `tables/nisar_pot_series.json` key `n`; separately recomputed R-valid crown counts `[302, 299, 302, 298, 202]` match `tables/polygon_null.json` key `n_px`. The earlier 296-versus-298 comparison mixed estimands. Aggregate count parity does not prove pixelwise source-grid mask parity.
- [x] Define and record deterministic exploratory control parameters (seed, draw count, PRNG, reject/accept accounting and quantile convention). - [ ] Verify exact sample geometry/algorithm against author scripts before claiming parity.

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
- [ ] Obtain and SHA-256 pin the five exact author-published GOFF HDF5 bytes and geometry cubes. All five exact P05023 IDs and direct HDF5 URLs are now confirmed in CMR, but no HDF5 payload has been downloaded and source SHA-256 pins remain 0/5. Verify height-axis metadata and quantify the vertical offset's impact on `cE/cN/kE/kN` coefficient maps and full-grid outputs. Do not substitute X05026.
- [ ] Resolve remaining source/datum provenance uncertainty with independent author input evidence; the current public GLO-90 replay and formal height transformation quantify the issue but do not prove what exact source tile bytes the author used or make the existing paper replay equivalent.
- [ ] Run exact author-pinned raw GOFF inputs on the documented 4230 x 4311 grid, regenerate five per-pair footprint maps and candidate vector outputs, and compare with archived screening rasters. Raw GOFF bytes/full per-pair rasters remain absent; catalog identity is not source-byte identity.
- [ ] Recreate the separate post-hoc downslope attribution/control test from candidate_attributes.py. This must not be folded into the screen or relabel a movement candidate as an event detection.
- [x] Keep HAZARD_DETECTION_STATUS=NOT_EVALUATED. The screen detects candidate moving surfaces, not impending failure; see docs/know-place/evidence/AUTHOR_FOOTPRINT_SCREEN_KERNEL_AUDIT_20261024.md.
- [ ] Keep core diagnostic separate and state its selection bias if implemented.

## Milestone 5 — Golden comparison and interpretation

- [x] Compare the 26 Jul–19 Aug crown median (0.966 m), mean-vector magnitude (1.722 m) and azimuth (277.79°) to rounded paper targets; residual geometry/mask/input-variant differences are documented.
- [x] Compare R on the common 0.17–2.75 m pointwise window (0.869 at 150 crown centres) to the published ~0.869 at 147 centres; document background R/count mismatch and non-equivalent controls.
- [x] Retrieve and inspect archived site-series and polygon-null code and compare all five published TableS4 values to the benchmark fixture. [ ] Recompute five polygon-null distributions with the exact author algorithm: seed 20260907, unique candidate centres, edge policy, strict quantile inequalities, and acceptance rule.
- [x] Recompute same-estimand statistics from all five exported author field GeoTIFFs and compare `nisar_pot_series.json`, `polygon_null.json` and Table S4: 120/120 comparison checks passed at archived table precision. Results and source-table hashes: `docs/know-place/evidence/AUTHOR_PROCESSED_FIELD_TABLE_PARITY_20261024.md`. This is exported-field/table parity only; exact source-grid mask and raw-GOFF parity remain blocked.
- [x] Record the paper’s interpretation and explicitly avoid describing this analysis as an early-warning detector.
- [x] Keep author-method/raw-replay parity BLOCKED/NOT_COMPARABLE: Zenodo archive is verified and processed fields/tables are available, but raw GOFF HDF5 bytes are absent and current geometry, correlation gate, coherence, crown mask and controls differ from author code; latest live CMR evidence confirms all five exact P05023 IDs and HDF5 URLs; raw bytes and exact method parity remain unverified.
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
- **Milestone 1:** blueprint, method contract and provenance implemented. Paper, Supplementary Information, 101-zone CSV and Zenodo archive are hash-recorded. CMR confirms exact metadata for the five P05023 identities and the exact-author resolver confirmed five direct HDF5 URLs. The archive still lacks raw GOFF source granules and no source SHA-256 hash is pinned; author-method parity remains unverified. See `docs/know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md` and `docs/know-place/evidence/CMR_AUTHOR_P05023_EXACT_CATALOG_RESOLUTION_20261024.md`.
- **Milestone 2:** scientific kernels, strict synthetic HDF5/geometry/integration tests, blind-split evaluator and threshold-selector tests, motion dynamics, author benchmark integrity, offline author-catalog handling and CSV bundle contract passed **122 tests** in [validation run 40035193088](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40035193088). The same run's YAML and actionlint checks passed. Live catalog identity is reported separately from code/test status; the author-exact source gate remains BLOCKED. Edge/missing-centre tests are current-kernel policy tests only, not author-method parity.
- **Milestone 3:** five raw candidate GOFF HDF5 products were fetched one at a time during [raw replay Run 40006999011](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40006999011); all five historical file-size/SHA-256 identity checks passed, and all five metric records were produced. The later saved-array reanalysis also verified the five NPZ hashes against the source report before computing any new R values.
- **Milestone 4:** per-pair gates, corrected dE/dN/magnitude metrics, 5x5 R and spatial-control diagnostics have been computed. The original run used a too-strict 25/25 neighbour rule; the separate [saved-array R sensitivity reanalysis, Run 40015023621](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015023621), computes the 1/5/10/15/20/25 sensitivity and does not modify the original run report.
- **Milestone 5:** the target pair gives 0.966 m crown median, 1.722 m mean-vector magnitude and 277.79° azimuth; R=0.869 on a common pointwise 0.17–2.75 m window (150 centres) is close to the paper’s ~0.869 (147 centres). Processed author fields are now available, but the former 296-versus-298 comparison mixed displacement-valid `n` with polygon-null R-valid `n_px`; both count series now match their respective archived tables on the exported fields, while exact pixelwise source-grid mask parity remains unverified. The archived historical first-pair input differs (X05026 vs author P05023); direct P05023 URL metadata is now resolved, but raw author bytes are not downloaded. Site geometry, coherence, mask and null-control implementation are not yet author-equivalent. Our 96.08th-percentile result is **not comparable** to the paper’s 94.7th percentile and must not be treated as a detection.
- **Milestone 6:** isolated raw and saved-array workflows are branch-only; saved-array result/summary retention has passed remote Drive verification. The AOI result bundle includes `timeseries.csv`, `motion-features.csv`, native-grid GeoTIFF placeholders in synthetic tests / real geotiffs in actual measurement runs, NPZ diagnostics, result, dashboard, and checksummed manifest; ephemeral-source manifests now state whether raw HDF5 was deleted or retained. All new commits remain on `feat/know-place-analysis`; no merge or edit to `main` was performed.
- **Paper reproduction:** `BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; processed archive and table values are verified, direct HDF5 URLs are resolved for all five author IDs, but exact raw GOFF bytes, source hashes, author-method parity, full-footprint replay and cross-version manuscript mapping remain unresolved.
- **Hazard detection:** `NOT_EVALUATED`. Do not report an operational landslide alarm from these results.


- [x] Add isolated archived-author kernels and synthetic regression cases in `tools/know_place/author_parity.py` and `tools/tests/test_know_place_author_parity.py`. These are not yet wired into the exploratory runner; end-to-end golden comparison remains pending.


## Latest exact-author acquisition workflow status — 2026-10-24

- [x] Add the exact-author acquisition runner and direct CMR HDF5 URL resolver. The resolver requires exact P05023 producer identity, the pinned CMR collection, trusted ASF/earthdatacloud hosts, the exact expected HDF5 path/name and exactly one data link per product.
- [x] Preserve failure manifests in the derived output area, bind config provenance to the source-manifest SHA-256, fail closed unless the analysis exit code is zero and all five scientific metrics are complete, and validate all five raw grids against the expected 4311 x 4230 EPSG:32645 / 80 m grid with identical coordinate axes.
- [x] Add offline acquisition-contract tests and wire them explicitly into the validation workflow. Latest validation [run 40058988024](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988024), branch head 2fddad5fbd3d66fc9ade40da41ce829bfabf7610: **204 passed in 4.87 s**, seven workflow YAML parses, actionlint v1.7.12 checksum and semantic validation passed.
- [x] Live CMR/data-link check: AUTHOR_CMR_CATALOG_GATE=PASS; AUTHOR_EXACT_PRODUCTS_CONFIRMED=5/5; AUTHOR_EXACT_CMR_DATA_URLS_CONFIRMED=5. Source payload downloads=0 and raw source SHA-256 pins=0. Evidence artifact [know-place-author-exact-live-cmr-access-evidence](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988024) (artifact digest SHA-256 b81e1d2b1ba4c78a90753ed84fd1ff1da0ff72c886bf46f31ffdd99928a1c4e9).
- [x] Register the exact-author raw workflow as manual-dispatch-only with an exact `[run-know-place]` consent input and credential preflight. Push registration run [40058988016](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988016) did not run the raw job; legacy run [40058988057](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988057) also skipped analysis.
- [ ] Manually dispatch the exact-author workflow with consent input `[run-know-place]` and working Earthdata/Google Drive secrets; download exactly five P05023 payloads, hash/validate, run analysis and verify Drive receipts. This step has not yet run from this session.
- **Status contract:** paper reproduction remains BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED; hazard detection remains NOT_EVALUATED; no merge/change to main.

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
- [ ] Use Actions → `SARGuardian AOI WKT E2E (safe branch dispatcher)` → branch `feat/know-place-analysis` → `author-exact-p05023`; enter `[run-know-place]` and dispatch. The workflow has not downloaded the five raw source products yet.
- [ ] Review each downloaded HDF5's byte count/SHA-256, HDF5 identity and grid; then review five-pair metrics, source-grid/mask checks, output bundle and verified Drive receipt.
- [ ] Only after the Bhote Koshi run, freeze AOI/source identities for Samudra Tapu and Bara Shigri; then validate Hubbard/Malaspina and the distinct Budhi Gandaki GUNW case. Do not tune using the final holdout.
- [ ] Do not claim paper parity, movement-detector validation or hazard detection until each distinct gate has its own evidence.

**Status rule:** The Run Workflow launch path and multi-site protocol are implemented; exact author raw payloads and source hashes are still 0/5. Generic AOI runs are exploratory displacement measurements. `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; `HAZARD_DETECTION_STATUS=NOT_EVALUATED`. The feature branch is isolated; no merge/change to `main`.


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
- [ ] Re-run isolated CI after this correction; then, only after explicit `[run-know-place]` manual dispatch, re-download/validate the exact five P05023 products and inspect new source hashes/metrics/verified Drive receipts. Keep paper parity BLOCKED and hazard detection NOT_EVALUATED.


- [x] Audit main's last pipeline merge and retry-policy commits; reuse its Earthdata/Drive secret names, pinned science SHA, version/run labels, source-byte expectation, one-attempt-per-worker policy, and bounded receipt-aware `retry-1` handling. No four-attempt large-file retry was introduced.
- [x] Fix raw GOFF false rejection where parser name includes `.h5` but CMR granule name does not. Hash/byte receipts are now saved before HDF5/grid validation, and counts separate downloaded+hashed products from grid-valid products.
- [x] Validate the correction in [run 40109347836](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347836): 217 tests passed, eight workflow YAML files parsed, and pinned actionlint validation passed. The catalog-only job confirmed exact P05023 IDs/URLs 5/5 with raw downloads 0.
- [ ] With explicit `[run-know-place]` authorization only, run the exact-author source workflow again; inspect each of the five actual payload byte counts/SHA-256 hashes, HDF5 identity/grid receipts, derived metrics, and both Drive receipts. Keep paper-method parity BLOCKED until true author implementation parity is demonstrated; do not substitute X05026.
