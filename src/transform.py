"""
transform.py

Early data transformation / standardization for the ML ingestion pipeline.

Takes raw records from any source (Gemini extraction output, CSV exports,
synthetic datasets like Synthea) and normalizes them into the exact shape
RawDoseRecord expects, so they can pass schema validation and move on to
the transformation pipeline (grouping by disease, dose sequencing, etc.).

Usage:
    python3 -m src.transform data/extracted_records.json
    python3 -m src.transform data/raw_samples/synthea_batch_1.json
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REQUIRED_FIELDS = [
    "user_id", "patient_name", "vaccine_name", "dose_date",
    "manufacturer", "lot_number", "provider", "clinic",
]

# Common date formats we might see coming from different raw sources
# (CSV exports, OCR output, different clinic systems, Synthea, etc.)
DATE_FORMATS = [
    "%Y-%m-%d",       # 2018-02-28  (already ISO — most common, check first)
    "%m/%d/%Y",       # 02/28/2018
    "%m/%d/%y",       # 02/28/18
    "%B %d, %Y",      # February 28, 2018
    "%b %d, %Y",      # Feb 28, 2018
    "%d-%m-%Y",       # 28-02-2018
    "%Y/%m/%d",       # 2018/02/28
]


def normalize_date(raw_value) -> Optional[str]:
    """
    Convert a messy raw date value into ISO 8601 (YYYY-MM-DD) string.
    Returns None if it can't be parsed — caller decides how to handle that.
    """
    if raw_value is None:
        return None

    raw_value = str(raw_value).strip()
    if not raw_value or raw_value.lower() in ("nan", "none", "unknown", ""):
        return None

    # Strip any time component some sources include, e.g. "2018-02-28T00:00:00Z"
    raw_value = re.split(r"[T ]", raw_value)[0]

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def strip_dose_suffix(vaccine_name: str) -> str:
    """
    Remove dose-number suffixes like '#1', '#2', '(Dose 1)' from a raw vaccine
    name, e.g. 'Hep A #1' -> 'Hep A'. Dose numbering is computed downstream
    from chronological order, not baked into the source name — and leaving it
    in breaks lookups against vaccine_mapping.json (e.g. 'Hep A #1' has no
    entry, only 'Hep A' does).
    """
    cleaned = re.sub(r"\s*#\d+\s*$", "", vaccine_name)
    cleaned = re.sub(r"\s*\(dose\s*\d+\)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned)  # NEW: strip trailing brand-name parentheticals
    return cleaned.strip()


def normalize_text_field(value) -> str:
    """
    Fill missing/null/NaN text fields with 'Unknown', otherwise strip whitespace.
    Deliberately does NOT change casing — vaccine_name casing (D vs d, P vs p)
    is semantically meaningful (see design doc) and must be preserved exactly.
    """
    if value is None:
        return "Unknown"
    value = str(value).strip()
    if not value or value.lower() in ("nan", "none", ""):
        return "Unknown"
    return value


def transform_record(raw: dict) -> dict:
    """Transform one raw record dict into the exact shape RawDoseRecord expects."""
    cleaned = {}

    for field in REQUIRED_FIELDS:
        if field == "dose_date":
            iso_date = normalize_date(raw.get("dose_date"))
            cleaned["dose_date"] = iso_date  # may be None — flagged as an error downstream
        elif field == "vaccine_name":
            name = normalize_text_field(raw.get("vaccine_name"))
            cleaned["vaccine_name"] = strip_dose_suffix(name)
        else:
            cleaned[field] = normalize_text_field(raw.get(field))

    return cleaned


def dedupe_records(records: list[dict]) -> list[dict]:
    """
    Remove exact-duplicate records (same patient, vaccine, and date).
    Keeps the first occurrence.
    """
    seen = set()
    deduped = []
    for r in records:
        key = (r["user_id"], r["vaccine_name"], r["dose_date"], r["provider"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def transform_file(input_path: str, output_path: Optional[str] = None) -> list[dict]:
    """
    Load raw records from a JSON file, transform + dedupe them,
    and write the cleaned result to output_path (default: same name with
    '_clean' suffix in the same folder).
    """
    input_path = Path(input_path)
    with open(input_path) as f:
        raw_records = json.load(f)

    transformed = [transform_record(r) for r in raw_records]
    deduped = dedupe_records(transformed)

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_clean.json"

    with open(output_path, "w") as f:
        json.dump(deduped, f, indent=2)

    unparseable_dates = sum(1 for r in deduped if r["dose_date"] is None)

    print(f"Transformed {len(raw_records)} raw records")
    print(f"  -> {len(transformed) - len(deduped)} exact duplicates removed")
    print(f"  -> {unparseable_dates} records have an unparseable dose_date (flag these for review)")
    print(f"  -> {len(deduped)} clean records written to {output_path}")

    return deduped


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/extracted_records.json"
    transform_file(path)