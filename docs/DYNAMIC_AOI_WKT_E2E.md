# Dynamic AOI WKT E2E processing

## Launch

Run the default-branch workflow **SARGuardian AOI WKT E2E (safe branch dispatcher)** from the repository's Actions tab. The dispatcher calls the isolated feature workflow in branch `feat/e2e-aoi-wkt-date-dashboard`; the existing source-AOI E2E workflow is not called or changed.

Inputs:

- **AOI WKT**: one `POLYGON ((lon lat, ...))` exterior ring, coordinates in EPSG:4326 and in longitude/latitude order. An open ring is closed automatically. Holes, `MULTIPOLYGON`, 3-D coordinates and other SRIDs are rejected.
- **Start / end date**: inclusive window on the **secondary acquisition date** parsed from the NISAR pair identifier. The search begins in 2024 to avoid missing pairs whose reference acquisition predates the selected secondary date.
- **validation-pilot**: newest supported GUNW and newest supported GOFF intersecting the AOI/window. A quick operational check, not a full baseline.
- **full-aoi-baseline**: all supported GUNW and GOFF granules discovered for the exact polygon/window. Discovery stops on an incomplete ASF result set or more than 200 selected products; narrow the dates/AOI instead of silently truncating.
- **derived-only**: store derived maps, metrics and provenance; raw worker copies can be deleted only after remote storage verification.
- **full-lossless**: also retain the lossless HDF5 archive and require raw/archive reader equivalence.

## Pipeline design

1. Validate WKT geometry and dates.
2. Query the ASF DAAC catalog with the actual polygon WKT (`intersectsWith`), separately for NISAR GUNW and GOFF.
3. Parse the pair ID and apply the inclusive secondary-date window. Record catalog counts, exclusions, product maturity, AOI WKT SHA-256 and the exact science commit.
4. Download and validate each exact granule with the existing protected worker pattern, but use the `custom` AOI all the way through product preflight, GUNW/GOFF reader, export, provenance and retention receipts.
5. Retry only products that lack a complete, hash-consistent processing/cleanup receipt pair.
6. Generate a downloadable, self-contained HTML dashboard, CSV product table, per-product quicklooks and a result ZIP. If Drive credentials are configured, also upload summary/bundle files to the configured private Drive location.

## Important interpretation limits

- This dashboard is generated as a **GitHub Actions artifact**; it is not automatically mounted into the public website/API. The UI can be opened offline after downloading the `sarguardian-aoi-dashboard-*` artifact and opening `index.html`.
- The existing 33-product source-AOI baseline is deliberately not used for numeric pixel-by-pixel comparison: a custom AOI has different spatial support, so that comparison would be scientifically invalid.
- Structural PASS means the requested AOI was used, the catalog/product identity and source SHA were recorded, the product grid intersects the AOI, exports exist and retention receipts validate. It is **not** independent geophysical validation, proof of slope failure, or a validated common-reference displacement time series.
- Per-image quicklook colour scales are independent. Cross-product medians are not directly comparable unless geometry, reference datum, coherence/quality support, atmosphere and release effects have been handled.
- No-valid-pixel products are surfaced as warnings rather than described as zero motion.
- The workflow needs the existing Earthdata credentials and private-Drive secrets required by the worker's chosen retention mode. These secrets must never be placed in WKT inputs.
