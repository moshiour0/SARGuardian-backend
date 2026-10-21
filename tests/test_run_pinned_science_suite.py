from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from tools.run_pinned_science_suite import (
    PINNED_SCIENCE_COMMIT,
    command_plan,
    run_suite,
)


def _fake_runner_factory(tmp_path: Path, *, retry_name: str | None = None):
    calls: list[list[str]] = []
    network_attempts: dict[str, int] = {}

    def runner(argv, **kwargs):
        args = list(argv)
        calls.append(args)
        if args[:4] == ["git", "-C", str(tmp_path.resolve()), "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout=PINNED_SCIENCE_COMMIT + "\n")
        if args[:4] == ["git", "-C", str(tmp_path.resolve()), "diff"]:
            return SimpleNamespace(returncode=0, stdout="")
        if args[:4] == ["git", "-C", str(tmp_path.resolve()), "status"]:
            return SimpleNamespace(returncode=0, stdout="")
        name = next((x["name"] for x in command_plan() if x["argv"] == args), None)
        assert name is not None, args
        if name == retry_name:
            network_attempts[name] = network_attempts.get(name, 0) + 1
            if network_attempts[name] == 1:
                return SimpleNamespace(returncode=1, stdout="HTTP Error 503: service unavailable")
        for item in command_plan():
            if item["name"] == name:
                for rel in item["outputs"]:
                    target = tmp_path / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.suffix.lower() == ".csv":
                        target.write_text("id,value\\n1,2\\n", encoding="utf-8")
                    elif target.suffix.lower() == ".geojson":
                        target.write_text(
                            '{"type":"FeatureCollection","features":[{"type":"Feature","geometry":null,"properties":{}}]}',
                            encoding="utf-8",
                        )
                break
        evidence = {
            "result2_track_sensitivity_and_dem_stencil_sweep": "SENSITIVITY ACROSS DEM STENCIL WIDTHS",
            "result2_north_face_aspect_hypothesis": "[OVERRIDE] aspect",
            "result6_sentinel2_scene_survey": "4 Sentinel-2 L2A scenes over the source zone",
            "result6_sentinel2_candidate_map": "DETACHMENT-like",
            "result6_reported_point_probe": "NOT A SCAR, usable pixels",
        }
        output = evidence.get(name, "Caveats: pools are not tested" if name.startswith("result3_impoundment_") else f"PASS {name}")
        return SimpleNamespace(returncode=0, stdout=output + "\\n")

    return runner, calls, network_attempts


def test_command_plan_uses_source_zip_entry_points_and_covers_results_1_2_3_6():
    plan = command_plan()
    names = {entry["name"] for entry in plan}
    assert "result1_detectability_noise_gates" in names
    assert "result2_track_sensitivity_and_dem_stencil_sweep" in names
    assert "result3_impoundment_blatten" in names
    assert "result6_sentinel2_candidate_map" in names
    assert len([x for x in plan if x["name"].startswith("result3_impoundment_")]) == 4
    assert all(Path(entry["argv"][1]).as_posix().startswith("src/") for entry in plan)
    assert not any(".h5" in " ".join(entry["argv"]).lower() for entry in plan)


def test_suite_records_all_steps_and_does_not_edit_science_sources(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "outputs").mkdir()
    runner, calls, _ = _fake_runner_factory(tmp_path)
    sleeps: list[float] = []
    report = run_suite(tmp_path, tmp_path / "aggregate", runner=runner, sleeper=sleeps.append)

    assert report["status"] == "PASS"
    assert report["source_scripts_modified"] is False
    assert report["raw_hdf5_used_by_supplementary_suite"] is False
    assert len(report["commands"]) == len(command_plan())
    assert not report["errors"]
    assert (tmp_path / "outputs/scar_candidates_source.csv").is_file()
    assert (tmp_path / "aggregate/logs/pinned-science-suite/pinned-science-suite.json").is_file()


def test_network_stage_retries_503_but_deterministic_model_does_not(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "outputs").mkdir()
    runner, _, attempts = _fake_runner_factory(
        tmp_path, retry_name="result3_impoundment_source"
    )
    sleeps: list[float] = []
    report = run_suite(
        tmp_path, tmp_path / "aggregate", runner=runner, sleeper=sleeps.append,
        max_attempts=3, base_delay=2,
    )

    row = next(x for x in report["commands"] if x["name"] == "result3_impoundment_source")
    assert row["status"] == "PASS"
    assert len(row["attempts"]) == 2
    assert attempts["result3_impoundment_source"] == 2
    assert 2 in sleeps
