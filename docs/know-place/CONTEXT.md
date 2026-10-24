# Know Place Analysis — Living Context (read first)

**Last reviewed:** 2026-10-24  
**Repository:** [moshiour0/SARGuardian-backend](https://github.com/moshiour0/SARGuardian-backend)  
**Working branch:** feat/know-place-analysis  
**Starting commit for the current count-estimand correction:** f258b1033ea114b7e9a72d6e6bb71565a1281430  
**Purpose:** durable handoff for future ChatGPT sessions. Read this file and the linked blueprint/checklist before continuing; update it whenever material code, evidence, decisions, validation status, or blockers change.

## 1. Non-negotiable rules

- All Know Place work stays isolated on feat/know-place-analysis. Never commit, merge, cherry-pick or otherwise write Know Place changes to main.
- The known main-branch baseline supplied for this task is 2218dfeb73353080d8d94bd733d9e7bd9a848886; previous branch validation reported main unchanged. Always verify refs before any operation that could affect them.
- **Do not run a raw GOFF replay/download workflow unless the user explicitly authorizes it using the exact consent marker [run-know-place].** Do not infer authorization from a general request to continue the audit. No raw replay is authorized by this context update.
- Scientific claims are fail-closed. Do not claim paper reproduction, source-data parity, full-footprint reproduction, hazard detection, prediction skill, or operational early warning without direct and suitable evidence.
- Never silently replace or relabel the author-exact first-pair P05023 product as the historical X05026 variant.
- Preserve the licensing boundary in Zenodo DOI https://doi.org/10.5281/zenodo.22730419: the main archive is CC BY 4.0 except the separate extent_CC-BY-NC-4.0 runout outline, which is CC BY-NC 4.0. Do not copy that extent into this repository or treat it as CC BY 4.0.
- Preserve the distinction between displacement-valid pixels, R-valid coherence pixels, P1, P2, polygon-null and displacement-null estimands. Never compare their counts or percentiles as though they measured the same thing.

## 2. Current verified state

### Repository and validation baseline

- Branch exists: feat/know-place-analysis.
- Branch head at the start of this correction: f258b1033ea114b7e9a72d6e6bb71565a1281430.
- Previous baseline validation: [run 40040361146](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40040361146), with 141 tests passed before this correction.
- **Latest validation of the corrected code/test tree:** [run 40043977505](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40043977505), testing commit 6e802df389ab38030cfb36fd08a656f736d2dad3. Result: **141 tests passed**, four workflow YAML files parsed, actionlint passed, and both validation jobs succeeded. Live ASF checks downloaded **zero raw products**; the exact first-pair author P05023 ID remains NOT_FOUND, and author-exact reproduction remains BLOCKED.
- The corresponding raw-replay workflow event was [run 40043977478](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40043977478); its consent-decision job succeeded and the actual five-pair analysis job was **skipped** because the commit lacked [run-know-place]. No raw GOFF replay was authorized or executed.
- This context-only refresh follows the tested code/test commit and does not change code/test files. Any subsequent code or test change requires fresh validation.
- Use the isolated validation workflow at .github/workflows/know-place-analysis-validation.yml and the AOI analysis workflow at .github/workflows/know-place-aoi-analysis.yml. A pushed change to tools/tests/test_know_place_*.py triggers isolated validation. The validation workflow's live ASF job is catalog-only and must not download products.
- Do not run the separate expensive raw replay job without [run-know-place].

### Scientific status (must not be relaxed)

- **Paper reproduction:** BLOCKED_RAW_GOFF_BYTES_AND_IMPLEMENTATION_PARITY_UNVERIFIED.
- **Hazard detection:** NOT_EVALUATED.
- **Operational status:** blocked; no calibrated risk score or operational alarm.
- Archive integrity/payload audit: pass.
- Exported derived-R band vs recomputation from archived dE/dN: pass.
- Exact source-product parity, original GOFF source-grid mask parity, full-footprint replay, and independent event/non-event validation: not established.

## 3. Author archive: byte integrity and actual contents

User-supplied source: [Zenodo record](https://doi.org/10.5281/zenodo.22730419), “Bhote Koshi 2026 ice–rock avalanche: NISAR L2 GOFF site series and footprint-wide offset-tracking screen — data and code”.

- ZIP: bhotekoshi2026_nisar_data-and-code_CC-BY-4.0.zip
- ZIP size: 183389034 bytes
- MD5: b07b7eb3b3178d3f69d5bca009cb0db4
- SHA-256: 002c2ba173a03693431b79578ca28d6b11e1ec00423d7533e82198871576c5e3
- ZIP integrity: PASS; 90 manifest-listed in-ZIP payloads match declared size and MD5, with zero mismatches.
- Contents include author scripts, five small processed site-field GeoTIFFs, tables/null distributions, the 101-zone inventory and three footprint-screen rasters.
- The ZIP does **not** contain the five raw source GOFF HDF5 granules or the five full-footprint 4230 × 4311 per-pair offset rasters.
- The five exported TIFFs are 80 × 73 pixels, EPSG:4326, three bands (dE, dN, R). This disagrees with the README's stated four-band EPSG:32645 field profile; preserve and report that documentation/profile inconsistency.
- The archive's tables/TableS7_all_validated_zones.csv is byte-identical to the supplied 101-zone CSV after the documented source-byte/line-ending handling. The post-event zone inventory is not an independent prospective validation set.
- Detailed evidence: docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md; reference records: docs/know-place/reference/author_archive_golden_v1.json and author_benchmark_v1.json.

## 4. Critical metric correction — completed 2026-10-24

### What was wrong

An earlier diagnostic incorrectly compared:
- displacement-valid crown cells from tables/nisar_pot_series.json field n; against
- polygon-null coherence-valid crown cells from tables/polygon_null.json field n_px.

These are different estimands. The prior statement that 296 displacement-valid pixels disagreed with 298 R-valid cells was wrong and must not be repeated.

### Independent recomputation on all five exported fields

The archive was read directly. For each field, I recomputed the author's 5 × 5 directional-coherence map using scipy.ndimage.uniform_filter default reflected edges, finite-vector normalization, and finite-support fraction strictly greater than 0.5. I then applied the exact author crown_slice policy using the exported GeoTIFF bounds as extent endpoints. This diagnoses the **exported raster grids only**, not the original GOFF source-grid mask.

| Pair | Displacement-valid crown cells (export / nisar_pot_series.json:n) | R-valid crown cells (export / polygon_null.json:n_px) |
|---|---:|---:|
| 2026-06-20 → 2026-07-02 | 283 / 283 | 302 / 302 |
| 2026-07-02 → 2026-07-14 | 294 / 294 | 299 / 299 |
| 2026-07-14 → 2026-07-26 | 296 / 296 | 302 / 302 |
| 2026-07-26 → 2026-08-19 | 292 / 292 | 298 / 298 |
| 2026-08-19 → 2026-08-31 | 195 / 195 | 202 / 202 |

Results:
- Difference from each corresponding source-table count is zero for all five pairs, for both estimands.
- Full-field recomputed-R finite masks equal archived TIFF band 3 finite masks for all five fields.
- Maximum absolute R-band error across the five fields is 3.4930149217515805e-8, below 1e-6.
- This resolves the former **count comparison** error. It does **not** establish exact pixelwise mask parity on the original GOFF source grid. The original source coordinate vectors/read window and pre-export author masks/rasterization extents are absent; the reason for any source-grid mask difference remains unresolved. **Do not invent a cause.**

Machine-readable per-field details are in docs/know-place/reference/author_archive_golden_v1.json. The benchmark was also corrected to schema v1.1 in docs/know-place/reference/author_benchmark_v1.json: displacement_valid_crown_pixels references nisar_pot_series.json key n; polygon_null_R_valid_crown_pixels references polygon_null.json key n_px; the ambiguous legacy valid_crown_pixels key was removed. Both tools/tests/test_know_place_author_archive.py and tools/tests/test_know_place_author_reference_data.py enforce the separation. Full audit: docs/know-place/evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md.

## 5. Exact author source IDs and historical variant warning

The supplied Research Square paper and Supplementary Information identify five ascending T098, L-SAR HH, GOFF layer-2 pairs, all with P05023. The authoritative manifest is docs/know-place/reference/author_benchmark_v1.json.

- 2026-06-20 → 2026-07-02: author P05023 ID returned NOT_FOUND in live ASF lookup.
- 2026-07-02 → 2026-07-14: P05023; route found.
- 2026-07-14 → 2026-07-26: P05023; route found.
- 2026-07-26 → 2026-08-19: P05023; route found.
- 2026-08-19 → 2026-08-31: P05023; route found.

The historical replay used X05026 for the first pair. Its hash remains valid for those historical bytes only; it is **not** an author-exact source substitute. Four of five P05023 routes do not mean the raw bytes have been downloaded or hashed. Original GOFF source SHA-256 values for the exact author five-product set, especially the first P05023 ID, are not pinned in this archive.

## 6. Author method facts that must remain distinct

Implementation kernels live in tools/know_place/author_parity.py; offline tests live in tools/tests/test_know_place_author_parity.py; processed-field integrity check is tools/know_place/verify_author_fields.py.

- Author site-series geometry uses the nearest radarGrid sample at the stated crown coordinate, then a median of each geometry component over the height axis. The current exploratory runner's fixed-height per-pixel geometry is not equivalent.
- Author source validity gate: finite SNR, SNR ≥ 5, and projected horizontal magnitude ≤ 10 m. Do not add correlationSurfacePeak as a validity gate for this author path.
- Author coherence kernel: 5 × 5 scipy.ndimage.uniform_filter, reflected edges, normalize using finite-vector support, retain finite support fraction > 0.5 (at least 13/25 vectors).
- Author stable-reference correction is applied only if the valid outside-AOI ring has **more than 200 cells**.
- Author P1 crown coherence is calculated **after cropping** to the crown. Full-box/background R and polygon-null R are different estimators.
- polygon_null.py uses a shared RNG sequence with seed 20260907; unique candidate centres sampled without replacement from all finite-R cells; radius sqrt(n_px/pi); accept a disk if at least 60% of target valid cells are present; strict comparisons (draw < crown, draw > box). This is not the same as displacement null, P1, or P2.
- The archive has no standalone displacement_null.py despite a planned reference to it; its output table is present. Exact generator parity for displacement-null cannot be claimed solely from that missing script.

Always label P1, P2, polygon-null and displacement-null separately.

## 7. Design blueprint and validation gates

Read these before implementing further changes:
1. [Scientific architecture blueprint](../KNOW_PLACE_ANALYSIS_BLUEPRINT.md)
2. [Engineering & scientific checklist](../KNOW_PLACE_ANALYSIS_CHECKLIST.md)
3. [Isolated runbook](../KNOW_PLACE_ANALYSIS_RUNBOOK.md)
4. [Multi-event validation plan](validation/MULTI_EVENT_VALIDATION_PLAN.md)
5. [Author-supplement retrieval audit](evidence/AUTHOR_SUPPLEMENT_RETRIEVAL_AUDIT_20261024.md)
6. [Raw replay and R-policy audit](evidence/RAW_REPLAY_40006999011_R_POLICY_AUDIT.md)
7. [Zenodo author archive audit](evidence/ZENODO_AUTHOR_ARCHIVE_AUDIT_20261024.md)
8. [Author archive golden/reference fixture](reference/author_archive_golden_v1.json)
9. [Offline regression test](../../tools/tests/test_know_place_author_archive.py)
10. [Isolated validation workflow](../../.github/workflows/know-place-analysis-validation.yml)

Promotion gates from the multi-event validation plan:
- **G0 structural:** schemas, exact identity metadata, hashes, grid checks and synthetic known-answer tests.
- **G1 measurement:** vector projection/sign/units, source masks, georeferencing and provenance independently verified.
- **G2 paper parity:** exact raw source IDs/bytes, author geometry/method, pixelwise/summarized golden comparisons.
- **G3 external validation:** independently labelled event and non-event cohort, held-out evaluation, uncertainty and false-alarm reporting.
- **G4 operational research pilot:** terrain-backed geometry, cadence/latency, drift, no-result behavior and human review.

Current state: archive integrity and exported derived-R verification pass; the correction above resolves count-estimand bookkeeping. Full source input and author-method parity are still **BLOCKED** (below G2), G1 remains partial, G3/G4 are blocked, and hazard detection remains **NOT_EVALUATED**.

## 8. Next actions — continue in this order

- [x] Inspect blueprint, checklist, runbook, source/validation audits, author archive fixture, author kernel and archive verifier.
- [x] Recompute displacement-valid and R-valid crown counts independently from all five exported fields and separate the two estimands in machine-readable evidence.
- [x] Correct both the author-archive diagnostic and benchmark fixture so displacement-valid n and polygon-null R-valid n_px are separate. CI passed in [run 40043977505](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40043977505), with 141 tests, four workflow YAML parses and actionlint passing. The ASF job downloaded zero products; the raw-replay job was skipped for lack of explicit consent.
- [ ] Extend same-estimand comparison of archived per-pair tables and raster statistics; keep P1/P2/polygon-null/displacement-null separate.
- [ ] Continue integrating the isolated author-parity path, always testing against archived processed fields/tables without silently changing the exploratory runner.
- [ ] Resolve and SHA-256-pin the exact first-pair P05023 GOFF HDF5 bytes and verify all five author-exact raw inputs; do not substitute X05026.
- [ ] Only after explicit [run-know-place] authorization and exact input pins, run the gated raw source replay.
- [ ] Recreate the full-footprint outputs from documented exact sources and author method; archived full-footprint per-pair offset rasters are absent.
- [ ] Assemble the independent event/non-event registry and held-out evaluation under the pre-registered multi-event plan. The 101-zone post-event inventory is not a prospective holdout.

## 9. Update protocol for future chats

When continuing from a new chat:
1. Read this file first, then KNOW_PLACE_ANALYSIS_BLUEPRINT.md, KNOW_PLACE_ANALYSIS_CHECKLIST.md, and the relevant evidence report.
2. Verify the current branch head, main SHA, and latest validation run; do not assume SHAs/results remain current.
3. Inspect the exact current files and their diff before editing; do not reapply old fixes blindly.
4. Keep an evidence ledger: what ran, inputs/hashes, output hashes, tested commit SHA, CI run URL, and any skipped expensive jobs.
5. Update this file as part of the same branch-only work whenever a scientific decision, blocker, code path, test or validation state changes.
6. Never mark a checklist item complete unless inspectable evidence supports the exact claim.
