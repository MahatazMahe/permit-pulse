"""
One-off diagnostic: check whether candidate primary keys are actually
unique across a real pulled dataset, before we commit to a table design
around an assumption.
"""

import json
from collections import Counter
from pathlib import Path

# Point this at whatever your most recent raw file is -- check your
# data/raw/ folder and update the filename below to match.
RAW_FILE = Path("data/raw/permits_2026-08-19T16-41-35.json")

with RAW_FILE.open(encoding="utf-8") as f:
    records = json.load(f)

print(f"Total records: {len(records)}\n")

# Candidate 1: work_permit alone
work_permit_counts = Counter(r.get("work_permit") for r in records)
duplicates_1 = {k: v for k, v in work_permit_counts.items() if v > 1}
print(f"Candidate 1 (work_permit alone):")
print(f"  Unique values: {len(work_permit_counts)}")
print(f"  Duplicated values: {len(duplicates_1)}")
if duplicates_1:
    # Show one example so we can inspect why it duplicated
    example_key = next(iter(duplicates_1))
    print(f"  Example duplicate: {example_key!r} appears {duplicates_1[example_key]} times")

print()

# Candidate 2: composite of job_filing_number + sequence_number + work_type
def composite_key(r):
    return (r.get("job_filing_number"), r.get("sequence_number"), r.get("work_type"))

composite_counts = Counter(composite_key(r) for r in records)
duplicates_2 = {k: v for k, v in composite_counts.items() if v > 1}
print(f"Candidate 2 (job_filing_number + sequence_number + work_type):")
print(f"  Unique values: {len(composite_counts)}")
print(f"  Duplicated values: {len(duplicates_2)}")
if duplicates_2:
    example_key = next(iter(duplicates_2))
    print(f"  Example duplicate: {example_key!r} appears {duplicates_2[example_key]} times")


print("\n--- Field-by-field diff across duplicate copies ---")
matches = [r for r in records if r.get("work_permit") == "M01012273-I1-SH"]

all_keys = matches[0].keys()
for key in all_keys:
    values = [m.get(key) for m in matches]
    if len(set(values)) > 1:  # only show fields that actually differ
        print(f"  {key}:")
        for i, v in enumerate(values, 1):
            print(f"    copy {i}: {v!r}")

print("\n--- Candidate 3: work_permit + work_type ---")
def candidate_3_key(r):
    return (r.get("work_permit"), r.get("work_type"))

c3_counts = Counter(candidate_3_key(r) for r in records)
duplicates_3 = {k: v for k, v in c3_counts.items() if v > 1}
print(f"  Unique values: {len(c3_counts)}")
print(f"  Duplicated values: {len(duplicates_3)}")

if duplicates_3:
    example_key = next(iter(duplicates_3))
    print(f"  Example duplicate: {example_key!r} appears {duplicates_3[example_key]} times")
    example_matches = [r for r in records if candidate_3_key(r) == example_key]
    print("\n  Field-by-field diff for this example:")
    for key in example_matches[0].keys():
        values = [m.get(key) for m in example_matches]
        if len(set(values)) > 1:
            print(f"    {key}:")
            for i, v in enumerate(values, 1):
                print(f"      copy {i}: {v!r}")

print("\n--- Candidate 4: work_permit + work_type + sequence_number ---")
def candidate_4_key(r):
    return (r.get("work_permit"), r.get("work_type"), r.get("sequence_number"))

c4_counts = Counter(candidate_4_key(r) for r in records)
duplicates_4 = {k: v for k, v in c4_counts.items() if v > 1}
print(f"  Unique values: {len(c4_counts)}")
print(f"  Duplicated values: {len(duplicates_4)}")

print("\n--- Inspecting the final remaining duplicate ---")
c4_dupes = {k: v for k, v in c4_counts.items() if v > 1}
last_dupe_key = next(iter(c4_dupes))
print(f"Duplicate key: {last_dupe_key!r}")

final_matches = [r for r in records if candidate_4_key(r) == last_dupe_key]
for key in final_matches[0].keys():
    values = [m.get(key) for m in final_matches]
    if len(set(values)) > 1:
        print(f"  {key}:")
        for i, v in enumerate(values, 1):
            print(f"    copy {i}: {v!r}")

print("\n--- Candidate 5: tracking_number alone ---")
tracking_counts = Counter(r.get("tracking_number") for r in records)
duplicates_5 = {k: v for k, v in tracking_counts.items() if v > 1}
print(f"  Unique values: {len(tracking_counts)}")
print(f"  Duplicated values: {len(duplicates_5)}")