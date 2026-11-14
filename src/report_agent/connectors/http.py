"""Bounded GET requests to preconfigured named JSON endpoints."""

import json

import pandas as pd


class HttpSource:
    def __init__(self, endpoints, *, headers=None, records_key=None):
        self.endpoints, self.headers, self.records_key = (
            endpoints,
            headers or {},
            records_key,
        )

    def fetch(self, source):
        import httpx

        if source.query not in self.endpoints:
            raise ValueError("Select a configured API endpoint name.")
        chunks, size = [], 0
        with httpx.stream(
            "GET",
            self.endpoints[source.query],
            params=source.params,
            headers=self.headers,
            timeout=30,
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise ValueError("API response exceeds 10 MiB.")
                chunks.append(chunk)
        records = json.loads(b"".join(chunks))
        if self.records_key:
            records = records[self.records_key]
        if not isinstance(records, list) or any(
            not isinstance(r, dict) for r in records
        ):
            raise ValueError("API must return a JSON list of records.")
        if len(records) > source.row_limit:
            raise ValueError(f"API exceeds row limit {source.row_limit}.")
        return pd.DataFrame(records)
