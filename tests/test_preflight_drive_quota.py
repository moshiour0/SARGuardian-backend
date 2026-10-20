from __future__ import annotations

import math

import pytest

from tools.preflight_drive_quota import (
    PER_PRODUCT_OVERHEAD_BYTES,
    RUN_OVERHEAD_BYTES,
    estimate_required_bytes,
    preflight_capacity,
)
from tools.drive_resumable_upload import DriveError


class FakeDrive:
    def __init__(self, limit: int, usage: int):
        self.limit = limit
        self.usage = usage

    def quota(self):
        return self.limit, self.usage


def manifest(*sizes: int) -> dict:
    return {
        "aoi": "source",
        "run_profile": "full-source-baseline",
        "products": [{"expected_source_bytes": size} for size in sizes],
    }


def test_estimate_includes_safety_margin_and_per_run_overhead():
    data = manifest(2_400_000_000, 1_000_000_000)
    result = estimate_required_bytes(data)
    assert result == (
        math.ceil(3_400_000_000 * 1.15)
        + 2 * PER_PRODUCT_OVERHEAD_BYTES
        + RUN_OVERHEAD_BYTES
    )
    assert result > sum(p["expected_source_bytes"] for p in data["products"])


def test_preflight_passes_when_estimated_storage_fits():
    data = manifest(2_400_000_000, 1_000_000_000)
    estimate = estimate_required_bytes(data)
    result = preflight_capacity(data, FakeDrive(limit=estimate + 100, usage=100))
    assert result["selected_products"] == 2
    assert result["estimated_required_bytes"] == estimate
    assert result["remaining_bytes"] == estimate


def test_preflight_fails_before_download_when_quota_is_insufficient():
    with pytest.raises(DriveError, match="DRIVE_QUOTA_INSUFFICIENT_FOR_SELECTED_RUN"):
        preflight_capacity(
            manifest(2_400_000_000, 1_000_000_000),
            FakeDrive(limit=1_000, usage=100),
        )


def test_preflight_fails_closed_when_quota_is_unknown():
    class UnknownQuota:
        def quota(self):
            raise DriveError("DRIVE_QUOTA_UNKNOWN_FAIL_CLOSED")

    with pytest.raises(DriveError, match="DRIVE_QUOTA_UNKNOWN_FAIL_CLOSED"):
        preflight_capacity(manifest(100), UnknownQuota())


@pytest.mark.parametrize(
    "data",
    [
        {"aoi": "source", "products": []},
        {"aoi": "other", "products": [{"expected_source_bytes": 100}]},
        {"aoi": "source", "products": [{"expected_source_bytes": 0}]},
        {"aoi": "source", "products": [{"expected_source_bytes": "100"}]},
    ],
)
def test_preflight_rejects_invalid_manifests(data):
    with pytest.raises(ValueError):
        preflight_capacity(data, FakeDrive(limit=100_000_000_000, usage=0))


def test_preflight_rejects_unsafe_safety_factor():
    with pytest.raises(ValueError, match="between 1.0 and 3.0"):
        estimate_required_bytes(manifest(100), safety_factor=0.99)
