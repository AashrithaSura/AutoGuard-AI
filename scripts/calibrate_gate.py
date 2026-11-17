"""Risk-controlled gate calibration.

Sweeps the review-gate engine-score threshold on the validation predictions,
finds the widest-coverage threshold whose accepted readings stay at or below a
target error rate, and reports the same threshold on the test split. The output
is a small JSON file the dashboard turns into an interactive risk/coverage lab.

Example:
    python scripts/calibrate_gate.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.anpr.selection import is_common_format


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [row for row in csv.DictReader(stream) if row.get("ground_truth")]


def point(rows: list[dict], pred_key: str, score_key: str, threshold: float) -> dict:
    eligible = [
        row for row in rows
        if float(row[score_key]) >= threshold and is_common_format(row[pred_key])
    ]
    if not eligible:
        return {
            "threshold": round(threshold, 2),
            "coverage": 0.0,
            "selective_accuracy": 0.0,
            "selective_error": 1.0,
            "eligible": 0,
        }
    correct = sum(1 for row in eligible if row[pred_key] == row["ground_truth"])
    accuracy = correct / len(eligible)
    return {
        "threshold": round(threshold, 2),
        "coverage": round(len(eligible) / len(rows), 4),
        "selective_accuracy": round(accuracy, 4),
        "selective_error": round(1.0 - accuracy, 4),
        "eligible": len(eligible),
    }


def curve(rows: list[dict], pred_key: str, score_key: str, step: float = 0.01) -> list[dict]:
    points = []
    value = 0.50
    while value <= 0.951:
        points.append(point(rows, pred_key, score_key, round(value, 2)))
        value += step
    return points


def operating_point(rows: list[dict], pred_key: str, score_key: str, target_error: float, min_eligible: int = 20) -> dict | None:
    best = None
    for item in curve(rows, pred_key, score_key):
        if item["eligible"] < min_eligible:
            continue
        if item["selective_error"] > target_error:
            continue
        if best is None or item["coverage"] > best["coverage"]:
            best = item
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate the review gate for a target selective error.")
    parser.add_argument("--val", default="reports/ocr_rect_val_v2.csv")
    parser.add_argument("--test", default="reports/ocr_rect_test_v2.csv")
    parser.add_argument("--pred-key", default="margin_0.25_prediction")
    parser.add_argument("--score-key", default="margin_0.25_score")
    parser.add_argument("--target-error", type=float, default=0.08,
                        help="Largest accepted-reading error rate allowed on validation.")
    parser.add_argument("--min-eligible", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=None,
                        help="Replay a frozen operating point instead of re-selecting it on validation.")
    parser.add_argument("--output", default="reports/gate_curve.json")
    args = parser.parse_args()

    val_rows = read_rows(ROOT / args.val)
    test_rows = read_rows(ROOT / args.test)
    if not val_rows or not test_rows:
        raise SystemExit("Prediction CSVs are empty; rerun evaluate_ocr_crops.py first.")

    if args.threshold is not None:
        recommended = point(val_rows, args.pred_key, args.score_key, args.threshold)
    else:
        recommended = operating_point(val_rows, args.pred_key, args.score_key, args.target_error, args.min_eligible)
    test_point = None
    if recommended is not None:
        test_point = point(test_rows, args.pred_key, args.score_key, recommended["threshold"])

    payload = {
        "target_error": args.target_error,
        "target_accuracy": round(1.0 - args.target_error, 4),
        "validation_samples": len(val_rows),
        "test_samples": len(test_rows),
        "recommended": recommended,
        "test_at_recommended": test_point,
        "risk_target_met_on_validation": recommended is not None,
        "risk_target_met_on_test": bool(
            test_point and test_point["selective_error"] <= args.target_error
        ),
        "validation_curve": curve(val_rows, args.pred_key, args.score_key),
        "test_curve": curve(test_rows, args.pred_key, args.score_key),
        "prediction_column": args.pred_key,
        "score_column": args.score_key,
        "threshold_pinned": args.threshold is not None,
        "note": (
            "Operating point pinned to the frozen shipped gate and replayed on the current "
            "predictions; it was selected on validation before final test evaluation. Engine "
            "scores are ranking signals, not probabilities of correctness."
            if args.threshold is not None
            else (
                "Threshold selected on validation predictions only. The test curve is shown "
                "for inspection and is not used to choose the operating point. Engine scores "
                "are ranking signals, not probabilities of correctness."
            )
        ),
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("recommended", "test_at_recommended", "risk_target_met_on_test")}, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
