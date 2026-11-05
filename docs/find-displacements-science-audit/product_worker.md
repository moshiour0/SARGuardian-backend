# Workflow audit: reusable AOI product worker

**Workflow:** `.github/workflows/sarguardian-aoi-product-worker.yml`  
**Workflow revision:** backend `main` at `78bc24b9b2c163d4ea899eeaf3793fbf9974e4d4`  
**Science source pin:** `f038e4dfdb53c8d9793aaaefe173570a1032026c`

## Exact science calls

- GUNW: `src/gunw_reader.py --read ... --aoi custom --auto-ref --csv ... --export ...`
- GOFF: `src/goff_reader.py --read ... --aoi custom --layer layer2 --csv ... --export ...`
- Both call the same exact WKT AOI mask and retain source granule/provenance receipts.
- GOFF layer2 is the only layer passed to the live AOI candidate path.
- `local_floor.py` is deliberately not run if target coordinates are absent; it reports `NOT_RUN_NO_IN_AOI_TARGET`.
- `measure_target_from_raster.py` is likewise conditional on explicit target coordinates. It is not part of Find Displacements.

## Separation rule

Do not make target coordinates required for Find Displacements. Do not generate a centroid, arbitrary seed or automatic crown and pass it into point-measurement scripts. Keep these target-dependent operations within Known Place Analysis.

## Audit findings

The worker's source pin is immutable and identical across discovery and per-product processing. Its current reader calls are reproducible. However, only GOFF layer2 is used, and current exports do not preserve all per-pixel GOFF variance/covariance for the downstream screen. These are science coverage gaps, not reasons to alter the Known Place branch.

**Verdict:** PASS for exact AOI worker routing and clear target gate; PARTIAL for multi-resolution GOFF and exported uncertainty coverage.
