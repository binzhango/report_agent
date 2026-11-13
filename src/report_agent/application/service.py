"""Public facade dispatching validated requests to document backends."""

from report_agent.application.backends import DocumentBackend
from report_agent.backends.latex_pdf import LatexPdfBackend
from report_agent.metadata.office import OfficeMetadata
from report_agent.models.results import Diagnostic, RenderResult


class ReportRenderer:
    def __init__(
        self,
        *,
        metadata_loader,
        office_backend: DocumentBackend | None = None,
        **latex_collaborators,
    ):
        self._metadata_loader = metadata_loader
        self._latex = LatexPdfBackend(
            metadata_loader=metadata_loader, **latex_collaborators
        )
        self._office_backend = office_backend
        self._workspaces = latex_collaborators["workspaces"]
        self._artifacts = latex_collaborators["artifacts"]

    def render(self, request):
        try:
            metadata = self._metadata_loader.load(request.metadata)
        except (ValueError, OSError) as exc:
            return RenderResult(
                diagnostics=(Diagnostic("metadata", "invalid_input", str(exc)),)
            )
        if isinstance(metadata, OfficeMetadata):
            from report_agent.backends.libreoffice import LibreOfficeBackend

            backend = self._office_backend or LibreOfficeBackend(
                workspaces=self._workspaces, artifacts=self._artifacts
            )
            return backend.render(request, metadata)
        return self._latex.render(request, metadata)
