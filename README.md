# SARGuardian Backend

A FastAPI backend foundation for multi-user SARGuardian jobs. User authentication is separate from the central server-side Google Drive storage identity.

## Local setup

```powershell
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python scripts/init_db.py
python -m uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Health check: `GET /health`.

## Authentication endpoints

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout` with `X-CSRF-Token`
- `GET /auth/me`
- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{job_id}`

Passwords are hashed with Argon2id. Sessions use opaque tokens whose hashes are stored in the database. The session cookie is HttpOnly; the CSRF cookie is readable by the application so it can be copied into the `X-CSRF-Token` header.

## Database

SQLite is the local default. Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL for deployment. Run `python scripts/init_db.py` locally; Alembic configuration is present under `alembic/` for migration revisions.

Google Drive settings are server-side only and are intentionally empty in `.env.example`. They must never be returned by API responses or sent to the browser.

## Jobs

Authenticated `POST /jobs` requests create queued, user-owned job records only. Science execution and Drive result storage are added in later phases. The server derives ownership from the authenticated session; a client-provided `user_id` is ignored.

## Science execution

`SCIENCE_MODE=mock` is the local default. It performs no Earthdata/NASA access and writes a deterministic four-file result package under `SCIENCE_RESULT_ROOT/<job_id>`.

`SCIENCE_MODE=real` invokes the configured `SCIENCE_REAL_COMMAND` after verifying that `SCIENCE_ROOT` is at commit `SCIENCE_EXPECTED_COMMIT`. The external runner must preserve the existing pinned GOFF processing and write the same four-file package. This backend layer does not copy or rewrite the scientific algorithm.

## Central Drive storage

Drive storage is server-side only. Set `DRIVE_MODE=real` and provide these values through the backend environment or secret manager:

- `GOOGLE_DRIVE_OAUTH_CLIENT_JSON`
- `GOOGLE_DRIVE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_PARENT_FOLDER_ID`

The refresh token must belong to the central `sarguardian.org@gmail.com` storage identity, not an end-user account. Never place these values in frontend configuration, browser storage, API responses, source files, or logs. `DRIVE_MODE=mock` is used for local tests and does not contact Google Drive.

## Science-data retention pilot

The non-destructive retention pilot lives in `.github/workflows/sarguardian-retention-pilot.yml`. It checks out the existing SARGuardian scientific engine at a fixed commit; it does not rewrite the scientific algorithm and it has no raw-source deletion step.

The default `engine-ready` profile keeps the native-resolution arrays used by the pinned readers and downstream LOS geometry: all GUNW `unwrappedInterferogram` and `pixelOffsets` datasets, all GOFF `pixelOffsets` layers/polarisations, scalar/1-D metadata and the GUNW `radarGrid` fields read by `geometry_merge.los_from_product`. It excludes high-posting GUNW `wrappedInterferogram`-grid rasters and other multidimensional fields that no pinned current `src/` processing path reads. Every exclusion is recorded with its path, shape, dtype and attributes alongside the full source inventory and source-file SHA-256.

Dataset copying uses HDF5's native object-copy operation to retain exact values and source chunks/compression filters without routing every pixel through Python and recompressing it. The archive still performs logical checksums, metadata/dimension-scale checks and raw-vs-curated reader equivalence. The `full-lossless` profile retains every dataset in supported standard NISAR HDF5 layouts. `include_wrapped=true` retains the whole high-posting wrapped grid; `derive_wrapped_phase=true` is an explicit optional phase-only derivative (radians), not spatial unwrapping and not a substitute for complex amplitude.

## Tests

```powershell
pytest
```

The science source and GitHub Actions workflows remain separate from this application foundation.

## Low-disk streaming processing for the Nepal source AOI

The sequential NISAR streaming workflow, its `validation-pilot` /
`full-source-baseline` profiles, default `derived-only` retention mode,
optional `full-lossless` archive mode, pre-cleanup baseline validation and
downstream parity gates are documented in
[docs/STREAMING_BATCH.md](docs/STREAMING_BATCH.md) and
[docs/RAW_HDF5_DEPENDENCY_AND_PARITY_PLAN.md](docs/RAW_HDF5_DEPENDENCY_AND_PARITY_PLAN.md).
The two-granule pilot and the 33-product source-baseline replay have now passed. See the run evidence and remaining scientific limits in `docs/STREAMING_BATCH.md` and `docs/RAW_HDF5_DEPENDENCY_AND_PARITY_PLAN.md`. The artifact-only replay is proven; the distinct full live `resume_from_run_id` recovery mode remains separately unverified.



## Dynamic AOI WKT processing (isolated feature branch)

The new WKT-driven NISAR acquisition and dashboard flow is documented in
[docs/DYNAMIC_AOI_WKT_E2E.md](docs/DYNAMIC_AOI_WKT_E2E.md). It lives on
`feat/final-aoi-science-integration` and uses the scientific AOI parser in
`science/aoi-wkt-dynamic-e2e`. The original
`feat/e2e-pinned-science-pipeline` workflow remains separate and unchanged.

The default-branch entry point
`.github/workflows/sarguardian-aoi-wkt-dispatcher.yml` only forwards inputs to
the isolated workflow; it does not replace or call the original source-AOI run.
