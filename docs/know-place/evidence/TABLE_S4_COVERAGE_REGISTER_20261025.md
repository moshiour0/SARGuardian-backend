# Supplementary Table S4 cell-coverage register — 2026-10-25

Source: author-deposited `tables/TableS4_site_series.csv/json` in Zenodo `10.5281/zenodo.22730419` (CC BY 4.0). Five intervals × 19 metric columns = **95 metric cells**; the pair identifier and `days` column are not included in this metric count.

This register is scoped to the latest completed raw replay, [run 40128950105](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40128950105), plus independently repeatable post-run checks documented in [the run audit](AUTHOR_EXACT_RUN_40128950105_AUDIT_20261025.md). Subsequent code/CI work adds a halo-aware P2 implementation, but run 40128950105 predates that implementation and therefore supplies no P2 result.

| Table S4 metric column | Cells | State as of this register | Evidence / reason |
|---|---:|---|---|
| `crown_disp_m` | 5 | **Verified** | Exact author site-series runner compared the median crown displacement against the archive at published precision. |
| `crown_rate_cm_per_day` | 5 | **Verified** | Calculated from the crown median and exact pair duration; matched archive rounding. |
| `P1_R_crown` | 5 | **Verified** | Bulk-reference P1 coherence; archive comparison passed. |
| `P1_R_bg` | 5 | **Verified** | P1 background coherence; archive comparison passed. |
| `P1_resolved` | 5 | **Verified (derived)** | Boolean reconstructed from the published P1 crown/background R inequality and checked against Table S4. |
| `P2_R_crown` | 5 | **Pending raw replay** | Halo-aware local-mean implementation now exists and synthetic tests pass, but these five values have not yet been compared on a run containing the 22-pixel context. |
| `P2_R_bg` | 5 | **Pending raw replay** | Same P2 requirement; background statistics must be computed from the actual residual field with context beyond the 6-km crop. |
| `P2_resolved` | 5 | **Pending raw replay** | Must be derived from P2 crown/background values after numerical parity is checked. |
| `polynull_R_crown` | 5 | **Verified** | Archive post-hoc polygon-null runner values passed the workflow comparison at published precision. |
| `polynull_R_box` | 5 | **Verified** | Same archive comparison. |
| `polynull_crown_pctile` | 5 | **Verified** | Same archive comparison; preserve its specified strict percentile convention. |
| `polynull_pct_beat_box` | 5 | **Verified** | Same archive comparison. |
| `polynull_n_draw` | 5 | **Verified** | Accepted random-candidate count matched the archived table. |
| `dispnull_crown_m` | 5 | **Blocked: missing draw-level method evidence** | The summary `tables/displacement_null.json` is available, but the Zenodo ZIP has no corresponding generator script or saved draw-level distribution. Do not copy the crown median into this separate table field by assumption. |
| `dispnull_null_med_m` | 5 | **Blocked: missing draw-level method evidence** | The null median depends on the exact candidate-generation and acceptance algorithm, which cannot be established from the supplied package. |
| `dispnull_pctile` | 5 | **Blocked: missing draw-level method evidence** | Exact percentile depends on the same absent draw-level method evidence. |
| `corescale_R_zone` | 5 | **Verified conditionally** | Recomputed at published precision from the run-derived raster, using the 0.19-km² candidate polygon supplied by the author archive. The screen selecting that polygon was not independently recreated. |
| `corescale_zone_pctile` | 5 | **Verified conditionally** | Recomputed using the author's archived `reconcile_scalebias.py` procedure and archived selected polygon. This is a scale diagnostic, not an unbiased detection test. |
| `corescale_npx` | 5 | **Verified conditionally** | All five source-archive zones contain 30 pixels for this diagnostic. Independent screen-selection parity remains unproven. |

## Totals

| Classification | Metric cells |
|---|---:|
| Directly checked by the 65-check site/polygon workflow | 45 |
| P1 booleans derived from already-verified P1 values | 5 |
| Core-scale metrics independently recalculated, conditioned on archived candidate geometry | 15 |
| **Verified or conditionally verified** | **65 / 95** |
| **Pending P2 local-mean parity** | **15** |
| **Blocked displacement-null parity** | **15** |
| **Total unverified** | **30 / 95** |

The 65/65 workflow result means only that its **selected 65 comparisons** passed. It is not a statement that all 95 Table S4 cells match.

## Next gates

1. Run the updated author-exact workflow only after explicit `[run-know-place]` consent. Its new final gate independently requires the 65 existing checks **and** all 15 P2 values to match the archive at the published precision. The current green run predates the P2 method and cannot satisfy that new gate retroactively.
2. Keep displacement-null marked blocked until the author’s exact script or draw-level data is located. If it cannot be retrieved, report the limitation rather than tuning a plausible algorithm to the published answers.
3. Keep full-footprint screening and hazard-detection statuses separate; neither is validated by the 65/95 site-scale coverage.
4. Do not merge this branch into `main` as part of the verification exercise.
