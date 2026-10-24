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
- [x] Pin the exact five author GOFF IDs and P05023 release from Supplementary Table 1 in `docs/know-place/reference/author_benchmark_v1.json`. The earlier raw replay used X05026 for the first pair, so that historical five-pair series is not the exact author-input series. [x] Run a no-download exact-ID query: 4/5 author P05023 identifiers were confirmed through trusted collection URLs, but the first pair returned NOT_FOUND (Run 40035193088). [ ] Resolve that exact source via author archive/direct metadata and hash the exact bytes; preserve historical X05026 evidence.
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
- [ ] Keep core diagnostic separate and state its selection bias if implemented.

## Milestone 5 — Golden comparison and interpretation

- [x] Compare the 26 Jul–19 Aug crown median (0.966 m), mean-vector magnitude (1.722 m) and azimuth (277.79°) to rounded paper targets; residual geometry/mask/input-variant differences are documented.
- [x] Compare R on the common 0.17–2.75 m pointwise window (0.869 at 150 crown centres) to the published ~0.869 at 147 centres; document background R/count mismatch and non-equivalent controls.
- [x] Retrieve and inspect archived site-series and polygon-null code and compare all five published TableS4 values to the benchmark fixture. [ ] Recompute five polygon-null distributions with the exact author algorithm: seed 20260907, unique candidate centres, edge policy, strict quantile inequalities, and acceptance rule.
- [x] Recompute same-estimand statistics from all five exported author field GeoTIFFs and compare `nisar_pot_series.json`, `polygon_null.json` and Table S4: 120/120 comparison checks passed at archived table precision. Results and source-table hashes: `docs/know-place/evidence/AUTHOR_PROCESSED_FIELD_TABLE_PARITY_20261024.md`. This is exported-field/table parity only; exact source-grid mask and raw-GOFF parity remain blocked.
- [x] Record the paper’s interpretation and explicitly avoid describing this analysis as an early-warning detector.
- [x] Keep author-method/raw-replay parity BLOCKED/NOT_COMPARABLE: Zenodo archive is verified and processed fields/tables are available, but raw GOFF HDF5 bytes are absent and current geometry, correlation gate, coherence, crown mask and controls differ from author code; live ASF did not find the first-pair P05023 ID.
- [ ] Complete independent scientific review before claiming reproduction; code-level method parity, exact raw-source hashes, full-footprint raster regeneration and pixelwise mask/output parity remain unverified.
- [x] Keep geometry policy explicit: crown-local constant geometry for the site series; per-pixel Copernicus GLO-90 geometry for the footprint screen. The exact datum/query behind the current 5151.0 m value remains unverified; do not tune it to scalar paper targets.
- [x] Add blind split enforcement so threshold calibration only accepts validation-only labels and held-out scoring requires a separate test-only registry plus a hash-matched validation registry.

## Milestone 6 — Operational isolation and review

- [x] Add an isolated expensive replay workflow gated by the explicit `[run-know-place]` commit marker; it exists only on this feature branch.
- [x] Verify compact CSV/JSON, NPZ diagnostics, source/array hashes, quality-gate accounting, scientific caveats and separate reanalysis artifacts; the latest reanalysis report and summary were remotely verified in Drive.
- [x] Run automated scientific tests, YAML parsing and `actionlint` with author-data integrity and offline ASF-gate tests included: **122 tests passed** in [validation run 40035193088](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40035193088). The historical-candidate gate passed; the separate author-exact gate recorded 4/5 exact P05023 IDs confirmed and the first ID NOT_FOUND, with zero raw downloads. A blocked science input is recorded in the artifact rather than misreported as a passing source match.
- [x] Latest branch validation after event/provenance hardening: [run 40047359607](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40047359607), commit `a0c41e721a9158d47d6ebb1505451d109ab33a23`: **150 tests passed**, four workflow YAML files parsed, actionlint v1.7.12 checksum and semantic validation passed. ASF source downloads were zero; first author P05023 remains NOT_FOUND. [Raw replay run 40047359560](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40047359560) skipped five-pair analysis due to missing `[run-know-place]`.
- [x] Keep every Know Place Analysis commit on `feat/know-place-analysis`; no `main` changes or merge were made.
- [ ] Do not merge to `main`. Any later integration requires explicit review and approval.

## Current gate status (updated 2026-10-24)

- **Milestone 0:** complete. Baseline run, source/dashboard artifacts, array/report checksums and findings are saved under `docs/know-place/evidence/`.
- **Milestone 1:** blueprint, method contract and versioned provenance implemented. The supplied Research Square paper, Supplementary Information and 101-zone CSV are source-hash recorded; crown bounds, five author P05023 IDs and Table 4 values are transcribed and tested. The existing blueprint cites a differently titled EGUsphere DOI; cross-version equivalence remains unresolved. The live author catalog gate found four of five P05023 IDs and could not find the first; historic replay used X05026 for that pair. The Zenodo archive is verified; raw source granules are not included, and author-method parity remains unverified. See `docs/know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md`.
- **Milestone 2:** scientific kernels, strict synthetic HDF5/geometry/integration tests, blind-split evaluator and threshold-selector tests, motion dynamics, author benchmark integrity, offline author-catalog handling and CSV bundle contract passed **122 tests** in [validation run 40035193088](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40035193088). The same run's YAML and actionlint checks passed. Live catalog identity is reported separately from code/test status; the author-exact source gate remains BLOCKED. Edge/missing-centre tests are current-kernel policy tests only, not author-method parity.
- **Milestone 3:** five raw candidate GOFF HDF5 products were fetched one at a time during [raw replay Run 40006999011](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40006999011); all five historical file-size/SHA-256 identity checks passed, and all five metric records were produced. The later saved-array reanalysis also verified the five NPZ hashes against the source report before computing any new R values.
- **Milestone 4:** per-pair gates, corrected dE/dN/magnitude metrics, 5x5 R and spatial-control diagnostics have been computed. The original run used a too-strict 25/25 neighbour rule; the separate [saved-array R sensitivity reanalysis, Run 40015023621](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015023621), computes the 1/5/10/15/20/25 sensitivity and does not modify the original run report.
- **Milestone 5:** the target pair gives 0.966 m crown median, 1.722 m mean-vector magnitude and 277.79° azimuth; R=0.869 on a common pointwise 0.17–2.75 m window (150 centres) is close to the paper’s ~0.869 (147 centres). Processed author fields are now available, but the former 296-versus-298 comparison mixed displacement-valid `n` with polygon-null R-valid `n_px`; both count series now match their respective archived tables on the exported fields, while exact pixelwise source-grid mask parity remains unverified. The first-pair input differs (X05026 vs P05023), and site geometry, coherence, mask and null-control implementation are not yet author-equivalent. Our 96.08th-percentile result is **not comparable** to the paper’s 94.7th percentile and must not be treated as a detection.
- **Milestone 6:** isolated raw and saved-array workflows are branch-only; saved-array result/summary retention has passed remote Drive verification. The AOI result bundle includes `timeseries.csv`, `motion-features.csv`, native-grid GeoTIFF placeholders in synthetic tests / real geotiffs in actual measurement runs, NPZ diagnostics, result, dashboard, and checksummed manifest; ephemeral-source manifests now state whether raw HDF5 was deleted or retained. All new commits remain on `feat/know-place-analysis`; no merge or edit to `main` was performed.
- **Paper reproduction:** `BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; processed archive and table values are verified, but exact raw GOFF bytes (especially first-pair P05023), author-method parity, full-footprint replay and cross-version manuscript mapping remain unresolved.
- **Hazard detection:** `NOT_EVALUATED`. Do not report an operational landslide alarm from these results.


- [x] Add isolated archived-author kernels and synthetic regression cases in `tools/know_place/author_parity.py` and `tools/tests/test_know_place_author_parity.py`. These are not yet wired into the exploratory runner; end-to-end golden comparison remains pending.
