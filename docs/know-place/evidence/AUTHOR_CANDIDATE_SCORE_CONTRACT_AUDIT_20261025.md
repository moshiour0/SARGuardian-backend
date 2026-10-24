# Author candidate-score contract audit — 2026-10-25

## Finding

A direct, zero-download audit of the supplied Zenodo archive found an internal difference between the archived screen script and its deposited attributed candidate inventory. This issue should be resolved before a new expensive raw-data replay is used to claim complete full-footprint reproduction.

Source archive: `bhotekoshi2026_nisar_data-and-code_CC-BY-4.0.zip`, SHA-256 `002c2ba173a03693431b79578ca28d6b11e1ec00423d7533e82198871576c5e3`.

| Evidence | SHA-256 | Contents |
|---|---|---|
| `code/wide_screen.py` | `60e4238b9a10510f52a4673939a9708bf513d8bae460ba797d2dd27a1357d7c9` | Original candidate score assignment at line 198: `score = n_epochs × anom_m × R`. |
| `inventory/candidates_attributed.csv` | `519b527fbbbde7ab8a78365e5f5ee39e66837fd5ea942b8196d4368c1e1e3f9d` | 106 candidate rows, including score, centroid coherence `R`, zone-aggregated `R_res`, and `quality`. |

## Arithmetic result on all 106 archived rows

I recomputed both candidate-score expressions from each deposited CSV row, with no raw GOFF processing:

| Expression | Exact matches to the archived `score` column |
|---|---:|
| `n_epochs × anom_m × R` — expression in archived `wide_screen.py` | **0 / 106** |
| `n_epochs × anom_m × R_res` — uses the row's zone-aggregated residual coherence | **106 / 106** |

For example, the first inventory row stores `n_epochs=5`, `anom_m=4.51`, `R=0.992`, `R_res=0.9323059800598357`, and `score=21.023499850349292`. The stored score equals the second expression, not the first.

The `candidate_attributes.py` archived copy assigns the per-zone `R_res` and other attributes, but does not overwrite `score` in the inspected source. Therefore, the deposited output and the inspected screen script are not score-contract-identical. The current full-footprint runner keeps the screen-script formula and compares the score field strictly, so it should report a mismatch rather than silently adopting the output-derived formula.

## 106 candidates versus 101 validated zones

The archive has **106** rows in `inventory/candidates_attributed.csv`. The `quality` flag is true for **101** and false for five zones. The archived `screen_diagnostics.py` defines quality as `R_res >= 0.75 and d_downslope < 45°`. Separately, `tables/TableS7_all_validated_zones.csv` contains the 101 validated rows. The full-footprint comparator has been corrected to compare these as two distinct targets:
- all 106 candidate rows, including the archived quality flag;
- the 101 directional/quality-passing rows against Table S7 at its displayed numeric precision.

The exact RGI 6.0 polygons are not packaged in this archive, so the comparator does not independently reproduce `glacier`, `RGIId`, or nearest-glacier distance fields.

## How the code now treats the finding

`tools/know_place/author_footprint_replay.py` now:
1. compares all 106 candidate records, not only the 101 quality-true rows;
2. compares the resulting 101 quality-passing features against Table S7;
3. emits a `score_formula_audit` distinguishing the screen-script score expression from the alternative expression that matches the deposited inventory;
4. fails the strict full-footprint parity gate if any candidate score or other compared attribute is inconsistent with the author-deposited inventory.

The final replay gate will also require all three aggregate screen rasters to match. This is intentional: green status must not hide a reproducibility conflict in the candidate score/ranking.

## Validation boundary and decision

The arithmetic above is directly reproducible from the supplied archive and does not consume raw NISAR payloads. The updated source runner and CI tests are being validated on `feat/know-place-analysis`; **no new full-footprint raw replay has been launched**. A full replay can produce valuable rasters and per-pair evidence, but under the current strict score check it may correctly end with an explicit candidate-score mismatch.

Until the score convention is resolved against a source-authoritative specification, do not silently substitute `R_res` for `R`, do not claim full footprint candidate-score parity, and do not change `main`. Hazard detection remains `NOT_EVALUATED`.
