# Dashboard audit: `dashboard/assets/prepare_web_assets.py`

**Backend dashboard source pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `ca5813901c626068e5ca100fe4d1fd5edcb78beb`

## Current presentation pipeline

The builder reads the aggregate summary, opens retained product GeoTIFF exports, reprojects display previews to the web map CRS, clips them to the exact AOI, produces per-band PNG assets and records source/output checksums. Product previews are placed into `public_layers`. It loads AOI-wide candidate GeoJSON into the dashboard manifest; the front-end map renders candidate polygon fill/outline and candidate list.

The preview scale is a display contrast rule (symmetric 98th-percentile scale for continuous layers), not a scientific threshold. Source rasters remain unchanged and are the underlying science assets.

## Verified gap

The builder's product loop walks only `product.exports` (or a fallback set of product TIFFs) and builds the selectable map layer list from those per-product export bands. It does not currently load the AOI-wide screen GeoTIFFs (`candidate_pair_count.tif`, `persistent_candidate_mask.tif`, directional coherence) or the GUNW `pixel_stack.py` velocity/sigma GeoTIFFs into `public_layers`. Thus a GeoJSON candidate polygon can appear while its underlying count/coherence raster is absent. Likewise, product PNGs are not a substitute for a dedicated velocity/candidate-science PNG.

## Required implementation

- Extend the result-manifest contract to describe derived-science layers with source path/hash, CRS/transform, exact units, band semantics, masks, observation support and status.
- Reproject/clip display previews without changing native science rasters.
- Publish independent PNG and map layers for candidate mask, pair count, directional coherence, LOS velocity, velocity sigma, valid support and longest contiguous support.
- Use explicit nodata transparency and separate legends. Never style nodata as zero or as no motion.
- Show method (GOFF pairwise offset anomaly vs GUNW relative LOS velocity), track, CRID/maturity, dates and support in popups.
- Add tests proving every expected scientific derivative is referenced by the manifest and that output pixels/hash match the source.
- Keep viewer wording: exploratory candidate, LOS-only, not forecast/hazard alert.

**Verdict:** PASS for product raster preview integrity; INCOMPLETE for exposing the important derived AOI-wide science rasters.
