import json
import shutil
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from agentic_uat.cli import app
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
        "schema_version": 2,
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
        "ux": {
            "ease_of_use": {
                "level": "minor_friction",
                "notes": "Report list needed one scan to find the region.",
                "evidence": ["clear-label"],
            },
            "intuitiveness": {
                "level": "no_friction",
                "notes": "The link label matched the task wording.",
                "evidence": ["open-report", "report-view"],
            },
            "performance": {
                "status": "measured",
                "notes": "Navigation timing duration after the click.",
                "evidence": ["open-report"],
            },
            "success_criteria": [
                {
                    "criterion": "Regional report title is visible",
                    "outcome": "met",
                    "evidence": ["report-view"],
                }
            ],
            "blockers": [],
        },
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


NOT_ASSESSED_UX = {
    "ease_of_use": {"level": "not_assessed", "notes": "Not run.", "evidence": []},
    "intuitiveness": {"level": "not_assessed", "notes": "Not run.", "evidence": []},
    "performance": {"status": "unavailable", "notes": "Not run.", "evidence": []},
    "success_criteria": [
        {
            "criterion": "Regional report title is visible",
            "outcome": "not_assessed",
            "evidence": [],
        }
    ],
    "blockers": [{"kind": "access", "description": "VPN is down.", "evidence": []}],
}


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
        "Find a regional report",
        "5/5",
        "Read help",
        "Not assessed",
        "data:image/png;base64,",
        "Regional report after opening",
        "The regional link matches the task.",
        "Retain the descriptive label.",
    ):
        assert text in html
    for text in (
        "Action log",
        "Tool-inclusive elapsed time",
        "Elapsed includes browser tools",
        "Task completed with clear navigation.",
    ):
        assert text not in html
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert "https://cdn." not in html
    assert "fetch(" not in html


def test_screenshots_are_attached_to_the_findings_they_support(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    journey = run / "journeys/analyst/find-report"
    result_path = journey / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["screenshots"].append(
        {
            "id": "unrelated",
            "file": "unrelated.png",
            "caption": "Unrelated screenshot",
            "action_id": "open-home",
        }
    )
    result_path.write_text(json.dumps(result), encoding="utf-8")
    Image.new("RGB", (4, 4), "red").save(journey / "unrelated.png")

    html = render_report(run).read_text(encoding="utf-8")
    finding = html.split('<article class="finding', 1)[1].split("</article>", 1)[0]
    assert "The regional link matches the task." in finding
    assert "Regional report after opening" in finding
    assert "data:image/png;base64," in finding
    assert "Unrelated screenshot" not in html
    assert "<h4>Screenshots</h4>" not in html


def report_content() -> dict:
    return {
        "schema_version": 1,
        "run_id": "demo-run",
        "scope": "Market analyst; regional reports.",
        "overview": "The regional report can be opened.",
        "findings": [
            {
                "title": "The link is clear",
                "location": "Reports page",
                "observation": "The label matches the report.",
                "impact": "Analysts can identify the report.",
                "recommendation": "Keep the label.",
                "sources": [
                    {
                        "persona_id": "analyst",
                        "journey_id": "find-report",
                        "finding_id": "clear-label",
                    }
                ],
                "screenshots": [
                    {
                        "file": "journeys/analyst/find-report/report.png",
                        "caption": "The report title is visible.",
                    }
                ],
            }
        ],
    }


def test_edited_report_uses_traced_findings_and_preserves_source_artifacts(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    result_path = run / "journeys/analyst/find-report/result.json"
    original = result_path.read_bytes()
    content = report_content()
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")

    html = render_report(run).read_text(encoding="utf-8")
    finding = html.split('<article class="finding', 1)[1].split("</article>", 1)[0]
    for text in (
        "The link is clear",
        "Reports page",
        "The label matches the report.",
        "Analysts can identify the report.",
        "Keep the label.",
        "The report title is visible.",
        "data:image/png;base64,",
    ):
        assert text in finding
    assert "Market analyst; regional reports." in html
    assert "The regional report can be opened." in html
    assert result_path.read_bytes() == original


@pytest.mark.parametrize("problem", ["unknown-source", "omitted-finding", "wrong-run"])
def test_edited_report_rejects_untraceable_or_omitted_findings(
    tmp_path: Path, problem: str
) -> None:
    run = make_run(tmp_path)
    content = report_content()
    if problem == "unknown-source":
        content["findings"][0]["sources"][0]["finding_id"] = "unknown"
    elif problem == "omitted-finding":
        content["findings"] = []
    else:
        content["run_id"] = "another-run"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(
        ValueError, match="unknown report finding|omits recorded|run_id"
    ):
        render_report(run)
    checked = CliRunner().invoke(app, ["check", str(run)])
    assert checked.exit_code != 0


def test_report_excludes_findings_only_for_confirmed_decisions(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["project"]["feature_status"] = [
        {
            "id": "reports",
            "feature": "Reports",
            "status": "available",
            "source": "owner",
        }
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    content = report_content()
    source = content["findings"].pop()["sources"][0]
    content["excluded"] = [{**source, "basis": "reports", "reason": "By design."}]
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="not a design decision or unavailable"):
        render_report(run)

    content["additional_decisions"] = [
        {"id": "label-wording", "decision": "Labels mirror data.", "source": "owner"}
    ]
    content["excluded"][0]["basis"] = "label-wording"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "The label matches the report." not in html

    content["additional_feature_status"] = [
        {
            "id": "exports",
            "feature": "Exports",
            "status": "in_development",
            "source": "owner",
        }
    ]
    content["excluded"][0]["basis"] = "exports"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    render_report(run)


def test_edited_report_rejects_unrelated_or_unsafe_screenshot(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    journey = run / "journeys/analyst/find-report"
    result_path = journey / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["screenshots"].append(
        {
            "id": "unrelated",
            "file": "unrelated.png",
            "caption": "Unrelated",
            "action_id": "open-home",
        }
    )
    result_path.write_text(json.dumps(result), encoding="utf-8")
    Image.new("RGB", (4, 4), "red").save(journey / "unrelated.png")

    content = report_content()
    screenshot = content["findings"][0]["screenshots"][0]
    screenshot["file"] = "journeys/analyst/find-report/unrelated.png"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="must support a referenced finding"):
        render_report(run)

    screenshot["file"] = "../outside.png"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe artifact path"):
        render_report(run)


def test_supplemental_report_screenshot_must_be_dated(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    (run / "report-evidence").mkdir()
    Image.new("RGB", (4, 4), "green").save(run / "report-evidence/detail.png")
    content = report_content()
    screenshot = content["findings"][0]["screenshots"][0]
    screenshot["file"] = "report-evidence/detail.png"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="dated image"):
        render_report(run)

    screenshot["captured_at"] = "2026-11-18T18:30:58Z"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "Captured 18 Nov 2026 18:30 UTC." in html
    assert "data:image/png;base64," in html


def test_missing_supplemental_screenshot_is_reported(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    content = report_content()
    content["findings"][0]["screenshots"][0] = {
        "file": "report-evidence/missing.png",
        "caption": "Detail no longer available.",
        "captured_at": "2026-11-18T18:30:58Z",
    }
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "Screenshot unavailable" in html
    assert "Detail no longer available." in html


def test_edited_report_escapes_untrusted_prose(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    content = report_content()
    content["findings"][0]["observation"] = '<img src=x onerror="alert(1)">'
    content["findings"][0]["screenshots"][0]["caption"] = "<script>bad()</script>"
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "<img src=x onerror=" not in html
    assert "<script>bad()</script>" not in html
    assert "&lt;img" in html
    assert "&lt;script&gt;bad()" in html


def test_edited_report_groups_related_findings_at_highest_severity(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path)
    result_path = run / "journeys/analyst/find-report/result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["findings"].append(
        {
            "id": "related-delay",
            "severity": "major",
            "category": "performance",
            "observation": "The report took too long to open.",
            "recommendation": "Reduce the wait.",
            "evidence": ["open-report"],
        }
    )
    result_path.write_text(json.dumps(result), encoding="utf-8")
    content = report_content()
    content["findings"][0]["sources"].append(
        {
            "persona_id": "analyst",
            "journey_id": "find-report",
            "finding_id": "related-delay",
        }
    )
    (run / "report-content.json").write_text(json.dumps(content), encoding="utf-8")

    html = render_report(run).read_text(encoding="utf-8")
    assert html.count('<article class="finding') == 1
    assert '<span class="badge major">Major</span>' in html


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
        ux=NOT_ASSESSED_UX,
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
    assert "Screenshot unavailable" in html
    assert "data:image/png" not in html


def test_report_presents_ux_assessment_for_successful_journey(tmp_path: Path) -> None:
    html = render_report(make_run(tmp_path)).read_text(encoding="utf-8")
    assert "Completed" in html
    assert "5/5" in html
    assert "Report list needed one scan to find the region." not in html
    assert "Navigation timing duration after the click." not in html


def test_legacy_result_shows_missing_ux_assessment(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    result = run / "journeys/analyst/find-report/result.json"
    data = json.loads(result.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    del data["ux"]
    result.write_text(json.dumps(data), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "Criteria not assessed" in html


def test_empty_findings_do_not_read_as_a_clean_bill(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    journey = run / "journeys/analyst/find-report"
    update_json(journey / "result.json", findings=[])
    update_json(journey / "score.json", evidence=["report-view"])
    data = json.loads((journey / "result.json").read_text(encoding="utf-8"))
    data["ux"]["ease_of_use"]["evidence"] = ["open-report"]
    (journey / "result.json").write_text(json.dumps(data), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "No issues recorded for the assessed tasks" in html
    assert "No findings recorded." not in html


def test_report_omits_preflight_section(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    checks = [
        {"capability": name, "available": True, "evidence": "Listed tool."}
        for name in (
            "open_page",
            "read_page",
            "interact",
            "capture_screenshot",
            "persist_screenshot",
            "delegate_subagent",
        )
    ]
    (run / "preflight").mkdir()
    shutil.copyfile(
        run / "journeys/analyst/find-report/report.png", run / "preflight/probe.png"
    )
    preflight = {
        "schema_version": 1,
        "run_id": "demo-run",
        "checked_at": "2026-11-18T16:00:30Z",
        "status": "ready",
        "checks": checks,
        "probe_screenshot": "preflight/probe.png",
    }
    (run / "preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "Preflight" not in html
    assert "Listed tool." not in html


def test_blocked_preflight_is_presented_as_a_stopped_run(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    for name in ("result.json", "score.json", "report.png"):
        (run / "journeys/analyst/find-report" / name).unlink()
    checks = [
        {
            "capability": name,
            "available": name != "open_page",
            "evidence": "No page-opening tool in this session."
            if name == "open_page"
            else "Listed.",
        }
        for name in (
            "open_page",
            "read_page",
            "interact",
            "capture_screenshot",
            "persist_screenshot",
            "delegate_subagent",
        )
    ]
    preflight = {
        "schema_version": 1,
        "run_id": "demo-run",
        "checked_at": "2026-11-18T16:00:30Z",
        "status": "blocked",
        "checks": checks,
        "probe_screenshot": None,
    }
    (run / "preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    html = render_report(run).read_text(encoding="utf-8")
    assert "Run stopped before any journey" in html
    assert "(open_page)" in html
    assert "Preflight" not in html


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


def test_report_lists_tasks_and_persona(tmp_path: Path) -> None:
    html = render_report(make_run(tmp_path)).read_text(encoding="utf-8")
    assert "Market analyst" in html
    assert "Find a regional report" in html
    assert "Read help" in html
