"""Per-render resource ownership boundary."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol


class WorkspaceManager(Protocol):
    def create(self) -> AbstractContextManager[Path]: ...


class TemporaryWorkspaceManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root

    def create(self) -> AbstractContextManager[Path]:
        """Own staging and cleanup for one render, including failed builds."""
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
        return self._workspace()

    @contextmanager
    def _workspace(self) -> Iterator[Path]:
        with TemporaryDirectory(prefix="report-agent-", dir=self.root) as directory:
            yield Path(directory)
