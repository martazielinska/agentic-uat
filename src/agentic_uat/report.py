"""Render validated journey evidence as a portable, offline report."""

import base64
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .models import Finding, Journey, JourneyResult, Persona, Score
from .storage import load_run, read_image, safe_path

_STATUS_LABELS = {
    "completed": "Completed",
    "application_blocked": "Application blocked",
    "setup_blocked": "Setup blocked",
    "policy_blocked": "Policy blocked",
    "incomplete": "Incomplete",
}
_SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}
_SEVERITY_LABELS = {
    "info": "What works",
    "minor": "Minor",
    "major": "Major",
    "critical": "Critical",
}


@dataclass(frozen=True)
class ScreenshotView:
    caption: str
    data_url: str | None
    captured_at: datetime | None = None


@dataclass(frozen=True)
class FindingView:
    title: str
    severity: str
    observation: str
    impact: str | None
    location: str | None
    recommendation: str
    tasks: list[str]
    screenshots: list[ScreenshotView]


@dataclass(frozen=True)
class JourneyView:
    persona: Persona
    journey: Journey
    result: JourneyResult | None
    score: Score | None
    status: str
    status_label: str


def _image_data(path: Path) -> str:
    raw, media_type = read_image(path)
    return f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"


def _cached_image(path: Path, cache: dict[Path, str | None]) -> str | None:
    if path not in cache:
        if path.exists() and not path.is_file():
            raise ValueError(f"Screenshot must be a regular file: {path}")
        cache[path] = _image_data(path) if path.is_file() else None
    return cache[path]


def render_report(run_dir: Path, output: Path | None = None) -> Path:
    """Validate a run and write a self-contained HTML report atomically."""
    bundle = load_run(run_dir)
    output = output if output is not None else run_dir / "report.html"
    if output.suffix.lower() != ".html":
        raise ValueError("Report output must have an .html extension.")
    if output.is_symlink():
        raise ValueError(f"Report output must not be a symlink: {output}")

    image_cache: dict[Path, str | None] = {}
    views: list[JourneyView] = []
    findings: list[FindingView] = []
    journeys: dict[tuple[str, str], Journey] = {}
    recorded: dict[tuple[str, str, str], Finding] = {}
    for persona in bundle.manifest.project.personas:
        for journey in persona.journeys:
            key = (persona.id, journey.id)
            journeys[key] = journey
            result = bundle.results.get(key)
            score = bundle.scores.get(key)
            if result is not None:
                journey_dir = safe_path(run_dir, f"journeys/{persona.id}/{journey.id}")
                for screenshot in result.screenshots:
                    image_path = safe_path(journey_dir, screenshot.file)
                    _cached_image(image_path, image_cache)
                for finding in result.findings:
                    recorded[(key[0], key[1], finding.id)] = finding
                    if bundle.report_content is None:
                        screenshots = [
                            ScreenshotView(
                                caption=screenshot.caption,
                                data_url=image_cache[
                                    safe_path(journey_dir, screenshot.file)
                                ],
                            )
                            for screenshot in result.screenshots
                            if screenshot.id in finding.evidence
                        ]
                        findings.append(
                            FindingView(
                                title=finding.title or finding.category,
                                severity=finding.severity,
                                observation=finding.observation,
                                impact=finding.impact,
                                location=finding.location,
                                recommendation=finding.recommendation,
                                tasks=[journey.name],
                                screenshots=screenshots,
                            )
                        )
            status = result.status if result is not None else "not_executed"
            views.append(
                JourneyView(
                    persona=persona,
                    journey=journey,
                    result=result,
                    score=score,
                    status=status,
                    status_label=_STATUS_LABELS.get(status, "Not assessed"),
                )
            )

    content = bundle.report_content
    if content is not None:
        for item in content.findings:
            source_findings = [
                recorded[(source.persona_id, source.journey_id, source.finding_id)]
                for source in item.sources
            ]
            tasks = list(
                dict.fromkeys(
                    journeys[(source.persona_id, source.journey_id)].name
                    for source in item.sources
                )
            )
            screenshots = [
                ScreenshotView(
                    caption=screenshot.caption,
                    data_url=_cached_image(
                        safe_path(run_dir, screenshot.file), image_cache
                    ),
                    captured_at=screenshot.captured_at,
                )
                for screenshot in item.screenshots
            ]
            findings.append(
                FindingView(
                    title=item.title,
                    severity=max(
                        (finding.severity for finding in source_findings),
                        key=_SEVERITY_RANK.__getitem__,
                    ),
                    observation=item.observation,
                    impact=item.impact,
                    location=item.location,
                    recommendation=item.recommendation,
                    tasks=tasks,
                    screenshots=screenshots,
                )
            )
    findings.sort(key=lambda finding: -_SEVERITY_RANK[finding.severity])

    env = Environment(
        loader=PackageLoader("agentic_uat", "templates"),
        autoescape=select_autoescape(("html",)),
    )
    html = env.get_template("report.html").render(
        manifest=bundle.manifest,
        content=content,
        severity_labels=_SEVERITY_LABELS,
        views=views,
        findings=findings,
        blocked_capabilities=(
            bundle.preflight.unavailable()
            if bundle.preflight is not None and bundle.preflight.status == "blocked"
            else []
        ),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(html)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output
