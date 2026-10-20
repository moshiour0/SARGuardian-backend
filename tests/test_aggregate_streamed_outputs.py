from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "aggregate_streamed_outputs.py"
spec = importlib.util.spec_from_file_location("aggregate_streamed_outputs", TOOL)
assert spec and spec.loader
agg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agg)


def test_stat_rows_key_by_product_and_layer():
    fields = ["file", "layer", "median", "maturity"]
    rows = [
        {"file": "A.h5", "layer": "HH/layer1", "median": "1", "maturity": "BETA"},
        {"file": "A.h5", "layer": "HH/layer2", "median": "2", "maturity": "BETA"},
        {"file": "B.h5", "layer": "HH/layer2", "median": "3", "maturity": "BETA"},
    ]
    assert len({agg.row_key(r, fields) for r in rows}) == 3


def test_candidate_floor_rows_do_not_collapse_to_same_file_key():
    fields = ["target_id", "file", "window_px", "local_floor_mm_day"]
    rows = [
        {"target_id": "1", "file": "A.h5", "window_px": "6", "local_floor_mm_day": "1.2"},
        {"target_id": "4", "file": "A.h5", "window_px": "6", "local_floor_mm_day": "2.4"},
        {"target_id": "4", "file": "A.h5", "window_px": "12", "local_floor_mm_day": "2.1"},
    ]
    assert len({agg.row_key(r, fields) for r in rows}) == 3


def test_common_reference_rows_key_by_target_pair_and_window():
    fields = ["target_id", "pair", "window_px", "datum_error_mm"]
    a = {"target_id": "4", "pair": "20260702_20260714", "window_px": "6", "datum_error_mm": "1.2"}
    b = {"target_id": "4", "pair": "20260714_20260726", "window_px": "6", "datum_error_mm": "-0.3"}
    assert agg.row_key(a, fields) != agg.row_key(b, fields)


def test_timeseries_rows_key_by_geometry_component_epoch():
    fields = ["geometry", "component", "epoch", "cumulative_mm"]
    a = {"geometry": "ASC", "component": "range", "epoch": "2026-07-01", "cumulative_mm": "1"}
    b = {"geometry": "ASC", "component": "range", "epoch": "2026-07-13", "cumulative_mm": "2"}
    assert agg.row_key(a, fields) != agg.row_key(b, fields)


def test_numeric_comparison_has_explicit_small_tolerance():
    assert agg.value_equal("10.00000", "10.00001", "median")
    assert not agg.value_equal("10.0", "10.1", "median")
    assert agg.value_equal("file.tif", "file.tif", "export_file")


def test_compare_rows_detects_missing_extra_and_value_differences():
    fields = ["file", "median"]
    baseline = [{"file": "A.h5", "median": "1.0"}, {"file": "B.h5", "median": "2.0"}]
    actual = [{"file": "A.h5", "median": "1.1"}, {"file": "C.h5", "median": "3.0"}]
    errors = []
    result = agg.compare_rows(baseline, actual, fields, label="test", errors=errors)
    assert result["status"] == "FAIL"
    assert result["row_keys_missing"] == 1
    assert result["row_keys_extra"] == 1
    assert result["field_mismatches"] == 1
    assert errors
