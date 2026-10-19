# SARGuardian Retention Audit — Validation Results (বাংলা)

**তারিখ:** ১৯ অক্টোবর ২০২৬
**অবস্থা:** Code/synthetic validation complete; real-product validation pending.

## Local validation

- Retention package tests: **22 passed** (`python -m pytest -q tests/`) when the main-source snapshot is present in the full audit bundle. In the smaller GitHub patch ZIP, the suite is designed for **21 passed, 1 skipped** because it intentionally does not bundle a second copy of the main science repository.
- Main SARGuardian scientific-engine tests: **178 passed**, with two known NumPy warnings in the test covering undefined correlation (`tests/test_troposphere.py`).
- GitHub Actions workflow: YAML parsed; 13 steps, 9 embedded Bash run blocks; all 9 passed `bash -n`.
- Machine-readable manifest JSON: parsed successfully.
- The provided main/backend ZIP SHA-256 values match the input snapshots copied into this bundle.
- Four critical scientific-source Git blob hashes (`gunw_reader.py`, `goff_reader.py`, `timeseries.py`, `paths.py`) match the pinned public science commit used by the workflow.

## Not yet validated

- No raw NISAR `.h5`/`.hdf5` product was present in either uploaded ZIP, so no real-product dataset inventory, schema, retention size, compression ratio, or live reader equivalence was measured.
- Google Drive OAuth credentials were not supplied or used; no real remote upload, remote checksum check, quota preflight, or sharing-permission check was run.
- The workflow was not dispatched on GitHub from this environment.
- The current workflow is a single-granule retention pilot, not the complete public user queue or the full multi-product GUNW+GOFF processing service.

## Data safety policy

- The archive builder never deletes the input file.
- The workflow has **no explicit raw-file delete step**. GitHub-hosted runner storage is ephemeral, so raw files are discarded by the host at job end; if the job fails, the next run must download the original product again.
- The pilot uploads a curated HDF5 only—not the original raw path—plus inventory/manifests/provenance/reader-equivalence receipts. The default pilot run excludes only the multidimensional GUNW `wrappedInterferogram` raster to preserve current-engine dependencies without accidentally uploading a source-sized data archive. Setting `include_wrapped=true` is explicit and may leave the archive near source size, potentially failing the Drive quota check.
- The archiver CLI compact mode excludes only the multidimensional GUNW `wrappedInterferogram` raster; all companion datasets and all other datasets are kept. This loses the original wrapped complex samples for possible future wrapped-phase/unwrapping methods, so do not choose it until that scope trade-off is explicitly accepted.
- **No automatic production deletion is authorized.** Real GUNW and GOFF pilots, whole-stack regression, output comparison, remote archive verification and scientific review are required before designing a deletion step.
