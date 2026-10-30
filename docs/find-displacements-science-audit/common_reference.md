# Backend adapter audit: `dashboard/common_reference.py`

**Backend dashboard source pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `79a014... ` (see exact checkout source in the pinned repository)

## Current behaviour

The function first checks `site_context.measurement_target.status`. If it is not `IN_AOI_TARGET_CAPTURED`, it writes `BLOCKED_NO_VALID_IN_AOI_TARGET` and returns before importing the science common-reference/time-series modules. If a target is supplied, it proceeds to group eligible GUNW products, enforce grid and common-support criteria, exclude a 2 km target buffer, then use the time-series graph logic where enough common support and redundancy exist.

## Scope boundary

This helper is target-buffered and belongs to Known Place Analysis. Do not call it in target-free Find Displacements by synthesizing a target or substituting AOI centroid. The separate target-free reference method must not silently inherit this helper's stable-ground claim: this helper itself says the AOI-derived datum is not independently validated stable ground.

## Correct next design

A distinct AOI-only reference estimator needs a provenance-carrying mask and explicit tests for spatial distribution, temporal stability, stable-ground external evidence and sensitivity to alternative masks. Until that work exists, target-free cumulative GUNW output remains withheld.

**Verdict:** correct fail-closed guard; not a target-free method.
