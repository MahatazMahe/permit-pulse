"""
Ingestion module for Permit Pulse.

Pulls NYC DOB Permit Issuance records from the Socrata Open Data API
(dataset id: ipu4-2q9a) for a recent date window, handling pagination,
and writes the raw response to a dated JSON file on disk.

We deliberately save the RAW, unmodified API response first (the "raw
landing zone" in our architecture) before any cleaning or validation
happens. This means if our validation/transformation code has a bug
later, we can always re-run against the raw file instead of re-hitting
the API -- and we have an audit trail of exactly what the source gave us.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# --- Configuration -----------------------------------------------------

DATASET_ID = "rbx6-tga4"
BASE_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"

# Socrata's default page size is 1,000 rows. We ask for the max
# comfortable batch size explicitly rather than relying on the default,
# so our behavior doesn't silently change if Socrata's default changes.
PAGE_SIZE = 5000

RAW_DATA_DIR = Path("data/raw")


def build_query_params(offset: int, since: date) -> dict:
    since_str = since.strftime("%Y-%m-%dT00:00:00")
    return {
        "$limit": PAGE_SIZE,
        "$offset": offset,
        "$where": f"issued_date >= '{since_str}'",
        "$order": "issued_date DESC",
    }


def fetch_all_recent_permits(days_back: int = 30) -> list[dict]:
    """
    Pull every permit record issued in the last `days_back` days,
    paginating through results until a page comes back empty.

    This is the "bootstrap" style pull -- a bounded, recent slice.
    Full historical backfill is a separate concern for a later milestone.
    """
    since = date.today() - timedelta(days=days_back)
    all_records: list[dict] = []
    offset = 0

    while True:
        params = build_query_params(offset=offset, since=since)
        print(f"  requesting offset={offset} ...", flush=True)
        response = requests.get(BASE_URL, params=params, timeout=(10, 60))
        print(f"  got response, status={response.status_code}", flush=True)
        response.raise_for_status()  # raises an exception on HTTP errors (4xx/5xx)

        page = response.json()
        if not page:
            # Empty page means we've reached the end of the results.
            break

        all_records.extend(page)
        print(f"  fetched {len(page)} rows (offset={offset}), running total={len(all_records)}")

        offset += PAGE_SIZE

    return all_records


def save_raw(records: list[dict]) -> Path:
    """
    Save the raw pulled records to a dated JSON file.

    Using a dated filename (not overwriting the same file every run)
    is what makes this a proper "raw landing zone" -- every run's
    exact snapshot is preserved, which we need later for change
    detection and auditability.
    """
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out_path = RAW_DATA_DIR / f"permits_{run_timestamp}.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    return out_path


def main() -> None:
    print("Fetching DOB Permit Issuance records from the last 30 days...")
    records = fetch_all_recent_permits(days_back=30)
    print(f"Total records fetched: {len(records)}")

    out_path = save_raw(records)
    print(f"Saved raw data to: {out_path}")


if __name__ == "__main__":
    main()