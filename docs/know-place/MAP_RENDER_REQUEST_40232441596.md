# Render interactive map from the retained Bhote Koshi P05023 measurement

Request date: 2026-10-26

Use the already successful author-exact measurement from GitHub Actions run [#40232441596](https://github.com/moshiour0/SARGuardian-backend/actions/runs/40232441596), attempt 1, artifact `know-place-author-exact-40232441596-1`.

This request authorizes **rendering only from the existing derived-only artifact**. Do not re-download or read raw GOFF HDF5, do not re-run measurement, and do not alter/merge `main`.

Expected checks: five exact `P05023` intervals, source SHA alignment, preview bounds derived from native EPSG:32645 coordinate axes, explicit published-bounds crown-rectangle approximation note, no native-grid GeoTIFF link unless an actual such file is included, Chromium pair-selection smoke test for 26 July–19 August 2026, hazard status `NOT_EVALUATED`, and private Drive remote verification of the rendered map and receipts.

The map is a presentation layer: its preview is downsampled/warped and must not be treated as a remeasurement or operational warning.
