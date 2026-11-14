"""Render model text without HTML execution or automatic image requests."""

from html import escape

from markdown_it import MarkdownIt


def plain_text_html(value):
    return "<p>" + escape(str(value)) + "</p>"


def chat_html(value):
    parser = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(
        ["table", "strikethrough"]
    )
    parser.renderer.rules["image"] = lambda tokens, index, options, env: escape(
        tokens[index].content
    )
    return '<div class="prose chat-prose">' + parser.render(str(value)) + "</div>"
