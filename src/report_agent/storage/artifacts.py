"""Publication boundary for artifacts that outlive a render workspace."""

from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile
from typing import Protocol


class ArtifactStore(Protocol):
    def publish(self, source: Path, destination: Path) -> Path: ...


class LocalArtifactStore:
    def publish(self, source: Path, destination: Path) -> Path:
        """Publish completed artifacts before workspace cleanup."""
        destination = destination.expanduser().absolute()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                temporary = Path(handle.name)
            copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return destination
