from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "dashboard" / "assets" / "prepare_web_assets.py"
AGGREGATOR = ROOT / "tools" / "aggregate_aoi_run.py"
PIPELINE = ROOT / "dashboard" / "science_pipeline.py"


def test_real_goff_metrics_are_carried_to_the_interactive_viewer() -> None:
    builder = BUILDER.read_text(encoding="utf-8")
    assert '"goff_range_median_mm": metric_number(stats.get("range_median_mm"))' in builder
    assert '"goff_azimuth_median_mm": metric_number(stats.get("azimuth_median_mm"))' in builder
    assert '"goff_detect_floor_mm_day": metric_number(stats.get("detect_floor_mm_day"))' in builder
    assert "GOFF range-offset median (mm)" in builder
    assert "GOFF along-track offset median (mm)" in builder
    assert "GOFF detection floor (mm/day)" in builder
    assert "Detection floors are noise bounds, not observed motion" in builder


def test_every_main_science_module_has_an_explicit_dynamic_aoi_stage_gate() -> None:
    pipeline = PIPELINE.read_text(encoding="utf-8")
    aggregator = AGGREGATOR.read_text(encoding="utf-8")
    for name in (
        "timeseries.py", "local_floor.py", "inverse_velocity.py",
        "geometry_merge.py", "bound.py", "gunw_reader.py", "goff_reader.py",
        "pixel_stack.py", "candidate_check.py",
    ):
        assert name in pipeline
    assert "timeseries.describe_network(pairs)" in pipeline
    assert "NETWORK_TOPOLOGY_ONLY_INVERSION_WITHHELD" in pipeline
    assert "BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET" in pipeline
    assert "BLOCKED_NO_VERIFIED_COMMON_DATUM_SERIES" in pipeline
    assert "NOT_APPLICABLE_GENERIC_AOI" in pipeline
    assert "build_science_pipeline_report" in aggregator
    assert '"science_pipeline":science_pipeline' in aggregator
    assert 'science-pipeline-report.json' in aggregator
    assert '"science_pipeline": summary.get("science_pipeline") or {}' in builder
