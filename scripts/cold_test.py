"""Frozen cold-test protocol.

The project test set has been inspected by the people who trained the model, so
numbers measured on it are not a clean held-out estimate.  This script freezes
a copy of the test labels, records its hash, and only evaluates against that
exact file.  Any edit after locking invalidates the hash and the run stops.

    python scripts/cold_test.py freeze
    # verify / correct labels with scripts/label_tool.html, then:
    python scripts/cold_test.py lock
    python scripts/cold_test.py run --predictions reports/ocr_final_test_v2.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate_final import wilson  # noqa: E402
from src.anpr.selection import REVIEW_SCORE_THRESHOLD, is_common_format  # noqa: E402

MANIFEST = ROOT / "data/prepared_corrected/ocr/test.csv"
LABELS = ROOT / "data/cold_test/labels.csv"
HASH = ROOT / "data/cold_test/labels.sha256"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(force: bool) -> None:
    if LABELS.exists() and not force:
        raise SystemExit(f"{LABELS} already exists; pass --force to overwrite the frozen copy.")
    with MANIFEST.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with LABELS.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_image", "crop_path", "plate_text", "verified"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "source_image": row["source_image"],
                "crop_path": (Path("data/prepared_corrected") / row["crop_path"]).as_posix(),
                "plate_text": row["plate_text"],
                "verified": 0,
            })
    print(f"Froze {len(rows)} rows to {LABELS}. Verify them, then run: python scripts/cold_test.py lock")


def lock() -> None:
    if not LABELS.is_file():
        raise SystemExit(f"Missing {LABELS}; run freeze first.")
    HASH.write_text(sha256(LABELS), encoding="ascii")
    print(f"Locked {LABELS} at sha256 {HASH.read_text(encoding='ascii').strip()}")


def run(predictions: Path, pred_key: str, score_key: str) -> None:
    if not HASH.is_file():
        raise SystemExit("No lock file; run `lock` after verifying labels.")
    if sha256(LABELS) != HASH.read_text(encoding="ascii").strip():
        raise SystemExit("Label file changed after locking; the cold test is no longer frozen.")
    with LABELS.open(newline="", encoding="utf-8-sig") as stream:
        labels = list(csv.DictReader(stream))
    with predictions.open(newline="", encoding="utf-8-sig") as stream:
        predicted = list(csv.DictReader(stream))
    if len(labels) != len(predicted):
        raise SystemExit(f"Row mismatch: {len(labels)} labels vs {len(predicted)} predictions.")
    verified = [row for row, prediction in zip(labels, predicted)
                if row["verified"] == "1" and row["source_image"] == prediction["source_image"]]
    if len(verified) < 30:
        raise SystemExit(f"Only {len(verified)} verified rows; verify at least 30 labels first.")
    rows = []
    for index, row in enumerate(labels):
        if row["verified"] != "1":
            continue
        prediction = predicted[index]
        if row["source_image"] != prediction["source_image"]:
            raise SystemExit(f"Row {index} does not line up with its prediction.")
        rows.append({
            "truth": row["plate_text"],
            "prediction": prediction[pred_key],
            "score": float(prediction[score_key]),
        })
    exact = [row["prediction"] == row["truth"] for row in rows]
    per_plate: dict[str, list[bool]] = defaultdict(list)
    for row, hit in zip(rows, exact):
        per_plate[row["truth"]].append(hit)
    eligible = [hit for row, hit in zip(rows, exact)
                if row["score"] >= REVIEW_SCORE_THRESHOLD and is_common_format(row["prediction"])]
    summary = {
        "verified_samples": len(rows),
        "unique_plates": len(per_plate),
        "exact_match": round(sum(exact) / len(rows), 4),
        "exact_match_wilson_95": wilson(len(rows) - sum(exact), len(rows)),
        "plate_macro_exact_match": round(sum(sum(hits) / len(hits) for hits in per_plate.values()) / len(per_plate), 4),
        "gate_threshold": REVIEW_SCORE_THRESHOLD,
        "gate_coverage": round(len(eligible) / len(rows), 4),
        "gate_selective_accuracy": round(sum(eligible) / len(eligible), 4) if eligible else None,
        "labels_sha256": sha256(LABELS),
        "predictions": str(predictions),
        "prediction_column": pred_key,
        "note": "Only rows marked verified=1 are scored; the label file is hash-locked.",
    }
    output = ROOT / "reports/cold_test.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["freeze", "lock", "run"])
    parser.add_argument("--force", action="store_true", help="freeze: overwrite an existing label file")
    parser.add_argument("--predictions", default="reports/ocr_final_test_v2.csv")
    parser.add_argument("--pred-key", default="margin_0.25_prediction")
    parser.add_argument("--score-key", default="margin_0.25_score")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.force)
    elif args.command == "lock":
        lock()
    else:
        run(ROOT / args.predictions, args.pred_key, args.score_key)


if __name__ == "__main__":
    main()
