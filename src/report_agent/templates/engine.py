"""Whole-document template expansion boundary."""

from collections.abc import Mapping
from typing import Protocol

from jinja2 import FileSystemLoader, StrictUndefined, meta
from jinja2.sandbox import SandboxedEnvironment

from report_agent.models.results import RenderedContent
from report_agent.models.template import TemplateBundle


class TemplateEngine(Protocol):
    def variables(self, bundle: TemplateBundle) -> frozenset[str]: ...

    def render(
        self, bundle: TemplateBundle, content: Mapping[str, RenderedContent]
    ) -> str: ...


class JinjaTemplateEngine:
    @staticmethod
    def _environment(bundle: TemplateBundle) -> SandboxedEnvironment:
        environment = SandboxedEnvironment(
            loader=FileSystemLoader(bundle.root),
            undefined=StrictUndefined,
            autoescape=False,
            variable_start_string="<<",
            variable_end_string=">>",
            block_start_string="<%",
            block_end_string="%>",
            comment_start_string="<#",
            comment_end_string="#>",
            keep_trailing_newline=True,
        )
        environment.globals.clear()
        return environment

    def variables(self, bundle: TemplateBundle) -> frozenset[str]:
        """Inspect the entrypoint and statically named Jinja includes/parents."""
        environment = self._environment(bundle)
        pending = [(bundle.entrypoint.relative_to(bundle.root).as_posix(), False)]
        visited: set[str] = set()
        active: set[str] = set()
        variables: set[str] = set()
        while pending:
            name, exiting = pending.pop()
            if exiting:
                active.remove(name)
                visited.add(name)
                continue
            if name in active:
                raise ValueError(f"Cyclic template dependency: {name}")
            if name in visited:
                continue
            active.add(name)
            pending.append((name, True))
            source, _, _ = environment.loader.get_source(environment, name)
            tree = environment.parse(source)
            variables.update(meta.find_undeclared_variables(tree))
            for reference in meta.find_referenced_templates(tree):
                if reference is None:
                    raise ValueError("Dynamic Jinja includes are not supported.")
                pending.append((reference, False))
        return frozenset(variables)

    def render(
        self, bundle: TemplateBundle, content: Mapping[str, RenderedContent]
    ) -> str:
        """Expand the full template once with custom delimiters and strict inputs."""
        environment = self._environment(bundle)
        template = environment.get_template(
            bundle.entrypoint.relative_to(bundle.root).as_posix()
        )
        return template.render({name: value.latex for name, value in content.items()})
