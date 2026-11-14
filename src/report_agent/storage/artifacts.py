"""Publication boundary for artifacts that outlive a render workspace."""

from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile, TemporaryDirectory
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


def publish_snapshot(
    store: ArtifactStore,
    publications: list[tuple[Path, Path]],
    destination: Path,
    protected: set[Path],
) -> tuple[Path, ...]:
    """Replace a complete artifact set after staging; never merge with an old run.

    Publication targets are relative to destination. A staging failure leaves the
    previous snapshot intact. Callers must serialize builds for one destination.
    """
    destination = destination.expanduser().absolute()
    if destination.is_symlink() or any(
        path.resolve().is_relative_to(destination.resolve()) for path in protected
    ):
        raise ValueError("Artifact destination would overwrite template resources.")
    if destination.exists() and not destination.is_dir():
        raise ValueError("Artifact destination must be a directory.")
    for _, relative in publications:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Artifact paths must stay inside the snapshot.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=".report-artifacts-", dir=destination.parent
    ) as directory:
        workspace = Path(directory)
        staged = workspace / "snapshot"
        staged.mkdir()
        for source, relative in publications:
            store.publish(source, staged / relative)
        previous = workspace / "previous"
        if destination.exists():
            destination.replace(previous)
        try:
            staged.replace(destination)
        except BaseException:
            if previous.exists():
                previous.replace(destination)
            raise
    return tuple(destination / relative for _, relative in publications)
