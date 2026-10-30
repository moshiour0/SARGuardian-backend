# Backend science-stage audit: `dashboard/science_pipeline.py`

**Backend dashboard source pin:** `ecd125f68ed61c276406f73a1d77eb27979e204e`  
**Blob:** `8fe1148d1f6a50fd15aa076a38cc70286bb3af7b`

## Role

Converts the actual per-product, network and diagnostics reports into explicit stage statuses. It does not run the core estimator itself and must not upgrade a blocked/diagnostic stage to a measurement.

## Current target-free status policy

- GUNW/GOFF reader stages: executed per product when family exists.
- Network assessment: may parse pair/epoch topology and report connected components/redundancy.
- `common_ref.py`: target-free request receives `BLOCKED_NO_VALID_IN_AOI_TARGET`.
- `timeseries.py`: topology can be shown; cumulative inversion is withheld unless common grid, sufficient common support, target support and a redundant network pass the guarded reference path.
- `local_floor.py`: `BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET`.
- `inverse_velocity.py`: `BLOCKED_NO_VERIFIED_COMMON_DATUM_SERIES`.
- `geometry_merge.py`: `BLOCKED_NO_COMPARABLE_ASC_DESC_SERIES`.
- `bound.py`: `NOT_APPLICABLE_GENERIC_AOI`.
- `pixel_stack.py`: separate GUNW relative LOS diagnostic.
- `candidate_check.py`: custom WKT skip if named-AOI assumptions are not met.

## Scientific assessment

This is the correct place to make non-execution visible, rather than running inappropriate point/event scripts with invented inputs. Do not change the meanings to make the stage list appear greener. Add a separately designed AOI-wide reference/uncertainty stage before enabling a target-free GUNW cumulative series.

**Verdict:** PASS for transparent gating and truthful status reporting; does not itself establish scientific accuracy.
