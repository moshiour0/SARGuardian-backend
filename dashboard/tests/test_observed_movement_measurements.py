from __future__ import annotations

import csv
import json

from dashboard.observed_movement_measurements import (
    SERIES_AVAILABLE,
    build_observed_movement_report,
)


def component(status=SERIES_AVAILABLE, field="cumulative_los_mm", values=(0.0, 5.0, 9.0)):
    return {
        "network": "ASC path 98 frame 2 CRID P05023 GUNW",
        "component": 1,
        "status": status,
        "first_epoch": "2026-01-01",
        "last_epoch": "2026-01-25",
        "epochs_count": len(values),
        "pairs_count": len(values) + 1,
        "redundancy": 1,
        "velocity_mm_per_day": 0.3,
        "velocity_fit_error_mm_per_day": 0.05,
        "series": [
            {
                "epoch": epoch,
                field: value,
                "graph_fit_standard_error_mm": 0.25,
            }
            for epoch, value in zip(
                ("2026-01-01", "2026-01-13", "2026-01-25")[:len(values)],
                values,
            )
        ],
    }


def test_builds_target_relative_movement_from_only_gate_approved_components(tmp_path):
    gunw = {
        "status": SERIES_AVAILABLE,
        "aoi_wkt_sha256": "a" * 64,
        "components": [
            component(),
            component(status="WITHHELD_NO_REDUNDANT_ROBUST_NETWORK"),
        ],
        # Pairwise rows are explicitly not promoted to a displacement series.
        "pairwise_measurements": [
            {"reference_date": "2026-01-01", "secondary_date": "2026-01-13", "target_mm_common_datum": 50.0}
        ],
    }
    goff_component = component(field="cumulative_offset_mm", values=(10.0, 7.0, 4.0))
    goff_component["network"] = "ASC path 98 frame 2 CRID P05023 GOFF"
    goff_component["component"] = "RANGE"
    goff = {
        "status": SERIES_AVAILABLE,
        "components": [goff_component],
        "aoi_wkt_sha256": "a" * 64,
    }

    report = build_observed_movement_report(gunw, goff, tmp_path)

    assert report["status"] == "OBSERVED_MOVEMENT_MEASUREMENTS_AVAILABLE"
    assert report["measurement_count"] == 2
    assert {row["measurement_family"] for row in report["measurements"]} == {"GUNW_LOS", "GOFF_OFFSET"}
    gunw_row = next(row for row in report["measurements"] if row["measurement_family"] == "GUNW_LOS")
    goff_row = next(row for row in report["measurements"] if row["measurement_family"] == "GOFF_OFFSET")
    assert gunw_row["net_change_from_first_epoch_mm"] == 9.0
    assert gunw_row["duration_days"] == 24
    assert gunw_row["endpoint_rate_mm_per_day"] == 9.0 / 24
    assert goff_row["net_change_from_first_epoch_mm"] == -6.0
    assert gunw_row["independent_geophysical_validation"] is False
    assert gunw_row["series"][-1]["relative_to_first_epoch_mm"] == 9.0

    saved = json.loads((tmp_path / "observed-movement-measurements.json").read_text(encoding="utf-8"))
    assert saved["measurement_count"] == 2
    with (tmp_path / "observed-movement-measurements.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert {row["measurement_family"] for row in rows} == {"GUNW_LOS", "GOFF_OFFSET"}


def test_does_not_promote_pairwise_rows_when_common_reference_gate_is_blocked(tmp_path):
    report = build_observed_movement_report(
        {"status": "BLOCKED_NO_VALID_IN_AOI_TARGET", "components": [], "pairwise_measurements": [{"value": 20}]},
        {"status": "BLOCKED_NO_VALID_IN_AOI_TARGET", "components": [], "pairwise_measurements": [{"value": 30}]},
        tmp_path,
    )

    assert report["status"] == "NO_QUALIFYING_DIAGNOSTIC_MOVEMENT_SERIES"
    assert report["measurement_count"] == 0
    assert report["measurements"] == []
    csv_text = (tmp_path / "observed-movement-measurements.csv").read_text(encoding="utf-8")
    assert "cumulative_value_mm" in csv_text
    assert len(csv_text.splitlines()) == 1


def test_rejects_series_with_duplicate_or_unordered_epochs(tmp_path):
    bad = component()
    bad["series"][1]["epoch"] = bad["series"][0]["epoch"]
    report = build_observed_movement_report(
        {"status": SERIES_AVAILABLE, "components": [bad]},
        {},
        tmp_path,
    )
    assert report["measurement_count"] == 0


def test_rejects_series_with_fewer_than_three_actual_epochs(tmp_path):
    short = component(values=(0.0, 5.0))
    report = build_observed_movement_report(
        {"status": SERIES_AVAILABLE, "components": [short]},
        {},
        tmp_path,
    )
    assert report["measurement_count"] == 0


def test_rejects_nonfinite_and_missing_epoch_values(tmp_path):
    bad = component(values=(0.0, float("nan"), 8.0))
    report = build_observed_movement_report(
        {"status": SERIES_AVAILABLE, "components": [bad]},
        {},
        tmp_path,
    )
    assert report["measurement_count"] == 0
