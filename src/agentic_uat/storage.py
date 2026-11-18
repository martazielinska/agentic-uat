from __future__ import annotations

import json
import os
import warnings as py_warnings
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeVar

import yaml
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from .models import (
    JourneyResult,
    Preflight,
    Project,
    ReportContent,
    RunBundle,
    RunManifest,
    Score,
)

ASSETS_DIR = Path(__file__).parent / "assets"
MEMORY_DIR = ".agentic-uat"
PROJECT_FILE = "project.yaml"
RUNS_DIR = "runs"
PREFLIGHT_FILE = "preflight.json"
REPORT_CONTENT_FILE = "report-content.json"
SCORE_ELIGIBLE = {"completed", "application_blocked"}
_IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_MAX_IMAGE_BYTES = 12 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_T = TypeVar("_T", bound=BaseModel)


def read_image(path: Path) -> tuple[bytes, str]:
    """Return verified image bytes and media type, rejecting unsafe files."""
    if path.stat().st_size > _MAX_IMAGE_BYTES:
        raise ValueError(f"Screenshot exceeds 12 MiB: {path}")
    raw = path.read_bytes()
    try:
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                media_type = _IMAGE_TYPES.get(image.format or "")
                if media_type is None:
                    raise ValueError(f"Unsupported screenshot image format: {path}")
                if image.width * image.height > _MAX_IMAGE_PIXELS:
                    raise ValueError(f"Screenshot exceeds 25 million pixels: {path}")
                image.verify()
            with Image.open(BytesIO(raw)) as decoded:
                decoded.load()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError(f"Invalid screenshot image {path}: {exc}") from exc
    return raw, media_type


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
    preflight = _load_preflight(run_dir, manifest)

    results: dict[tuple[str, str], JourneyResult] = {}
    scores: dict[tuple[str, str], Score] = {}
    warnings: list[str] = []
    known_keys: set[tuple[str, str]] = set()
    for persona in manifest.project.personas:
        for journey in persona.journeys:
            key = (persona.id, journey.id)
            label = f"{persona.id}/{journey.id}"
            known_keys.add(key)
            relative = f"journeys/{persona.id}/{journey.id}"
            journey_dir = safe_path(run_dir, relative)
            result_path = safe_path(run_dir, f"{relative}/result.json")
            score_path = safe_path(run_dir, f"{relative}/score.json")
            if not result_path.is_file():
                if score_path.exists():
                    raise ValueError(f"score file has no journey result: {score_path}")
                warnings.append(f"Missing result for {label}.")
                continue
            if preflight is not None and preflight.status == "blocked":
                raise ValueError(
                    f"journey result exists although preflight is blocked: {label}"
                )
            result = _read_json(result_path, JourneyResult)
            if (result.persona_id, result.journey_id) != key:
                raise ValueError(
                    f"result identifiers do not match manifest path {relative}"
                )
            if result.ux is None:
                warnings.append(
                    f"UX assessment not recorded for {label} "
                    f"(schema version {result.schema_version} result)."
                )
            elif [c.criterion for c in result.ux.success_criteria] != list(
                journey.success_criteria
            ):
                raise ValueError(
                    f"ux success criteria must match the manifest journey {label}"
                )
            _validate_screenshot_paths(run_dir, journey_dir, result, warnings)
            results[key] = result
            score = (
                _load_score(score_path, result, key) if score_path.is_file() else None
            )
            if score is not None:
                scores[key] = score
            if result.status in SCORE_ELIGIBLE and (
                score is None or score.score is None
            ):
                warnings.append(f"No numeric score for score-eligible journey {label}.")

    _reject_unexpected_results(run_dir, known_keys)
    if results and preflight is None:
        warnings.append("No preflight record; capability evidence is unavailable.")
    report_content = _load_report_content(run_dir, manifest, results, warnings)
    return RunBundle(
        manifest=manifest,
        preflight=preflight,
        results=results,
        scores=scores,
        warnings=warnings,
        report_content=report_content,
    )


def _load_report_content(
    run_dir: Path,
    manifest: RunManifest,
    results: dict[tuple[str, str], JourneyResult],
    warnings: list[str],
) -> ReportContent | None:
    path = safe_path(run_dir, REPORT_CONTENT_FILE)
    if not path.exists():
        return None
    content = _read_json(path, ReportContent)
    if content.run_id != manifest.run_id:
        raise ValueError("report content run_id does not match the manifest")

    recorded = {
        (persona_id, journey_id, finding.id): finding
        for (persona_id, journey_id), result in results.items()
        for finding in result.findings
    }
    represented: set[tuple[str, str, str]] = set()
    extra_images = safe_path(run_dir, "report-evidence").resolve()
    for item in content.findings:
        allowed_images: set[Path] = set()
        for source in item.sources:
            key = (source.persona_id, source.journey_id, source.finding_id)
            finding = recorded.get(key)
            if finding is None:
                raise ValueError(f"unknown report finding source: {'/'.join(key)}")
            represented.add(key)
            result = results[(source.persona_id, source.journey_id)]
            journey_dir = safe_path(
                run_dir, f"journeys/{source.persona_id}/{source.journey_id}"
            )
            allowed_images.update(
                safe_path(journey_dir, screenshot.file).resolve()
                for screenshot in result.screenshots
                if screenshot.id in finding.evidence
                or (
                    screenshot.action_id is not None
                    and screenshot.action_id in finding.evidence
                )
            )
        for screenshot in item.screenshots:
            image = safe_path(run_dir, screenshot.file)
            supplemental = image.resolve().is_relative_to(extra_images)
            if image.resolve() not in allowed_images and not (
                supplemental and screenshot.captured_at is not None
            ):
                raise ValueError(
                    "report screenshot must support a referenced finding or be "
                    f"a dated image in report-evidence/: {screenshot.file}"
                )
            if image.exists() and not image.is_file():
                raise ValueError(f"Screenshot must be a regular file: {image}")
            if not image.is_file():
                warnings.append(f"Missing report screenshot {screenshot.file}.")
            else:
                read_image(image)

    missing = recorded.keys() - represented
    if missing:
        omitted = ", ".join("/".join(key) for key in sorted(missing))
        raise ValueError(f"report content omits recorded findings: {omitted}")
    return content


def _load_preflight(run_dir: Path, manifest: RunManifest) -> Preflight | None:
    path = safe_path(run_dir, PREFLIGHT_FILE)
    if not path.exists():
        return None
    preflight = _read_json(path, Preflight)
    if preflight.run_id != manifest.run_id:
        raise ValueError("preflight run_id does not match the manifest")
    if preflight.probe_screenshot is not None:
        probe = safe_path(run_dir, preflight.probe_screenshot)
        if not probe.is_file():
            raise ValueError(
                f"preflight probe screenshot is missing: {preflight.probe_screenshot}"
            )
        read_image(probe)
    return preflight


def _load_score(score_path: Path, result: JourneyResult, key: tuple[str, str]) -> Score:
    label = f"{key[0]}/{key[1]}"
    score = _read_json(score_path, Score)
    if (score.persona_id, score.journey_id) != key:
        raise ValueError(f"score identifiers do not match manifest path {label}")
    available_evidence = (
        {action.id for action in result.actions}
        | {screenshot.id for screenshot in result.screenshots}
        | {finding.id for finding in result.findings}
    )
    if score.score is not None:
        if result.status not in SCORE_ELIGIBLE:
            raise ValueError(
                f"numeric score is not allowed for {result.status} journey {label}"
            )
        if not set(score.evidence) & available_evidence:
            raise ValueError(f"numeric score requires actual evidence for {label}")
    unknown = set(score.evidence) - available_evidence
    if unknown:
        raise ValueError(
            f"unknown score evidence references for {label}: {sorted(unknown)}"
        )
    return score


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
