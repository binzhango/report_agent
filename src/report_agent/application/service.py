"""Public facade dispatching validated requests to document backends."""

from dataclasses import replace

from report_agent.application.backends import DocumentBackend
from report_agent.backends.latex_pdf import LatexPdfBackend
from report_agent.backends.libreoffice import LibreOfficeBackend
from report_agent.metadata.office import OfficeMetadata
from report_agent.models.results import Diagnostic, RenderResult
from report_agent.resolution.resolver import ContentResolver


class ReportRenderer:
    def __init__(
        self,
        *,
        metadata_loader,
        office_backend: DocumentBackend | None = None,
        resolver: ContentResolver | None = None,
        **latex_collaborators,
    ):
        self._metadata_loader = metadata_loader
        self._latex = LatexPdfBackend(
            metadata_loader=metadata_loader, **latex_collaborators
        )
        self._workspaces = latex_collaborators["workspaces"]
        self._artifacts = latex_collaborators["artifacts"]
        self._office_backend = office_backend or LibreOfficeBackend(
            workspaces=self._workspaces, artifacts=self._artifacts
        )
        self._resolver = resolver or ContentResolver(sources={})

    def render(self, request):
        try:
            metadata = self._metadata_loader.load(request.metadata)
        except (ValueError, OSError) as exc:
            return RenderResult(
                diagnostics=(Diagnostic("metadata", "invalid_input", str(exc)),)
            )
        backend = (
            self._office_backend
            if isinstance(metadata, OfficeMetadata)
            else self._latex
        )
        if request.queries or any(d.source != "user" for d in metadata.inputs.values()):
            # Generated paths remain alive through conversion and artifact publication.
            with self._workspaces.create() as media_workspace:
                resolved = self._resolver.resolve(
                    metadata,
                    inputs=request.inputs,
                    queries=request.queries,
                    media_workspace=media_workspace,
                )
                if any(d.severity == "error" for d in resolved.diagnostics):
                    return RenderResult(diagnostics=resolved.diagnostics)
                result = backend.render(
                    replace(request, inputs=resolved.inputs, queries={}), metadata
                )
                return replace(
                    result, diagnostics=resolved.diagnostics + result.diagnostics
                )
        return backend.render(request, metadata)
