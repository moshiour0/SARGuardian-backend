# Exact author P05023 product resolved in NASA CMR catalog

**Checked:** 2026-10-24 UTC  
**Branch:** `feat/know-place-analysis`  
**Validation:** [run 40056005969](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005969) — 191 tests passed.  
**Catalog artifact:** ID `12544869799`, name `know-place-author-live-asf-catalog-evidence`, 2,823 bytes, SHA-256 `57426b152b6ab83001d5472d03786c1da78401e75f13018559a3619b6cf132f9`.

## Exact product recovered

The first author-selected pair is **2026-06-20 → 2026-07-02**, release `P05023`, PR, ascending track 098, HH:

`NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001`

ASF Search's direct-ID, AOI/date and wildcard paths did not return that row; the latter two surfaced the parallel `X05026` variant. A collection-scoped NASA CMR lookup then confirmed the exact producer-granule ID:

| CMR field | Value |
|---|---|
| CMR granule concept ID | `G4248299988-ASF` |
| Collection concept ID | `C2854341702-ASF` |
| Producer-granule ID | Exact P05023 ID above |
| Start | `2026-06-20T23:39:21.000Z` |
| End | `2026-07-02T23:39:55.999Z` |
| Updated | `2026-07-15T16:07:07.506Z` |
| Exact producer-ID query | HTTP 200, 1 result |
| Exact readable-granule-name query | HTTP 200, 1 result |

CMR's API documentation defines `producer_granule_id[]` and `readable_granule_name[]` as exact granule search filters and requires a collection-scoped query. References: [CMR Search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html), [official CMR date listing](https://cmr.earthdata.nasa.gov/virtual-directory/collections/C2854341702-ASF/temporal/2026/06/20).

## Official access URL returned by CMR

CMR returned this data endpoint for the exact HDF5:

**[Open P05023 HDF5 access URL](https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GOFF_PROVISIONAL_V1/NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001/NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001.h5)**

S3 URI from the same metadata:

`s3://sds-n-cumulus-prod-nisar-products/NISAR_L2_GOFF_PROVISIONAL_V1/NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001/NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001.h5`

These are catalog access routes, **not** proof that the payload downloaded. This catalog run downloaded zero GOFF payloads. The first product's byte size and SHA-256 remain unknown.

## Live five-product identity gate

| Interval | Identity status | SHA-256 |
|---|---|---|
| 2026-06-20 → 2026-07-02 | `EXACT_CMR_GRANULE_CONFIRMED` | Not downloaded |
| 2026-07-02 → 2026-07-14 | `EXACT_URL_CONFIRMED` | Not downloaded |
| 2026-07-14 → 2026-07-26 | `EXACT_URL_CONFIRMED` | Not downloaded |
| 2026-07-26 → 2026-08-19 | `EXACT_URL_CONFIRMED` | Not downloaded |
| 2026-08-19 → 2026-08-31 | `EXACT_URL_CONFIRMED` | Not downloaded |

Result: **catalog identity 5/5 confirmed; source SHA-256 pins 0/5; raw source downloads 0**. The workflow output correctly distinguishes `AUTHOR_CATALOG_IDENTITY_GATE=PASS` from `PAPER_REPRODUCTION_STATUS=BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`. `HAZARD_DETECTION_STATUS=NOT_EVALUATED`.

Raw replay run [40056005985](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40056005985) skipped its five-pair analysis job because `[run-know-place]` was not supplied. No merge or write to `main` occurred; its baseline is `2218dfeb73353080d8d94bd733d9e7bd9a848886`.
