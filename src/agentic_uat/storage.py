from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeVar

import yaml
from pydantic import BaseModel

from .models import (
    JourneyResult,
    Project,
    RunBundle,
    RunManifest,
    Score,
)

ASSETS_DIR = Path(__file__).parent / "assets"
MEMORY_DIR = ".agentic-uat"
PROJECT_FILE = "project.yaml"
RUNS_DIR = "runs"
_T = TypeVar("_T", bound=BaseModel)


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("artifact path must be a non-empty relative path")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or not posix.parts
        or any(part in {"", ".", ".."} for part in posix.parts)
        or "\\" in relative
    ):
        raise ValueError(f"unsafe artifact path: {relative}")
    base = root.resolve()
    candidate = base.joinpath(*posix.parts)
    try:
        candidate.resolve(strict=False).relative_to(base)
    except ValueError as exc:
        raise ValueError(f"artifact path escapes its root: {relative}") from exc
    return candidate


def load_project(workspace: Path) -> Project:
    project_path = workspace / MEMORY_DIR / PROJECT_FILE
    try:
        with project_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except OSError:
        raise
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid project YAML in {project_path}: {exc}") from exc
    return Project.model_validate(data)


def init_project(workspace: Path) -> Path:
    memory_dir = workspace / MEMORY_DIR
    _reject_symlink_components(workspace, memory_dir)
    memory_dir.mkdir(parents=True, exist_ok=True)
    project_path = memory_dir / PROJECT_FILE
    draft: dict[str, object] = {
        "schema_version": 1,
        "name": None,
        "base_url": None,
        "access": {
            "mode": None,
            "login_instructions": None,
            "vpn_required": None,
            "vpn_instructions": None,
            "proxy_required": None,
            "proxy_instructions": None,
            "openapi_url": None,
        },
        "personas": [],
        "approved_actions": [],
    }
    try:
        descriptor = os.open(project_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            yaml.safe_dump(draft, file, sort_keys=False, allow_unicode=True)
    context_path = memory_dir / "context.md"
    try:
        context_descriptor = os.open(
            context_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
    except FileExistsError:
        pass
    else:
        with os.fdopen(context_descriptor, "w", encoding="utf-8") as file:
            file.write(
                "# Application context\n\n"
                "## Terminology\n\n"
                "Record non-secret application terms here.\n\n"
                "## Interview notes\n\n"
                "Record non-secret interview context here. "
                "Keep structured intake answers in project.yaml.\n"
            )
    return project_path


def install_assets(workspace: Path, force: bool = False) -> list[Path]:
    if not ASSETS_DIR.is_dir():
        raise FileNotFoundError(f"packaged assets directory is missing: {ASSETS_DIR}")
    sources = sorted(path for path in ASSETS_DIR.rglob("*") if path.is_file())
    entries: list[tuple[Path | None, Path]] = [
        (source, source.relative_to(ASSETS_DIR)) for source in sources
    ]
    ignore_relative = Path(MEMORY_DIR, ".gitignore")
    if not any(
        relative.as_posix() == ignore_relative.as_posix() for _, relative in entries
    ):
        entries.append((None, ignore_relative))

    pending: list[tuple[Path | None, Path, Path]] = []
    conflicts: list[Path] = []
    for source, relative in entries:
        target = workspace / relative
        _reject_symlink_components(workspace, target)
        if target.exists():
            if target.is_dir():
                raise IsADirectoryError(f"asset destination is a directory: {target}")
            if relative.name == "AGENTS.md":
                continue
            same = source is not None and target.read_bytes() == source.read_bytes()
            if same:
                continue
            if relative == ignore_relative and source is None:
                continue
            if not force:
                conflicts.append(target)
                continue
        pending.append((source, relative, target))
    if conflicts:
        formatted = ", ".join(str(path) for path in conflicts)
        raise FileExistsError(
            f"conflicting asset files (use --force to replace): {formatted}"
        )

    installed: list[Path] = []
    for source, relative, target in pending:
        _reject_symlink_components(workspace, target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            target.write_text("/runs/\n", encoding="utf-8")
        else:
            target.write_bytes(source.read_bytes())
        installed.append(target)
    return installed


def prepare_run(workspace: Path) -> Path:
    project = load_project(workspace)
    memory_dir = workspace / MEMORY_DIR
    runs_dir = memory_dir / RUNS_DIR
    _reject_symlink_components(workspace, runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    while True:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S%f")
        run_id = f"run-{timestamp}z"
        run_dir = runs_dir / run_id
        try:
            run_dir.mkdir()
            break
        except FileExistsError:
            continue
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
        project=project,
    )
    (run_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return run_dir


def load_run(run_dir: Path) -> RunBundle:
    manifest_path = safe_path(run_dir, "manifest.json")
    manifest = _read_json(manifest_path, RunManifest)

    results: dict[tuple[str, str], JourneyResult] = {}
    scores: dict[tuple[str, str], Score] = {}
    warnings: list[str] = []
    known_keys: set[tuple[str, str]] = set()
    for persona in manifest.project.personas:
        for journey in persona.journeys:
            key = (persona.id, journey.id)
            known_keys.add(key)
            relative = f"journeys/{persona.id}/{journey.id}"
            journey_dir = safe_path(run_dir, relative)
            result_path = safe_path(run_dir, f"{relative}/result.json")
            score_path = safe_path(run_dir, f"{relative}/score.json")
            if not result_path.is_file():
                if score_path.exists():
                    raise ValueError(f"score file has no journey result: {score_path}")
                warnings.append(f"Missing result for {persona.id}/{journey.id}.")
                continue
            result = _read_json(result_path, JourneyResult)
            if (result.persona_id, result.journey_id) != key:
                raise ValueError(
                    f"result identifiers do not match manifest path {relative}"
                )
            _validate_screenshot_paths(run_dir, journey_dir, result, warnings)
            results[key] = result
            if not score_path.is_file():
                if result.status == "completed":
                    warnings.append(
                        f"Missing score for completed journey {persona.id}/{journey.id}."
                    )
                continue
            score = _read_json(score_path, Score)
            if (score.persona_id, score.journey_id) != key:
                raise ValueError(
                    f"score identifiers do not match manifest path {relative}"
                )
            if score.score is not None:
                if result.status not in {"completed", "application_blocked"}:
                    raise ValueError(
                        f"numeric score is not allowed for {result.status} journey {persona.id}/{journey.id}"
                    )
                available_evidence = (
                    {action.id for action in result.actions}
                    | {screenshot.id for screenshot in result.screenshots}
                    | {finding.id for finding in result.findings}
                )
                if not score.evidence or not (set(score.evidence) & available_evidence):
                    raise ValueError(
                        f"numeric score requires actual evidence for {persona.id}/{journey.id}"
                    )
            available_evidence = (
                {action.id for action in result.actions}
                | {screenshot.id for screenshot in result.screenshots}
                | {finding.id for finding in result.findings}
            )
            unknown = set(score.evidence) - available_evidence
            if unknown:
                raise ValueError(
                    f"unknown score evidence references for {persona.id}/{journey.id}: {sorted(unknown)}"
                )
            scores[key] = score

    _reject_unexpected_results(run_dir, known_keys)
    return RunBundle(
        manifest=manifest,
        results=results,
        scores=scores,
        warnings=warnings,
    )


def _read_json(path: Path, model: type[_T]) -> _T:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    return model.model_validate(data)


def _validate_screenshot_paths(
    run_dir: Path,
    journey_dir: Path,
    result: JourneyResult,
    warnings: list[str],
) -> None:
    for screenshot in result.screenshots:
        screenshot_path = safe_path(journey_dir, screenshot.file)
        try:
            screenshot_path.resolve(strict=False).relative_to(run_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"screenshot path escapes run directory: {screenshot.file}"
            ) from exc
        if not screenshot_path.is_file():
            warnings.append(
                f"Missing screenshot {screenshot.file} for "
                f"{result.persona_id}/{result.journey_id}."
            )


def _reject_unexpected_results(run_dir: Path, known_keys: set[tuple[str, str]]) -> None:
    journeys_dir = run_dir / "journeys"
    if not journeys_dir.exists():
        return
    for result_path in journeys_dir.rglob("result.json"):
        relative = result_path.relative_to(journeys_dir)
        if len(relative.parts) != 3:
            raise ValueError(f"unexpected journey result path: {relative}")
        key = (relative.parts[0], relative.parts[1])
        if key not in known_keys:
            raise ValueError(f"result is not declared in manifest: {relative}")


def _reject_symlink_components(root: Path, target: Path) -> None:
    root_path = root.absolute()
    target_path = target.absolute()
    try:
        relative = target_path.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"asset destination escapes workspace: {target}") from exc
    current = root_path
    if current.is_symlink():
        raise ValueError(f"symlink destinations are not allowed: {current}")
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"symlink destinations are not allowed: {current}")
