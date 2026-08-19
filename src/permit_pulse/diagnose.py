"""
One-off diagnostic script -- NOT part of the pipeline.
Just fetch a few raw records with no filtering/ordering assumptions,
so we can see the actual field names in the DOB NOW dataset.
"""

import requests

DATASET_ID = "rbx6-tga4"
BASE_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"

params = {
    "$limit": 3,
}

response = requests.get(BASE_URL, params=params, timeout=30)
response.raise_for_status()
records = response.json()

print(f"Got {len(records)} records\n")
for i, record in enumerate(records, 1):
    print(f"--- Record {i} ---")
    for key, value in record.items():
        print(f"{key}: {value}")
    print()