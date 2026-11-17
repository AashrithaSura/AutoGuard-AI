from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import cv2
import easyocr
import torch

from src.anpr.pipeline import SelfHealingANPR
from src.anpr.recovery import RESCUE_SCORE_THRESHOLD, build_rescue_pool, read_candidates
from src.anpr.rectify import rectify
from src.anpr.selection import DEFAULT_RETRY_MARGIN, REVIEW_SCORE_THRESHOLD, choose_candidate, is_common_format, review_status

NORMALIZE = lambda value: re.sub(r"[^A-Z0-9]", "", value.upper())

def edit_distance(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (char_left != char_right)))
        row = current
    return row[-1]

def read(reader, image, method, decoder="beamsearch", beam_width=10):
    return read_candidates(reader, image, method, decoder=decoder, beam_width=beam_width)

def metrics(rows, prediction_key):
    exact = sum(row[prediction_key] == row["ground_truth"] for row in rows)
    errors = sum(edit_distance(row[prediction_key], row["ground_truth"]) for row in rows)
    characters = sum(max(1, len(row["ground_truth"])) for row in rows)
    return {"exact_match_accuracy": exact / len(rows), "character_error_rate": errors / characters}

def main():
    parser = argparse.ArgumentParser(description="Evaluate OCR and cautious recovery on labeled plate crops.")
    parser.add_argument("--data-root", default="data/prepared_corrected", help="Prepared dataset directory containing the ocr/ folder.")
    parser.add_argument("--csv", default="data/prepared_corrected/ocr/test.csv")
    parser.add_argument("--output", default="reports/ocr_final_test_v2.csv")
    parser.add_argument("--margins", nargs="+", type=float, default=[0.05, 0.10, 0.15, 0.20, 0.25])
    parser.add_argument("--recognizer-weights", default="models/plate_ocr.pth")
    parser.add_argument("--decoder", choices=["greedy", "beamsearch"], default="beamsearch")
    parser.add_argument("--beam-width", type=int, default=10)
    parser.add_argument("--no-rescue", action="store_true", help="Disable the hybrid direct-CRNN rescue for a baseline comparison.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source, output = root / args.csv, root / args.output
    ocr_weights = root / args.recognizer_weights
    reader = easyocr.Reader(["en"], gpu=False, quantize=not ocr_weights.is_file())
    if ocr_weights.is_file():
        reader.recognizer.load_state_dict(torch.load(ocr_weights, map_location="cpu", weights_only=True))
        reader.recognizer.eval()
    with source.open(newline="", encoding="utf-8-sig") as stream:
        items = list(csv.DictReader(stream))
    rows = []
    for index, item in enumerate(items, 1):
        crop_path = root / args.data_root / item["crop_path"]
        image = cv2.imread(str(crop_path))
        if image is None:
            raise SystemExit(f"Missing or unreadable crop: {crop_path}")
        original_reads = read(reader, image, "upscaled original", args.decoder, args.beam_width)
        original = original_reads[0]
        brightness = float(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean())
        enhanced, thresholded = SelfHealingANPR._enhance(image, brightness)
        raw_candidates = list(original_reads)
        raw_candidates.extend(read(reader, enhanced, "enhanced + upscaled", args.decoder, args.beam_width))
        raw_candidates.extend(read(reader, thresholded, "thresholded + upscaled", args.decoder, args.beam_width))
        warped = rectify(image)
        if warped is not None:
            raw_candidates.extend(read(reader, warped, "rectified perspective", args.decoder, args.beam_width))
        unique = {}
        for candidate in raw_candidates:
            if candidate.text and (candidate.text not in unique or candidate.score > unique[candidate.text].score):
                unique[candidate.text] = candidate
        candidates = list(unique.values())
        rescue_trusted = True
        if not args.no_rescue:
            candidates, rescue_trusted = build_rescue_pool(
                reader, image, original, candidates, enhanced, thresholded
            )
        best = max(candidates, key=lambda candidate: candidate.score) if candidates else original
        truth = NORMALIZE(item["plate_text"])
        row = {
            "source_image": item["source_image"], "ground_truth": truth,
            "original_prediction": original.text, "original_score": round(original.score, 4),
            "confidence_best_prediction": best.text, "confidence_best_score": round(best.score, 4),
            "rescue_trusted": rescue_trusted,
            "original_exact_match": original.text == truth,
            "original_edit_distance": edit_distance(original.text, truth),
            "candidate_details": json.dumps([
                {"text": c.text, "score": round(c.score, 4), "method": c.method}
                for c in sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
            ]),
        }
        for margin in args.margins:
            selected, reason = choose_candidate(original, candidates, margin)
            key = f"margin_{margin:.2f}"
            row[f"{key}_prediction"] = selected.text
            row[f"{key}_score"] = round(selected.score, 4)
            row[f"{key}_variant"] = selected.method
            row[f"{key}_reason"] = (
                ("hybrid rescue: " + reason) if not rescue_trusted and not args.no_rescue else reason
            )
            row[f"{key}_review_status"] = review_status(selected.text, selected.score)
            row[f"{key}_exact_match"] = selected.text == truth
            row[f"{key}_edit_distance"] = edit_distance(selected.text, truth)
        rows.append(row)
        if index % 10 == 0 or index == len(items):
            print(f"Processed {index}/{len(items)} OCR crops", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    review_gate = {}
    for margin in args.margins:
        key = f"{margin:.2f}"
        prediction_key = f"margin_{key}_prediction"
        score_key = f"margin_{key}_score"
        exact_key = f"margin_{key}_exact_match"
        eligible = [
            row for row in rows
            if float(row[score_key]) >= REVIEW_SCORE_THRESHOLD
            and is_common_format(row[prediction_key])
        ]
        review_gate[key] = {
            "score_threshold": REVIEW_SCORE_THRESHOLD,
            "eligible_samples": len(eligible),
            "coverage": len(eligible) / len(rows),
            "exact_match_accuracy_when_eligible": (
                sum(row[exact_key] for row in eligible) / len(eligible) if eligible else 0.0
            ),
        }
    summary = {
        "samples": len(rows), "decoder": args.decoder, "beam_width": args.beam_width,
        "rescue": {
            "enabled": not args.no_rescue,
            "rule": (
                "Keep a common-format base reading with engine score >= "
                f"{RESCUE_SCORE_THRESHOLD}; otherwise add direct-CRNN, rotated and per-row candidates."
            ),
            "trusted_samples": sum(1 for row in rows if row["rescue_trusted"]),
        },
        "original": metrics(rows, "original_prediction"),
        "confidence_best": metrics(rows, "confidence_best_prediction"),
        "format_aware_by_margin": {
            f"{margin:.2f}": metrics(rows, f"margin_{margin:.2f}_prediction") for margin in args.margins
        },
        "review_gate_by_margin": review_gate,
        "note": "Uses the same enhancement code as the app. Choose thresholds on validation data and freeze them before final test evaluation. OCR engine scores are not probabilities.",
    }
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Detailed predictions: {output}")

if __name__ == "__main__":
    main()







