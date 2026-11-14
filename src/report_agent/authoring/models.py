"""Content blocks and presentation settings, never executable model output."""

from typing import Literal

from pydantic import Field, model_validator

from report_agent.definitions.parameters import StrictModel
from report_agent.errors import ReportError


class Block(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,49}$")
    kind: Literal["text", "table", "chart"] = "text"
    heading: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=10000)
    max_chars: int = Field(default=4000, ge=1, le=10000)
    page_break_before: bool = False


class Layout(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    format: Literal["pdf", "docx", "pptx", "xlsx"] = "docx"
    accent: str = Field(default="#16324F", pattern=r"^#[0-9A-Fa-f]{6}$")
    font: Literal["sans", "serif"] = "sans"
    orientation: Literal["portrait", "landscape"] = "portrait"
    blocks: list[Block] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_blocks(self):
        names = [b.name for b in self.blocks]
        if len(set(names)) != len(names):
            raise ReportError("Block names must be unique.", code="duplicate_block")
        if any(n == "title" or n.startswith("heading_") for n in names):
            raise ReportError(
                "title and heading_* are reserved input names.",
                code="reserved_block_name",
            )
        if self.format == "xlsx" and any(b.kind == "chart" for b in self.blocks):
            raise ReportError(
                "The current XLSX backend supports text and table blocks.",
                code="unsupported_layout",
            )
        return self
