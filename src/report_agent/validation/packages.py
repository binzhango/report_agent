"""Check literal template package declarations and local TeX dependencies."""

import re
from pathlib import Path

from report_agent.models.template import TemplateBundle

_COMMAND = re.compile(
    r"\\(?:PassOptionsToPackage\s*\{(?P<passed_options>[^{}]+)\}\s*|"
    r"(?P<command>usepackage|RequirePackage|documentclass|LoadClass|input|include)\s*"
    r"(?:\[(?P<options>[^\]]*)\]\s*)?)\{(?P<names>[^{}]+)\}"
)


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
        xcolor_table_option = False
        visited: set[Path] = set()
        root = bundle.root.resolve()

        def scan(current: Path, source: str) -> None:
            nonlocal xcolor_table_option
            visited.add(current)
            for match in _COMMAND.finditer(_source(source)):
                command = match["command"]
                names = [name.strip() for name in match["names"].split(",")]
                options = match["passed_options"] or match["options"] or ""
                has_table_option = "table" in {
                    option.strip() for option in options.split(",")
                }
                if command is None:
                    if "xcolor" in names and has_table_option:
                        xcolor_table_option = True
                    continue
                if command == "documentclass" and has_table_option:
                    xcolor_table_option = True
                suffix = (
                    ".sty"
                    if command in {"usepackage", "RequirePackage"}
                    else ".cls"
                    if command in {"documentclass", "LoadClass"}
                    else ".tex"
                )
                for name in names:
                    if not name or "\\" in name or "#" in name:
                        continue
                    if suffix == ".sty":
                        if (
                            name == "xcolor"
                            and name not in packages
                            and (xcolor_table_option or has_table_option)
                        ):
                            packages.add("colortbl")
                        packages.add(name)
                    relative = Path(name)
                    if not relative.suffix:
                        relative = relative.with_suffix(suffix)
                    for base in (bundle.entrypoint.parent, bundle.root, current.parent):
                        path = (base / relative).resolve()
                        if path.is_relative_to(root) and path.is_file():
                            if path not in visited:
                                # Process the dependency before the next command.
                                scan(path, path.read_text(encoding="utf-8"))
                            break

        scan(bundle.entrypoint.resolve(), expanded_source)
        return frozenset(packages)
