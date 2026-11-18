from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer
import yaml
from pydantic import ValidationError

from . import models
from .storage import init_project, install_assets, load_project, prepare_run

app = typer.Typer(no_args_is_help=True, help="Evidence-backed Copilot UAT tools.")
SchemaName = Literal["project", "journey", "score", "manifest"]


def _show_error(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)


@app.command()
def install(
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", file_okay=False, dir_okay=True)
    ] = Path("."),
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Install packaged Copilot skills and agents in a workspace."""
    try:
        installed = install_assets(workspace, force=force)
    except (OSError, ValueError) as exc:
        _show_error(exc)
        raise typer.Exit(1) from exc
    typer.echo(f"Installed {len(installed)} asset(s) in {workspace}.")


@app.command()
def init(
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", file_okay=False, dir_okay=True)
    ] = Path("."),
) -> None:
    """Create an explicit, incomplete project-memory draft."""
    try:
        project_path = init_project(workspace)
    except OSError as exc:
        _show_error(exc)
        raise typer.Exit(1) from exc
    typer.echo(f"Project draft: {project_path}")


@app.command()
def validate(
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", file_okay=False, dir_okay=True)
    ] = Path("."),
) -> None:
    """Validate project memory before preparing a run."""
    try:
        project = load_project(workspace)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        _show_error(exc)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Project '{project.name}' is valid ({len(project.personas)} persona(s))."
    )


@app.command()
def run(
    workspace: Annotated[
        Path, typer.Option("--workspace", "-w", file_okay=False, dir_okay=True)
    ] = Path("."),
) -> None:
    """Prepare run artifacts and hand off browser work to Copilot."""
    try:
        run_dir = prepare_run(workspace)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        _show_error(exc)
        raise typer.Exit(1) from exc
    typer.echo(f"Prepared run: {run_dir}")
    typer.echo("Invoke the installed UAT coordinator in Copilot to execute this run.")
    typer.echo("Browser UAT has not been executed by this command.")


@app.command()
def report(
    run_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", file_okay=True, dir_okay=False)
    ] = None,
) -> None:
    """Render a validated run as a portable HTML report."""
    try:
        from .report import render_report

        report_path = render_report(run_dir, output)
    except (OSError, ValueError, ValidationError) as exc:
        _show_error(exc)
        raise typer.Exit(1) from exc
    typer.echo(f"Report: {report_path}")


@app.command()
def schema(
    name: Annotated[SchemaName, typer.Argument(help="Artifact schema to emit.")],
) -> None:
    """Print a JSON Schema for an artifact model."""
    schema_models: dict[str, type[models.Model]] = {
        "project": models.Project,
        "journey": models.JourneyResult,
        "score": models.Score,
        "manifest": models.RunManifest,
    }
    typer.echo(
        json.dumps(schema_models[name].model_json_schema(), indent=2, sort_keys=True)
    )
