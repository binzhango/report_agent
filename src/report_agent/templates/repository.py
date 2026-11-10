"""Template discovery boundary and local-filesystem implementation."""

from pathlib import Path
from typing import Protocol

from report_agent.metadata.models import TemplateMetadata
from report_agent.models.template import TemplateBundle


class TemplateRepository(Protocol):
    def load(self, entrypoint: Path, metadata: TemplateMetadata) -> TemplateBundle: ...


class LocalTemplateRepository:
    def load(self, entrypoint: Path, metadata: TemplateMetadata) -> TemplateBundle:
        """Resolve resources and reject entrypoints outside the selected bundle."""
        selected = entrypoint.expanduser().absolute()
        root = selected if selected.is_dir() else selected.parent
        relative = Path(metadata.entrypoint)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(
                "Metadata entrypoint must be relative to the template root."
            )
        main = root / relative
        if not selected.is_dir() and selected != main:
            raise ValueError("Selected template does not match metadata.entrypoint.")
        if main.suffix.lower() != ".tex" or not main.is_file():
            raise ValueError(f"Template entrypoint is not a .tex file: {main}")
        resources = []
        for path in sorted(root.rglob("*")):
            if any(
                part.startswith(".") or part.endswith(".artifacts")
                for part in path.relative_to(root).parts
            ):
                continue
            if path.is_symlink():
                raise ValueError(f"Template resources cannot be symlinks: {path}")
            if path.is_file():
                resources.append(path)
        if main not in resources or not main.resolve().is_relative_to(root.resolve()):
            raise ValueError("Template entrypoint must be inside the selected bundle.")
        return TemplateBundle(root=root, entrypoint=main, resources=tuple(resources))
