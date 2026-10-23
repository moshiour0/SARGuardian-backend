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
- [ ] Locate and verify author supplementary scripts/rasters/statistics; preserve original licence and checksums.
- [ ] Pin exact five raw HDF5 product IDs and releases from the paper supplement; do not infer from date alone.
- [ ] Confirm GOFF HDF5 paths, units, sign convention, metadata-grid coordinates and unit-vector sampling against the exact five files and product specification.
- [x] Define a versioned input/output JSON schema and separate structural / method-reproduction / interpretation statuses.
- [x] Define separate WKT masks for the reference box, crown and box-minus-crown; persist crown-WKT SHA-256 and geometry provenance. (An author-exact crown polygon is still outstanding.)
- [ ] Define deterministic spatial-null sample count, PRNG/seed, draw rejection policy and quantile convention; compare these with author scripts before claiming parity.

## Milestone 2 — Implement pure scientific kernels (no downloads in unit tests)

- [x] Unit-test horizontal dE/dN projection against hand-computed vectors including sign checks.
- [x] Unit-test quality gate order, SNR ≥ 5, magnitude ≤ 10 m, reject-not-clip behavior, and per-gate rejection counts.
- [x] Unit-test component-wise background median correction on synthetic arrays with known bias.
- [x] Unit-test crown median magnitude, mean-vector magnitude/azimuth, and day-normalized descriptive rate as distinct statistics.
- [ ] Test 5×5 mean resultant length using known uniform and aligned vectors, edge windows and nodata.
- [x] Unit-test deterministic size-matched control sampling, accepted/rejected draw accounting and empirical percentile.
- [x] Unit-test missing/finite/nodata behavior and explicit failure when background/crown support is empty; test HDF5 attribute and creation-property fill handling without mistaking a default zero for nodata.
- [x] Unit-test missing or duplicate products, wrong track/direction, invalid geometry, unit/CRS mismatches and ambiguous metadata fail closed.

## Milestone 3 — Strict raw GOFF HDF5 reader

- [ ] Find exact layer2 AT, SR, SNR, coordinate vectors, CRS/projection, valid mask and radar geometry datasets.
- [x] Implement geometry metadata interpolation with explicit cube selection, axis/unit/CRS checks and no extrapolation; synthetic schema tests pass. Actual five-product metadata verification remains pending.
- [x] Refuse ambiguous geometry groups, missing fields, non-finite geometry, unit mismatches and out-of-domain interpolation. Confirm actual product sign convention from the five raw files before scientific use.
- [ ] Validate all five products are compatible on the same native grid; do not silently resample.
- [x] Implement source SHA-256 and record granule name, catalog maturity evidence, CRID, exact pair dates, track, direction, polarization and layer in the report.

## Milestone 4 — Paper-method analysis

- [ ] Produce per-pair raw quality-gate count report (finite, SNR, projected-magnitude, crown valid, background valid).
- [ ] Produce corrected dE/dN/magnitude outputs on the source grid.
- [ ] Produce 5×5 R from unit vectors without assuming adjacent pixels are independent.
- [ ] Calculate crown and background medians using documented mask variants.
- [ ] Create deterministic size-matched control distributions for magnitude and R; report accepted and rejected draws and percentile ranks.
- [ ] Examine 19–31 Aug co-event decorrelation / directional disorder so large magnitudes are not mistaken for organised motion.
- [ ] Process every eligible interval; do not choose only pairs that appear to support a precursor.
- [ ] Keep core diagnostic separate and state its selection bias if implemented.

## Milestone 5 — Golden comparison and interpretation

- [ ] Compare the 26 Jul–19 Aug crown median to ≈0.96 m, mean-vector magnitude to ≈1.72 m and direction to ≈278°; explain all differences.
- [ ] Compare crown/background R to ≈0.87 / ≈0.69 and displacement null median to ≈0.14 m where method definitions match.
- [ ] Compare each pre-event interval's null percentile with the author's supplementary results.
- [ ] Reproduce the published interpretation: no pre-event polygon-scale metric passed the 95th-percentile criterion; this is not a calibrated failure detector.
- [ ] If the supplement is unavailable or processing differs, clearly label the exact parity gate BLOCKED/NOT_COMPARABLE rather than PASS.
- [ ] Verify outputs with independent reviewer inspection before claiming reproduction.

## Milestone 6 — Operational isolation and review

- [x] Add an isolated expensive replay workflow gated by the explicit `[run-know-place]` commit marker; it exists only on this feature branch.
- [ ] Verify output artifacts include compact CSV/JSON, geometry and source hashes, per-pair maps, quality-gate accounting and caveats.
- [x] Run automated tests, YAML parsing and `actionlint` from the feature branch: 43 tests passed; both workflows parsed and actionlint passed in [run 40004184248](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40004184248).
- [x] Keep every Know Place Analysis commit on `feat/know-place-analysis`; no `main` changes or merge were made.
- [ ] Do not merge to `main`. Any later integration requires explicit review and approval.

## Current gate status (updated 2026-10-24)

- **Milestone 0:** baseline review and artifact-hash note saved. The downloaded manifest/dashboard ZIP SHA-256 values identify the exact review bundles, not the original HDF5 input bytes.
- **Milestone 1:** blueprint and input/output provenance contract implemented; live ASF identity gate currently passes for five exact candidate granules without downloading raw products. The Research Square/EGUsphere paper's author-supplement raster/script package and exact crown WKT have not yet been independently recovered. The selected CRID variants therefore remain `NOT_VERIFIED_AGAINST_AUTHOR_SUPPLEMENT`.
- **Milestone 2:** isolated pure-kernel and synthetic HDF5/geometry tests pass: **43 passed**.
- **Milestone 3:** strict raw reader and metadata interpolation are implemented and synthetic-tested; exact source HDF5 inspection, signs, grids and product geometry remain pending until the protected five-product replay.
- **Milestones 4–5:** code path is implemented, but raw five-pair metrics have not yet been run. Author-golden parity is explicitly blocked until exact crown geometry and author outputs/variants are verified. No scientific reproduction or hazard-detection claim is authorized.
- **Milestone 6:** isolated CI passes. The raw replay is launched only by an explicit commit marker; Drive secrets and Earthdata credentials must pass preflight, raw bytes/SHA must match the recorded historical files, derived outputs must be durably verified before local raw cleanup. `main` remains unchanged.