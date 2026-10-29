# Mandatory SARGuardian Scientific Regression Guard

This backend's Find Displacements pipeline is subject to the **canonical mandatory guard** in the science repository:

- Canonical document: [`docs/SCIENTIFIC_REGRESSION_GUARD.md`](https://github.com/moshiour0/SARGuardian/blob/65443092ee47f9eaf71eed7887313869d655f09b/docs/SCIENTIFIC_REGRESSION_GUARD.md)
- Immutable revision containing the guard: `65443092ee47f9eaf71eed7887313869d655f09b`
- Canonical working branch for the associated science fixes: `fix/science-regression-guards-20261029`

Every AI or contributor changing this backend, the dashboard builder, scientific stage orchestration, or the AOI-wide candidate screen must read the canonical guard before making a change. The guard is normative: it defines pixel-attrition accounting, GUNW/GOFF mask and reference invariants, temporal inversion preconditions, synthetic truth/null tests, workflow/UI integration requirements, release blockers, and scientific wording.

Do not silently copy an outdated version of the guard into another file. When the canonical guard changes, update this pointer to the new immutable commit and review the backend against the revised requirements.

**Feature separation:** Find Displacements must search the full submitted AOI without requiring a hand-selected target/crown. Known Place Analysis remains a separate deeper-analysis workflow.

**Branch protection for this task:** make changes only on `fix/find-displacements-science-20261029` (and the linked science-fix branch above). Do not edit or merge into `main` without separate explicit authorization.

A workflow or code test passing does not by itself establish geophysical accuracy. Any unresolved gate, threshold, datum, uncertainty, or lack of real-data validation must remain visible as unresolved.
