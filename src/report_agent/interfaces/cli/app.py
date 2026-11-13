"""Command-line entry point for report-agent."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from report_agent.application.bootstrap import create_renderer
from report_agent.application.request import RenderRequest
from report_agent.interfaces.cli.inputs import InputFileLoader
from report_agent.models.inputs import TextInput

app = typer.Typer(
    help="Render template-based PDF and Office reports.",
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
        Path,
        typer.Option(
            "--output", "-o", help="Destination PDF, DOCX, XLSX, or PPTX path."
        ),
    ],
    text: Annotated[
        list[str] | None,
        typer.Option("--text", help="Text input as NAME=VALUE; repeat as needed."),
    ] = None,
    table: Annotated[
        list[str] | None,
        typer.Option("--table", help="Table as NAME=CSV_OR_PARQUET_PATH."),
    ] = None,
    image: Annotated[
        list[str] | None, typer.Option("--image", help="Image as NAME=PATH.")
    ] = None,
    graph: Annotated[
        list[str] | None, typer.Option("--graph", help="Graph file as NAME=PATH.")
    ] = None,
    animation: Annotated[
        list[str] | None,
        typer.Option("--animation", help="Animation as NAME=GIF_PATH."),
    ] = None,
    inputs_file: Annotated[
        Path | None,
        typer.Option(
            "--inputs",
            help="JSON/YAML content file; explicit flags override its values.",
        ),
    ] = None,
    input_root: Annotated[
        Path | None,
        typer.Option(
            "--input-root", help="Restrict all input asset paths to this directory."
        ),
    ] = None,
) -> None:
    """Render using text, file-backed assets, and JSON/YAML input manifests."""
    try:
        loader = InputFileLoader(base_directory=input_root)
        inputs = loader.load(inputs_file) if inputs_file is not None else {}
        explicit = set()
        for kind, items in [
            ("text", text),
            ("table", table),
            ("image", image),
            ("graph", graph),
            ("animation", animation),
        ]:
            for item in items or []:
                name, separator, value = item.partition("=")
                if not separator or not name or name in explicit:
                    raise ValueError(
                        "Use unique NAME=VALUE entries across input flags."
                    )
                explicit.add(name)
                inputs[name] = (
                    TextInput(value)
                    if kind == "text"
                    else loader.from_path(kind, Path(value).expanduser())
                )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    result = create_renderer().render(RenderRequest(template, metadata, inputs, output))
    for diagnostic in result.diagnostics:
        label = f" ({diagnostic.input_name})" if diagnostic.input_name else ""
        typer.echo(
            f"{diagnostic.severity}: {diagnostic.stage}/{diagnostic.code}{label}: "
            f"{diagnostic.message}",
            err=True,
        )
    if result.output_path is None:
        raise typer.Exit(1)
    typer.echo(str(result.output_path))
