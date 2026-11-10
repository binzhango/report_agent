"""Explicit strategy selection by the validated metadata input type."""

from collections.abc import Mapping

from report_agent.rendering.base import ContentRenderer


class RendererRegistry:
    def __init__(self, renderers: Mapping[str, ContentRenderer]) -> None:
        self._renderers = dict(renderers)

    def get(self, input_type: str) -> ContentRenderer:
        try:
            return self._renderers[input_type]
        except KeyError as exc:
            raise ValueError(f"No renderer registered for {input_type!r}.") from exc
