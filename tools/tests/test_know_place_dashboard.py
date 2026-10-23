from __future__ import annotations

from tools.know_place.dashboard import build_dashboard_html, write_dashboard


def test_dashboard_contains_displacement_chart_spatial_preview_and_scientific_gates(tmp_path):
    report = {
        "schema_version": "know-place-aoi-result/1.0",
        "engine_version": "1.0.0",
        "status": "SCIENTIFIC_METRICS_COMPUTED",
        "structural_status": "PASS",
        "measurement_status": "METRICS_COMPUTED",
        "paper_reproduction_status": "NOT_EVALUATED_GENERIC_AOI",
        "hazard_detection_status": "NOT_EVALUATED",
        "request_sha256": "a" * 64,
        "source_adapters": ["NISAR_GOFF"],
        "reference_policy": "explicit test",
        "request": {
            "aoi": {"wkt": "POLYGON ((85 28, 86 28, 86 29, 85 29, 85 28))"},
            "date_range": {"start": "2026-06-20", "end": "2026-08-31"},
        },
        "pairs": [{
            "reference_date": "2026-07-26",
            "secondary_date": "2026-08-19",
            "granule_name": "NISAR_L2_PR_GOFF_TEST.h5",
            "release_id": "P05023",
            "epsg": 32645,
            "status": "METRICS_COMPUTED",
            "valid_aoi_pixels": 147,
            "geotiff_file": "../maps/pair_displacement.tif",
            "statistics": {
                "crown_median_horizontal_magnitude_m": 0.96,
                "crown_mean_vector_magnitude_m": 1.72,
                "crown_mean_vector_azimuth_deg_clockwise_from_north": 278.0,
                "crown_median_directional_coherence_R": 0.87,
            },
            "map_preview": {
                "values": [[0.1, 0.2], [None, 0.5]],
                "min_x_m": 100.0, "max_y_m": 200.0,
                "pixel_size_x_m": 80.0, "pixel_size_y_m": 80.0,
                "aoi_ring_xy": [[100.0,200.0],[180.0,200.0],[180.0,120.0],[100.0,120.0],[100.0,200.0]],
            },
        }],
    }
    rendered = build_dashboard_html(report)

    assert "SARGuardian — Know Place Analysis" in rendered
    assert "0.960 m" in rendered
    assert "PAPER_REPRODUCTION" not in rendered or "NOT_EVALUATED_GENERIC_AOI" in rendered
    assert "Hazard detection" in rendered
    assert "No raster preview available" in rendered or "pairMaps" in rendered
    assert "map-canvas-0" in rendered
    assert "pair_displacement.tif" in rendered
    assert "https://" not in rendered  # no CDN/external dependency
    target = write_dashboard(report, tmp_path / "dashboard.html")
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == rendered


def test_dashboard_escapes_user_html_and_script_terminator():
    report = {
        "request": {
            "aoi": {"wkt": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))"},
            "date_range": {"start": "2026-01-01", "end": "2026-01-02"},
            "label": "</script><script>alert(1)</script>",
        },
        "pairs": [{
            "reference_date": "2026-01-01",
            "secondary_date": "2026-01-02",
            "granule_name": "</script><script>alert(1)</script>",
            "map_preview": {"values": [[0.1]], "aoi_ring_xy": []},
        }],
    }
    rendered = build_dashboard_html(report)
    assert "</script><script>alert(1)" not in rendered
    assert "&lt;/script&gt;&lt;script&gt;alert(1)" in rendered
