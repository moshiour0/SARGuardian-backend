# Author-supplement retrieval audit — Know Place Analysis

**Audit date:** 2026-10-24  
**Working branch:** `feat/know-place-analysis`  
**Paper reproduction status:** `BLOCKED_AUTHOR_GEOMETRY_VARIANT_AND_GOLDEN_OUTPUTS_UNVERIFIED`  
**Hazard-detection status:** `NOT_EVALUATED`

## 1. Authoritative sources checked

- Copernicus/EGUsphere preprint page: https://egusphere.copernicus.org/preprints/2026/egusphere-2026-5462/
- Preprint PDF linked from that page: https://egusphere.copernicus.org/preprints/2026/egusphere-2026-5462/egusphere-2026-5462.pdf
- Full-study Research Square DOI cited by the author's site: https://doi.org/10.21203/rs.3.rs-11022365/v1
- Author's publication page: https://www.sansarmeena.com/

The Copernicus HTML page's visible “Download & links” section lists the PDF, metadata XML, BibTeX and EndNote, but no supplementary archive link was present in the page content inspected on this audit. The Research Square DOI was discoverable from the author's site and a Sciety article record, but the available browser retrieval returned HTTP 403. Guessed Copernicus supplement URLs were not accessible through the retrieval tools. These outcomes establish a **retrieval blocker in this pass**, not proof that no supplement exists.

## 2. Supplement contents asserted by the preprint

The PDF's “Code availability” section says processing/figure scripts are included in a CC BY 4.0 supplement, using Python 3.11 with rasterio/GDAL, geopandas, NumPy, SciPy and scikit-learn. It warns that local paths and additional inputs remain, so the supplement is not a self-contained computational environment.

The “Data availability” section says the supplement contains:

- Five NISAR-derived GeoTIFFs with eastward displacement, northward displacement and directional-coherence bands, on an EPSG:4326 grid (different from the native EPSG:32645 analysis grid).
- Statistical tables.
- A supplement README listing the five source NISAR L2 GOFF granule identifiers, with those source products available from ASF DAAC.

The paper describes the supplement data/fields as CC BY 4.0; the mapped extent is separately described as CC BY-NC 4.0. Reuse must preserve those distinctions. No supplement bytes were obtained in this pass, so **no supplement or sub-file SHA-256 can truthfully be reported**.

## 3. Method facts verified from the paper

The methods and figure notes specify the following target-pair procedure:

1. Use layer2 along-track (AT) and slant-range (SR) offsets where SNR is at least 5.
2. Project to horizontal displacement with the product convention; the LOS unit vector points from target to sensor, so positive slant-range offset denotes movement away from the sensor. Vertical motion is assumed zero.
3. Reject projected horizontal displacement magnitudes above 10 m; do not clip them.
4. Remove component-wise median reference bias using valid cells in the background box outside the source/crown polygon.
5. Calculate the 5×5 mean resultant length of unit displacement directions. The published paper does not specify the code-level minimum-valid-neighbour, missing-centre, or edge-padding policy; those must be read from the author code and parity-tested.
6. Spatial controls use circular regions at random valid positions in the same box, nominal area based on the crown's valid-cell count, and retain draws with at least 60% of that count. The preprint reports a control displacement median around 0.14 m and source rank around the 94.7th percentile. The exact PRNG, draw order, handling of polygon-overlap/invalid cells and full accepted sample still require author-code verification.

The official paper page currently states that no pre-event interval exceeds the 95th percentile of the spatial comparison distributions for displacement or directional coherence. Results should be described as measurement/statistical comparisons, not as a successful early-warning detection.

## 4. What remains unverified / blocked

- Exact supplement archive and its checksum.
- Author README's exact five granule names/releases, especially whether the 20 June–2 July X05026 candidate matches the author's variant.
- Exact author crown/source polygon, coordinate order/CRS, and geometry-file checksum.
- The five author-derived GeoTIFF checksums and the statistic tables used as golden references.
- Author implementation of spatial-control sampling and 5×5 R centre/edge/valid-neighbour policies.
- Provenance and effect of the current fixed `geometry_height_m=5151.0 m` HAE query applied to every ROI pixel. The radar-geometry cubes are elevation-dependent; the author code/golden rasters must establish whether this constant-height sampling is equivalent or quantify its effect. This is an unresolved assumption, not a proven defect; do not tune the height to force scalar agreement.
- Pixelwise parity and all-five-interval statistic parity.

Current candidate GOFF HDF5 source files have already been downloaded, historical byte sizes/SHA-256 matched, and processed in Raw Replay Run 40006999011. Do not repeat that expensive download merely to search for the supplement. Use the existing derived arrays for any analysis that does not require a source input absent from them.

## 5. Retrieval follow-up and acceptance rule

1. Retrieve the supplement via an accessible official attachment or the author/Research Square file record, preserving original filenames and licence.
2. Hash the original archive and every extracted source file before inspection.
3. Parse the README and compare the author manifest against the current five candidate granules without substitution.
4. Extract the exact crown polygon and derive a provenance-recorded WKT/raster mask; do not infer it from the published bounds.
5. Run parity tests against each author GeoTIFF/statistical table, and implement the author's control/coherence policies only after the source code makes those policies explicit.

Until the required inputs and independent golden-output comparisons pass, leave paper reproduction **BLOCKED** and hazard detection **NOT_EVALUATED**.
