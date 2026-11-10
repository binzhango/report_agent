"""Typed presentation settings shared by every placeholder content type."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from report_agent.metadata.dimensions import validate_dimension


class StyleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TypographyStyle(StyleModel):
    font_size_pt: float | None = Field(default=None, gt=0, le=72)
    line_height_pt: float | None = Field(default=None, gt=0, le=144)
    paragraph_spacing_pt: float | None = Field(default=None, ge=0, le=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    bold: bool | None = None
    italic: bool | None = None

    @model_validator(mode="after")
    def line_height_requires_size(self) -> "TypographyStyle":
        if self.line_height_pt is not None and self.font_size_pt is None:
            raise ValueError("line_height_pt requires font_size_pt.")
        return self


class HeadingStyle(StyleModel):
    text: str
    level: Literal["section", "subsection", "subsubsection"] = "section"
    numbered: bool = False


class PlaceholderLayout(StyleModel):
    display: Literal["inline", "block"] = "inline"
    alignment: Literal["left", "center", "right"] | None = None
    space_before_pt: float = Field(default=0, ge=0, le=720)
    space_after_pt: float = Field(default=0, ge=0, le=720)
    page_break_before: bool = False
    page_break_after: bool = False
    heading: HeadingStyle | None = None


class BoxStyle(StyleModel):
    """A single unbreakable container; do not use for multi-page content."""

    width: str = r"1\linewidth"
    padding_pt: float = Field(default=8, ge=0, le=100)
    background_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    border_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    border_width_pt: float = Field(default=0, ge=0, le=10)

    _valid_width = field_validator("width")(validate_dimension)


class PlaceholderStyle(StyleModel):
    typography: TypographyStyle = Field(default_factory=TypographyStyle)
    layout: PlaceholderLayout = Field(default_factory=PlaceholderLayout)
    container: BoxStyle | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "PlaceholderStyle":
        if self.layout.display == "inline":
            block_options = (
                self.layout.alignment is not None,
                self.layout.space_before_pt != 0,
                self.layout.space_after_pt != 0,
                self.layout.page_break_before,
                self.layout.page_break_after,
                self.layout.heading is not None,
                self.container is not None,
                self.typography.line_height_pt is not None,
                self.typography.paragraph_spacing_pt is not None,
            )
            if any(block_options):
                raise ValueError("Paragraph/container layout requires display: block.")
        return self
