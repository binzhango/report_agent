"""Template and text contracts independent of the compiler executable."""

from pathlib import Path

import pytest
from jinja2 import UndefinedError

from report_agent.metadata.models import InputDefinition, TemplateMetadata
from report_agent.models.inputs import TextInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext, TemplateBundle
from report_agent.rendering.text import TextRenderer
from report_agent.templates.engine import JinjaTemplateEngine
from report_agent.templates.repository import LocalTemplateRepository


def test_text_is_escaped_once_without_interpreting_markdown(tmp_path: Path) -> None:
    result = TextRenderer().render(
        TextInput(r"**bold** 12% $5 & x_y #1 {draft} ~ ^ \input{secret}"),
        InputDefinition(type="text"),
        RenderContext(tmp_path, "summary"),
    )
    assert result.latex == (
        r"**bold** 12\% \$5 \& x\_y \#1 \{draft\} "
        r"\textasciitilde{} \textasciicircum{} \textbackslash{}input\{secret\}"
    )


def test_text_preserves_paragraphs_and_rejects_control_characters(
    tmp_path: Path,
) -> None:
    renderer = TextRenderer()
    context = RenderContext(tmp_path, "summary")
    definition = InputDefinition(type="text")
    assert (
        renderer.render(TextInput("a\r\n\r\nb"), definition, context).latex == "a\n\nb"
    )
    with pytest.raises(ValueError, match="control characters"):
        renderer.render(TextInput("a\x00b"), definition, context)


def test_text_length_is_checked(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="character limit"):
        TextRenderer().render(
            TextInput("long"),
            InputDefinition(type="text", max_chars=3),
            RenderContext(tmp_path, "title"),
        )


def test_engine_inspects_includes_and_does_not_rerender_inserted_text(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    main.write_text('<<title>> <% include "section.tex" %>')
    (tmp_path / "section.tex").write_text("<<summary>>")
    bundle = TemplateBundle(tmp_path, main)
    engine = JinjaTemplateEngine()
    assert engine.variables(bundle) == {"title", "summary"}
    assert (
        engine.render(
            bundle,
            {
                "title": RenderedContent("<<not_a_variable>>"),
                "summary": RenderedContent("Body"),
            },
        )
        == "<<not_a_variable>> Body"
    )
    with pytest.raises(UndefinedError):
        engine.render(bundle, {"title": RenderedContent("Title")})


def test_dynamic_includes_are_rejected(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("<% include filename %>")
    with pytest.raises(ValueError, match="Dynamic"):
        JinjaTemplateEngine().variables(TemplateBundle(tmp_path, main))


def test_repository_rejects_parent_entrypoint_and_symlink(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("static")
    repository = LocalTemplateRepository()
    with pytest.raises(ValueError, match="relative"):
        repository.load(
            tmp_path, TemplateMetadata(id="t", entrypoint="../main.tex", inputs={})
        )
    (tmp_path / "linked.tex").symlink_to(main)
    with pytest.raises(ValueError, match="symlink"):
        repository.load(tmp_path, TemplateMetadata(id="t", inputs={}))


def test_template_cycles_fail_before_expansion(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text('<% include "section.tex" %>')
    (tmp_path / "section.tex").write_text('<% include "main.tex" %>')
    with pytest.raises(ValueError, match="Cyclic"):
        JinjaTemplateEngine().variables(TemplateBundle(tmp_path, main))
