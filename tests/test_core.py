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
from agentic_uat.models import JourneyResult, Project, Score
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
        "schema_version": 1,
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
    }


def write_run(
    root: Path,
    *,
    result: dict[str, object] | None = None,
    score: dict[str, object] | None = None,
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
    return run_dir


def write_project(workspace: Path) -> Path:
    project_file = workspace / ".agentic-uat" / "project.yaml"
    project_file.parent.mkdir(parents=True, exist_ok=True)
    project_file.write_text(yaml.safe_dump(project_data()), encoding="utf-8")
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
    result = result_data()
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


def test_completed_without_score_is_a_warning_not_a_synthetic_score(
    tmp_path: Path,
) -> None:
    bundle = load_run(write_run(tmp_path, result=result_data()))
    assert bundle.scores == {}
    assert any("score" in warning.lower() for warning in bundle.warnings)


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
