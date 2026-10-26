# Dynamic-AOI Scientific E2E Integration — Context

**Status:** active implementation plan; this folder is the source of truth for the next scientific-integration phase.  
**Repository:** `moshiour0/SARGuardian-backend`  
**Working branch:** `feat/dynamic-aoi-science-e2e`  
**Science engine pin used by dynamic-AOI product workers:** `moshiour0/SARGuardian@10639a916c9829850775410b3ed7de62e527770d`  
**Rule:** develop and validate on this branch first; never bypass review by committing this work directly to `main`.

## 1. The actual gap

SARGuardian already reads individual NISAR L2 products and produces AOI-clipped, georeferenced displacement/quality rasters. The dashboard work added an interactive spatial presentation of those **per-product observations**.

That is not the same as a validated displacement time series. A product table with a median for each interferogram is not itself cumulative ground movement, and changing a map layer over time does not invert the interferogram network.

The currently dispatched dynamic WKT/date path is:

1. Discover products intersecting the supplied WKT and date window.
2. Run an isolated worker for each selected product.
3. Read GUNW or GOFF with the pinned scientific reader, apply AOI and quality masks, export derived rasters, validate provenance, and preserve the existing retention/Drive flow.
4. Aggregate product reports and clipped rasters into `aoi-derived-results.zip`.
5. Build the interactive map/timeline from these existing outputs.

The dynamic AOI workflow calls `tools/aggregate_aoi_run.py` after the workers. It does **not yet orchestrate the complete measurement-analysis chain** of time-series inversion, target-specific detection-floor estimation, guarded inverse-velocity analysis, and geometry-aware interpretation as one general-AOI result contract.

## 2. Three workflows that must not be confused

### A. Generic WKT/date workflow

- Entry point: `.github/workflows/sarguardian-aoi-wkt-dispatcher.yml`
- Reusable workflow: `.github/workflows/sarguardian-aoi-wkt-dashboard.yml`
- Product worker: `.github/workflows/sarguardian-aoi-product-worker.yml`
- Appropriate for a user-selected WGS84 polygon and date window.
- Current scientific result: per-product reports/raster exports, support/quality diagnostics, and the interactive pair-observation dashboard. The full generic analysis contract still needs implementation.

### B. Source-AOI streaming baseline

- Entry point: `.github/workflows/sarguardian-streaming-batch.yml`
- Uses the committed **source-AOI** product inventory at the older pinned science revision `ab547ecc82bcc4d6ccef545a59852536c2beacc6`.
- `tools/aggregate_streamed_outputs.py` reconstructs source-AOI GUNW/GOFF series from exported GeoTIFFs, runs the pinned supplemental suite and runs event-specific downstream analysis.
- The source baseline is deliberately tied to an inventory of 15 GUNW + 18 GOFF products. Its strict counts and committed source CSVs are not a general WKT implementation.

### C. Extended Scientific Evidence

- Entry point: `.github/workflows/sarguardian-extended-science.yml`
- Input: a successful, artifact-backed `full-source-baseline` run on `main`.
- `tools/resolve_science_source_run.py` intentionally requires `aoi=source`, science revision `ab547ecc...`, exactly 33 products (15 GUNW and 18 GOFF), and validated source-run artifacts.
- `tools/run_extended_science.py` consumes retained derived data rather than re-downloading raw HDF5. It runs supplemental detectability, geometry-sensitivity, DEM/impoundment and candidate-screening work; when the fresh candidate path passes, it runs local floors, a source-specific bound and an inverse-velocity gate.
- This is valuable source-AOI research evidence, **not** the generic new-location processing workflow. Its fixed event date, candidate logic, track assumptions and published comparison must not silently be applied to an unrelated AOI.

## 3. The five requested science scripts

The dynamic worker pins the SARGuardian source revision that contains all five scripts, but the existence of a script in the checkout does not mean the dynamic workflow calls it.

| Script | Scientific job | Required input/guard | General-AOI status |
|---|---|---|---|
| `src/timeseries.py` | Invert pairwise measurements into cumulative LOS displacement per connected acquisition-network component and geometry | Consistent pair measurements/datum, pair identity/date/path, valid-pixel support, and connected network; each disconnected component has its own zero | The dynamic workflow does not currently execute the full inversion; the source baseline has a separate export adapter |
| `src/local_floor.py` | Estimate a local detection/noise floor and bootstrap interval from real clipped rasters at a target or candidate | Valid target inside the exact AOI, enough local pixels, correct band/units, pair span, appropriate family/layer | The algorithm is reusable when the input contract is satisfied |
| `src/inverse_velocity.py` | Test for accelerating creep and optionally estimate a failure-time intercept using a measured cumulative series | Correct time series, compatible per-pair floors, enough consecutive significant intervals, valid fit/CI, and strict no-future-data cutoff | It is not a generic classifier; “no alarm” is a valid scientific result |
| `src/geometry_merge.py` | Evaluate sensor look-direction sensitivity and combine compatible per-track measurements into a downslope/other component series | Correct track/look-side/incidence information and terrain slope/aspect; reject ill-conditioned geometries | Current track table and named-AOI coverage options are not a universal arbitrary-track solution |
| `src/bound.py` | Recompute a specific source-AOI research comparison/bound | Hardcoded 26-Aug-2026 event, historical precursor assumption, source candidate/track dates and source-AOI outputs | **Not generic. Do not run as the final bound for arbitrary locations**; parameterize as a separate scenario evaluator first |

The science source also has `src/common_ref.py`. That is a core prerequisite when a stack needs a consistent spatial datum: it requires a shared lattice and at least 200 common pixels by default, with a buffer around the target. Products that do not share a grid must be explicitly reprojected/aligned under a documented policy before this operation; they must not be aligned by assumption.

## 4. Units and interpretation

- **GUNW:** unwrapped interferometric phase converted by the reader to line-of-sight (LOS) displacement, with coherence/unwrapping-quality gates. Positive sign follows the reader's declared convention; preserve this in metadata.
- **GOFF:** pixel-offset/range-offset measurements, not interferometric phase. The selected GOFF layer and units must be checked from the export metadata; offsets must not be silently treated as GUNW phase or as 3-D displacement.
- LOS is one projection of motion. A single track cannot independently identify full 3-D movement.
- Pairwise medians describe a particular interferogram and its chosen referencing; they must not be labelled cumulative movement without temporal inversion.
- A time-series component is relative to its own datum/first epoch. Never concatenate disconnected components or different look geometries as if they shared a zero.
- `PASS` for acquisition, structural validation, or dashboard generation is not independent geophysical validation and is not an operational landslide warning.

## 5. Concrete evidence to keep visible

The prior inspected real artifact, run [40308665800](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40308665800), contained 10 GUNW products and 0 GOFF products for a Bangladesh custom AOI, not the Nepal validation AOI. All 10 products passed structural validation, but the recorded common-pixel temporal-stack diagnostic had zero complete-series pixels in each reported chain. Its pair medians are not a demonstrated movement trend. The dashboard smoke run [40350998396](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40350998396) proved the viewer can be built from this existing artifact (10 observations / 20 display layers) without rerunning raw processing; it did not prove geophysical accuracy.

These facts are a useful regression fixture, not a successful displacement-detection example.

## 6. Current workflow-revision hazard

At the time of this audit, the default-branch dispatcher called the reusable WKT workflow using `@feat/final-aoi-science-integration`; that workflow also checked out orchestration code from that branch and pinned the dashboard builder separately. This could make the actual launched path differ from the newer implementation merged into `main`.

The implementation phase must change those references coherently: the dispatcher and reusable workflow must execute the same reviewed revision, and every product worker must keep checking out the exact orchestration SHA recorded in its manifest. Never fix a stale reference by silently following a moving branch in the middle of an existing run.

## 7. Required result contract

Each new dynamic AOI run should retain, inside `aoi-derived-results.zip` and expose in the dashboard when valid:

- Exact AOI WKT/hash, requested date interval and filtering policy, source granule IDs, GUNW/GOFF family, processing maturity/release, pinned science SHA, reader settings and source hashes.
- Per-pair valid-pixel counts, quality support, selected band/layer and explicit units/sign.
- Time-series inversion status by family + track + connected component, number of pairs/epochs, datum/reference method, support, fit residuals and uncertainty.
- Target-specific per-pair detection floors and uncertainty only where target support is sufficient.
- Inverse-velocity result as `NOT_EVALUATED`, `INSUFFICIENT_DATA`, `NO_QUALIFYING_ACCELERATION`, `CANDIDATE_FOR_REVIEW`, or another explicit evidence state; never convert a missing fit into a zero velocity.
- Geometry sensitivity status and any rejected/blind track; any combined series must state its terrain-motion assumption and conditioning.
- A separate scientific-analysis status so a valid map still works when an analysis stage is blocked or inconclusive.
- Charts/rasters tied to these verified outputs rather than fabricated interpolation.

## 8. Release gates

1. Contract/tests and workflow reference audit pass.
2. A small, explicitly authorized custom-AOI job creates scientific-analysis outputs or an explicit blocked/insufficient-evidence report.
3. The ZIP checksum/provenance, Drive upload, callback status, dashboard route and legacy download path pass.
4. Independently validate a known event/held-out dataset before using the label “early warning”.
