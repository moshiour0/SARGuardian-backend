# Dynamic-AOI Scientific E2E — Checklist

Legend: `[x]` verified in the current default branch/code audit; `[ ]` not complete; `[~]` partly present but not complete for arbitrary AOIs. Do not mark a checkbox complete based on the presence of a source file alone. Link a test/run/commit or report as evidence.

## Phase 0 — Workflow truth and revision safety

- [ ] Audit the complete path from Dynamic API dispatch → backend dispatcher → reusable AOI workflow → product worker → aggregation → signed callback/result ZIP.
- [ ] Replace the stale dispatcher target `@feat/final-aoi-science-integration` only after the same-run workflow contract is verified; ensure the called workflow, manifest, and product worker use one immutable orchestration SHA.
- [ ] Remove or justify the split revision arrangement where the workflow uses a legacy feature branch for discovery/workers and a separate SHA for dashboard generation.
- [ ] Update the signed-callback helper/source pin to the merged reviewed revision or a documented immutable commit; test callback request/status compatibility.
- [ ] Preserve existing GDrive bundle upload and upload-receipt-of-receipt steps; test that a dashboard/science analysis error does not silently skip existing durable products when their policy says upload.
- [ ] Confirm there is no invocation of `sarguardian-extended-science.yml` on arbitrary AOIs; it remains a source-AOI, 33-product extension.
- [ ] Add a regression test that extracts every script invocation from the dynamic workflow and checks the expected science steps are actually wired, not merely present in the science checkout.

## Phase 1 — Context and contracts

- [x] Record workflow audit, pinned revisions, script responsibilities and known real-run limitations in `CONTEXT.md`.
- [x] Define intended processing stages, failure/insufficient-data states and data products in `ARCHITECTURE.md`.
- [ ] Add a versioned JSON schema or typed contract for `science-analysis/analysis-report.json` and `analysis-manifest.json`.
- [ ] Require provenance for all outputs: AOI WKT/hash, dates, selection policy, per-pair ID, track/path/direction, science SHA, units, sign convention, band, mask, source hash and datum method.
- [ ] Separate product-processing status, dashboard-build status and scientific-analysis status in UI/API.
- [ ] Document that source A/B pairs are not cumulative movement; disconnected components have independent zeros; a single LOS direction is not 3-D movement.

## Phase 2 — Evidence inventory and preflight

- [ ] Inventory GeoTIFF exports from each validated product artifact using the manifest/reader receipts, without depending on guessed filenames.
- [ ] Verify each raster's CRS, transform, shape, bounds, pixel posting, band descriptions/units, NoData, AOI-mask evidence, source identity and hash.
- [ ] Validate GUNW LOS/coherence/connected-component band semantics independently from GOFF range/azimuth-offset/correlation layers.
- [ ] Group pairs by product family, processing maturity, mission/path/direction and actual acquisition dates; flag PR/UR duplicates and inconsistent product releases.
- [ ] Check target point is inside the exact AOI polygon and source raster footprint; target-outside is a blocked measurement, not a zero.
- [ ] Create a diagnostic for pixel counts through each gate (finite → AOI → coherence/correlation → connected-component → target window).
- [ ] Choose a documented projected grid for grid alignment; reproject values and masks rather than relabeling CRS; measure the retained AOI and common-pixel counts after alignment.
- [ ] Require a configured stable-reference polygon, or an explicitly labelled provisional relative datum whose stability is not asserted. Fail closed on insufficient common mask (< the pinned algorithm threshold) or target-buffer conflicts.
- [ ] Add unit fixtures for mixed UTM zones, NoData, shifted transforms, bad CRS, zero/low common pixels, target outside AOI, band missing/unknown units and source TIFF immutability.

## Phase 3 — Generic temporal inversion

- [ ] Build a reusable adapter for retained AOI-clipped rasters to the pinned `timeseries.py` pair/network API; do not invoke raw-HDF5 directory mode on TIFF-only input.
- [ ] Preserve one temporal graph per family + physical geometry + layer. Never combine ascending/descending measurements before each is independently inverted.
- [ ] Resolve pair endpoints from source granule metadata and validate against the manifest.
- [ ] Use a shared, evidenced spatial datum for all pair measurements that enter a component; report datum method and spatial support.
- [ ] Build graph components; do not connect disjoint acquisition epochs by interpolation. Store component IDs and each component's reference/zero.
- [ ] Publish pairs, epochs, degrees of freedom, residual RMS, uncertainty and jackknife/single-edge sensitivity.
- [ ] Produce CSV/JSON/PNG series for GUNW and GOFF separately where measurement semantics permit. If a family lacks pairs, record `NOT_AVAILABLE_NO_PRODUCTS`.
- [ ] Add synthetic tests for exact linear motion, zero motion/noise, one bad edge, duplicate pair/release, missing edge, independent components and known recovery within stated tolerance.
- [ ] Add a real-artifact regression that compares only compatible existing source series / validates schema; don't claim a known movement recovered unless independently measured truth supports it.

## Phase 4 — Target-specific floors

- [ ] Invoke `local_floor.py` on the validated per-family exports using actual target coordinates and verified bands/units.
- [ ] Generate one row per pair/layer with target pixel support, date span, local robust floor, bootstrap interval and any block/AOI estimator.
- [ ] Save unusable cases with reasons (`OUTSIDE_AOI`, `NO_DATA_AT_TARGET`, `INSUFFICIENT_LOCAL_PIXELS`, `UNSUPPORTED_BAND_UNITS`, etc.).
- [ ] Match `inverse_velocity.py` floors to the precise observation interval, geometry and layer. Never join floors on dates alone if track/family/product identity differs.
- [ ] Test non-finite/zero/negative/very-large floor values and confirm they block the forecast rather than make the gate easier to pass.
- [ ] Verify all thresholds are expressed in the same unit/sign/measurement component as the observed velocity.

## Phase 5 — Inverse-velocity analysis

- [ ] Run only on a verified cumulative series and pair-specific target floors; never on product medians or a pair-observation playback list.
- [ ] Set an explicit forecast cutoff; assert every fit interval ends strictly before the cutoff for historical backtest.
- [ ] Record all floor-gate exclusions, the number of eligible intervals, the consecutive-window size, acceleration sign, R², horizon and confidence interval boundedness.
- [ ] Add tests for no acceleration, insufficient sample, noise-only series, acceleration with known synthetic failure date, missing floors and future-data leakage.
- [ ] Distinguish `NO_QUALIFYING_ACCELERATION`, `INSUFFICIENT_DATA`, `MODEL_UNRESOLVED` and `CANDIDATE_FOR_REVIEW`; never turn non-detection into an all-clear or a hazard event.
- [ ] Do not enable user-facing operational alarm until the method is calibrated on event and non-event historical holdouts and false-alarm rates are documented.

## Phase 6 — Geometry-aware interpretation

- [ ] Read per-product geometry metadata when available; create a track record with explicit mission, path, direction, look side, incidence/look vector and acquisition policy.
- [ ] Refactor away from assuming the current finite hardcoded track table fits arbitrary AOIs; keep it as a fallback only when its assumptions are explicitly valid.
- [ ] Read elevation/slope/aspect for the actual target; record DEM source/resolution and test sensitivity to stencil size.
- [ ] Reject low-sensitivity and ill-conditioned geometry projections; retain the LOS result when a projected downslope estimate is not valid.
- [ ] Merge tracks only after each track has its own valid time series and references are compatible; propagate uncertainty/covariance.
- [ ] Label outputs as LOS, downslope under terrain assumptions, or E/U decomposition only when sufficient independent look geometry exists.
- [ ] Test the known wrong-look-side regression, one-geometry-only site, low slope, aspect uncertainty and correlated-error cases.

## Phase 7 — Generic scenario/bound separation

- [ ] Refactor current `bound.py` into a parameterized scenario evaluator; keep its 2026 Nepal source-event configuration separate.
- [ ] Require independently sourced event date, reference displacement/rate, candidate region, track/date policy and citations for a benchmark comparison.
- [ ] When no ground-truth scenario is supplied, return `NOT_APPLICABLE_NO_SCENARIO` rather than computing the source event bound on new AOI data.
- [ ] Test candidate outside exact polygon, invalid reference rate, incompatible LOS/downslope units, missing candidate floors and absent independent ground truth.

## Phase 8 — Results, dashboard and app integration

- [ ] Add `science-analysis/` artifacts to `aoi-derived-results.zip` before ZIP finalization and before existing Drive uploads.
- [ ] Ensure manifests distinguish product-selection `manifest.json` from `web-dashboard/manifest.json` and scientific `analysis-manifest.json`.
- [ ] Extend dashboard to show cumulative per-geometry LOS series only when its scientific contract validates; render components separately and show errors/support.
- [ ] Add per-pair floor vs measured velocity plot and guarded inverse-velocity fit with confidence region; avoid fake interpolation.
- [ ] Add geometry sensitivity/limitations panel and show `NOT_APPLICABLE` for current source-event bound on generic AOIs.
- [ ] Expose analysis status through the authenticated owner-scoped API only when the bundle checksum/manifest says the artifact exists and matches.
- [ ] Preserve existing result downloads, Drive links/secrecy, access control, signed callbacks, no-store behavior, checksum validation and safe ZIP member selection.
- [ ] Ensure UI uses separate badges/labels for processing, dashboard and science state; do not signal “alert” from a builder/reader PASS.
- [ ] Test old jobs without new science files, partial jobs, malformed/duplicate manifests, checksum mismatch and owner-access rejection.

## Phase 9 — E2E validation and release

- [ ] Unit and integration suites pass with source script pins verified.
- [ ] Run builder/aggregation tests against synthetic GUNW + GOFF fixtures with multiple CRSs and common/no-common reference cases.
- [ ] Re-run the existing-output dashboard smoke test only for asset compatibility; do not confuse it with a scientific reprocessing run.
- [ ] Confirm private Drive output and upload receipts remain present and verified.
- [ ] Run browser visual / click-through E2E when an approved deployed test environment is accessible; the previous local browser attempt was blocked by the environment and does not count as a pass.
- [ ] After review/merge/deployment, ask the user to dispatch one small, specific, authorized AOI/date validation run; inspect its actual logs, series, floor, uncertainty, ZIP and dashboard route.
- [ ] Test a known independent event and at least one quiet/non-event site before making an “early warning” performance claim.
- [ ] Only after the acceptance evidence exists, consider promoting any scientific signal from “research candidate” to “warning candidate”; operational deployment requires a separate safety/operations review.

## Current acceptance rule

The implementation is not finished until one generic WKT/date run produces either:

1. a validated, provenance-complete, uncertainty-bearing measurement series and all eligible downstream results; **or**
2. an explicit and scientifically correct blocked/insufficient-evidence report with the exact reason, while still preserving useful product maps and downloads.

A green Actions status alone does not satisfy acceptance.
