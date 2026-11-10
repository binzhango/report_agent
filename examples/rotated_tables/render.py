"""Demonstrate two LaTeX table rotation techniques using the report engine."""

from pathlib import Path

import pandas as pd

from report_agent import RenderRequest, TableInput, create_renderer


def main() -> None:
    bundle = Path(__file__).resolve().parent
    quarters = [
        f"Q{quarter} {year}" for year in (2025, 2026) for quarter in range(1, 5)
    ]
    frame = pd.DataFrame(
        {
            "Region": ["North America", "EMEA", "APAC", "Latin America"],
            **{
                quarter: [
                    1250 + index * 100,
                    800 + index * 70,
                    540 + index * 55,
                    280 + index * 35,
                ]
                for index, quarter in enumerate(quarters)
            },
        }
    )
    result = create_renderer().render(
        RenderRequest(
            template=bundle,
            metadata=bundle / "template.json",
            inputs={"revenue_table": TableInput(frame)},
            output=bundle.parents[1] / "output/pdf/rotated-tables.pdf",
        )
    )
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.severity}: {diagnostic.message}")
    if result.pdf_path is None:
        raise SystemExit(1)
    print(result.pdf_path)


if __name__ == "__main__":
    main()
