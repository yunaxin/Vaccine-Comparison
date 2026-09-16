"""
validate_extraction.py

Checks a JSON file of dose records against the RawDoseRecord schema
(the input format the ledger-building step expects).

Run this after transform.py, on the *_clean.json output.

Usage:
    python3 -m src.validate_extraction data/synthea_extracted_records_clean.json
"""

import json
import sys
from pydantic import ValidationError
from src.schema import RawDoseRecord


def validate_records(path: str):
    with open(path) as f:
        records = json.load(f)

    valid, invalid = [], []
    for i, record in enumerate(records):
        try:
            validated = RawDoseRecord(**record)
            valid.append(validated)
        except ValidationError as e:
            invalid.append({"index": i, "record": record, "errors": e.errors()})

    print(f"Checked {len(records)} records: {len(valid)} valid, {len(invalid)} invalid\n")

    for item in invalid:
        print(f"--- Record {item['index']} failed ---")
        print(f"  data: {item['record']}")
        for err in item["errors"]:
            print(f"  field '{err['loc'][0]}': {err['msg']}")
        print()

    return valid, invalid


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/extracted_records_clean.json"
    validate_records(path)