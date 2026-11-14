"""Deterministic execution of saved definitions with new parameter values."""

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from report_agent import RenderRequest, TableInput, TextInput, create_renderer
from report_agent.definitions.bindings import bind_queries
from report_agent.errors import ReportError
from report_agent.models.inputs import GraphInput


class ReportRuns:
    def __init__(self, store, sources, output_root: Path, *, renderer=None):
        self.store, self.sources, self.output_root = (
            store,
            sources,
            output_root.resolve(),
        )
        self.renderer = renderer or create_renderer()

    def prepare(self, reference, supplied):
        definition = self.store.load(reference)
        params, queries = bind_queries(definition, supplied)
        for query in queries.values():
            if query.connection not in self.sources:
                raise ReportError(f"Data source is unavailable: {query.connection}")
        return definition, params, queries

    def fetch(self, definition, queries):
        tables = {}
        for name, query in queries.items():
            from report_agent.connectors.files import FileSource

            source = self.sources[query.connection]
            binding = definition.queries[name]
            if binding.filters:
                if not isinstance(source, FileSource):
                    raise ReportError("Column filters require a file source.")
                source = FileSource(
                    source.path,
                    filters={
                        key: value.model_dump()
                        for key, value in binding.filters.items()
                    },
                )
            frame = source.fetch(query)
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                raise ReportError(f"{name}: data source returned no rows.")
            if len(frame) > query.row_limit:
                raise ReportError(f"{name}: row limit exceeded.")
            missing = set(definition.queries[name].columns) - set(frame.columns)
            if missing:
                raise ReportError(f"{name}: missing columns {sorted(missing)}")
            tables[name] = frame.loc[:, binding.columns] if binding.columns else frame
        return tables

    def run(self, reference, supplied, *, sample_tables=None):
        definition = self.store.load(reference)
        params, queries = bind_queries(definition, supplied)
        directory = self.output_root / uuid4().hex
        directory.mkdir(parents=True)
        record = {
            "reference": reference,
            "parameters": params,
            "preview": sample_tables is not None,
        }
        try:
            if sample_tables is None:
                self.prepare(reference, supplied)
                tables = self.fetch(definition, queries)
            else:
                if set(sample_tables) != set(queries):
                    raise ReportError("Provide demonstration records for every query.")
                tables = {
                    name: pd.DataFrame(rows) for name, rows in sample_tables.items()
                }
                for name, frame in tables.items():
                    if frame.empty or len(frame) > 20:
                        raise ReportError("Demonstration tables require 1–20 rows.")
                    if set(definition.queries[name].columns) - set(frame.columns):
                        raise ReportError(
                            f"Sample table {name} lacks required columns."
                        )
            inputs = {}
            for name, template in definition.text_bindings.items():
                try:
                    inputs[name] = TextInput(template.format_map(params))
                except KeyError as exc:
                    raise ReportError(f"Missing text parameter: {exc.args[0]}") from exc
            for block in definition.layout.blocks:
                if block.kind == "table":
                    frame = tables[block.name]
                    if definition.layout.format == "pptx" and (
                        len(frame) > 12 or len(frame.columns) > 6
                    ):
                        raise ReportError(
                            "Slide tables support up to 12 rows and 6 columns; "
                            "aggregate or split the data."
                        )
                    inputs[block.name] = TableInput(frame)
                elif block.kind == "chart":
                    chart = definition.charts[block.name]
                    inputs[block.name] = GraphInput(
                        _chart(
                            tables[chart.table], chart, directory / f"{block.name}.png"
                        )
                    )
                elif definition.layout.format == "pptx":
                    text = inputs.get(block.name, TextInput(block.text)).text
                    if len(text) > 700:
                        raise ReportError(
                            f"{block.name}: slide text must be <=700 characters."
                        )
            result = self.renderer.render(
                RenderRequest(
                    template=self.store.path(reference),
                    metadata=self.store.path(reference) / "template.yaml",
                    inputs=inputs,
                    output=directory / f"{definition.id}.{definition.layout.format}",
                )
            )
            record["status"] = "succeeded" if result.output_path else "failed"
            record["diagnostics"] = [d.__dict__ for d in result.diagnostics]
            record["output"] = str(result.output_path) if result.output_path else None
            return result
        except Exception as exc:
            record.update(status="failed", error=str(exc))
            raise
        finally:
            (directory / "run.json").write_text(
                json.dumps(record, indent=2, default=str)
            )


def _chart(frame, chart, path):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if chart.x not in frame or chart.y not in frame:
        raise ReportError("Chart columns are missing.")
    if len(frame) > 50 or not pd.api.types.is_numeric_dtype(frame[chart.y]):
        raise ReportError("Charts require at most 50 rows and a numeric y column.")
    figure = Figure(figsize=(9, 4.5), layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    getattr(axes, chart.kind)(
        frame[chart.x].astype(str), frame[chart.y], color="#17665B"
    )
    axes.set_ylabel(chart.y)
    axes.tick_params(axis="x", labelrotation=30)
    figure.savefig(path, dpi=150)
    return path
