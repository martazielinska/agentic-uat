"""Render validated journey evidence as a portable, offline report."""

import base64
import os
import tempfile
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from PIL import Image, UnidentifiedImageError

from .models import Journey, JourneyResult, Persona, Score
from .storage import load_run, safe_path

_IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_MAX_IMAGE_BYTES = 12 * 1024 * 1024
_MAX_IMAGE_PIXELS = 25_000_000
_STATUS_LABELS = {
    "completed": "Completed",
    "application_blocked": "Application blocked",
    "setup_blocked": "Setup blocked",
    "policy_blocked": "Policy blocked",
    "incomplete": "Incomplete",
}


@dataclass(frozen=True)
class ScreenshotView:
    id: str
    caption: str
    file: str
    data_url: str | None


@dataclass(frozen=True)
class JourneyView:
    persona: Persona
    journey: Journey
    result: JourneyResult | None
    score: Score | None
    status: str
    status_label: str
    clicks: int | None
    elapsed_seconds: float | None
    screenshots: list[ScreenshotView]


def _image_data(path: Path) -> str:
    if path.stat().st_size > _MAX_IMAGE_BYTES:
        raise ValueError(f"Screenshot exceeds 12 MiB: {path}")
    raw = path.read_bytes()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
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
    return f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"


def render_report(run_dir: Path, output: Path | None = None) -> Path:
    """Validate a run and write a self-contained HTML report atomically."""
    bundle = load_run(run_dir)
    output = output if output is not None else run_dir / "report.html"
    if output.suffix.lower() != ".html":
        raise ValueError("Report output must have an .html extension.")
    if output.is_symlink():
        raise ValueError(f"Report output must not be a symlink: {output}")

    report_warnings = list(bundle.warnings)
    views: list[JourneyView] = []
    for persona in bundle.manifest.project.personas:
        for journey in persona.journeys:
            key = (persona.id, journey.id)
            result = bundle.results.get(key)
            score = bundle.scores.get(key)
            screenshots: list[ScreenshotView] = []
            if result is not None:
                journey_dir = safe_path(run_dir, f"journeys/{persona.id}/{journey.id}")
                for screenshot in result.screenshots:
                    image_path = safe_path(journey_dir, screenshot.file)
                    if image_path.exists() and not image_path.is_file():
                        raise ValueError(
                            f"Screenshot must be a regular file: {image_path}"
                        )
                    if not image_path.is_file():
                        report_warnings.append(
                            f"Missing screenshot: {persona.id}/{journey.id}/"
                            f"{screenshot.file}"
                        )
                        data_url = None
                    else:
                        data_url = _image_data(image_path)
                    screenshots.append(
                        ScreenshotView(
                            id=screenshot.id,
                            caption=screenshot.caption,
                            file=screenshot.file,
                            data_url=data_url,
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
                    status_label=_STATUS_LABELS.get(status, "Not executed"),
                    clicks=(
                        sum(action.kind == "click" for action in result.actions)
                        if result is not None
                        else None
                    ),
                    elapsed_seconds=(
                        (result.finished_at - result.started_at).total_seconds()
                        if result is not None
                        else None
                    ),
                    screenshots=screenshots,
                )
            )

    env = Environment(
        loader=PackageLoader("agentic_uat", "templates"),
        autoescape=select_autoescape(("html",)),
    )
    html = env.get_template("report.html").render(
        manifest=bundle.manifest,
        views=views,
        warnings=list(dict.fromkeys(report_warnings)),
        scored_count=sum(
            v.score is not None and v.score.score is not None for v in views
        ),
        completed_count=sum(v.status == "completed" for v in views),
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
