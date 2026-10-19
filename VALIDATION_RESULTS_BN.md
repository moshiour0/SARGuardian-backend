# SARGuardian Retention Audit — Validation Results (বাংলা)

**তারিখ:** ২০ অক্টোবর ২০২৬
**অবস্থা:** Real GUNW download/inventory exercised; first real archive attempt failed closed on coordinate dimension-scale attributes. Corrective branch adds scale reconstruction and a verified wrapped-phase derivative; CI and a fresh live run are still required.

## Local validation

- Retention package tests: **22 passed** (`python -m pytest -q tests/`) when the main-source snapshot is present in the full audit bundle. In the smaller GitHub patch ZIP, the suite is designed for **21 passed, 1 skipped** because it intentionally does not bundle a second copy of the main science repository.
- Main SARGuardian scientific-engine tests: **178 passed**, with two known NumPy warnings in the test covering undefined correlation (`tests/test_troposphere.py`).
- GitHub Actions workflow: YAML parsed; 13 steps, 9 embedded Bash run blocks; all 9 passed `bash -n`.
- Machine-readable manifest JSON: parsed successfully.
- The provided main/backend ZIP SHA-256 values match the input snapshots copied into this bundle.
- Four critical scientific-source Git blob hashes (`gunw_reader.py`, `goff_reader.py`, `timeseries.py`, `paths.py`) match the pinned public science commit used by the workflow.

## Not yet validated

- A live GUNW pilot downloaded a real 2,411,724,800-byte product and inventoried 219 datasets / 45 groups. Archive generation failed closed because empty-name `xCoordinates` and `yCoordinates` dimension-scale metadata did not compare equal. Reader-equivalence and Google Drive upload steps were not reached; no real archive or remote checksum was verified. The corrective branch now recreates actual scales and adds phase-domain derivation, but must pass CI and a fresh live run.
- Google Drive OAuth credentials were not supplied or used; no real remote upload, remote checksum check, quota preflight, or sharing-permission check was run.
- The workflow was not dispatched on GitHub from this environment.
- The current workflow is a single-granule retention pilot, not the complete public user queue or the full multi-product GUNW+GOFF processing service.

## Data safety policy

- The archive builder never deletes the input file.
- The workflow has **no explicit raw-file delete step**. GitHub-hosted runner storage is ephemeral, so raw files are discarded by the host at job end; if the job fails, the next run must download the original product again.
- The pilot uploads a curated HDF5 only—not the original raw path—plus inventory/manifests/provenance/reader-equivalence receipts, after all verification gates pass. Compact mode excludes the original multidimensional GUNW `wrappedInterferogram` complex array, but creates and retains a sibling `wrappedPhase` float array in radians derived with chunked `numpy.angle`; coherence, coordinate axes and other datasets remain retained. This is not spatial phase unwrapping and does not preserve complex amplitude.
- If future algorithms need original complex samples or amplitude information, set `include_wrapped=true`; this retains the original complex array as well as derived phase, and the archive may approach source size or exceed Drive quota. The option is not silently changed by the workflow.
- **No automatic production deletion is authorized.** Real GUNW and GOFF pilots, whole-stack regression, output comparison, remote archive verification and scientific review are required before designing a deletion step.
