"""
Transformation module for Permit Pulse.

Reads raw pulled records, validates/cleans them, and applies our
change-detection logic against the database:

  - new permit                -> insert into permits_current,
                                  log history row (old_status=NULL)
  - existing, status changed  -> update permits_current,
                                  log history row (old -> new)
  - existing, unchanged       -> touch last_seen_at only, no history row
  - duplicate key within pull -> keep first occurrence, count + skip rest
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator


# --- Validation layer ---------------------------------------------------

class CleanPermit(BaseModel):
    """
    Defines what a valid permit record looks like for OUR purposes.
    Fields we don't care about are simply not listed here -- pydantic
    will ignore extras rather than error on them.

    Using Optional + defaults for most fields because real government
    data is messy: we'd rather store a permit with some missing fields
    than throw the whole record away over one blank column.
    """

    work_permit: str
    work_type: str
    sequence_number: str

    job_filing_number: Optional[str] = None
    borough: Optional[str] = None
    house_no: Optional[str] = None
    street_name: Optional[str] = None
    zip_code: Optional[str] = None

    permit_status: str  # required -- this is the field our whole pipeline hinges on
    filing_reason: Optional[str] = None

    approved_date: Optional[datetime] = None
    issued_date: Optional[datetime] = None
    expired_date: Optional[datetime] = None

    applicant_business_name: Optional[str] = None
    owner_business_name: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @field_validator("work_permit", "work_type", "sequence_number", "permit_status")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v


def validate_records(raw_records: list[dict]) -> tuple[list[CleanPermit], list[dict]]:
    """
    Validates each raw record. Returns (valid_records, rejected_records).
    Rejected records are NOT silently dropped -- we keep them so we can
    report on data quality instead of losing evidence of problems.
    """
    valid: list[CleanPermit] = []
    rejected: list[dict] = []

    for raw in raw_records:
        try:
            valid.append(CleanPermit(**raw))
        except ValidationError as e:
            rejected.append({"record": raw, "errors": str(e)})

    return valid, rejected


def dedupe_records(records: list[CleanPermit]) -> tuple[list[CleanPermit], int]:
    """
    Keeps the first occurrence of each (work_permit, work_type,
    sequence_number) combination. Returns (deduped_records, skip_count).

    We know from check_uniqueness.py that this key is 99.994% reliable
    against real data, with one unexplained collision per ~15,000 rows.
    Rather than crash the pipeline over that one row, we keep the first
    copy seen and count the rest -- a documented, deliberate trade-off.
    """
    seen: dict[tuple[str, str, str], CleanPermit] = {}
    skip_count = 0

    for record in records:
        key = (record.work_permit, record.work_type, record.sequence_number)
        if key in seen:
            skip_count += 1
            continue
        seen[key] = record

    return list(seen.values()), skip_count


# --- Change-detection / upsert layer ------------------------------------

def upsert_permit(cursor, record: CleanPermit) -> str:
    """
    Applies our change-detection logic for a single permit record.
    Returns one of: "inserted", "updated", "unchanged".
    """
    cursor.execute(
        """
        SELECT permit_status FROM permits_current
        WHERE work_permit = %s AND work_type = %s AND sequence_number = %s
        """,
        (record.work_permit, record.work_type, record.sequence_number),
    )
    existing = cursor.fetchone()

    if existing is None:
        cursor.execute(
            """
            INSERT INTO permits_current (
                work_permit, work_type, sequence_number,
                job_filing_number, borough, house_no, street_name, zip_code,
                permit_status, filing_reason,
                approved_date, issued_date, expired_date,
                applicant_business_name, owner_business_name,
                latitude, longitude,
                first_seen_at, last_seen_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                now(), now()
            )
            """,
            (
                record.work_permit, record.work_type, record.sequence_number,
                record.job_filing_number, record.borough, record.house_no,
                record.street_name, record.zip_code,
                record.permit_status, record.filing_reason,
                record.approved_date, record.issued_date, record.expired_date,
                record.applicant_business_name, record.owner_business_name,
                record.latitude, record.longitude,
            ),
        )
        cursor.execute(
            """
            INSERT INTO permit_status_history
                (work_permit, work_type, sequence_number, old_status, new_status)
            VALUES (%s, %s, %s, NULL, %s)
            """,
            (record.work_permit, record.work_type, record.sequence_number,
             record.permit_status),
        )
        return "inserted"

    old_status = existing[0]

    if old_status != record.permit_status:
        cursor.execute(
            """
            UPDATE permits_current SET
                permit_status = %s, filing_reason = %s,
                approved_date = %s, issued_date = %s, expired_date = %s,
                last_seen_at = now()
            WHERE work_permit = %s AND work_type = %s AND sequence_number = %s
            """,
            (
                record.permit_status, record.filing_reason,
                record.approved_date, record.issued_date, record.expired_date,
                record.work_permit, record.work_type, record.sequence_number,
            ),
        )
        cursor.execute(
            """
            INSERT INTO permit_status_history
                (work_permit, work_type, sequence_number, old_status, new_status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (record.work_permit, record.work_type, record.sequence_number,
             old_status, record.permit_status),
        )
        return "updated"

    cursor.execute(
        """
        UPDATE permits_current SET last_seen_at = now()
        WHERE work_permit = %s AND work_type = %s AND sequence_number = %s
        """,
        (record.work_permit, record.work_type, record.sequence_number),
    )
    return "unchanged"


def main(limit: int | None = None) -> None:
    load_dotenv()

    raw_files = sorted(Path("data/raw").glob("permits_*.json"))
    if not raw_files:
        raise SystemExit("No raw data files found in data/raw/. Run ingest.py first.")
    latest_file = raw_files[-1]
    print(f"Processing: {latest_file}")

    with latest_file.open(encoding="utf-8") as f:
        raw_records = json.load(f)
    print(f"Raw records loaded: {len(raw_records)}")

    
    if limit is not None:
        raw_records = raw_records[:limit]
        print(f"TEST MODE: limited to first {limit} records")

    valid_records, rejected = validate_records(raw_records)
    print(f"Valid: {len(valid_records)}, Rejected: {len(rejected)}")

    deduped, skip_count = dedupe_records(valid_records)
    print(f"After dedup: {len(deduped)} (skipped {skip_count} duplicate-key collisions)")

    database_url = os.environ["DATABASE_URL"]
    print("Connecting to database...")
    conn = psycopg2.connect(database_url, connect_timeout=10, options="-c statement_timeout=15000")
    print("Connected. Applying changes...")
    cursor = conn.cursor()

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for i, record in enumerate(deduped, 1):
        print(f"  [{i}/{len(deduped)}] {record.work_permit}...", flush=True)
        result = upsert_permit(cursor, record)
        counts[result] += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\nDone. Inserted: {counts['inserted']}, "
          f"Updated: {counts['updated']}, Unchanged: {counts['unchanged']}")

    if rejected:
        print(f"\n{len(rejected)} records failed validation. First example:")
        print(rejected[0])


if __name__ == "__main__":
    main(limit=50)