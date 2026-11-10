"""Public report facade; collaborators own individual rendering stages."""

from collections.abc import Mapping
from pathlib import Path
from shutil import copyfile

from jinja2 import TemplateError

from report_agent.application.request import RenderRequest
from report_agent.application.validation import RenderValidator
from report_agent.compilation.base import LatexCompiler
from report_agent.metadata.loader import MetadataLoader
from report_agent.metadata.models import TemplateMetadata
from report_agent.models.inputs import ContentInput, TextInput
from report_agent.models.results import (
    CompileResult,
    Diagnostic,
    RenderedContent,
    RenderResult,
)
from report_agent.models.template import RenderContext, TemplateBundle
from report_agent.presentation.styler import PlaceholderStyler
from report_agent.rendering.registry import RendererRegistry
from report_agent.storage.artifacts import ArtifactStore
from report_agent.storage.workspace import WorkspaceManager
from report_agent.templates.engine import TemplateEngine
from report_agent.templates.repository import TemplateRepository

_RETAINED_EXTENSIONS = {
    ".tex",
    ".sty",
    ".cls",
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".otf",
    ".ttf",
}


class _ContentError(ValueError):
    def __init__(self, input_name: str, cause: Exception) -> None:
        super().__init__(str(cause))
        self.input_name = input_name


class ReportRenderer:
    def __init__(
        self,
        *,
        metadata_loader: MetadataLoader,
        templates: TemplateRepository,
        validator: RenderValidator,
        renderers: RendererRegistry,
        template_engine: TemplateEngine,
        compiler: LatexCompiler,
        workspaces: WorkspaceManager,
        artifacts: ArtifactStore,
        styler: PlaceholderStyler,
    ) -> None:
        self._metadata_loader = metadata_loader
        self._templates = templates
        self._validator = validator
        self._renderers = renderers
        self._template_engine = template_engine
        self._compiler = compiler
        self._workspaces = workspaces
        self._artifacts = artifacts
        self._styler = styler

    def render(self, request: RenderRequest) -> RenderResult:
        """Build one report without retaining mutable per-request state."""
        stage = "metadata"
        try:
            metadata = self._metadata_loader.load(request.metadata)
            stage = "template"
            bundle = self._templates.load(request.template, metadata)
            stage = "validation"
            output = Path(request.output).expanduser().absolute()
            if output.suffix.lower() != ".pdf":
                raise ValueError("Output path must end in .pdf.")
            issues = self._validator.validate(metadata, bundle, request.inputs)
            if issues:
                return RenderResult(None, issues)
            with self._workspaces.create() as workspace:
                stage = "staging"
                staged = self._stage(bundle, workspace / "template")
                stage = "content"
                content = self._content(metadata, request.inputs, workspace, staged)
                stage = "template"
                source = self._template_engine.render(staged, content)
                staged.entrypoint.write_text(source, encoding="utf-8")
                stage = "compilation"
                compiled = self._compiler.compile(staged.entrypoint, metadata.compiler)
                stage = "publication"
                return self._publish(bundle, staged, content, compiled, output)
        except (OSError, ValueError, TemplateError) as exc:
            return RenderResult(
                None,
                (
                    Diagnostic(
                        stage,
                        "invalid_input"
                        if isinstance(exc, ValueError)
                        else "build_failed",
                        str(exc),
                        input_name=exc.input_name
                        if isinstance(exc, _ContentError)
                        else None,
                    ),
                ),
            )

    @staticmethod
    def _stage(bundle: TemplateBundle, root: Path) -> TemplateBundle:
        resources = []
        for resource in bundle.resources:
            destination = root / resource.relative_to(bundle.root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(resource, destination)
            resources.append(destination)
        return TemplateBundle(
            root, root / bundle.entrypoint.relative_to(bundle.root), tuple(resources)
        )

    def _content(
        self,
        metadata: TemplateMetadata,
        inputs: Mapping[str, ContentInput],
        workspace: Path,
        bundle: TemplateBundle,
    ) -> dict[str, RenderedContent]:
        content = {}
        for name, definition in metadata.inputs.items():
            try:
                value = inputs.get(name)
                if value is None and definition.default is not None:
                    value = TextInput(definition.default)
                fragment = (
                    RenderedContent("")
                    if value is None
                    else self._renderers.get(definition.type).render(
                        value,
                        definition,
                        RenderContext(workspace, name, bundle.entrypoint.parent),
                    )
                )
                content[name] = self._styler.apply(fragment, definition.style)
            except (OSError, ValueError) as exc:
                raise _ContentError(name, exc) from exc
        return content

    def _publish(
        self,
        original: TemplateBundle,
        staged: TemplateBundle,
        content: Mapping[str, RenderedContent],
        compiled: CompileResult,
        output: Path,
    ) -> RenderResult:
        destination = output.parent / f"{output.stem}.artifacts"
        publications = [
            (
                staged.entrypoint,
                destination / staged.entrypoint.relative_to(staged.root),
            )
        ]
        if compiled.log_path is not None and compiled.log_path.is_file():
            publications.append((compiled.log_path, destination / "compile.log"))
        resources = {
            asset for fragment in content.values() for asset in fragment.assets
        }
        resources.update(
            path
            for path in staged.resources
            if path != staged.entrypoint and path.suffix.lower() in _RETAINED_EXTENSIONS
        )
        publications.extend(
            (path, destination / path.relative_to(staged.root))
            for path in sorted(resources)
        )
        # Catch destination aliases before changing any original bundle resources.
        protected = {path.resolve() for path in original.resources}
        if any(target.resolve() in protected for _, target in publications):
            raise ValueError("Artifact destination would overwrite template resources.")
        retained = tuple(
            self._artifacts.publish(source, target) for source, target in publications
        )
        if any(issue.severity == "error" for issue in compiled.diagnostics):
            return RenderResult(None, compiled.diagnostics, retained)
        if compiled.pdf_path is None or not compiled.pdf_path.is_file():
            return RenderResult(
                None,
                (
                    Diagnostic(
                        "compilation", "missing_pdf", "Compiler returned no PDF."
                    ),
                ),
                retained,
            )
        return RenderResult(
            self._artifacts.publish(compiled.pdf_path, output),
            compiled.diagnostics,
            retained,
        )
