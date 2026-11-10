"""Check literal template package declarations and local TeX dependencies."""

import re
from pathlib import Path

from report_agent.models.template import TemplateBundle

_COMMAND = re.compile(
    r"\\(usepackage|RequirePackage|documentclass|LoadClass|input|include)\s*"
    r"(?:\[([^\]]*)\]\s*)?\{([^{}]+)\}"
)
_PASS_OPTIONS = re.compile(r"\\PassOptionsToPackage\s*\{([^{}]+)\}\s*\{([^{}]+)\}")


def _source(text: str) -> str:
    text = re.sub(
        r"\\begin\{(verbatim\*?|Verbatim|lstlisting|minted)\}.*?\\end\{\1\}",
        "",
        text,
        flags=re.S,
    )
    text = re.sub(r"\\verb\*?([^A-Za-z\s]).*?\1", "", text)
    return "\n".join(
        re.split(r"(?<!\\)(?:\\\\)*%", line, maxsplit=1)[0]
        for line in text.splitlines()
    )


class TemplatePackageScanner:
    def loaded(self, bundle: TemplateBundle, expanded_source: str) -> frozenset[str]:
        packages: set[str] = set()
        xcolor_options: set[str] = set()
        class_options: set[str] = set()
        visited: set[Path] = set()
        pending = [(bundle.entrypoint, expanded_source)]
        while pending:
            current, source = pending.pop()
            if current.resolve() in visited:
                continue
            visited.add(current.resolve())
            source = _source(source)
            for options, names in _PASS_OPTIONS.findall(source):
                if "xcolor" in {name.strip() for name in names.split(",")}:
                    xcolor_options.update(
                        option.strip() for option in options.split(",")
                    )
            for command, options, names in _COMMAND.findall(source):
                if command in {"documentclass", "LoadClass"}:
                    class_options.update(
                        option.strip() for option in options.split(",")
                    )
                suffix = (
                    ".sty"
                    if command in {"usepackage", "RequirePackage"}
                    else ".cls"
                    if command in {"documentclass", "LoadClass"}
                    else ".tex"
                )
                for name in names.split(","):
                    name = name.strip()
                    if not name or "\\" in name or "#" in name:
                        continue
                    if suffix == ".sty":
                        packages.add(name)
                        if name == "xcolor":
                            xcolor_options.update(
                                option.strip() for option in options.split(",")
                            )
                    relative = Path(name)
                    if not relative.suffix:
                        relative = relative.with_suffix(suffix)
                    for base in (bundle.entrypoint.parent, bundle.root, current.parent):
                        path = (base / relative).resolve()
                        if (
                            path.is_relative_to(bundle.root.resolve())
                            and path.is_file()
                        ):
                            pending.append((path, path.read_text(encoding="utf-8")))
                            break
        if "xcolor" in packages and "table" in (xcolor_options | class_options):
            packages.add("colortbl")
        return frozenset(packages)
