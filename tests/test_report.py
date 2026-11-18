import json
from pathlib import Path

import pytest
from PIL import Image

from agentic_uat.report import render_report


def make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    journey = run / "journeys" / "analyst" / "find-report"
    journey.mkdir(parents=True)
    project = {
        "schema_version": 1,
        "name": 'Research <script>alert("project")</script>',
        "base_url": "https://example.test/",
        "access": {
            "mode": "public",
            "login_instructions": None,
            "vpn_required": False,
            "vpn_instructions": None,
            "proxy_required": False,
            "proxy_instructions": None,
            "openapi_url": None,
        },
        "approved_actions": [],
        "personas": [
            {
                "id": "analyst",
                "name": "Sam",
                "role": "Market analyst",
                "description": "Compares weekly sales before a planning meeting.",
                "goals": ["Find the latest regional report"],
                "experience": "First-time visitor, familiar with spreadsheets.",
                "permissions": ["Read published reports"],
                "journeys": [
                    {
                        "id": "find-report",
                        "name": "Find a regional report",
                        "start_url": "https://example.test/",
                        "task": "Open the latest regional report.",
                        "success_criteria": ["Regional report title is visible"],
                    },
                    {
                        "id": "read-help",
                        "name": "Read help",
                        "start_url": "https://example.test/help",
                        "task": "Find the help page.",
                        "success_criteria": ["Help topics are visible"],
                    },
                ],
            }
        ],
    }
    manifest = {
        "schema_version": 1,
        "run_id": "demo-run",
        "created_at": "2026-11-18T16:00:00Z",
        "project": project,
    }
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = {
        "schema_version": 1,
        "persona_id": "analyst",
        "journey_id": "find-report",
        "status": "completed",
        "summary": 'Report opened. <img src=x onerror="alert(1)">',
        "started_at": "2026-11-18T16:01:00Z",
        "finished_at": "2026-11-18T16:01:12Z",
        "timing_notes": "Elapsed includes browser tools and agent reasoning.",
        "actions": [
            {
                "id": "open-home",
                "timestamp": "2026-11-18T16:01:01Z",
                "kind": "navigate",
                "description": "Open home",
                "outcome": "Reports link is visible",
                "application_ms": None,
            },
            {
                "id": "open-report",
                "timestamp": "2026-11-18T16:01:06Z",
                "kind": "click",
                "description": "Choose regional report",
                "outcome": "Regional report title is visible",
                "application_ms": 180.0,
            },
        ],
        "findings": [
            {
                "id": "clear-label",
                "severity": "info",
                "category": "discoverability",
                "observation": "The regional link matches the task.",
                "recommendation": "Retain the descriptive label.",
                "evidence": ["open-report", "report-view"],
            }
        ],
        "screenshots": [
            {
                "id": "report-view",
                "file": "report.png",
                "caption": "Regional report after opening",
                "action_id": "open-report",
            }
        ],
        "limitations": ["One desktop viewport; no human participants."],
    }
    (journey / "result.json").write_text(json.dumps(result), encoding="utf-8")
    score = {
        "schema_version": 1,
        "persona_id": "analyst",
        "journey_id": "find-report",
        "score": 5,
        "rationale": "Task completed with clear navigation.",
        "confidence": "medium",
        "limitations": ["Single execution"],
        "evidence": ["clear-label", "report-view"],
    }
    (journey / "score.json").write_text(json.dumps(score), encoding="utf-8")
    Image.new("RGB", (4, 4), "blue").save(journey / "report.png")
    return run


def update_json(path: Path, **fields: object) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_report_embeds_evidence_and_preserves_unexecuted_journeys(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    output = render_report(run)
    html = output.read_text(encoding="utf-8")
    assert output == run / "report.html"
    for text in (
        "Market analyst",
        "Compares weekly sales",
        "First-time visitor",
        "Read published reports",
        "Find the latest regional report",
        "Regional report title is visible",
        "5/5",
        "Read help",
        "Not executed",
        "data:image/png;base64,",
        "Regional report after opening",
        "Task completed with clear navigation.",
        "180",
        "12.0",
        "<details",
        'id="persona-filter"',
        'id="status-filter"',
        'id="score-filter"',
    ):
        assert text in html
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert "https://cdn." not in html
    assert "fetch(" not in html


def test_setup_blocked_journey_is_unscored(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    journey = run / "journeys/analyst/find-report"
    update_json(
        journey / "result.json",
        status="setup_blocked",
        summary="VPN is unavailable.",
        actions=[],
        findings=[],
        screenshots=[],
    )
    update_json(
        journey / "score.json",
        score=None,
        rationale="No application interaction was possible.",
        evidence=[],
        confidence="low",
    )
    html = render_report(run).read_text(encoding="utf-8")
    assert "Setup blocked" in html
    assert "Unscored" in html
    assert "VPN is unavailable." in html
    assert 'data-score="5"' not in html


def test_missing_screenshot_is_visible_not_silently_discarded(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    (run / "journeys/analyst/find-report/report.png").unlink()
    html = render_report(run).read_text(encoding="utf-8")
    assert "Missing screenshot" in html
    assert "report.png" in html
    assert "data:image/png" not in html


@pytest.mark.parametrize("filename", ["../outside.png", "/tmp/outside.png"])
def test_report_rejects_escaping_image_paths(tmp_path: Path, filename: str) -> None:
    run = make_run(tmp_path)
    result = run / "journeys/analyst/find-report/result.json"
    update_json(
        result,
        screenshots=[
            {
                "id": "report-view",
                "file": filename,
                "caption": "Unsafe screenshot",
                "action_id": "open-report",
            }
        ],
    )
    with pytest.raises(ValueError):
        render_report(run)


def test_report_rejects_image_symlink_escape(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    image = run / "journeys/analyst/find-report/report.png"
    outside = tmp_path / "outside.png"
    image.rename(outside)
    image.symlink_to(outside)
    with pytest.raises(ValueError):
        render_report(run)


def test_report_rejects_mislabeled_or_corrupt_images(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    image = run / "journeys/analyst/find-report/report.png"
    image.write_text('<svg onload="alert(1)"></svg>', encoding="utf-8")
    with pytest.raises(ValueError, match="image|Image"):
        render_report(run)


def test_report_rejects_directory_used_as_screenshot(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    image = run / "journeys/analyst/find-report/report.png"
    image.unlink()
    image.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        render_report(run)


def test_report_does_not_overwrite_evidence(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    with pytest.raises(ValueError, match="html"):
        render_report(run, run / "manifest.json")
