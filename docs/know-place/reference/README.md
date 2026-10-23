# Author reference data for Know Place Analysis

## Attribution and licence

Meena, Sansar Raj (2026), **"NISAR offsets measure pre-failure motion but do not single out the Bhote Koshi avalanche source."** Research Square, posted 22 September 2026. Article DOI: https://doi.org/10.21203/rs.3.rs-11022365/v1.

The author identifies Supplementary Data 1 (the 101-zone inventory) and all supplementary items other than Supplementary Figure 1 and Supplementary Table 5 as CC BY 4.0. The exceptions are third-party CC BY-NC 4.0 material and are not copied into this directory.

The original user-uploaded CSV SHA-256 is `b800d90bd6e7322ef2f8548370de0fb922ef057cbdce2d0c2caa681ae76a42a8`. The paper's code, rasters, and full golden data archive is separately cited at https://doi.org/10.5281/zenodo.22730419; its archive payload and checksum are not yet verified here.

## Files

- `author_validated_zones_supplementary_data_1.csv`: the supplied author inventory of 101 validated zones (93 intersect RGI 6.0; 8 do not).
- `author_benchmark_v1.json`: transcribed article/supplement values, exact crown/reference bounds, exact five source granule identifiers, the per-pair site-series table and key footprint-screen values.

## Scientific boundaries

- This is a **source-derived reference dataset**, not an independent blind holdout set. The source zone is identified by the article after the event and must not be used to claim prospective detection skill.
- Supplementary Table 1 specifies `P05023` for all five GOFF granules. The earlier historical raw replay used `X05026` for 20 June-2 July. That previous replay remains historical/checksum-verified, but it is not an exact reproduction of the author's five-input series.
- The article reports that no pre-event pair reaches the 95th percentile on displacement or directional coherence and that no acceleration is resolved. Do not reinterpret the 101-zone screen as an operational hazard detector.
- Preserve the published distinction between the site-series crown-local geometry and per-pixel GLO-90 geometry in the footprint-wide screen. Exact geometry sampling/datum and pixelwise parity still require the author's code/golden archive.
