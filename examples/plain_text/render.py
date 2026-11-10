"""Run with uv run python examples/plain_text/render.py from the repository."""

from pathlib import Path

from report_agent import RenderRequest, TextInput, create_renderer


def main() -> None:
    bundle = Path(__file__).resolve().parent
    result = create_renderer().render(
        RenderRequest(
            template=bundle,
            metadata=bundle / "template.json",
            inputs={
                "title": TextInput("Q3 Sales & Operations"),
                "period": TextInput("July - September 2026"),
                "summary": TextInput(
                    "Revenue increased by 12% to $1,250,000. "
                    "The North & South teams completed the quarterly review.\n\n"
                    "Next quarter, the team will focus on customer retention "
                    "and service quality."
                ),
                "notes": TextInput(
                    "Figures are illustrative and provided for demonstration only. "
                    "Prepared for internal quarterly review."
                ),
            },
            output=bundle.parents[1] / "output/pdf/plain-text.pdf",
        )
    )
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.severity}: {diagnostic.message}")
    if result.pdf_path is None:
        raise SystemExit(1)
    print(result.pdf_path)


if __name__ == "__main__":
    main()
