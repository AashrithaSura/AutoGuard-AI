"""Measure whether perspective correction helps the plate recogniser.

For every labeled crop this runs the same reading path as the app, adds the
rectified copy as one extra candidate, and reports gains and losses against the
conservative format-aware selector.  Choose on validation; confirm on test.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import easyocr
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluate_ocr_crops import NORMALIZE, edit_distance, read  # noqa: E402
from src.anpr.pipeline import SelfHealingANPR  # noqa: E402
from src.anpr.rectify import rectify  # noqa: E402
from src.anpr.recovery import build_rescue_pool  # noqa: E402
from src.anpr.selection import DEFAULT_RETRY_MARGIN, choose_candidate  # noqa: E402


def run(rows, reader, margin: float) -> dict:
    stats = {
        "samples": len(rows),
        "quad_found": 0,
        "base_correct": 0,
        "rectified_alone_correct": 0,
        "with_rectified_correct": 0,
        "gained": 0,
        "lost": 0,
        "changed": 0,
    }
    for row in rows:
        image = cv2.imread(str(row["path"]))
        if image is None:
            raise SystemExit(f"Missing crop: {row['path']}")
        truth = NORMALIZE(row["truth"])
        original = read(reader, image, "upscaled original")
        brightness = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean())
        enhanced, thresholded = SelfHealingANPR._enhance(image, brightness)
        candidates = [
            original,
            read(reader, enhanced, "enhanced + upscaled"),
            read(reader, thresholded, "thresholded + upscaled"),
        ]
        base_pool, _ = build_rescue_pool(reader, image, original, candidates, enhanced, thresholded)
        base_selected, _ = choose_candidate(original, base_pool, margin)

        warped = rectify(image)
        rectified = read(reader, warped, "rectified perspective") if warped is not None else None
        if rectified is not None:
            stats["quad_found"] += 1
        treated_pool, _ = build_rescue_pool(
            reader, image, original, candidates + ([rectified] if rectified else []), enhanced, thresholded
        )
        selected, _ = choose_candidate(original, treated_pool, margin)

        base_ok = base_selected.text == truth
        new_ok = selected.text == truth
        stats["base_correct"] += base_ok
        stats["with_rectified_correct"] += new_ok
        stats["rectified_alone_correct"] += bool(rectified and rectified.text == truth)
        stats["changed"] += base_selected.text != selected.text
        stats["gained"] += new_ok and not base_ok
        stats["lost"] += base_ok and not new_ok
    for key in ("base_correct", "with_rectified_correct", "rectified_alone_correct"):
        stats[key + "_rate"] = round(stats[key] / max(stats["samples"], 1), 4)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate rectification as an extra OCR candidate.")
    parser.add_argument("--data-root", default="data/prepared_corrected")
    parser.add_argument("--csv", default="ocr/val.csv")
    parser.add_argument("--recognizer-weights", default="models/plate_ocr.pth")
    parser.add_argument("--margin", type=float, default=DEFAULT_RETRY_MARGIN)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="reports/rectify_val_v2.json")
    args = parser.parse_args()

    weights = ROOT / args.recognizer_weights
    reader = easyocr.Reader(["en"], gpu=False, quantize=not weights.is_file())
    if weights.is_file():
        reader.recognizer.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        reader.recognizer.eval()

    with (ROOT / args.data_root / args.csv).open(newline="", encoding="utf-8-sig") as stream:
        items = list(csv.DictReader(stream))
    if args.limit:
        items = items[: args.limit]
    rows = [
        {"path": ROOT / args.data_root / item["crop_path"], "truth": item["plate_text"]}
        for item in items
    ]
    result = {"csv": args.csv, "margin": args.margin, **run(rows, reader, args.margin)}
    (ROOT / args.output).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    known = ["samples", "quad_found", "base_correct_rate", "rectified_alone_correct_rate",
             "with_rectified_correct_rate", "gained", "lost", "changed"]
    print(json.dumps({key: result[key] for key in known}, indent=2))


if __name__ == "__main__":
    main()
