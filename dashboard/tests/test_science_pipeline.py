from __future__ import annotations

from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from dashboard.science_pipeline import build_science_pipeline_report


def test_network_topology_is_reported_without_fabricating_common_datum_series(tmp_path: Path) -> None:
    fake = ModuleType("timeseries")
    fake.granule_metadata = lambda name: {
        "path": 48, "direction": "D", "product": "GUNW", "cycle": 26,
        "frame": 71, "subswath": 28, "bandwidth": 4000,
        "polarisation": "SH", "crid": "P05023", "processing": "PR",
    }

    class Pair:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake.Pair = Pair
    fake.describe_network = lambda pairs: {
        "DESC path 048 frame 071 CRID P05023 GUNW": [
            {"epochs": ["2026-07-11", "2026-07-23", "2026-08-16"], "n_pairs": 2, "redundancy": 0}
        ]
    }

    products = [
        {
            "id": "GUNW-001",
            "product_type": "GUNW",
            "granule_name": "NISAR_L2_PR_GUNW_026_048_D_071_028_4000_SH_20260711T000000_20260711T000000_20260723T000000_20260723T000000_P05023_N_F_J_001",
            "reference_date": "2026-07-11",
            "secondary_date": "2026-07-23",
            "valid_pixels": 10,
            "stats": {"mean_coherence": 0.6},
        },
        {
            "id": "GUNW-002",
            "product_type": "GUNW",
            "granule_name": "NISAR_L2_PR_GUNW_026_048_D_071_028_4000_SH_20260723T000000_20260723T000000_20260816T000000_20260816T000000_P05023_N_F_J_001",
            "reference_date": "2026-07-23",
            "secondary_date": "2026-08-16",
            "valid_pixels": 10,
            "stats": {"mean_coherence": 0.6},
        },
    ]

    with patch.dict("sys.modules", {"timeseries": fake}):
        report = build_science_pipeline_report(products, tmp_path, {"pixel_stack": {"status": "COMPLETED_NO_DETECTION"}})

    assert report["network_assessment_status"] == "COMPLETED"
    assert report["overall_status"] == "NETWORK_ASSESSED_WITH_DOWNSTREAM_STAGES_WITHHELD"
    assert report["networks"][0]["redundancy"] == 0
    assert report["networks"][0]["topology_status"] == "EXACTLY_DETERMINED_NO_REDUNDANCY"
    stages = {row["name"]: row["status"] for row in report["modules"]}
    assert stages["timeseries.py"] == "NETWORK_TOPOLOGY_ONLY_INVERSION_WITHHELD"
    assert stages["local_floor.py"] == "BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET"
    assert stages["inverse_velocity.py"] == "BLOCKED_NO_VERIFIED_COMMON_DATUM_SERIES"
    assert stages["geometry_merge.py"] == "BLOCKED_NO_COMPARABLE_ASC_DESC_SERIES"
    assert stages["bound.py"] == "NOT_APPLICABLE_GENERIC_AOI"
    assert report["structural_validation_is_geophysical_validation"] is False


def test_no_data_run_keeps_downstream_methods_blocked_and_reports_reader_coverage(tmp_path: Path) -> None:
    fake = ModuleType("timeseries")
    fake.granule_metadata = lambda name: None
    fake.Pair = object
    fake.describe_network = lambda pairs: {}
    with patch.dict("sys.modules", {"timeseries": fake}):
        report = build_science_pipeline_report([], tmp_path, {"candidate_checks": {"status": "SKIPPED_UNSUPPORTED_CUSTOM_AOI"}})
    stages = {row["name"]: row["status"] for row in report["modules"]}
    assert stages["gunw_reader.py"] == "NO_GUNW_PRODUCTS"
    assert stages["goff_reader.py"] == "NO_GOFF_PRODUCTS"
    assert stages["local_floor.py"] == "BLOCKED_NO_EXPLICIT_MEASUREMENT_TARGET"
    assert stages["bound.py"] == "NOT_APPLICABLE_GENERIC_AOI"
