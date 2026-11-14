"""Command-line entry point for report-agent."""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from report_agent.application.bootstrap import create_renderer
from report_agent.application.request import RenderRequest
from report_agent.interfaces.cli.inputs import InputFileLoader
from report_agent.interfaces.cli.resolution import load_queries, load_resolver
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


@app.command("serve")
def serve(
    library: Path = Path("report_library"),
    output: Path = Path("output/runs"),
    connections: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 7860,
) -> None:
    """Launch conversational report onboarding and parameterized runs."""
    try:
        from report_agent.agent.config import AgentConfig
        from report_agent.application.conversation import ConversationService
        from report_agent.application.onboarding import OnboardingService
        from report_agent.application.report_runs import ReportRuns
        from report_agent.connectors.registry import load_sources
        from report_agent.interfaces.gradio.app import create_app
        from report_agent.interfaces.gradio.theme import launch_options
        from report_agent.storage.report_definitions import ReportStore

        config = AgentConfig.from_environment()
        store = ReportStore(library)
        sources = load_sources(connections)
        runs = ReportRuns(store, sources, output)
        service = ConversationService(config, OnboardingService(store, runs), sources)
        create_app(service).launch(
            server_name=host,
            server_port=port,
            share=False,
            max_file_size="20mb",
            **launch_options(),
        )
    except ImportError as exc:
        raise typer.BadParameter(
            "Install optional features with uv sync --extra agent."
        ) from exc
    except (ValueError, OSError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("run")
def run_saved_report(
    reference: str,
    parameters: Annotated[
        Path, typer.Option("--parameters", help="JSON parameter values.")
    ],
    library: Path = Path("report_library"),
    output: Path = Path("output/runs"),
    connections: Path | None = None,
) -> None:
    """Run a saved accepted report; supplying parameters authorizes this CLI run."""
    import json

    from report_agent.application.report_runs import ReportRuns
    from report_agent.connectors.files import FileSource
    from report_agent.connectors.registry import load_sources
    from report_agent.storage.report_definitions import ReportStore

    try:
        if not reference.startswith("accepted/"):
            raise ValueError("Use an accepted report reference.")
        sources = load_sources(connections)
        for path in (library / "sources").glob("*/source.json"):
            data = json.loads(path.read_text())
            sources[data["name"]] = FileSource(
                path.parent / data["file"], filters=data.get("filters")
            )
        result = ReportRuns(ReportStore(library), sources, output).run(
            reference, json.loads(parameters.read_text())
        )
    except (ValueError, OSError, KeyError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    for diagnostic in result.diagnostics:
        typer.echo(f"{diagnostic.severity}: {diagnostic.message}", err=True)
    if result.output_path is None:
        raise typer.Exit(1)
    typer.echo(str(result.output_path))


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
    resolver_factory: Annotated[
        str | None,
        typer.Option(
            "--resolver",
            help="Trusted application module:factory returning ContentResolver.",
        ),
    ] = None,
    queries_file: Annotated[
        Path | None,
        typer.Option(
            "--queries", help="JSON/YAML query bindings for the application resolver."
        ),
    ] = None,
) -> None:
    """Render using text, file-backed assets, and JSON/YAML input manifests."""
    try:
        queries = load_queries(queries_file) if queries_file is not None else {}
        resolver = load_resolver(resolver_factory) if resolver_factory else None
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
    result = create_renderer(resolver=resolver).render(
        RenderRequest(template, metadata, inputs, output, queries=queries)
    )
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
