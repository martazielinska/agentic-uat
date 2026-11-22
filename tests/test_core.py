from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from agentic_uat.cli import app
from agentic_uat.models import JourneyResult, Preflight, Project, Score
from agentic_uat.storage import (
    init_project,
    install_assets,
    load_project,
    load_run,
    prepare_run,
    safe_path,
)

runner = CliRunner()
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def project_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Example app",
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
        "personas": [
            {
                "id": "member",
                "name": "Member",
                "role": "Standard member",
                "description": "Uses the app to manage records.",
                "goals": ["Find a record"],
                "experience": "Experienced",
                "permissions": ["Read records"],
                "journeys": [
                    {
                        "id": "find-record",
                        "name": "Find a record",
                        "start_url": "https://example.test/records",
                        "task": "Find a named record.",
                        "success_criteria": ["The record is displayed."],
                    }
                ],
            }
        ],
        "approved_actions": [],
    }


BLOCKER_KINDS = {
    "application_blocked": "application",
    "setup_blocked": "setup",
    "policy_blocked": "policy",
}


def ux_data(
    *, status: str = "completed", evidence: list[str] | None = None
) -> dict[str, object]:
    refs = ["open-records"] if evidence is None else evidence
    assessed = status in {"completed", "application_blocked"} and bool(refs)
    rating = {
        "level": "minor_friction" if assessed else "not_assessed",
        "notes": "One label was ambiguous." if assessed else "Journey did not run.",
        "evidence": refs if assessed else [],
    }
    blockers = (
        [{"kind": BLOCKER_KINDS[status], "description": "Blocked.", "evidence": []}]
        if status in BLOCKER_KINDS
        else []
    )
    return {
        "ease_of_use": dict(rating),
        "intuitiveness": dict(rating),
        "performance": {
            "status": "unavailable",
            "notes": "No navigation timing was exposed by the browser tools.",
            "evidence": [],
        },
        "success_criteria": [
            {
                "criterion": "The record is displayed.",
                "outcome": "met" if status == "completed" else "not_assessed",
                "evidence": refs if status == "completed" else [],
            }
        ],
        "blockers": blockers,
    }


def result_data(
    *,
    status: str = "completed",
    with_action: bool = True,
    persona_id: str = "member",
    journey_id: str = "find-record",
) -> dict[str, object]:
    actions = (
        [
            {
                "id": "open-records",
                "timestamp": NOW.isoformat(),
                "kind": "navigate",
                "description": "Opened records.",
                "outcome": "Records page loaded.",
                "application_ms": None,
            }
        ]
        if with_action
        else []
    )
    return {
        "schema_version": 2,
        "persona_id": persona_id,
        "journey_id": journey_id,
        "status": status,
        "summary": "The journey ended.",
        "started_at": NOW.isoformat(),
        "finished_at": (NOW + timedelta(seconds=2)).isoformat(),
        "timing_notes": "Elapsed time includes tool use.",
        "actions": actions,
        "findings": [],
        "screenshots": [],
        "limitations": [],
        "ux": ux_data(status=status, evidence=None if with_action else []),
    }


def legacy_result_data() -> dict[str, object]:
    data = result_data()
    data["schema_version"] = 1
    del data["ux"]
    return data


def write_run(
    root: Path,
    *,
    result: dict[str, object] | None = None,
    score: dict[str, object] | None = None,
    preflight: dict[str, object] | None = None,
) -> Path:
    run_id = "run-2026-11-18t120000z"
    run_dir = root / ".agentic-uat" / "runs" / run_id
    journey_dir = run_dir / "journeys" / "member" / "find-record"
    journey_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": NOW.isoformat(),
        "project": project_data(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if result is not None:
        (journey_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
    if score is not None:
        (journey_dir / "score.json").write_text(json.dumps(score), encoding="utf-8")
    if preflight is not None:
        (run_dir / "preflight.json").write_text(json.dumps(preflight), encoding="utf-8")
    return run_dir


def project_v2_data(**changes: object) -> dict[str, object]:
    return {**project_data(), "schema_version": 2, "clarifications": [], **changes}


def write_project(workspace: Path, data: dict[str, object] | None = None) -> Path:
    project_file = workspace / ".agentic-uat" / "project.yaml"
    project_file.parent.mkdir(parents=True, exist_ok=True)
    payload = project_v2_data() if data is None else data
    project_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return project_file


def score_data(
    *, score: int | None = 4, evidence: list[str] | None = None
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "persona_id": "member",
        "journey_id": "find-record",
        "score": score,
        "rationale": "The record was found with minor friction.",
        "confidence": "high",
        "limitations": [],
        "evidence": ["open-records"] if evidence is None else evidence,
    }


def test_missing_intake_is_rejected_and_init_writes_explicit_draft(
    tmp_path: Path,
) -> None:
    with pytest.raises((FileNotFoundError, ValueError)):
        load_project(tmp_path)

    draft = init_project(tmp_path)
    content = yaml.safe_load(draft.read_text(encoding="utf-8"))
    assert content["name"] is None
    assert content["base_url"] is None
    assert content["access"] == {
        "mode": None,
        "login_instructions": None,
        "vpn_required": None,
        "vpn_instructions": None,
        "proxy_required": None,
        "proxy_instructions": None,
        "openapi_url": None,
    }
    assert content["personas"] == []
    assert init_project(tmp_path) == draft
    assert draft.read_text(encoding="utf-8") == yaml.safe_dump(content, sort_keys=False)


def test_init_creates_context_markdown_and_preserves_existing_memory(
    tmp_path: Path,
) -> None:
    draft = init_project(tmp_path)
    context = draft.parent / "context.md"
    assert context.is_file()
    assert "terminology" in context.read_text(encoding="utf-8").lower()
    context.write_text("Existing interview notes.\n", encoding="utf-8")
    draft.write_text("existing: memory\n", encoding="utf-8")

    assert init_project(tmp_path) == draft
    assert context.read_text(encoding="utf-8") == "Existing interview notes.\n"
    assert draft.read_text(encoding="utf-8") == "existing: memory\n"


def test_project_rejects_duplicate_ids_and_unsafe_urls() -> None:
    duplicate = project_data()
    personas = duplicate["personas"]
    assert isinstance(personas, list)
    personas.append(personas[0])
    with pytest.raises(ValidationError):
        Project.model_validate(duplicate)

    for url in ("javascript:alert(1)", "https://user:pass@example.test/"):
        invalid = project_data()
        invalid["base_url"] = url
        with pytest.raises(ValidationError):
            Project.model_validate(invalid)

    invalid_boolean = project_data()
    access = invalid_boolean["access"]
    assert isinstance(access, dict)
    access["vpn_required"] = 1
    with pytest.raises(ValidationError):
        Project.model_validate(invalid_boolean)

    with pytest.raises(ValidationError):
        Score.model_validate(score_data(score=True))


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:\\outside", "."])
def test_safe_path_rejects_non_relative_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(tmp_path, path)


def test_models_require_aware_ordered_timestamps_and_valid_references() -> None:
    naive = result_data()
    naive["started_at"] = "2026-11-18T12:00:00"
    with pytest.raises(ValidationError):
        JourneyResult.model_validate(naive)

    unordered = result_data()
    unordered["actions"] = [
        {
            "id": "late",
            "timestamp": (NOW + timedelta(seconds=3)).isoformat(),
            "kind": "observe",
            "description": "Observed the page.",
            "outcome": "The page is visible.",
            "application_ms": None,
        }
    ]
    with pytest.raises(ValidationError):
        JourneyResult.model_validate(unordered)

    broken = result_data()
    broken["findings"] = [
        {
            "id": "missing-evidence",
            "severity": "major",
            "category": "navigation",
            "observation": "The menu was absent.",
            "recommendation": "Show the menu.",
            "evidence": ["not-an-action"],
        }
    ]
    with pytest.raises(ValidationError):
        JourneyResult.model_validate(broken)


@pytest.mark.parametrize("bad", [True, -0.5, "12", math.inf, math.nan])
def test_timing_values_reject_coercion(bad: object) -> None:
    result = result_data()
    actions = result["actions"]
    assert isinstance(actions, list)
    actions[0]["application_ms"] = bad
    with pytest.raises(ValidationError):
        JourneyResult.model_validate(result)


def test_timing_values_allow_fractional_milliseconds() -> None:
    result = legacy_result_data()
    actions = result["actions"]
    assert isinstance(actions, list)
    actions[0]["application_ms"] = 1.25
    validated = JourneyResult.model_validate(result)
    assert validated.actions[0].application_ms == 1.25


def test_scores_are_not_allowed_for_setup_or_policy_blockers(tmp_path: Path) -> None:
    for status in ("setup_blocked", "policy_blocked", "incomplete"):
        run_dir = write_run(
            tmp_path / status,
            result=result_data(status=status),
            score=score_data(score=3),
        )
        with pytest.raises(ValueError, match="score"):
            load_run(run_dir)

    blocked = write_run(
        tmp_path / "application-blocked",
        result=result_data(status="application_blocked"),
        score=score_data(score=2),
    )
    bundle = load_run(blocked)
    assert bundle.scores[("member", "find-record")].score == 2


@pytest.mark.parametrize("status", ["completed", "application_blocked"])
@pytest.mark.parametrize("with_score_file", [False, True])
def test_score_eligible_journey_without_numeric_score_warns(
    tmp_path: Path, status: str, with_score_file: bool
) -> None:
    score = score_data(score=None, evidence=[]) if with_score_file else None
    bundle = load_run(
        write_run(tmp_path, result=result_data(status=status), score=score)
    )
    assert ("member", "find-record") not in bundle.scores or (
        bundle.scores[("member", "find-record")].score is None
    )
    score_warnings = [w for w in bundle.warnings if "score" in w]
    assert score_warnings == [
        "No numeric score for score-eligible journey member/find-record."
    ]


def test_ineligible_journey_without_score_does_not_warn(tmp_path: Path) -> None:
    bundle = load_run(
        write_run(
            tmp_path, result=result_data(status="setup_blocked", with_action=False)
        )
    )
    assert not any("score" in warning for warning in bundle.warnings)


def test_load_run_rejects_manifest_symlink_outside_run_root(tmp_path: Path) -> None:
    run_dir = write_run(tmp_path)
    manifest_path = run_dir / "manifest.json"
    outside_manifest = tmp_path / "outside-manifest.json"
    manifest_path.rename(outside_manifest)
    manifest_path.symlink_to(outside_manifest)

    with pytest.raises(ValueError, match="escapes its root"):
        load_run(run_dir)


def test_load_run_checks_result_identifiers_and_evidence_references(
    tmp_path: Path,
) -> None:
    mismatched = result_data(journey_id="another-journey")
    with pytest.raises(ValueError, match="journey"):
        load_run(write_run(tmp_path / "ids", result=mismatched))

    invalid_score = write_run(
        tmp_path / "evidence",
        result=result_data(),
        score=score_data(evidence=["missing-action"]),
    )
    with pytest.raises((ValueError, ValidationError), match="evidence"):
        load_run(invalid_score)


def test_run_directories_are_unique(tmp_path: Path) -> None:
    write_project(tmp_path)
    first = prepare_run(tmp_path)
    second = prepare_run(tmp_path)
    assert first != second
    assert first.is_dir() and second.is_dir()
    assert (first / "manifest.json").is_file()
    assert (second / "manifest.json").is_file()
    assert (first / "journeys" / "member" / "find-record" / "outputs").is_dir()


def test_init_drafts_business_context_intake(tmp_path: Path) -> None:
    draft = init_project(tmp_path)
    content = yaml.safe_load(draft.read_text(encoding="utf-8"))
    assert content["schema_version"] == 2
    assert content["context_sources"] == [".agentic-uat/business-context"]
    assert content["clarifications"] is None
    guide = tmp_path / ".agentic-uat" / "business-context" / "README.md"
    assert "Feature availability" in guide.read_text(encoding="utf-8")


def test_project_runs_only_with_answered_business_context(tmp_path: Path) -> None:
    write_project(tmp_path, project_data())
    with pytest.raises(ValueError, match="rerun /uat-init"):
        load_project(tmp_path)

    implicit = project_v2_data()
    del implicit["clarifications"]
    with pytest.raises(ValidationError, match="clarifications are required"):
        Project.model_validate(implicit)

    question = {"id": "ls-channel", "question": "What is Ls?"}
    write_project(
        tmp_path,
        project_v2_data(clarifications=[{**question, "answer": None, "source": None}]),
    )
    result = runner.invoke(app, ["run", "--workspace", str(tmp_path)])
    assert result.exit_code == 1
    assert "unanswered business-context clarifications: ls-channel" in result.output

    answered = {**question, "answer": "Large supermarkets.", "source": "owner"}
    write_project(
        tmp_path,
        project_v2_data(clarifications=[answered], context_sources=["docs"]),
    )
    with pytest.raises(ValueError, match="context source does not exist: docs"):
        load_project(tmp_path)
    (tmp_path / "docs").mkdir()
    assert load_project(tmp_path).clarifications[0].answer == "Large supermarkets."


def test_codebase_facts_require_a_reference() -> None:
    decision = {"id": "sales-only", "decision": "Lists use sales data only."}
    with pytest.raises(ValidationError, match="codebase facts require a reference"):
        Project.model_validate(
            project_v2_data(design_decisions=[{**decision, "source": "codebase"}])
        )
    Project.model_validate(
        project_v2_data(design_decisions=[{**decision, "source": "owner"}])
    )


def test_install_preflights_conflicts_and_never_overwrites_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_uat import storage

    assets = tmp_path / "assets"
    (assets / ".github" / "skills" / "uat-run").mkdir(parents=True)
    source = assets / ".github" / "skills" / "uat-run" / "SKILL.md"
    source.write_text("asset", encoding="utf-8")
    monkeypatch.setattr(storage, "ASSETS_DIR", assets)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("keep me", encoding="utf-8")
    conflict = workspace / ".github" / "skills" / "uat-run" / "SKILL.md"
    conflict.parent.mkdir(parents=True)
    conflict.write_text("user version", encoding="utf-8")

    with pytest.raises(FileExistsError):
        install_assets(workspace)
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "keep me"
    assert conflict.read_text(encoding="utf-8") == "user version"

    (workspace / ".agentic-uat").mkdir()
    ignored = workspace / ".agentic-uat" / ".gitignore"
    installed = install_assets(workspace, force=True)
    assert conflict in installed
    assert conflict.read_text(encoding="utf-8") == "asset"
    assert ignored.is_file()
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "keep me"


def test_install_rejects_symlink_destinations_without_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_uat import storage

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "first.txt").write_text("first", encoding="utf-8")
    (assets / "later.txt").write_text("later", encoding="utf-8")
    monkeypatch.setattr(storage, "ASSETS_DIR", assets)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (workspace / "later.txt").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install_assets(workspace)
    assert not (workspace / "first.txt").exists()


def test_schema_command_emits_model_schemas() -> None:
    result = runner.invoke(app, ["schema", "project"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["properties"]["access"]["$ref"]
    assert schema["additionalProperties"] is False
    preflight = runner.invoke(app, ["schema", "preflight"])
    assert preflight.exit_code == 0
    assert "checks" in json.loads(preflight.stdout)["properties"]
    report = runner.invoke(app, ["schema", "report"])
    assert report.exit_code == 0
    assert "findings" in json.loads(report.stdout)["properties"]


def test_cli_help_is_available() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "install" in result.stdout
    assert "schema" in result.stdout


def test_run_command_says_browser_uat_was_not_executed(tmp_path: Path) -> None:
    init_project(tmp_path)
    write_project(tmp_path)
    result = runner.invoke(app, ["run", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "browser uat has not been executed" in result.stdout.lower()


def test_current_results_require_ux_assessment() -> None:
    missing = result_data()
    del missing["ux"]
    with pytest.raises(ValidationError, match="ux"):
        JourneyResult.model_validate(missing)
    assert JourneyResult.model_validate(legacy_result_data()).ux is None


def test_ux_ratings_need_known_evidence_unless_not_assessed() -> None:
    unsupported = result_data()
    ux = unsupported["ux"]
    assert isinstance(ux, dict)
    ux["ease_of_use"]["evidence"] = []
    with pytest.raises(ValidationError, match="evidence"):
        JourneyResult.model_validate(unsupported)

    unknown = result_data()
    ux = unknown["ux"]
    assert isinstance(ux, dict)
    ux["intuitiveness"]["evidence"] = ["not-recorded"]
    with pytest.raises(ValidationError, match="not-recorded"):
        JourneyResult.model_validate(unknown)


@pytest.mark.parametrize(
    ("status", "outcome", "blocker_kind"),
    [
        ("completed", "not_met", None),
        ("completed", "met", "application"),
        ("application_blocked", "not_met", None),
        ("setup_blocked", "not_assessed", "application"),
        ("policy_blocked", "not_assessed", "setup"),
    ],
)
def test_status_must_agree_with_criteria_and_blockers(
    status: str, outcome: str, blocker_kind: str | None
) -> None:
    data = result_data(status=status)
    ux = data["ux"]
    assert isinstance(ux, dict)
    ux["success_criteria"][0]["outcome"] = outcome
    ux["success_criteria"][0]["evidence"] = ["open-records"]
    ux["blockers"] = (
        []
        if blocker_kind is None
        else [{"kind": blocker_kind, "description": "Blocked.", "evidence": []}]
    )
    with pytest.raises(ValidationError, match="status"):
        JourneyResult.model_validate(data)


def test_performance_status_matches_recorded_timings() -> None:
    claimed = result_data()
    ux = claimed["ux"]
    assert isinstance(ux, dict)
    ux["performance"] = {
        "status": "measured",
        "notes": "Navigation timing.",
        "evidence": ["open-records"],
    }
    with pytest.raises(ValidationError, match="application_ms"):
        JourneyResult.model_validate(claimed)

    hidden = result_data()
    actions = hidden["actions"]
    assert isinstance(actions, list)
    actions[0]["application_ms"] = 412.5
    with pytest.raises(ValidationError, match="measured"):
        JourneyResult.model_validate(hidden)

    actions_claimed = claimed["actions"]
    assert isinstance(actions_claimed, list)
    actions_claimed[0]["application_ms"] = 412.5
    validated = JourneyResult.model_validate(claimed)
    assert validated.ux is not None
    assert validated.ux.performance.status == "measured"


def test_success_criteria_must_match_manifest_journey(tmp_path: Path) -> None:
    data = result_data()
    ux = data["ux"]
    assert isinstance(ux, dict)
    ux["success_criteria"][0]["criterion"] = "Something easier."
    with pytest.raises(ValueError, match="success criteria"):
        load_run(write_run(tmp_path, result=data))


def test_legacy_result_loads_with_visible_missing_ux_warning(tmp_path: Path) -> None:
    bundle = load_run(
        write_run(tmp_path, result=legacy_result_data(), score=score_data())
    )
    assert bundle.results[("member", "find-record")].ux is None
    assert (
        "UX assessment not recorded for member/find-record "
        "(schema version 1 result)." in bundle.warnings
    )


CAPABILITIES = [
    "open_page",
    "read_page",
    "interact",
    "capture_screenshot",
    "persist_screenshot",
    "delegate_subagent",
]


def preflight_data(
    *, missing: tuple[str, ...] = (), probe: str | None = "preflight/probe.png"
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": "run-2026-11-18t120000z",
        "checked_at": NOW.isoformat(),
        "status": "blocked" if missing else "ready",
        "checks": [
            {
                "capability": name,
                "available": name not in missing,
                "evidence": "Tool not in session inventory."
                if name in missing
                else f"Tool for {name} listed.",
            }
            for name in CAPABILITIES
        ],
        "probe_screenshot": probe,
    }


def test_preflight_status_must_follow_capability_checks() -> None:
    inconsistent = preflight_data(missing=("open_page",))
    inconsistent["status"] = "ready"
    with pytest.raises(ValidationError, match="status"):
        Preflight.model_validate(inconsistent)

    partial = preflight_data()
    checks = partial["checks"]
    assert isinstance(checks, list)
    checks.pop()
    with pytest.raises(ValidationError, match="delegate_subagent"):
        Preflight.model_validate(partial)

    with pytest.raises(ValidationError, match="probe"):
        Preflight.model_validate(preflight_data(probe=None))


def test_blocked_preflight_rejects_dispatched_journeys(tmp_path: Path) -> None:
    run_dir = write_run(
        tmp_path,
        result=result_data(status="setup_blocked", with_action=False),
        preflight=preflight_data(missing=("open_page",), probe=None),
    )
    with pytest.raises(ValueError, match="preflight"):
        load_run(run_dir)


def test_check_command_gates_journey_dispatch_on_ready_preflight(
    tmp_path: Path,
) -> None:
    missing = write_run(tmp_path / "missing")
    result = runner.invoke(app, ["check", str(missing), "--require-preflight"])
    assert result.exit_code == 1
    assert "preflight" in result.output.lower()

    blocked = write_run(
        tmp_path / "blocked",
        preflight=preflight_data(missing=("open_page",), probe=None),
    )
    result = runner.invoke(app, ["check", str(blocked), "--require-preflight"])
    assert result.exit_code == 1
    assert "open_page" in result.output

    ready = write_run(tmp_path / "ready", preflight=preflight_data())
    result = runner.invoke(app, ["check", str(ready), "--require-preflight"])
    assert result.exit_code == 1
    assert "probe" in result.output.lower()

    probe = ready / "preflight" / "probe.png"
    probe.parent.mkdir()
    from PIL import Image

    Image.new("RGB", (4, 4), "white").save(probe)
    result = runner.invoke(app, ["check", str(ready), "--require-preflight"])
    assert result.exit_code == 0, result.output
    assert "ready" in result.output.lower()


def test_results_without_preflight_record_warn(tmp_path: Path) -> None:
    bundle = load_run(write_run(tmp_path, result=result_data(), score=score_data()))
    assert "No preflight record; capability evidence is unavailable." in bundle.warnings
