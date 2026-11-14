"""Bounded file-backed data with explicit parameter-to-column filters."""

from pathlib import Path

import pandas as pd

from report_agent.errors import ReportError
from report_agent.ingestion.archives import validate_archive


class FileSource:
    def __init__(self, path: Path, *, filters=None):
        self.path = path.resolve()
        self.filters = filters or {}

    def fetch(self, source):
        if source.params.keys() - self.filters.keys():
            raise ReportError("File parameters require configured column filters.")
        if self.path.stat().st_size > 20 * 1024 * 1024:
            raise ReportError("Data files must be no larger than 20 MiB.")
        if self.path.suffix.lower() == ".csv":
            frame = pd.read_csv(self.path, nrows=100001)
        elif self.path.suffix.lower() == ".xlsx":
            validate_archive(self.path)
            frame = pd.read_excel(
                self.path,
                sheet_name=0 if source.query == "data" else source.query,
                nrows=100001,
                engine="openpyxl",
            )
        else:
            raise ReportError("File sources support CSV and XLSX.")
        if len(frame) > 100000:
            raise ReportError("Data file exceeds 100,000 rows; use a database source.")
        for name, value in source.params.items():
            rule = self.filters[name]
            series = frame[rule["column"]]
            if rule.get("type") == "date":
                series, value = pd.to_datetime(series), pd.Timestamp(value)
            op = rule.get("op", "eq")
            if op not in {"eq", "ge", "gt", "le", "lt"}:
                raise ReportError(
                    "Use a configured filter operator: eq, ge, gt, le, or lt."
                )
            frame = frame[getattr(series, op)(value)]
        if len(frame) > source.row_limit:
            raise ReportError(f"Data exceeds row limit {source.row_limit}.")
        return frame.reset_index(drop=True)
