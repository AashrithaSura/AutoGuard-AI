"""Combine the original prepared crops with IURS-derived crops into one manifest.

Both sources keep their own split, and audit found no plate text shared across
splits or datasets, so the combination adds training material without leaking.
Crop paths are written relative to the project root so a single data root works.

    python scripts/combine_ocr_datasets.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# (dataset directory, whether its manifests store paths relative to that directory)
SOURCES = (
    ("data/prepared_corrected", True),
    ("data/iurs_plates", False),
)
OUTPUT = "data/combined_ocr"


def main() -> None:
    summary = {}
    for split in ("train", "val", "test"):
        rows = []
        for source, relative_to_source in SOURCES:
            manifest = ROOT / source / "ocr" / f"{split}.csv"
            with manifest.open(newline="", encoding="utf-8-sig") as stream:
                for item in csv.DictReader(stream):
                    crop_path = Path(source) / item["crop_path"] if relative_to_source else Path(item["crop_path"])
                    rows.append({
                        "crop_path": crop_path.as_posix(),
                        "plate_text": item["plate_text"],
                        "source_image": item["source_image"],
                        "origin": source,
                    })
        destination = ROOT / OUTPUT / f"{split}.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        summary[split] = {
            "rows": len(rows),
            "origin": {source: sum(1 for row in rows if row["origin"] == source) for source, _ in SOURCES},
        }
    (ROOT / OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
