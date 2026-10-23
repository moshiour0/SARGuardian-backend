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
- [ ] Save baseline manifest/report/diagnostics under `docs/know-place/evidence/` with hashes or durable artifact references.

## Milestone 1 — Lock method and provenance contract

- [x] Write blueprint with geometry roles, five exact pair dates, equations, filtering, background correction and known limitations.
- [x] Write this evidence-based checklist.
- [ ] Locate and verify author supplementary scripts/rasters/statistics; preserve original licence and checksums.
- [ ] Pin exact five raw HDF5 product IDs and releases from the paper supplement; do not infer from date alone.
- [ ] Confirm GOFF HDF5 paths, units, sign convention, metadata-grid coordinates and unit-vector sampling against the exact five files and product specification.
- [ ] Define strict JSON schema and separate structural / method-reproduction / interpretation statuses.
- [ ] Define masks explicitly: background box, crown, box-minus-crown, and optional core. Persist exact WKT/geometry checksum.
- [ ] Define deterministic spatial-null sample count, PRNG/seed, draw rejection policy and quantile convention; compare these with author scripts before claiming parity.

## Milestone 2 — Implement pure scientific kernels (no downloads in unit tests)

- [ ] Test horizontal dE/dN projection against hand-computed vectors including sign checks.
- [ ] Test quality gate order: finite/required quality → SNR ≥ 5 → projection → reject horizontal magnitude > 10 m; verify a blunder is removed, never clipped.
- [ ] Test component-wise background median correction on synthetic arrays with known bias.
- [ ] Test crown median magnitude, mean vector magnitude/azimuth, and day-normalized descriptive rate separately.
- [ ] Test 5×5 mean resultant length using known uniform and aligned vectors, edge windows and nodata.
- [ ] Test deterministic size-matched spatial sampling and empirical percentile on fixed synthetic arrays.
- [ ] Test the algorithm does not treat missing values as zero and fails on zero/no-valid-pixel inputs.
- [ ] Test single-product/track/polarization mismatch and malformed metadata fail closed.

## Milestone 3 — Strict raw GOFF HDF5 reader

- [ ] Find exact layer2 AT, SR, SNR, coordinate vectors, CRS/projection, valid mask and radar geometry datasets.
- [ ] Interpolate/sampling geometry metadata to the crown grid cell using documented HDF5 geolocation-grid axes, with bounds/unit checks.
- [ ] Refuse ambiguous dataset paths, missing fields, non-finite geometry, unit mismatch, or unverified sign convention.
- [ ] Validate all five products are compatible on the same native grid; do not silently resample.
- [ ] Compute and record source SHA-256, granule name, maturity, CRID, exact pair dates, track direction/number, polarization and layer.

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

- [ ] Add a separate manual workflow on this feature branch only after code/tests are ready; no edits to the current main workflow.
- [ ] Verify output artifacts include compact CSV/JSON, geometry and source hashes, per-pair maps, quality-gate accounting and caveats.
- [ ] Run automated tests and workflow syntax checks from the feature branch.
- [ ] Inspect the commit list to ensure no main-branch changes or unrelated feature scope.
- [ ] Do not merge to `main`. Any later integration requires explicit review and approval.

## Current gate status

- **Milestone 0:** evidence review complete, local evidence bundle persistence pending.
- **Milestone 1:** blueprint/checklist committed; raw field schema, supplementary scripts and exact metadata confirmation pending.
- **Milestones 2–6:** not yet complete. No scientific reproduction claim is authorized.