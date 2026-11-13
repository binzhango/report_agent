"""Build the complete Flat XML example with native Office tables."""

from pathlib import Path

import pandas as pd

from report_agent import RenderRequest, TableInput, TextInput, create_renderer

ROOT = Path(__file__).resolve().parent


def main():
    inputs = {
        "sales": TableInput(
            pd.DataFrame({"Region": ["EMEA", "APAC", "AMER"], "Revenue": [12, 25, 31]})
        )
    }
    inputs.update(
        title=TextInput("Quarterly sales review"),
        summary=TextInput(
            "Revenue increased across the period.\n\nPrepared from current data."
        ),
    )
    result = create_renderer().render(
        RenderRequest(
            ROOT, ROOT / "template.yaml", inputs, Path("output/office/docx-review.docx")
        )
    )
    for issue in result.diagnostics:
        print(issue.severity, issue.code, issue.message)
    if result.output_path is None:
        raise SystemExit(1)
    print(result.output_path)


if __name__ == "__main__":
    main()
