# Author footprint-wide candidate-screen kernel audit — 2026-10-24

## Scope and source identity

This audit extracts the footprint-wide candidate screen into an isolated, array-level module. It is a different estimator from the crown/site-series calculation in tools/know_place/paper_method.py. It does not run raw GOFF data and does not establish full paper reproduction.

Author-supplied Zenodo archive: https://doi.org/10.5281/zenodo.22730419. The ZIP and manifest-listed payloads were integrity-audited separately. Source files inspected:

| Source | SHA-256 |
|---|---|
| code/wide_screen.py | 60e4238b9a10510f52a4673939a9708bf513d8bae460ba797d2dd27a1357d7c9 |
| code/geometry.py | 0f056c46f2f5f9418dd1735b666edaa5c055514694fcd2c66490e09b6bb63004 |
| tables/TableS6_screen_params.json | 85743e828c4d684046acf43bdb0bfbc8b8c194626aacad8fd58e154e925d8e76 |

The source archive main code/data is CC BY 4.0. The separate extent_CC-BY-NC-4.0 runout outline was not used or copied.

## Author-source behavior transcribed

The new tools/know_place/footprint_screen.py isolates the numerical screen and enforces the ordered five-pair date sequence.

1. **Projection and first quality gate.** Author wide_screen.project calculates dE = AT*cE + SR*kE and dN = AT*cN + SR*kN from per-pixel coefficients delivered by geometry.load(). It retains only finite projected magnitudes with SNR >= 5 and magnitude <= 10 m. The isolated helper requires per-pixel coefficient rasters as input; it does not implement geometry-cube interpolation or DEM/HAE construction.
2. **Local mean.** lmean(a, w) is reproduced as float32 nan_to_num, finite-value support, scipy.ndimage.uniform_filter with default reflected edges, and output only where support fraction is strictly greater than 0.15.
3. **Magnitude anomaly.** The anomaly is mag - lmean(mag, 41). Its scale is the local mean of the absolute anomaly using the same 41-pixel window; the divisor floor is 0.05 m. This is a local scale statistic, not a conventional median absolute deviation.
4. **Residual vector coherence.** Subtract the local 41-pixel mean independently from dE and dN, normalize residual vectors, and estimate R in a 5x5 window. A window is retained only if finite-direction support fraction is strictly greater than 0.5.
5. **Within-pair candidate rule.** A cell is flagged only when all conditions hold in the same pair: z >= 4, magnitude anomaly >= 0.50 m, finite residual R, and residual R >= 0.75.
6. **Persistence.** The same grid cell must flag in at least 2 of the exact ordered pairs: 20 Jun–2 Jul, 2–14 Jul, 14–26 Jul, 26 Jul–19 Aug, and 19–31 Aug 2026. Mean anomaly and residual R are averaged only over intervals that flagged that cell.
7. **Candidate components.** scipy.ndimage.label default 2-D connectivity is retained (four-connected components), and components smaller than 10 pixels are excluded. Ten pixels at 80 m posting correspond to 0.064 km². The module returns component masks/labels; it does not recreate author GeoPackage/shapefile/CSV polygonization or centroid-ranking outputs.

The parameter inventory is in tables/TableS6_screen_params.json. The downslope-angle check is a later, separate analysis in candidate_attributes.py; topography is not used in wide_screen.py itself.

## Implementation added

- tools/know_place/footprint_screen.py: per-pixel AT/SR projection with mandatory 2-D coefficient rasters; quality gates; author-formula local mean; residual R; per-pair threshold screen; exactly-five-pair persistence; four-connected minimum-component filter.
- tools/tests/test_know_place_footprint_screen.py: tests for parameter constants; edge/support behavior; projection and quality gates; mandatory per-pixel geometry; diagnostic-map parity against a separately written reference of archived formulas on deterministic synthetic arrays; invalid-mask and interval rejection; five-pair persistence; default component connectivity and size threshold.
- Each result deliberately contains hazard_detection_status=NOT_EVALUATED. Its output is a movement candidate to inspect, not an operational alert.

## What the tests establish and do not establish

The tests compare the isolated equations with an independent test-local transcription of relevant archived formulas; they are synthetic known-answer tests, not execution of the original archive script. They can catch implementation drift in the extracted kernel but are not raw-input parity.

This module does not yet read exact author GOFF HDF5 products or verify their source hashes; construct per-pixel imaging geometry from the author geometry cube and exact DEM/HAE path; verify all five output rasters share the exact 4230 x 4311 native grid and coordinates; run the footprint screen across the five raw exact P05023 products; recreate GeoTIFF/GPKG/shapefile/CSV outputs or centroid-based candidate score ordering; run post-hoc topographic downslope validation; or establish detection skill, recall, precision, false-alarm rate, lead time, or operational value.

The archive includes three footprint screening rasters and a post-event 101-zone source-derived inventory, but not the five raw source GOFF HDF5 granules or five full-footprint per-pair offset rasters. The first author-exact P05023 pair remains unresolved in the live ASF identity gate; do not silently substitute X05026.

## Scientific interpretation

The source says the screen finds coherent moving surfaces, and active glaciers dominate its candidate set. It is not a prospectively validated event detector. The Bhote Koshi site-series analysis reporting no pre-event comparison above the 95th percentile is a separate result; do not infer that the footprint screen validates or contradicts it.

Current status:

- PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED
- HAZARD_DETECTION_STATUS=NOT_EVALUATED
- Operational warning / alert: not implemented.

Raw-source replay was not run. A branch push alone is not authorization; the exact [run-know-place] consent marker remains required.
