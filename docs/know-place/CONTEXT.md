# Know Place Analysis — Living Context (read first)

**Last reviewed:** 2026-10-24  
**Repository:** [moshiour0/SARGuardian-backend](https://github.com/moshiour0/SARGuardian-backend)  
**Working branch:** feat/know-place-analysis  
**Latest CI-validated code/test/workflow baseline:** `5354a344ce19eac652fa8102c790fce18e18ec13` (validation run [40115947045](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40115947045): 217 tests passed in 2.62 s)
**Main baseline (rechecked):** 2218dfeb73353080d8d94bd733d9e7bd9a848886  
**Purpose:** durable handoff for future ChatGPT sessions. Read this file and the linked blueprint/checklist before continuing; update it whenever material code, evidence, decisions, validation status, or blockers change.

## 1. Non-negotiable rules

- All Know Place work stays isolated on feat/know-place-analysis. Never commit, merge, cherry-pick or otherwise write Know Place changes to main.
- The known main-branch baseline supplied for this task is 2218dfeb73353080d8d94bd733d9e7bd9a848886; previous branch validation reported main unchanged. Always verify refs before any operation that could affect them.
- **Do not run a raw GOFF replay/download workflow unless the user explicitly authorizes it using the exact consent marker [run-know-place].** Do not infer authorization from a general request to continue the audit. No raw replay is authorized by this context update.
- Scientific claims are fail-closed. Do not claim paper reproduction, source-data parity, full-footprint reproduction, hazard detection, prediction skill, or operational early warning without direct and suitable evidence.
- Never silently replace or relabel the author-exact first-pair P05023 product as the historical X05026 variant.
- Preserve the licensing boundary in Zenodo DOI https://doi.org/10.5281/zenodo.22730419: the main archive is CC BY 4.0 except the separate extent_CC-BY-NC-4.0 runout outline, which is CC BY-NC 4.0. Do not copy that extent into this repository or treat it as CC BY 4.0.
- Preserve the distinction between displacement-valid pixels, R-valid coherence pixels, P1, P2, polygon-null and displacement-null estimands. Never compare their counts or percentiles as though they measured the same thing.

## 2. Current verified state

### Current Run Workflow entry point

- Default-branch `main` remains unchanged (`2218dfeb73353080d8d94bd733d9e7bd9a848886`). A feature-branch copy of `.github/workflows/sarguardian-aoi-wkt-dispatcher.yml` is registered on `feat/know-place-analysis` so the existing Run Workflow UI path can be used without changing main.
- In Actions, select **SARGuardian AOI WKT E2E (safe branch dispatcher)**, select branch `feat/know-place-analysis`, then choose `author-exact-p05023` for the five-pair author run or `generic-aoi-date` for arbitrary WKT/date measurement.
- The author profile requires exact manual input `[run-know-place]`. It checks Earthdata/Google Drive secrets before download, obtains exactly five P05023 sources, hashes and validates the HDF5s/grids, runs the analyzer, retains derived-only evidence in Drive, verifies remote receipts, then removes temporary raw files only after durable retention is verified.
- The generic profile has `execute_downloads=false` by default. That profile is a no-source-download catalog/series dry run. Set it true only with `[run-know-place]` and working Earthdata + Drive credentials.
- Runbook: `docs/KNOW_PLACE_ANALYSIS_RUNBOOK.md`. Architecture/validation plan: `docs/know-place/REPRODUCIBLE_ENGINE_AND_MULTI_SITE_VALIDATION_20261024.md`. Benchmark registry: `docs/know-place/reference/multi_site_benchmark_v1.json`.
- Multi-site registry is pre-registered but not scored: Bhote Koshi (author-method reproduction target and hazard-discrimination challenge); Samudra Tapu and Bara Shigri (glacier-flow positives); Hubbard and Malaspina (high-speed/speckle challenges); Budhi Gandaki (GUNW cross-product no-precursor challenge). Four non-Bhote site geometries/product IDs remain pending. Budhi Gandaki is not directly comparable to GOFF until a versioned GUNW adapter exists.

### Repository and validation baseline

- Branch exists: feat/know-place-analysis.
- Latest fully CI-validated code/test/workflow baseline: `5354a344ce19eac652fa8102c790fce18e18ec13`.
- Previous baseline validation: [run 40040361146](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40040361146), with 141 tests passed before this correction.
- **Latest CI-validated code/test/workflow baseline:** `5354a344ce19eac652fa8102c790fce18e18ec13` (validation: [run 40115947045](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40115947045)).
- **Latest isolated validation:** [run 40115947045](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40115947045), commit `5354a344ce19eac652fa8102c790fce18e18ec13`. Result: **217 tests passed in 2.62 s**; all eight workflow YAML files parsed, pinned actionlint v1.7.12 checksum and semantic validation passed, and both jobs succeeded. This validates the corrected post-download paper-status contract.
- The validated tree includes separate footprint-screen equations, an array-only per-pixel geometry builder, geometry → dE/dN projection → screen integration tests, fail-closed vertical-reference checks, a public Copernicus GLO-90 terrain-tile acquisition workflow, and a separate exact-author P05023 CMR link/acquisition path. The acquisition workflow downloaded and verified 16 public tiles in [run 40052506016](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40052506016); an independent local replay found their raster values reproduce the archived `terrain/elev_m.tif` to float32 rounding. This does not prove original tile-byte identity or process raw GOFF geometry cubes.
- The geometry builder audit records a material vertical-reference risk: Copernicus GLO-90 is EGM2008-referenced, while the NISAR radarGrid height axis is ellipsoidal. The original author tile bytes remain absent, but current public-mirror tiles were downloaded and their archived preparation recipe reproduced the archived `terrain/elev_m.tif` to Float32 rounding. A separate official-grid experiment quantifies the crown-area ellipsoidal-minus-EGM2008 offset at median −31.7705 m; no correction is applied to the author path. See `docs/know-place/evidence/EGM2008_VERTICAL_DATUM_SENSITIVITY_20261024.md`.
- Earlier catalog-only runs recorded zero source downloads. The later author-exact replay [40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362) downloaded and verified all five exact P05023 payloads, recorded source SHA-256 pins 5/5, and validated grids 5/5. Full receipts: `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- Latest actual raw acquisition/analysis is [run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362), which passed with explicit consent and downloaded/hashed/validated all five P05023 products. Subsequent code-push runs skipped raw acquisition because no new consent input was supplied; raw files were not downloaded again just to refresh the historical artifact.
- Main was rechecked and remains `2218dfeb73353080d8d94bd733d9e7bd9a848886`. The branch remains separate. This current handoff refresh is context-only and does not change code/tests; any future code/test change requires fresh validation.
- Use `.github/workflows/know-place-analysis-validation.yml`, `.github/workflows/know-place-aoi-analysis.yml`, `.github/workflows/know-place-dem-source-acquisition.yml`, and `.github/workflows/know-place-terrain-datum-sensitivity.yml`. The author-catalog gate in `tools/know_place/author_catalog.py` now performs direct exact-ID, AOI/date, and granule-wildcard searches without downloading payloads. Changes to `tools/tests/test_know_place_*.py` trigger isolated validation.
- Do not run the separate expensive raw replay job without [run-know-place].

### Scientific status (must not be relaxed)

- **Paper reproduction:** `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED` (raw source byte identity is pinned 5/5; exact author crown geometry and method parity remain unverified).
- **Hazard detection:** NOT_EVALUATED.
- **Operational status:** blocked; no calibrated risk score or operational alarm.
- Archive integrity/payload audit: pass.
- Exported derived-R band vs recomputation from archived dE/dN: pass.
- Exact author source-byte identity is pinned 5/5. Exact crown-mask parity, full-footprint author-screen replay, terrain vertical-datum resolution, and independent event/non-event validation remain unestablished.

## 3. Author archive: byte integrity and actual contents

User-supplied source: [Zenodo record](https://doi.org/10.5281/zenodo.22730419), “Bhote Koshi 2026 ice–rock avalanche: NISAR L2 GOFF site series and footprint-wide offset-tracking screen — data and code”.

- ZIP: bhotekoshi2026_nisar_data-and-code_CC-BY-4.0.zip
- ZIP size: 183389034 bytes
- MD5: b07b7eb3b3178d3f69d5bca009cb0db4
- SHA-256: 002c2ba173a03693431b79578ca28d6b11e1ec00423d7533e82198871576c5e3
- ZIP integrity: PASS; 90 manifest-listed in-ZIP payloads match declared size and MD5, with zero mismatches.
- Contents include author scripts, five small processed site-field GeoTIFFs, tables/null distributions, the 101-zone inventory and three footprint-screen rasters.
- The ZIP does **not** contain the five raw source GOFF HDF5 granules or the five full-footprint 4230 × 4311 per-pair offset rasters.
- The five exported TIFFs are 80 × 73 pixels, EPSG:4326, three bands (dE, dN, R). This disagrees with the README's stated four-band EPSG:32645 field profile; preserve and report that documentation/profile inconsistency.
- The archive's tables/TableS7_all_validated_zones.csv is byte-identical to the supplied 101-zone CSV after the documented source-byte/line-ending handling. The post-event zone inventory is not an independent prospective validation set.
- Detailed evidence: docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md; reference records: docs/know-place/reference/author_archive_golden_v1.json and author_benchmark_v1.json.

## 4. Critical metric correction — completed 2026-10-24

### What was wrong

An earlier diagnostic incorrectly compared:
- displacement-valid crown cells from tables/nisar_pot_series.json field n; against
- polygon-null coherence-valid crown cells from tables/polygon_null.json field n_px.

These are different estimands. The prior statement that 296 displacement-valid pixels disagreed with 298 R-valid cells was wrong and must not be repeated.

### Independent recomputation on all five exported fields

The archive was read directly. For each field, I recomputed the author's 5 × 5 directional-coherence map using scipy.ndimage.uniform_filter default reflected edges, finite-vector normalization, and finite-support fraction strictly greater than 0.5. I then applied the exact author crown_slice policy using the exported GeoTIFF bounds as extent endpoints. This diagnoses the **exported raster grids only**, not the original GOFF source-grid mask.

| Pair | Displacement-valid crown cells (export / nisar_pot_series.json:n) | R-valid crown cells (export / polygon_null.json:n_px) |
|---|---:|---:|
| 2026-06-20 → 2026-07-02 | 283 / 283 | 302 / 302 |
| 2026-07-02 → 2026-07-14 | 294 / 294 | 299 / 299 |
| 2026-07-14 → 2026-07-26 | 296 / 296 | 302 / 302 |
| 2026-07-26 → 2026-08-19 | 292 / 292 | 298 / 298 |
| 2026-08-19 → 2026-08-31 | 195 / 195 | 202 / 202 |

Results:
- Difference from each corresponding source-table count is zero for all five pairs, for both estimands.
- Full-field recomputed-R finite masks equal archived TIFF band 3 finite masks for all five fields.
- Maximum absolute R-band error across the five fields is 3.4930149217515805e-8, below 1e-6.
- This resolves the former **count comparison** error. It does **not** establish exact pixelwise mask parity on the original GOFF source grid. The original source coordinate vectors/read window and pre-export author masks/rasterization extents are absent; the reason for any source-grid mask difference remains unresolved. **Do not invent a cause.**

Machine-readable per-field details are in docs/know-place/reference/author_archive_golden_v1.json. The benchmark was also corrected to schema v1.1 in docs/know-place/reference/author_benchmark_v1.json: displacement_valid_crown_pixels references nisar_pot_series.json key n; polygon_null_R_valid_crown_pixels references polygon_null.json key n_px; the ambiguous legacy valid_crown_pixels key was removed. Both tools/tests/test_know_place_author_archive.py and tools/tests/test_know_place_author_reference_data.py enforce the separation. Full audit: docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md.

## 5. Exact author source IDs and historical variant warning

The supplied Research Square paper and Supplementary Information identify five ascending T098, L-SAR HH, GOFF layer-2 pairs, all with P05023. The authoritative manifest is docs/know-place/reference/author_benchmark_v1.json.

- 2026-06-20 → 2026-07-02: author P05023 was NOT_FOUND in the earlier ASF-only lookup; collection-scoped CMR later confirmed the producer metadata. Direct raw bytes remain unverified.
- 2026-07-02 → 2026-07-14: P05023; route found.
- 2026-07-14 → 2026-07-26: P05023; route found.
- 2026-07-26 → 2026-08-19: P05023; route found.
- 2026-08-19 → 2026-08-31: P05023; route found.

The historical replay used X05026 for the first pair. Its hash remains valid for those historical bytes only; it is **not** an author-exact source substitute. Four of five P05023 routes do not mean the raw bytes have been downloaded or hashed. Original GOFF source SHA-256 values for the exact author five-product set, especially the first P05023 ID, are not pinned in this archive.

## 6. Author method facts that must remain distinct

Implementation kernels live in tools/know_place/author_parity.py; offline tests live in tools/tests/test_know_place_author_parity.py; processed-field integrity check is tools/know_place/verify_author_fields.py.

- Author site-series geometry uses the nearest radarGrid sample at the stated crown coordinate, then a median of each geometry component over the height axis. The current exploratory runner's fixed-height per-pixel geometry is not equivalent.
- Author source validity gate: finite SNR, SNR ≥ 5, and projected horizontal magnitude ≤ 10 m. Do not add correlationSurfacePeak as a validity gate for this author path.
- Author coherence kernel: 5 × 5 scipy.ndimage.uniform_filter, reflected edges, normalize using finite-vector support, retain finite support fraction > 0.5 (at least 13/25 vectors).
- Author stable-reference correction is applied only if the valid outside-AOI ring has **more than 200 cells**.
- Author P1 crown coherence is calculated **after cropping** to the crown. Full-box/background R and polygon-null R are different estimators.
- polygon_null.py uses a shared RNG sequence with seed 20260907; unique candidate centres sampled without replacement from all finite-R cells; radius sqrt(n_px/pi); accept a disk if at least 60% of target valid cells are present; strict comparisons (draw < crown, draw > box). This is not the same as displacement null, P1, or P2.
- The archive has no standalone displacement_null.py despite a planned reference to it; its output table is present. Exact generator parity for displacement-null cannot be claimed solely from that missing script.

Always label P1, P2, polygon-null and displacement-null separately.

## 7. Event-evaluation leakage, timing and provenance safeguards — updated 2026-10-24

The held-out evaluator is a research scoring contract, not a hazard detector. The event evaluator/threshold selector were hardened and CI-tested in the current code/test tree:

- Registry canonicalization rejects one exact canonical WGS84 AOI ring assigned to multiple site IDs inside the same registry.
- The held-out evaluator rejects any site ID overlap and any exact canonical AOI-ring overlap between validation and test splits, including reversed polygon winding or rotated starting vertex. It reports disjoint site/geometry split counts.
- A supplied `first_alarm_time_utc` is only allowed for `ALERT` and must fall within the declared observation window; `NO_ALERT`/`NO_RESULT` cannot claim an alarm timestamp.
- Threshold policy schema is now `know-place-frozen-threshold-policy/1.1`; validation score and prediction payload schemas are now `know-place-validation-scores/1.1` and `know-place-event-predictions/1.1`.
- Threshold CLI requires a `know-place-detector-policy/1.0` manifest and hashes the exact file bytes. The model-policy hash is included in the frozen threshold, validation score payload, and held-out prediction payload; mismatched hashes are rejected.
- Each validation-score and prediction case carries `source_product_sha256s`, which must match the source-product hashes declared by the corresponding registry case. The evaluation report hashes the prediction payload and records `PASS_ALL_CASE_SOURCE_HASHES_MATCH_REGISTRY` after consistency checks.
- Regression tests exercise model-policy mismatch, source-product hash mismatch, exact geometry leakage, repeated AOI under different site IDs, and contradictory/out-of-window alarm timestamps.

**Limit of these protections:** they validate declared manifests/hashes and cross-file consistency. They do not prove that the claimed implementation actually ran on precisely those source bytes; that needs an independently captured run attestation/receipt tying runtime, code revision, inputs and outputs. Exact geometry matching also does not detect all partial AOI overlaps or nearby spatial leakage. Those must be handled by a spatial buffer/separation audit before independent-site validation is credible.

These changes do not change scientific status: `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; `HAZARD_DETECTION_STATUS=NOT_EVALUATED`.

## 8. Author footprint-wide candidate-screen kernel — added 2026-10-24

Added `tools/know_place/footprint_screen.py` and `tools/tests/test_know_place_footprint_screen.py`, adapted with attribution from the Zenodo archive's `code/wide_screen.py` (SHA-256 `60e4238b9a10510f52a4673939a9708bf513d8bae460ba797d2dd27a1357d7c9`) and `tables/TableS6_screen_params.json` (SHA-256 `85743e828c4d684046acf43bdb0bfbc8b8c194626aacad8fd58e154e925d8e76`). Full notes: `docs/know-place/evidence/AUTHOR_FOOTPRINT_SCREEN_KERNEL_AUDIT_20261024.md`.

The pure-array kernel keeps this estimator separate from the crown/site-series path and includes:
- Per-pixel AT/SR formula dE = AT*cE + SR*kE; dN = AT*cN + SR*kN. The footprint screen requires verified per-pixel coefficients; a separate array-only builder in `tools/know_place/footprint_geometry.py` interpolates supplied geometry cubes/DEM to produce them. It does not read/hash HDF5 or DEM files and has not been run on the exact author raw inputs.
- SNR >= 5 and projected magnitude <= 10 m gate; float32 local mean with reflected default edges and support fraction strictly > 0.15.
- 41-pixel local magnitude anomaly; scale is local mean absolute anomaly with 0.05 m floor; 5x5 residual-vector coherence requires finite direction support > 0.5.
- Same-pair screen requires z >= 4, anomaly >= 0.50 m and residual R >= 0.75. Candidate cell must flag in >=2 of five exact author intervals. Candidate connected components use scipy.ndimage.label default four-connectivity and minimum 10 cells.
- Result status remains `hazard_detection_status=NOT_EVALUATED`.

CI [run 40049074686](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40049074686) passed 164 tests including the newly explicitly wired footprint test. This establishes synthetic equation/policy checks only; it does not execute the original script, process exact author GOFF products, verify the 4230 x 4311 grid, create geometry coefficients, recreate author GIS outputs or validate detection skill. The archive's three screening rasters do not replace the missing five raw GOFF HDF5 inputs/full-footprint per-pair offset rasters. The first author P05023 input remains NOT_FOUND; do not substitute X05026. Active glaciers dominate the author screen's own candidates; it is a movement screen, not a failure prediction.

## 9. Author per-pixel geometry builder and vertical-reference risk — updated 2026-10-24

Added `tools/know_place/footprint_geometry.py` as an array-only implementation of the archived `code/geometry.py` interpolation recipe. It uses supplied radarGrid height/y/x axes and five geometry cubes, supplied warped DEM elevations, linear `RegularGridInterpolator((height, y, x), ..., bounds_error=False, fill_value=None)`, source-method median fill for DEM nodata/nonfinite cells, height-axis clipping, and coefficient equations `cE=alongTrackUnitVectorX`, `cN=alongTrackUnitVectorY`, `kE=-(losX/hypot(losX,losY))/sin(incidence)`, analogous `kN`. It reports XY extrapolation and nonfinite coefficients.

Horizontal CRS and exact affine-grid agreement are checked. Vertical references must now be explicitly declared; differing reference strings are rejected by default. An explicit source-reproduction override can preserve the author code's direct-use behavior, but report fields state that no vertical transformation was applied and the output is not datum-corrected.

Verified archived DEM facts: `terrain/elev_m.tif` SHA-256 `d593f74142d930fb3f1f4a320950019f318842f933f4da64139ea4e214ecd8a1`, MD5 `a5451bac63051bdf36ed2bde6acca7cc`, 59,400,495 bytes, 4,311 × 4,230 Float32 cells, EPSG:32645, 80 m transform, all 18,235,530 cells finite, values 77.5–8,146.092 m, median 4,674.589 m. All three archived footprint screen rasters share the same 4,311 × 4,230 horizontal grid. These profile checks do not establish datum compatibility.

**Unresolved datum caveat — now quantified in a separate experiment:** Copernicus GLO-90 specifies EGM2008 height, while NISAR's radarGrid `heightAboveEllipsoid` axis is ellipsoidal. In [datum-sensitivity run 40053719232](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40053719232), the selected PROJ/NGA 2.5-arc-minute grid operation (grid SHA-256 `4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a`) gives a median ellipsoidal-minus-EGM2008 offset of −31.7705 m across the 323 cells in the published crown rectangle. This is a separate experimental DEM; the author reproduction path has **not** been modified. The original author tile bytes and raw GOFF geometry cube remain unavailable, so coefficient-map sensitivity is still uncomputed. See [full datum sensitivity audit](evidence/EGM2008_VERTICAL_DATUM_SENSITIVITY_20261024.md).

Validation run [40050020868](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40050020868) passed 176 tests, four workflow YAML parses and actionlint. Raw replay [40050020872](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40050020872) skipped the five-pair analysis for lack of `[run-know-place]`.

### Additional terrain-source acquisition and raster replay — 2026-10-24

The isolated public-data workflow `.github/workflows/know-place-dem-source-acquisition.yml` downloaded sixteen Copernicus GLO-90 GeoTIFF tiles covering 83–87°E, 27–31°N, and recorded per-tile SHA-256 hashes and raster-profile checks. Successful acquisition: [run 40052506016](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40052506016); artifact ZIP digest from GitHub is `sha256:0499832696ccf4dbda584a848f6373771c498b168232b3acc486576c2bda26f8`. Full tile hash ledger is `reference/copernicus_glo90_current_manifest_20261024.json`; replay evidence is `evidence/COPERNICUS_GLO90_SOURCE_TILE_REPLAY_20261024.md`.

Using those tiles, the archived `code/prep_terrain.py` mosaic → bilinear reproject recipe reproduced `terrain/elev_m.tif` on the exact archived 4311 × 4230 EPSG:32645 80 m grid: all 18,235,530 target cells were finite in both rasters, finite masks were identical, 18,235,529 cells were bitwise-identical Float32 values, the only difference was 0.000244140625 m, and RMSE was 5.717166719e-8 m. This supports that the archived elevation grid contains current public GLO-90 values resampled as in the source code. It does **not** establish byte identity of the original 16 author input files. The source script contains horizontal warp/resampling but no visible vertical datum operation; the EGM2008 ↔ ellipsoidal-height discrepancy remains unresolved, and no correction has been applied. Raw GOFF download remains separately gated.
### EGM2008 vertical datum sensitivity — separate experiment, 2026-10-24

- Workflow: [run 40053719232](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40053719232), artifact `know-place-egm2008-vertical-datum-sensitivity-40053719232-1`, SHA-256 `4defe3a608e8514ce76d22f948264fd9aa806fb286a7aa413ea384756d39a13c`.
- Official PROJ/NGA grid SHA-256 `4191d471eefebf24091b56dbc604353cb3b8cf8cc70e448bb9ae56a272bef17a`; selected EPSG:9518 → EPSG:4979 grid operation, declared accuracy 0.113 m; ballpark/no-op rejected.
- Across all 18,235,530 cells, signed offset median −30.1587 m and range −67.0417 to −24.2041 m. In the published crown rectangle, 323 cells yield median −31.7705 m (range −31.9634 to −31.5728 m).
- Archived prepared DEM replay still matches current public GLO-90 inputs on the exact 80 m target grid: finite masks identical, 18,235,529 / 18,235,530 float32 cells bitwise equal, maximum difference 0.000244140625 m, RMSE 5.71717e−8 m.
- The height conversion is experimental and **not** used by the author reproduction path. Original terrain tile byte identity is unknown, raw GOFF geometry is still missing, and `cE/cN/kE/kN` impact is not yet computed. Audit: `docs/know-place/evidence/EGM2008_VERTICAL_DATUM_SENSITIVITY_20261024.md`; machine-readable summary: `docs/know-place/reference/terrain_vertical_datum_sensitivity_20261024.json`.

### Extended author P05023 catalog audit — 2026-10-24

ASF exact-ID/AOI-date/wildcard queries did not find first author P05023 and only exposed X05026 as the same-interval candidate. A follow-up collection-scoped NASA CMR lookup resolved catalog identity: exact P05023 producer ID in collection `C2854341702-ASF`, concept ID `G4248299988-ASF`, with producer-ID and readable-name filters both returning HTTP 200 / one record each. All five author IDs now have catalog identity confirmations, but none has a source-byte SHA-256; paper reproduction remains blocked. See `docs/know-place/evidence/CMR_AUTHOR_P05023_EXACT_CATALOG_RESOLUTION_20261024.md`; validation [40056005969](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005969) passed 191 tests.

### Latest exact-source catalog resolution — 2026-10-24

NASA CMR confirms the exact first-pair P05023 record in collection `C2854341702-ASF`: granule concept `G4248299988-ASF`, exact producer granule ID, and CMR update timestamp `2026-07-15T16:07:07.506Z`. The collection-scoped producer-ID and readable-name queries each returned HTTP 200 / one result. This corrects the earlier ASF-only `NOT_FOUND`; it does not prove source-byte identity. Catalog identity is now 5/5, source hashes remain 0/5, and raw source downloads remain 0. Exact HDF5 URL and metadata: `docs/know-place/evidence/CMR_AUTHOR_P05023_EXACT_CATALOG_RESOLUTION_20261024.md`. Validation [40056005969](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005969) passed 191 tests.

## 10. Design blueprint and validation gates

Read these before implementing further changes:
1. [Scientific architecture blueprint](../KNOW_PLACE_ANALYSIS_BLUEPRINT.md)
2. [Engineering & scientific checklist](../KNOW_PLACE_ANALYSIS_CHECKLIST.md)
3. [Isolated runbook](../KNOW_PLACE_ANALYSIS_RUNBOOK.md)
4. [Multi-event validation plan](validation/MULTI_EVENT_VALIDATION_PLAN.md)
5. [Author-supplement retrieval audit](evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md)
6. [Raw replay and R-policy audit](evidence/RAW_REPLAY_40006999011_R_POLICY_AUDIT.md)
7. [Zenodo author archive audit](evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md)
8. [Footprint-wide screen-kernel audit](evidence/AUTHOR_FOOTPRINT_SCREEN_KERNEL_AUDIT_20261024.md)
9. [Footprint geometry builder and vertical-datum audit](evidence/AUTHOR_FOOTPRINT_GEOMETRY_BUILDER_AUDIT_20261024.md)
10. [Author archive golden/reference fixture](reference/author_archive_golden_v1.json)
11. [Offline regression test](../../tools/tests/test_know_place_author_archive.py)
12. [Isolated validation workflow](../../.github/workflows/know-place-analysis-validation.yml)
13. [Exact-author acquisition workflow audit](evidence/AUTHOR_EXACT_ACQUISITION_WORKFLOW_AUDIT_20261024.md)

Promotion gates from the multi-event validation plan:
- **G0 structural:** schemas, exact identity metadata, hashes, grid checks and synthetic known-answer tests.
- **G1 measurement:** vector projection/sign/units, source masks, georeferencing and provenance independently verified.
- **G2 paper parity:** exact raw source IDs/bytes, author geometry/method, pixelwise/summarized golden comparisons.
- **G3 external validation:** independently labelled event and non-event cohort, held-out evaluation, uncertainty and false-alarm reporting.
- **G4 operational research pilot:** terrain-backed geometry, cadence/latency, drift, no-result behavior and human review.

Current state: archive integrity and exported derived-R verification pass; the correction above resolves count-estimand bookkeeping. Full source input and author-method parity are still **BLOCKED** (below G2), G1 remains partial, G3/G4 are blocked, and hazard detection remains **NOT_EVALUATED**.

## 11. Next actions — continue in this order

- [x] Inspect blueprint, checklist, runbook, source/validation audits, author archive fixture, author kernel and archive verifier.
- [x] Recompute displacement-valid and R-valid crown counts independently from all five exported fields and separate the two estimands in machine-readable evidence.
- [x] Correct both the author-archive diagnostic and benchmark fixture so displacement-valid n and polygon-null R-valid n_px are separate. CI passed in [run 40043977505](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40043977505), with 141 tests, four workflow YAML parses and actionlint passing. The ASF job downloaded zero products; the raw-replay job was skipped for lack of explicit consent.
- [x] Extend same-estimand comparison of archived per-pair tables and raster statistics; keep P1/P2/polygon-null/displacement-null separate. See `docs/know-place/evidence/AUTHOR_PROCESSED_FIELD_TABLE_PARITY_20261024.md` (120/120 checks; exported fields only).
- [ ] Continue integrating the isolated author-parity path, always testing against archived processed fields/tables without silently changing the exploratory runner.
- [x] Resolve, download and SHA-256-pin the five exact author P05023 GOFF HDF5 inputs; all five passed HDF5 identity and 4311 × 4230 EPSG:32645 / 80 m grid validation in [run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362). Do not substitute X05026.
- [x] Run the consent-gated source replay and review the source hashes, five-pair metrics and remote Drive receipts; evidence is `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- [ ] Verify the author-supplement crown geometry/control sampling, golden tables/masks and full-footprint author screen outputs.
- [x] Extract and test the author footprint-wide candidate-screen equations in a separate module; synthetic kernel tests included in CI. See `docs/know-place/evidence/AUTHOR_FOOTPRINT_SCREEN_KERNEL_AUDIT_20261024.md`.
- [x] Add an array-only per-pixel coefficient builder with synthetic tests and geometry-to-screen integration; horizontal CRS/affine and vertical-reference mismatch guards are explicit. See `docs/know-place/evidence/AUTHOR_FOOTPRINT_GEOMETRY_BUILDER_AUDIT_20261024.md`.
- [x] Download and SHA-256-pin all 16 current public Copernicus GLO-90 tiles for the terrain bbox and independently recreate the archived `terrain/elev_m.tif` warp. See `docs/know-place/evidence/COPERNICUS_GLO90_SOURCE_TILE_REPLAY_20261024.md` and `docs/know-place/reference/copernicus_glo90_current_manifest_20261024.json`. This is raster-value parity, not original input-file byte parity.
- [ ] Obtain the author's original 16 terrain-tile hashes/copies or exact delivery version, and resolve/quantify EGM2008-to-ellipsoid height conversion before asserting correct GOFF geometry coefficients. The archived source appears to use EGM2008 elevations directly against `heightAboveEllipsoid` with no visible vertical conversion; no correction has been applied.
- [x] Downloaded and SHA-256-pinned the five exact author-published GOFF HDF5 inputs in run 40114703362; all passed identity and common-grid validation. [ ] Verify geometry-axis interpretation, units/sign conventions, exact crown mask and full-footprint outputs against an author reference. Do not substitute X05026.
- [ ] Recreate full-footprint outputs from documented exact sources and author method; archived full-footprint per-pair offset rasters are absent. The exact-source site-ROI replay is complete, but the full-footprint parity check remains pending.
- [ ] Assemble an independently labelled event/non-event registry, perform explicit partial-overlap/spatial-buffer auditing, and run held-out evaluation under the pre-registered multi-event plan. The 101-zone post-event inventory is not a prospective holdout. Hash checks validate declared provenance consistency, not proof of actual execution; add trusted run attestation before relying on production evaluation.

## 12. Update protocol for future chats

When continuing from a new chat:
1. Read this file first, then KNOW_PLACE_ANALYSIS_BLUEPRINT.md, KNOW_PLACE_ANALYSIS_CHECKLIST.md, and the relevant evidence report.
2. Verify the current branch head, main SHA, and latest validation run; do not assume SHAs/results remain current.
3. Inspect the exact current files and their diff before editing; do not reapply old fixes blindly.
4. Keep an evidence ledger: what ran, inputs/hashes, output hashes, tested commit SHA, CI run URL, and any skipped expensive jobs.
5. Update this file as part of the same branch-only work whenever a scientific decision, blocker, code path, test or validation state changes.
6. Never mark a checklist item complete unless inspectable evidence supports the exact claim.


## 13. Exact-author acquisition workflow and latest CI — 2026-10-24

Current branch head at the start of this update: 2fddad5fbd3d66fc9ade40da41ce829bfabf7610. Main remains unchanged at 2218dfeb73353080d8d94bd733d9e7bd9a848886. The workflow/runner audit is in docs/know-place/evidence/AUTHOR_EXACT_ACQUISITION_WORKFLOW_AUDIT_20261024.md.

- Validation run [40058988024](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988024): 204 tests passed in 4.87 s, seven workflow YAML files parsed, actionlint v1.7.12 checksum and semantic validation passed.
- Live catalog workflow resolved exactly five author-P05023 direct HDF5 data URLs: AUTHOR_CMR_CATALOG_GATE=PASS, AUTHOR_EXACT_PRODUCTS_CONFIRMED=5/5, AUTHOR_EXACT_CMR_DATA_URLS_CONFIRMED=5. The metadata artifact is know-place-author-exact-live-cmr-access-evidence (SHA-256 digest b81e1d2b1ba4c78a90753ed84fd1ff1da0ff72c886bf46f31ffdd99928a1c4e9); the artifact records accessible link evidence, not source payload hashes.
- The source payload count is still 0/5 and source SHA-256 count 0/5. Direct URL resolution is not byte acquisition, HDF5 validation, or paper-method parity.
- The new .github/workflows/know-place-author-exact-replay.yml is manual-dispatch-only for raw work; it requires the exact consent input [run-know-place] and checks Earthdata and Drive credentials before download. The latest dispatch-shaped workflow run had no consent input, so its acquisition job skipped. The legacy X05026 replay also skipped. No raw source was downloaded in this turn.
- The GitHub connector used for this task can inspect runs and update branch files but has no workflow-dispatch operation. Therefore manual dispatch was not initiated from this session. To execute the raw download, open the exact-author workflow in the Actions tab, choose Run workflow, enter [run-know-place] in consent_marker, and ensure the Earthdata and Google Drive secrets are configured. The workflow will record size/SHA-256, validate HDF5 identity/grid, analyze, retain derived-only outputs in Drive, and only delete temporary raw files after verified Drive receipts.
- Scientific state remains PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED and HAZARD_DETECTION_STATUS=NOT_EVALUATED. Do not treat this as a hazard detector.


## 14. Prior post-documentation CI confirmation — 2026-10-24

Validation run 40059962163 tested the integrated audit/checklist commit 5901c10c2bb38379acd23c0a0e2c01952c4e7d1e: 204 tests passed in 6.56 s, seven workflow YAML files parsed, and actionlint v1.7.12 checksum plus semantic validation passed. Both validation jobs succeeded. Live metadata logs report AUTHOR_CMR_CATALOG_GATE=PASS, AUTHOR_EXACT_PRODUCTS_CONFIRMED=5/5, AUTHOR_EXACT_CMR_DATA_URLS_CONFIRMED=5, SOURCE_DOWNLOADS=0. Artifact `know-place-author-exact-live-cmr-access-evidence` (ID 12546952625; 4,117 bytes) has SHA-256 digest `7b91d3db92422d1e39f3412e1318b1455dc87aeb1e8677897339ee24f459dbb7`; the ZIP was downloaded and independently integrity/hash checked.

Legacy push run 40093380207 skipped raw analysis, and exact-author workflow run 40058988016 skipped its acquisition job because the exact consent input [run-know-place] was absent. Raw source payload count remains 0/5, raw SHA-256 count remains 0/5, paper reproduction remains blocked, and hazard detection remains NOT_EVALUATED. The available GitHub connector has no workflow_dispatch operation, so no manual dispatch occurred from this session. A user must open the exact-author workflow in GitHub Actions, choose Run workflow, enter [run-know-place], and ensure Earthdata and Drive secrets are configured. Main remains unchanged at 2218dfeb73353080d8d94bd733d9e7bd9a848886.

## 15. Latest exact-author CMR artifact independently verified — 2026-10-24

The latest complete validation is [run 40093352981](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40093352981), testing commit `87dce99f5f20b7e02c46d8e5a168c4c877d8a3d2`: **204 tests passed in 4.73 s**, all seven workflow YAML files parsed, and actionlint v1.7.12 checksum plus semantic workflow validation passed. The exact-author artifact `know-place-author-exact-live-cmr-access-evidence` (ID `12559877337`, 4,118 bytes) was downloaded and ZIP integrity checked; its SHA-256 `20929525a6d20e4011563d23ddde16d1144b5f4afbad44505b54c220c42e8897` matches GitHub's artifact digest.

The live manifest confirms all five author P05023 product IDs and exact HDF5 URLs. For each product, both `producer_granule_id[]` and `readable_granule_name[]` queries returned HTTP 200 / one exact record. Counts: CMR identities 5/5; data URLs 5/5; blocking products 0; raw source downloads 0; source SHA-256 pins 0/5. Raw source identity is still unverified; paper reproduction remains blocked and hazard detection remains not evaluated.

Latest legacy raw-replay run [40060195873](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40060195873) completed only its decision job and skipped analysis. Dedicated author-exact workflow run [40058988016](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40058988016) also skipped because the exact manual input `[run-know-place]` was absent. No raw GOFF payload was downloaded. This session's available GitHub connector has no `workflow_dispatch` operation; actual replay must be manually initiated in Actions after confirming Earthdata and Drive secrets. Main remains `2218dfeb73353080d8d94bd733d9e7bd9a848886`.


## 16. Follow-up verification — 2026-10-24 (latest branch head 85bbda3)

- Latest isolated validation remains [run 40102959304](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40102959304), on commit `cc0f2d101c717e80f4abcf2d9ace1479dc1168d2`: **213 tests passed**, all eight Know Place workflow YAMLs plus the branch dispatcher parsed, and actionlint v1.7.12 checksum/semantic checks passed.
- The latest exact-author live CMR artifact from that run is `know-place-author-exact-live-cmr-access-evidence`, artifact ID `12562589832`, size 4,117 bytes. I downloaded it, checked ZIP integrity, and independently calculated SHA-256 `65e65ae2c4dec384c50ca5a8877e69b705a1861c1e85312026d62512c5dd9386`, matching GitHub's artifact digest. Its manifest confirms all five exact P05023 producer IDs, five direct HTTPS HDF5 links on `nisar.asf.earthdatacloud.nasa.gov`, and exact collection-scoped CMR identities. This is catalog/link evidence only: `source_downloads=0`, source payload SHA-256 values remain 0/5.
- Latest branch push run [40103092615](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40103092615) passed the no-download decision gate and skipped the expensive five-pair analysis job because the exact `[run-know-place]` input was not supplied. The exact-author raw replay workflow has not been manually dispatched with consent. No raw GOFF payload was downloaded in this follow-up.
- I rechecked the active GitHub connector capabilities: it supports reading runs/artifacts and branch-file updates, but exposes no workflow-dispatch API. I cannot truthfully claim to have clicked **Run workflow** or launched the raw job from this session. The remaining operational step is to open the branch-specific dispatcher in Actions, select branch `feat/know-place-analysis`, choose `author-exact-p05023`, enter the exact marker `[run-know-place]`, and ensure Earthdata and Google Drive secrets are configured. This marker is required before raw HDF5 acquisition.
- Scientific status remains `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED` and `HAZARD_DETECTION_STATUS=NOT_EVALUATED`. Do not substitute `X05026` for author `P05023`; do not merge to main.
- Main was rechecked at `2218dfeb73353080d8d94bd733d9e7bd9a848886`; it remains untouched. Working branch head before this context-only update: `85bbda3294f2305e6e5a706bde003a5360d49931`.


## 17. Dispatcher consent failure and fix — 2026-10-24

Failed run [40107037642](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40107037642) stopped in the first consent gate. Log evidence is CONSENT_MARKER=run-know-place; the required exact value is [run-know-place]. Both raw-processing jobs were skipped; source downloads, analysis and Drive upload were not started. This was a consent-input mismatch, not a data/science failure. The dispatcher now states the exact correction in the log and step summary; a regression test keeps the bracket requirement strict. Full audit: docs/know-place/evidence/DISPATCHER_CONSENT_MISMATCH_20261024.md. Main remains unchanged.


## 18. Main-branch downloader/retry audit and author-exact failure — 2026-10-24

- Main baseline was rechecked at `2218dfeb73353080d8d94bd733d9e7bd9a848886`. The last integration merge is `5465efdaba097581e1b6973e638360b4d0de1e13`; the retry policy was deliberately reduced to one attempt in `05cbecea1c3728a0820131690fd085eb3a92cce1`.
- The proven main worker carries `EARTHDATA_TOKEN`, `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`, `GOOGLE_DRIVE_OAUTH_CLIENT_JSON`, `GOOGLE_DRIVE_REFRESH_TOKEN`, `GOOGLE_DRIVE_PARENT_FOLDER_ID`; run metadata includes `PRODUCT_ID`, `GRANULE_NAME`, `PRODUCT_TYPE`, `MATURITY`, `EXPECTED_SOURCE_BYTES`, `DRIVE_VERSION_TAG=${{ github.run_id }}-${{ github.run_attempt }}`, `AOI_NAME`, `SCIENCE_COMMIT`, `RETENTION_PROFILE`, and `PRODUCT_EXECUTION_LABEL`. Main uses one whole-product attempt per worker (90-minute step timeout), and receipt-gated targeted retry `execution_label=retry-1` only when receipts are missing/invalid. The worker does not repeatedly download a failed large product four times.
- Author-exact dispatcher run [40107851266](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40107851266) successfully authenticated and completed the first exact P05023 HDF5 transfer: `1,090,519,040` bytes. It then falsely rejected the product because GOFF parser identity includes `.h5`, while CMR `granule_name` omits the extension. This is an implementation comparison bug, not an Earthdata authentication or network download failure.
- Fix: compare the parsed HDF5 filename to the exact source filename, separately compare its stem to the extension-free CMR granule ID, and save byte count/SHA-256 before grid validation. Failure receipts now distinguish downloaded+hashed payloads from grid-validated products. Retry is limited to one separately labeled `retry-1` phase for retryable network/HTTP failures; schema/identity/grid failures do not trigger an expensive redownload.
- The failed run had no durable source hash before this correction; its temporary HDF5 was removed only after the derived artifact and both Drive receipts were remotely verified. So no source hash from that run is claimed. The corrected code has regression tests for the extension mismatch, wrong release/CRS, and separate byte/hash vs grid-validated counts.
- Scientific result remains `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`, `HAZARD_DETECTION_STATUS=NOT_EVALUATED`. Do not treat this first source-transfer test as a completed analysis. No changes to `main`.


## 19. Main download/retry variables adopted and byte/grid receipt fix verified — 2026-10-24

- Main is unchanged at `2218dfeb73353080d8d94bd733d9e7bd9a848886`. Reference history: merge `5465efdaba097581e1b6973e638360b4d0de1e13`; one-attempt downloader policy `05cbecea1c3728a0820131690fd085eb3a92cce1`.
- The author-exact workflow now uses the main pipeline's Earthdata and Drive secret names: `EARTHDATA_TOKEN`, `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`, `GOOGLE_DRIVE_OAUTH_CLIENT_JSON`, `GOOGLE_DRIVE_REFRESH_TOKEN`, and `GOOGLE_DRIVE_PARENT_FOLDER_ID`. It also records `DRIVE_VERSION_TAG=${{ github.run_id }}-${{ github.run_attempt }}`, `RUN_ID_SAFE`, `PRODUCT_EXECUTION_LABEL`, `RETENTION_PROFILE=derived-only`, `SCIENCE_COMMIT=10639a916c9829850775410b3ed7de62e527770d`, `PRODUCT_ID`, `GRANULE_NAME`, `PRODUCT_TYPE=GOFF`, `MATURITY=PROVISIONAL`, `EXPECTED_SOURCE_BYTES`, and `RAW_DIR`. The pinned scientific checkout is explicitly verified before analysis.
- Download retry policy now mirrors the main worker's intent: one transfer attempt per worker phase (`max_attempts=1`), one separately labeled `retry-1` phase only for failures classified retryable, bounded `min(15 * 2^(phase-1), 120)` sleep, and no repeated download for HDF5 identity/grid-validation failures. Drive upload and receipt-upload verification remain required before deleting temporary raw source.
- Fixed the false `RAW_HDF5_NOT_EXACT_AUTHOR_GRID_OR_INTERVAL` reject: the GOFF parser returns a basename including `.h5`, while CMR's `granule_name` is extension-free. Identity validation now checks the exact filename and stem separately, plus release/date/CRS. New offline tests cover this suffix bug, reject X05026/wrong CRS, and ensure downloaded+hashed source counts are separate from grid-validated count.
- A completed transfer now records byte count/SHA-256 before HDF5 and grid validation. Failure manifests distinguish `source_downloads`, `source_sha256_count`, and `source_products_grid_validated`; an HDF5 or grid-validation failure cannot be misreported as though no bytes were transferred. The failed run [40107851266](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40107851266) had transferred the first P05023 payload (1,090,519,040 bytes) before the old string comparison rejected it, but it did not save a durable hash receipt; its temporary raw file was removed only after derived output and Drive receipt verification. No hash is claimed for that old run.
- Validation [40109194403](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109194403) passed 217 tests in 3.25 s; eight workflow YAML files parsed, and actionlint v1.7.12 checksum/semantic checks passed. The subsequent receipt-order hardening is tested in [40109347836](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347836): **217 tests passed in 5.73 s**, eight YAML files parsed and actionlint checks passed. The live CMR job confirms 5/5 exact-author P05023 HDF5 URLs; metadata-validation payload downloads remain 0.
- Raw replay run [40109347847](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347847) skipped the acquire/analyze job because the exact `[run-know-place]` consent marker was absent. No raw replay was run on this follow-up. Paper reproduction remains `BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; hazard detection remains `NOT_EVALUATED`. Do not rerun the raw replay until the exact marker is deliberately supplied, and do not merge to main.


## 20. Latest live CMR artifact integrity and raw-run status — 2026-10-24

- Latest validation [40112970146](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112970146) tested commit `bc0913a203511879dc6ba6d101f04194bd307383`: **217 tests passed in 4.99 s**; eight workflow YAML files parsed; pinned actionlint v1.7.12 checksum and semantic validation passed; both jobs succeeded.
- Latest independently downloaded CMR artifact is from run [40112528293](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112528293): ID `12566734581`, 4,117 bytes, SHA-256 `ab1dc5ce3e237649b9c5e404d4c92e6b87c3dae3bf1565dde28e55f66dfe9a49`, matches GitHub's digest. Manifest: exact CMR identities 5/5, direct HDF5 URLs 5/5, blocking count 0, raw downloads 0, SHA-256 pins 0/5.
- Latest legacy raw replay [40112970152](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40112970152) passed its decision job but skipped analysis because the branch commit message did not contain the exact `[run-know-place]` marker. Latest dedicated author-exact run [40109347847](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40109347847) also skipped acquisition because its exact consent input was absent. No raw GOFF payload was downloaded.
- Paper reproduction remains `BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`; hazard detection remains `NOT_EVALUATED`. Main remains unchanged at `2218dfeb73353080d8d94bd733d9e7bd9a848886`.
- Report: `docs/know-place/evidence/LATEST_CMR_ARTIFACT_INTEGRITY_20261024.md`. Connected GitHub tools do not expose workflow dispatch; actual raw acquisition must be manually dispatched in Actions with `[run-know-place]` and configured Earthdata/Drive secrets.

## 21. Latest author-exact raw replay and status-label correction — 2026-10-24

- [x] Audited [run 40114703362](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40114703362): exact author profile and consent passed; all five P05023 GOFF HDF5 files were downloaded, SHA-256-pinned, HDF5 identity-checked and grid-validated. Total bytes 5,473,566,720; grid 4311 × 4230, EPSG:32645, 80 m posting. Derived bundle and both Drive receipts were remotely verified; temporary raw files were removed after durable retention. Full receipts: `docs/know-place/evidence/AUTHOR_EXACT_RAW_REPLAY_AUDIT_20261024.md`.
- [x] Five-pair metrics were computed. The 2026-07-26 → 2026-08-19 pair gives median crown magnitude 0.966063 m, mean vector 1.722246 m, azimuth 277.793°, median rate 0.040253 m/day and median coherence R=0.852850. This is numerical agreement only; the report marks the comparison `NOT_COMPARABLE_EXACT_CROWN_GEOMETRY_UNVERIFIED`.
- [x] Corrected the wrapper's stale post-download status overwrite. Raw byte identity is now `FIVE_EXACT_AUTHOR_SOURCE_HASHES_PINNED`; paper status is `BLOCKED_AUTHOR_CROWN_GEOMETRY_AND_METHOD_PARITY_UNVERIFIED`; hazard remains `NOT_EVALUATED`. The historical run artifact is immutable and keeps its pre-fix status label. No raw files were re-downloaded just to refresh the artifact.
- [x] Validation [40115947045](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40115947045), commit `5354a344ce19eac652fa8102c790fce18e18ec13`: 217 tests passed in 2.62 s; eight workflow YAMLs parsed; pinned actionlint v1.7.12 checksum and semantic validation passed. The live catalog stage downloaded zero payloads; raw replay skipped on subsequent push because no new consent marker was supplied.
- [ ] Verify the author-supplement crown geometry and control sampling, compare golden tables/masks, resolve terrain vertical-datum provenance, and run full-footprint screen parity. Do not claim hazard detection.
- Main remains `2218dfeb73353080d8d94bd733d9e7bd9a848886`; no merge or write to main.
