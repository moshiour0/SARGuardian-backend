# Extended ASF catalog audit: unresolved first author P05023 GOFF pair

**Checked:** 2026-10-24 UTC  
**Isolated branch:** `feat/know-place-analysis`  
**Catalog workflow run:** [40054946010](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40054946010)  
**Catalog artifact:** `know-place-author-live-asf-catalog-evidence`, artifact ID `12544428178`, ZIP bytes 1,561, SHA-256 `cf23a0893ae6b08f18abb379a76e483edf99c8f1f37a020c552f82adbcb07711`.

## Query sequence and outcome

The target is the author-specified granule

`NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_P05023_N_F_J_001`

for **2026-06-20 → 2026-07-02**, PR, ascending track 098, HH, and collection `NISAR_L2_GOFF_PROVISIONAL_V1`.

| Query | Result |
|---|---|
| Direct exact `granule_list` query for the author P05023 ID | `NOT_FOUND` |
| AOI + inclusive date range + GOFF + HH | 5 catalog results; one same-interval/track/direction candidate |
| Wildcard release-variant query (`…20260702T233955_*_N_F_J_001`) | 1 catalog result |
| Exact author P05023 found by either fallback | **No** |
| Source GOFF downloads from these queries | **0** |

The sole same-interval candidate in both fallback searches is:

`NISAR_L2_PR_GOFF_023_098_A_016_024_4000_SH_20260620T233921_20260620T233956_20260702T233920_20260702T233955_X05026_N_F_J_001`

with `release_id=X05026`, recorded as `SAME_INTERVAL_VARIANT_CANDIDATE_ONLY`. The manifest remains `BLOCKED` with one blocking author product. The author P05023 identity has not been recovered; no source SHA-256 exists because the payload was not downloaded.

ASF's published search documentation describes `granule_list` wildcard queries and notes that NISAR CMR has limited searchable extra attributes, making granule-name patterns useful for catalog-only discovery: [wildcard query guidance](https://docs.asf.alaska.edu/datasets/wildcard_usage/), [NISAR ASF search guide](https://nisar-docs.asf.alaska.edu/asf-search/). The extra wildcard query confirms the same variant returned by spatial/time search but does not produce the exact P05023 record.

## Validation

- Isolated validation run [40054946010](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40054946010) completed successfully.
- **188 tests passed in 6.78 seconds**.
- All six Know Place workflows parsed; pinned `actionlint` v1.7.12 checksum and semantic workflow checks passed.
- Both the historical-candidate and author-exact catalog jobs completed. These searches did not download GOFF payloads.

## Scientific disposition

- The first P05023 input remains `NOT_FOUND / UNRESOLVED`; do not substitute X05026.
- The four other author P05023 identifiers have trusted collection-route evidence only. Their HDF5 bytes and SHA-256 hashes remain unverified.
- Paper reproduction remains `BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED`.
- Hazard detection remains `NOT_EVALUATED`.
- Raw analysis was skipped in [run 40054945959](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40054945959), because the repository's explicit `[run-know-place]` consent marker was not supplied.
- Main remained at `2218dfeb73353080d8d94bd733d9e7bd9a848886`; no merge or main-branch write occurred.
