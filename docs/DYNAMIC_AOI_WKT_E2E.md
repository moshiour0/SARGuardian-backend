# Dynamic AOI WKT E2E processing

## Launch

Run the default-branch workflow **SARGuardian AOI WKT E2E (safe branch dispatcher)** from the repository's Actions tab. The dispatcher calls the isolated feature workflow in branch `feat/e2e-aoi-wkt-date-dashboard`; the existing source-AOI E2E workflow is not called or changed.

Inputs:

- **AOI WKT**: one `POLYGON ((lon lat, ...))` exterior ring, coordinates in EPSG:4326 and in longitude/latitude order. An open ring is closed automatically. Holes, `MULTIPOLYGON`, 3-D coordinates and other SRIDs are rejected.
- **Start / end date**: inclusive acquisition interval. The default `both-acquisitions-in-window` mode requires both the reference and secondary acquisitions represented in each GUNW/GOFF pair to fall inside the interval. This is the scientifically conservative meaning for a bounded full-baseline run. The optional `secondary-acquisition-in-window` compatibility mode filters only on the timestamp labelled secondary and can admit a pair whose reference acquisition is before the requested start. That is an explicit boundary-pair choice, not a generic date-window interpretation. The catalog search starts in 2024 so pair products can be retrieved before the exact in-window test is applied.
- **validation-pilot**: newest supported GUNW and newest supported GOFF intersecting the AOI/window. A quick operational check, not a full baseline.
- **full-aoi-baseline**: all supported GUNW and GOFF granules discovered for the exact polygon/window. Discovery stops on an incomplete ASF result set or more than 200 selected products; narrow the dates/AOI instead of silently truncating.
- **derived-only**: store derived maps, metrics and provenance; raw worker copies can be deleted only after remote storage verification.
- **full-lossless**: also retain the lossless HDF5 archive and require raw/archive reader equivalence.

## Pipeline design

1. Validate WKT geometry and dates.
2. Query the ASF DAAC catalog with the actual polygon WKT (`intersectsWith`), separately for NISAR GUNW and GOFF. The working query uses `dataset=NISAR`, the exact `processingLevel=GUNW` or `GOFF` and GeoJSON output. We tested the `shortName` parameter against the legacy Search endpoint and observed that it was ignored there, so it is not treated as authoritative maturity evidence. Response normalization handles GeoJSON properties and a nested-list response shape. The log records per-family discovery, date-policy and maturity counts.
3. Parse both reference and secondary acquisition dates from the four timestamps in the pair granule identifier. Apply the selected date-window mode. The product date fields are distinct from processing/production time and do not, by themselves, define maturity. Record catalog counts, date exclusions, maturity evidence, AOI WKT SHA-256 and the exact science commit.
4. Apply the maturity policy conservatively: recognize CRID `P05023` and later production CRIDs as PROVISIONAL, recognize supported earlier X-release CRIDs as BETA, and reject unknown CRIDs or conflicts between an explicit catalog maturity/collection label and CRID. Never promote an unknown CRID to PROVISIONAL just because its acquisition date is after June 17, 2026. This matters because products with CRID `X05026` appeared in the spatial/date-matched catalog but are not safe to relabel based on date alone. `PR`, `UR`, and `OD` identify processing type; `N`, `F`, `M`, `P` in the product-accuracy position are not maturity labels.
5. Collapse duplicate variants of the same product family, geometry/mode and reference-secondary pair. Prefer standard `PR` production over `OD` science-on-demand and `UR` urgent-response; then prefer the higher declared product-accuracy class and full coverage when variants otherwise match. The selected variant and excluded alternatives remain inspectable in the manifest.
6. Download and validate each exact selected granule with the existing protected worker pattern, but use the `custom` AOI all the way through product preflight, GUNW/GOFF reader, export, provenance and retention receipts.
7. Retry only products that lack a complete, hash-consistent processing/cleanup receipt pair.
8. Generate a downloadable, self-contained HTML dashboard, CSV product table, per-product quicklooks and a result ZIP. If Drive credentials are configured, also upload summary/bundle files to the configured private Drive location.

## Important interpretation limits

- This dashboard is generated as a **GitHub Actions artifact**; it is not automatically mounted into the public website/API. The UI can be opened offline after downloading the `sarguardian-aoi-dashboard-*` artifact and opening `index.html`.
- The existing 33-product source-AOI baseline is deliberately not used for numeric pixel-by-pixel comparison: a custom AOI has different spatial support, so that comparison would be scientifically invalid.
- Structural PASS means the requested AOI was used, the catalog/product identity and source SHA were recorded, the product grid intersects the AOI, exports exist and retention receipts validate. It is **not** independent geophysical validation, proof of slope failure, or a validated common-reference displacement time series.
- Per-image quicklook colour scales are independent. Cross-product medians are not directly comparable unless geometry, reference datum, coherence/quality support, atmosphere and release effects have been handled.
- No-valid-pixel products are surfaced as warnings rather than described as zero motion.
- The workflow needs the existing Earthdata credentials and private-Drive secrets required by the worker's chosen retention mode. These secrets must never be placed in WKT inputs.


## Scientific policy sources

- NISAR naming convention identifies GUNW and GOFF as products generated from a **pair** of acquisitions: https://nisar-docs.asf.alaska.edu/naming-conventions/
- ASF/NISAR data availability states PROVISIONAL products use CRID P05023 and are available from acquisitions starting June 17, 2026; the earlier BETA release covers a selected set of acquisitions from October 2025 to January 2026. It explicitly warns against mixing BETA and PROVISIONAL without care because processing software changes can mimic landscape change: https://nisar-docs.asf.alaska.edu/availability-overview/
- PROVISIONAL means calibrated and partially validated, not fully validated. Known issues and ongoing processing improvements remain: https://nisar-docs.asf.alaska.edu/provisional-known-issues/
