-- Permit Pulse database schema
--
-- Primary key design note: we tested several candidate keys against
-- real pulled data (see check_uniqueness.py) before settling on this
-- composite key. work_permit alone is NOT unique (one filing can cover
-- multiple work types), and adding work_type still leaves collisions
-- from permit re-issuance (sequence_number distinguishes those). One
-- unexplained collision remains out of 15,659 real rows tested; we
-- handle that defensively at insert time rather than assuming it away.

-- "Current state" table: one row per permit, always reflects the
-- latest known values. This gets overwritten (via upsert) every run.
CREATE TABLE IF NOT EXISTS permits_current (
    work_permit         TEXT NOT NULL,
    work_type           TEXT NOT NULL,
    sequence_number     TEXT NOT NULL,

    job_filing_number   TEXT,
    borough             TEXT,
    house_no            TEXT,
    street_name         TEXT,
    zip_code            TEXT,

    permit_status       TEXT,
    filing_reason       TEXT,

    approved_date       TIMESTAMP,
    issued_date         TIMESTAMP,
    expired_date         TIMESTAMP,

    applicant_business_name TEXT,
    owner_business_name     TEXT,

    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,

    -- Bookkeeping columns -- not from the source API, added by us.
    first_seen_at       TIMESTAMP NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMP NOT NULL DEFAULT now(),

    PRIMARY KEY (work_permit, work_type, sequence_number)
);

-- "History log" table: append-only. A new row is added only when
-- permit_status actually changes for a given permit -- never
-- overwritten, never deleted. This is what lets us answer
-- "what changed, and when" -- the entire point of this project.
CREATE TABLE IF NOT EXISTS permit_status_history (
    id                  SERIAL PRIMARY KEY,
    work_permit         TEXT NOT NULL,
    work_type           TEXT NOT NULL,
    sequence_number     TEXT NOT NULL,

    old_status          TEXT,          -- NULL for the very first time we see a permit
    new_status          TEXT NOT NULL,

    detected_at         TIMESTAMP NOT NULL DEFAULT now()
);

-- Speeds up "show me all history for this permit" lookups, which
-- we'll need for the analytics layer later.
CREATE INDEX IF NOT EXISTS idx_history_permit
    ON permit_status_history (work_permit, work_type, sequence_number);