"""Validate template metadata and runtime-input compatibility."""

from collections.abc import Mapping

from report_agent.metadata.models import TemplateMetadata
from report_agent.models.inputs import (
    ContentInput,
    FigureInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)
from report_agent.models.results import Diagnostic
from report_agent.models.template import TemplateBundle
from report_agent.rendering.registry import RendererRegistry
from report_agent.templates.engine import TemplateEngine
from report_agent.validation.text import text_issues


class RenderValidator:
    def __init__(
        self, template_engine: TemplateEngine, renderers: RendererRegistry
    ) -> None:
        self._template_engine = template_engine
        self._renderers = renderers

    def validate(
        self,
        metadata: TemplateMetadata,
        bundle: TemplateBundle,
        inputs: Mapping[str, ContentInput],
    ) -> tuple[Diagnostic, ...]:
        """Check required inputs, types, placeholders, and permitted options."""
        issues = []

        def issue(code: str, message: str, name: str) -> None:
            issues.append(
                Diagnostic("input_validation", code, message, input_name=name)
            )

        variables = self._template_engine.variables(bundle)
        for name in sorted(variables - metadata.inputs.keys()):
            issue(
                "undeclared_placeholder",
                "Placeholder is not declared in metadata.",
                name,
            )
        for name in sorted(metadata.inputs.keys() - variables):
            issue("unused_input", "Declared input has no template placeholder.", name)
        for name in inputs.keys() - metadata.inputs.keys():
            issue("unknown_input", "Runtime input is not declared in metadata.", name)
        types = {
            "text": (TextInput,),
            "image": (ImageInput,),
            "graph": (GraphInput, FigureInput),
            "table": (TableInput,),
        }
        for name, definition in metadata.inputs.items():
            if name not in inputs:
                if definition.required and definition.default is None:
                    issue("missing_input", "Required input was not supplied.", name)
                continue
            value = inputs[name]
            try:
                self._renderers.get(definition.type, definition.backend)
            except ValueError as exc:
                issue("unsupported_backend", str(exc), name)
            if not isinstance(value, types[definition.type]):
                issue("input_type", f"Expected a typed {definition.type} input.", name)
            elif isinstance(value, TextInput):
                for code, message in text_issues(value, definition):
                    issue(code, message, name)
        return tuple(issues)
