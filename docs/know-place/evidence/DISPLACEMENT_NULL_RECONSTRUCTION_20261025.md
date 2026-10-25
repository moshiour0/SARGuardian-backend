# Independent displacement-null reconstruction — 2026-10-25

## Scope and provenance

This is the first computational reconstruction of the paper's size-matched displacement null using only the five processed-field GeoTIFFs in the supplied Zenodo archive (DOI 10.5281/zenodo.22730419). It did not read or download raw GOFF HDF5. The source archive was inspected for every member and its Python source was searched for the displacement-null generation path.

The archive contains tables/displacement_null.json as five aggregate rows but no displacement-null generator script, seed, draw-level samples, or rejection trail. code/polygon_null.py is not that generator: it estimates directional coherence R for spatial disks. The article describes compact regions with the crown's own valid-pixel count, random placement on valid ground in the fixed 6 km box, and rejection of regions with insufficient valid pixels; reported accepted samples are 857–996 per pair. It does not fully specify the missing displacement sampler in the supplied archive.

## Independent policy v1

The new module tools/know_place/displacement_null.py uses a deterministic, explicit reconstruction policy: displacement magnitude is hypot(dE,dN); observed statistic is the median over valid crown cells; null samples are median magnitudes in raster-index disks with area set by the crown's valid-pixel count; centres are sampled without replacement from finite east/north displacement cells inside the 6 km box; up to 1,200 centres are tested per pair; a region is accepted with at least 60% of the crown valid-cell count; percentile is 100 times the fraction of accepted medians strictly below the observed crown median. A single NumPy PCG64 generator, seed 20261025, is reused across pairs in chronological order. These shape, RNG and acceptance choices are declared independent assumptions, not recovered author settings.

All attempted centres, including rejected centres, and all accepted median values are retained in the JSON report. Input GeoTIFF sizes, SHA-256 hashes, CRS and transforms are recorded. The report version is method-derived-displacement-null/1.0.

## Archive run results

| Pair | Crown valid pixels | Accepted / tried | Independent null median | Independent percentile | Published percentile |
|---|---:|---:|---:|---:|---:|
| 20 Jun–2 Jul | 283 | 832 / 1,200 | 0.168 m | 95.1 | 94.9 |
| 2–14 Jul | 294 | 815 / 1,200 | 0.195 m | 88.6 | 87.5 |
| 14–26 Jul | 296 | 832 / 1,200 | 0.136 m | 82.8 | 81.0 |
| 26 Jul–19 Aug | 292 | 835 / 1,200 | 0.144 m | 92.2 | 94.7 |
| 19–31 Aug | 195 | 882 / 1,200 | 0.092 m | 82.8 | 81.3 |

The computed crown medians round to the published crown values at two decimals. Independent null medians are close to the aggregate table but some percentiles differ, including -2.5 percentage points on the 26 Jul–19 Aug pair. This is evidence that the chosen explicit policy does not reproduce the missing sampler exactly; it is not a failed code test and must not be “fixed” by tuning parameters to the answer.

## Acceptance status and next work

Status: INDEPENDENT_METHOD_DERIVED_NOT_AUTHOR_SAMPLER_PARITY. Exact author-code parity remains unverifiable from the supplied archive. The 94.7th percentile is a published ranking against a null distribution, not a calibrated hazard probability or proof of early-warning capability.

The next scientific iteration is a predeclared sensitivity matrix over plausible compact-region and acceptance choices, with no result-driven tuning. If further author source or draw-level output is found, compare it directly. Then verify the exact crown geometry/source-grid mask, and run a separately named vertical-datum sensitivity. Keep whole-paper status PARTIAL and hazard detection NOT_EVALUATED.
