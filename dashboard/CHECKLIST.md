# Implementation Checklist — Interactive Science Dashboard

Statuses: `DONE`, `IN_PROGRESS`, `BLOCKED`, `NOT_STARTED`. A checklist item moves to DONE only with code/test/evidence links.

## Phase 0 — Evidence and architecture
- [x] Audit the successful processing run and download dashboard artifact.
- [x] Inventory existing PNG quicklooks, multi-band GeoTIFFs, CSV/reports, provenance, and pixel-stack diagnostics.
- [x] Identify no-geospatial-map and no-playback gaps in current HTML.
- [x] Document scientific guardrails, current AOI distinction, formats, and source references.
- [ ] Add a representative sample fixture to automated tests without committing proprietary or large raw HDF5 files.

## Phase 1 — Processing-time map assets (no raw replay)
- [ ] Implement a deterministic web-asset builder in `dashboard/assets/`.
- [ ] Reproject each validated raster band to display-friendly geographic coordinates from the source CRS and affine transform.
- [ ] Produce transparent preview PNGs with explicit corners/bounds; keep native GeoTIFFs unchanged.
- [ ] Build `web-dashboard/manifest.json`, `aoi.geojson`, `timeline.json`, `metrics.json`, STAC catalog/collection/items.
- [ ] Record per-layer band name/units, value range, color scale policy, NoData count, source CRS, source hash, science/orchestration commits and AOI hash.
- [ ] Validate every generated PNG, metadata shape, corners and checksum; fail closed if an overlay points outside the AOI beyond expected grid padding.
- [ ] Add tests for different UTM zones, NoData transparency, missing band descriptions, empty bands, and reproducibility.
- [ ] Wire builder into AOI aggregation before ZIP creation and Drive upload.
- [ ] Add generated file list and explicit status to workflow summary; preserve Drive result upload and the current three required account artifacts.
- [ ] Run the builder against the downloaded artifact fixture and compare source TIFF hashes before/after.

## Phase 2 — Interactive offline/presentation viewer
- [ ] Add map panel showing true AOI geometry and geo-located preview layer, never a schematic pretending to be the map.
- [ ] Add product/band selector, opacity slider, legend with units/scale, product details and pixel count.
- [ ] Add acquisition-pair timeline, Play/Pause, previous/next, playback speed and date labels.
- [ ] Group observations by track/view geometry; do not interpolate missing acquisitions or join incompatible pairwise measurements as a trend.
- [ ] Add scientific metric charts, data-quality/support chart, provenance card, limitation banners, and export links.
- [ ] Add graceful no-basemap/offline fallback and explicit map-data attribution.
- [ ] Add keyboard, mobile, contrast, reduced-motion, and presentation/full-screen checks.

## Phase 3 — Authenticated Dynamic app integration
- [ ] Define owner-scoped read-only dashboard metadata/assets endpoint or verified bundle download.
- [ ] Enforce Firebase owner authentication and server-side job ownership.
- [ ] Verify stored artifact byte count and SHA-256 before serving; do not leak private Drive IDs.
- [ ] Add “Open interactive dashboard” for successful jobs and a resilient direct-link route.
- [ ] Show `processing PASS`, `visual assets PASS`, and `independent scientific validation NOT PERFORMED` as distinct states.
- [ ] Preserve current Retry task, account history, and private Drive retention behavior.
- [ ] Test authorization failures, expired/missing artifacts, API retries and older schema versions.

## Phase 4 — Scientific visualization QA
- [ ] Test expected product/observation count and pair/date sorting.
- [ ] Test cross-CRS overlays (e.g. EPSG:32645 and EPSG:32646) against source affine bounds / sample coordinates.
- [ ] Ensure no values are silently converted or labeled as cumulative, vertical, 3-D, mm/day, or hazard probability.
- [ ] Check fixed-scale animation within compatible groups and compare source values to identify readouts.
- [ ] Surface unsupported candidate screen and zero common-pixel time-series diagnostics.
- [ ] Confirm no false “stable/hazard/no hazard” inference from missing data, zero valid pixels, or NoData regions.
- [ ] Independent reviewer sign-off on the visual measurement semantics before any operational hazard-alert language.

## Phase 5 — Performance and release
- [ ] Verify dashboard generation adds no source HDF5 downloads and does not increase raw retention.
- [ ] Benchmark asset build time, bundle size, first contentful display, and playback frame consistency.
- [ ] Check reproducible manifests/checksums on a second run with the same fixture.
- [ ] Document browser requirements, external basemap dependency, and offline behavior.
- [ ] Complete code review and CI; integrate only into the approved science-integration branch, never commit directly to backend `main`.
