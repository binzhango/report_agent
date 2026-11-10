"""Explicit strategy selection by the validated metadata input type."""

from collections.abc import Mapping

from report_agent.rendering.base import ContentRenderer

type RendererKey = tuple[str, str | None]


class RendererRegistry:
    def __init__(self, renderers: Mapping[RendererKey, ContentRenderer]) -> None:
        self._renderers = dict(renderers)

    def get(self, input_type: str, backend: str | None = None) -> ContentRenderer:
        key = (input_type, backend or ("styler" if input_type == "table" else None))
        try:
            return self._renderers[key]
        except KeyError as exc:
            raise ValueError(
                f"No renderer registered for {input_type!r}, backend={key[1]!r}."
            ) from exc
