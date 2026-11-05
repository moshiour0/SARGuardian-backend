# Backend scientific audit: `tools/aoi_wide_displacement_screen.py`

**Code pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `cea9a8bd7f95a3107f3aec0bbc66f9bdce253141`  
**Find Displacements use:** executed target-free by the AOI aggregator.

## Current algorithm

- Groups compatible GOFF products by processing, track/direction, frame, bandwidth, polarization and CRID. Incompatible series are kept separate.
- Requires the retained export provenance to indicate AOI masking, metric projected CRS and the common AOI grid.
- Reads pre-global-MAD screen-valid range/azimuth offsets and correlation (not only the stricter robust inlier mask), preserving coherent localized outliers for spatial review.
- Subtracts a local mean using a 41-pixel neighbourhood; screens vector anomaly magnitude against a minimum 0.25 m or larger pair threshold, robust-z >= 4 and local directional coherence >= 0.75.
- Combines candidate hits over compatible pairs; default minimum persistence is two pair observations, minimum cross-pair direction coherence 0.75, minimum component size 10 pixels.
- Writes GeoJSON/CSV and per-series candidate-pair-count, persistent-mask and directional-coherence GeoTIFFs. Metadata declares `target_required=false` and candidate interpretation is explicitly exploratory.

## Scientific risks

1. **Uncertainty mismatch:** `_pair_offset_threshold_m` derives the pair floor from the reader's range-component robust sigma and applies it to a joint range/azimuth magnitude. This does not propagate azimuth variance or range/azimuth covariance. The robust scale uses the maximum component MAD and a 0.03 m floor, not a calibrated bivariate error distribution.
2. **No per-pixel variance in screen:** the reader loads range variance, but worker exports do not carry per-pixel variance/covariance into this stage. SNR is used upstream as a reader gate, but is not spatially available to re-weight the screen.
3. **Scale bias:** local mean subtraction is a high-pass operation. Broad, slowly varying or AOI-wide coherent displacement can be suppressed, and the result depends on 41-pixel neighbourhood size.
4. **Limited persistence:** two pair hits permit an exploratory review candidate, but this is not equivalent to a redundant time-series network or an independent rate estimate.
5. **Resolution:** current worker selects GOFF `layer2` only. Feature detectability and uncertainty can differ across GOFF layers.
6. **Threshold interpretation:** robust-z >= 4 and coherence >= 0.75 are screening parameters; they are not calibrated false-alarm probabilities. The minimum 0.25 m is a design floor, not a universal physical detection limit.
7. **No direct velocity:** current candidates report offset-anomaly magnitudes and persistence. They do not estimate a temporal velocity field in mm/day.

## Existing test coverage

`tools/tests/test_aoi_wide_displacement_screen.py` includes target-free coherent-patch recovery, low-correlation rejection, single-pair non-persistence, duplicate-date protection, CRID separation, opposing directions, bandwidth identity and pair-floor usage. These tests establish logic invariants, not external measurement accuracy.

## Required scientific improvements

- Extend GOFF exports with slant-range and azimuth variance and, where product schema supports it, cross-covariance. Store SNR and correlation at the pixel level.
- Use a covariance-aware 2-D statistic (or report separate range and azimuth scores) with independently calibrated thresholds.
- Run layer1/layer2 sensitivity tests and publish disagreement, sampling and support.
- Inject known displacement objects at several sizes, directions and rates into realistic spatially correlated null fields. Quantify recall, false-candidate rate and object-scale bias across alternative local-window sizes.
- Make broad-motion sensitivity explicit. Preserve raw, locally detrended and multi-scale components rather than one high-pass output.
- Require more temporal support for velocity claims; candidate persistence may remain a review heuristic.
- Keep the status `EXPLORATORY_RANKING_ONLY` until held-out positive/null validation supports a stronger status.

**Verdict:** useful target-free candidate generator with deliberate fail-closed provenance checks; NOT a validated offset-velocity detector.
