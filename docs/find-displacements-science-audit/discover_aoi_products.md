# Workflow audit: `tools/discover_aoi_products.py`

**Workflow:** `sarguardian-aoi-wkt-dashboard.yml`  
**Backend revision:** `78bc24b9b2c163d4ea899eeaf3793fbf9974e4d4`  
**Science pin:** `f038e4dfdb53c8d9793aaaefe173570a1032026c`

## Role

Validates the submitted AOI/date contract against NISAR/ASF catalogue records and emits the exact-product manifest. It is a discovery/selection component, not a displacement measurement.

The manifest is the provenance boundary for all subsequent workers: exact granule/product ID, GUNW/GOFF family, acquisition dates, processing maturity/CRID and source identity must remain available downstream. The requested date-window mode matters: current default is secondary-acquisition-in-window, which can intentionally include a pair whose reference acquisition predates the selected start date. This must be explained in the run report and must not be mistaken for an out-of-range bug.

## Scientific checks

- Keep granule identity and CRID; do not join by dates alone.
- Keep BETA and PROVISIONAL product maturity visible. ASF warns BETA products are not fully calibrated; current PROVISIONAL collections are calibrated but still partially validated and subject to improvements.
- Record the exact normalized AOI hash and date-filter mode.
- Report expected count and all excluded/ineligible catalogue records; do not interpret no catalogue results as no movement.

## Validation required

Test date boundary inclusion, exact polygon intersection, duplicate products, CRID maturity consistency and catalogue pagination/coverage against fixed catalogue snapshots. Product availability is not a scientific detection result.

**Verdict:** selection/provenance stage; not a movement estimator.
