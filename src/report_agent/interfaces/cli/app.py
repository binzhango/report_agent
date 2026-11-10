"""Command-line entry point for report-agent."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from report_agent.application.bootstrap import create_renderer
from report_agent.application.request import RenderRequest
from report_agent.models.inputs import TextInput

app = typer.Typer(
    help="Render LaTeX templates into PDF reports with metadata and runtime content.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Manage business reports."""


@app.command("version")
def show_version() -> None:
    """Show the installed report-agent version."""
    typer.echo(version("report-agent"))


@app.command("render")
def render_report(
    template: Annotated[
        Path, typer.Argument(help="Template file or bundle directory.")
    ],
    metadata: Annotated[
        Path, typer.Option("--metadata", "-m", help="JSON or YAML metadata.")
    ],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Destination PDF path.")
    ],
    text: Annotated[
        list[str] | None,
        typer.Option("--text", help="Text input as NAME=VALUE; repeat as needed."),
    ] = None,
) -> None:
    """Render a complete template using supplied plain-text inputs."""
    inputs = {}
    for item in text or []:
        name, separator, value = item.partition("=")
        if not separator or not name or name in inputs:
            raise typer.BadParameter("Use unique NAME=VALUE entries for --text.")
        inputs[name] = TextInput(value)
    result = create_renderer().render(RenderRequest(template, metadata, inputs, output))
    for diagnostic in result.diagnostics:
        label = f" ({diagnostic.input_name})" if diagnostic.input_name else ""
        typer.echo(
            f"{diagnostic.severity}: {diagnostic.stage}/{diagnostic.code}{label}: "
            f"{diagnostic.message}",
            err=True,
        )
    if result.pdf_path is None:
        raise typer.Exit(1)
    typer.echo(str(result.pdf_path))
