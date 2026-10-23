from __future__ import annotations

import math

import numpy as np
import pytest

from tools.know_place.uncertainty import spatial_block_bootstrap_summary


def test_spatial_block_bootstrap_recovers_constant_vector_known_answer_and_is_reproducible():
    east = np.full((30, 30), 3.0)
    north = np.full((30, 30), 4.0)
    valid = np.ones((30, 30), dtype=bool)
    aoi = np.ones((30, 30), dtype=bool)

    first = spatial_block_bootstrap_summary(
        east, north, valid, aoi, block_size_cells=5, replicates=100, seed=123,
    )
    second = spatial_block_bootstrap_summary(
        east, north, valid, aoi, block_size_cells=5, replicates=100, seed=123,
    )

    assert first["status"] == "COMPUTED_EXPLORATORY"
    assert first["valid_block_count"] == 36
    assert first["statistics"]["median_horizontal_magnitude_m"] == pytest.approx(5.0)
    assert first["statistics"]["median_horizontal_magnitude_95pct_interval_m"] == pytest.approx([5.0, 5.0])
    assert first["statistics"]["mean_vector_magnitude_m"] == pytest.approx(5.0)
    assert first["statistics"]["mean_vector_azimuth_deg_clockwise_from_north"] == pytest.approx(
        math.degrees(math.atan2(3.0, 4.0))
    )
    assert first["statistics"] == second["statistics"]


def test_spatial_block_bootstrap_marks_small_aoi_as_insufficient_not_false_zero():
    east = np.ones((4, 4))
    north = np.zeros((4, 4))
    valid = np.ones((4, 4), dtype=bool)
    aoi = valid.copy()

    result = spatial_block_bootstrap_summary(
        east, north, valid, aoi, block_size_cells=5, replicates=100,
    )

    assert result["status"] == "INSUFFICIENT_SPATIAL_BLOCKS"
    assert result["valid_block_count"] == 1
    assert "statistics" not in result


def test_spatial_block_bootstrap_rejects_shape_and_policy_errors():
    with pytest.raises(ValueError, match="UNCERTAINTY_ARRAY_SHAPE_MISMATCH"):
        spatial_block_bootstrap_summary(
            np.ones((3, 4)), np.ones((4, 3)), np.ones((3, 4), bool),
            np.ones((3, 4), bool), replicates=100,
        )
    with pytest.raises(ValueError, match="UNCERTAINTY_REPLICATES_MUST_BE_AT_LEAST_100"):
        spatial_block_bootstrap_summary(
            np.ones((20, 20)), np.ones((20, 20)),
            np.ones((20, 20), bool), np.ones((20, 20), bool),
            replicates=20,
        )
