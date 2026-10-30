# Backend science audit: `tools/aggregate_aoi_run.py`

**Backend dashboard source pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `08956842615cbc88287e33ee4d08834831a64513`  
**Find Displacements use:** executed once after product workers and receipt gate.

## Orchestration responsibilities

- Validates manifest/receipt identity and product metadata.
- Reconciles retained product artefacts and reader reports.
- Calls `run_export_science_diagnostics.py` for GUNW stack and custom-AOI candidate-check status.
- Calls `aoi_wide_displacement_screen.run_aoi_wide_screen(...)` on GOFF exports without target input.
- Separately attempts the GUNW common-reference report and science stage report.
- Records science commit, workflow commit, AOI hash, date window, product counts and limitation statuses in the summary.

If the AOI-wide screen fails, it emits `SCREEN_FAILED`/an explicit error and states that this is not evidence of no displacement. This fail-closed semantic should be preserved.

## Scientific assessment

The aggregator correctly keeps GOFF candidate screening independent from GUNW LOS trend diagnostics; the two are not numerically mixed. It is an orchestrator, not a new estimator. A successful aggregate and a successfully built ZIP do not constitute independent geophysical validation.

## Test coverage

`tools/tests/test_aggregate_aoi_run.py` checks maturity consistency, dashboard metric grouping, exact manifest/reader name matching, layer2 identity and that Find Displacements screening is target-free and family-separated.

## Required additions

- Include output hashes and explicit path/status for every scientific derivative in the summary.
- Assert that each expected screen and stack raster appears in the bundle manifest.
- Promote missing expected map-layer exports to a distinct presentation warning, not science failure or silent omission.
- Preserve GOFF and GUNW family separation and all limitations.

**Verdict:** PASS as an orchestration/data-contract layer; map layer completeness remains a downstream gap.
