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
- [ ] Retrieve and verify the actual author-supplement archive/scripts/rasters/statistics; the preprint says these exist, but the official page's visible links do not expose a supplement and the Research Square file could not be retrieved in this pass. No supplement checksum is claimed. See `docs/know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md`.
- [ ] Pin exact five raw HDF5 product IDs and releases from the paper supplement; do not infer from date alone.
- [ ] Confirm GOFF HDF5 paths, units, sign convention, metadata-grid coordinates and unit-vector sampling against the exact five files and product specification.
- [x] Define a versioned input/output JSON schema and separate structural / method-reproduction / interpretation statuses.
- [x] Define separate WKT masks for the reference box, crown and box-minus-crown; persist crown-WKT SHA-256 and geometry provenance. (An author-exact crown polygon is still outstanding.)
- [x] Define and record deterministic exploratory control parameters (seed, draw count, PRNG, reject/accept accounting and quantile convention). - [ ] Verify exact sample geometry/algorithm against author scripts before claiming parity.

## Milestone 2 — Implement pure scientific kernels (no downloads in unit tests)

- [x] Unit-test horizontal dE/dN projection against hand-computed vectors including sign checks.
- [x] Unit-test quality gate order, SNR ≥ 5, magnitude ≤ 10 m, reject-not-clip behavior, and per-gate rejection counts.
- [x] Unit-test component-wise background median correction on synthetic arrays with known bias.
- [x] Unit-test crown median magnitude, mean-vector magnitude/azimuth, and day-normalized descriptive rate as distinct statistics.
- [x] Test 5×5 mean resultant length using uniform/opposed vectors and expose 1/5/10/15/20/25-neighbour sensitivity in the report.
- [x] Add explicit corner/edge and missing-centre-vector regression cases as current-kernel policy tests; these do not claim author-method parity.
- [x] Unit-test deterministic size-matched control sampling, accepted/rejected draw accounting and empirical percentile.
- [x] Unit-test missing/finite/nodata behavior and explicit failure when background/crown support is empty; test HDF5 attribute and creation-property fill handling without mistaking a default zero for nodata.
- [x] Unit-test missing or duplicate products, wrong track/direction, invalid geometry, unit/CRS mismatches and ambiguous metadata fail closed.

## Milestone 3 — Strict raw GOFF HDF5 reader

- [x] Read exact layer2 AT, SR, SNR, correlation, coordinate vectors, CRS/projection and per-product radar geometry from all five candidate raw HDF5 inputs.
- [x] Implement geometry metadata interpolation with explicit cube selection, axis/unit/CRS checks and no extrapolation; synthetic schema tests pass. Actual five-product metadata verification remains pending.
- [ ] Verify that the configured constant HAE query (the current runbook example uses 5151.0 m for every ROI pixel) matches the author's geometry-sampling procedure; compare against author outputs and/or quantify height-sampling sensitivity before claiming projection parity.
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
- [ ] Compare each pre-event interval's null percentile with the author's supplementary results.
- [x] Record the paper’s interpretation and explicitly avoid describing this analysis as an early-warning detector.
- [ ] If the supplement is unavailable or processing differs, clearly label the exact parity gate BLOCKED/NOT_COMPARABLE rather than PASS.
- [ ] Complete independent scientific review before claiming reproduction; exact author geometry/variant/control golden outputs remain unavailable.

## Milestone 6 — Operational isolation and review

- [x] Add an isolated expensive replay workflow gated by the explicit `[run-know-place]` commit marker; it exists only on this feature branch.
- [x] Verify compact CSV/JSON, NPZ diagnostics, source/array hashes, quality-gate accounting, scientific caveats and separate reanalysis artifacts; the latest reanalysis report and summary were remotely verified in Drive.
- [x] Run automated tests, YAML parsing and `actionlint` from the feature branch: **46 tests passed**, all three isolated workflow files parsed, and actionlint passed in [validation run 40015371603](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015371603).
- [x] Keep every Know Place Analysis commit on `feat/know-place-analysis`; no `main` changes or merge were made.
- [ ] Do not merge to `main`. Any later integration requires explicit review and approval.

## Current gate status (updated 2026-10-24)

- **Milestone 0:** complete. Baseline run, source/dashboard artifacts, array/report checksums and findings are saved under `docs/know-place/evidence/`.
- **Milestone 1:** blueprint, method contract and versioned provenance implemented. Live ASF identity gate passes for five candidate products. The official preprint states that its supplement contains scripts, five derived GeoTIFFs, tables and source IDs, but we have not retrieved the actual archive or checksum; retrieval is **UNRESOLVED**, not proof of absence. Exact crown WKT, author variant manifest, control code and golden outputs remain unverified. See `docs/know-place/evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md`.
- **Milestone 2:** scientific kernels and strict synthetic HDF5/geometry/integration tests previously passed 46 tests in the 2026-10-23 validation. Two additional independent known-answer regressions now lock the current 3×3 edge-window and missing-centre behaviour; their post-change workflow result must be checked before marking the new test count validated. YAML/actionlint status before those changes was PASS.
- **Milestone 3:** five raw candidate GOFF HDF5 products were fetched one at a time during [raw replay Run 40006999011](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40006999011); all five historical file-size/SHA-256 identity checks passed, and all five metric records were produced. The later saved-array reanalysis also verified the five NPZ hashes against the source report before computing any new R values.
- **Milestone 4:** per-pair gates, corrected dE/dN/magnitude metrics, 5x5 R and spatial-control diagnostics have been computed. The original run used a too-strict 25/25 neighbour rule; the separate [saved-array R sensitivity reanalysis, Run 40015023621](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40015023621), computes the 1/5/10/15/20/25 sensitivity and does not modify the original run report.
- **Milestone 5:** the target pair gives 0.966 m crown median, 1.722 m mean-vector magnitude and 277.79° azimuth; R=0.869 on a common pointwise 0.17–2.75 m window (150 centres) is close to the paper’s ~0.869 (147 centres). The approximate crown geometry, sample-count differences and exploratory-control mismatch remain material. Our 96.08th-percentile result is **not comparable** to the paper’s 94.7th percentile and must not be treated as a detection.
- **Milestone 6:** isolated raw and saved-array workflows are branch-only; saved-array result/summary retention has passed remote Drive verification. All new commits remain on `feat/know-place-analysis`; no merge or edit to `main` was performed.
- **Paper reproduction:** `BLOCKED_AUTHOR_GEOMETRY_VARIANT_AND_GOLDEN_OUTPUTS_UNVERIFIED`; supplement retrieval unresolved, no author-exact polygon/control/golden parity.
- **Hazard detection:** `NOT_EVALUATED`. Do not report an operational landslide alarm from these results.
