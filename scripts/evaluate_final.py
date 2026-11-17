"""Honest, composition-aware evaluation of saved OCR predictions.

Reads a predictions CSV produced by ``evaluate_ocr_crops.py`` (or
``scripts/replay_ocr_selection.py``) and reports accuracy at three levels:

* **frame**  - every crop counts once (what the old number reported);
* **plate**  - every unique plate text counts once (macro average);
* **plate-any** - a plate counts as read if at least one of its crops is right.

The frame metric is inflated when one vehicle dominates the test set.  A test
set with 165 frames but 97 unique plates is effectively 97 examples, and this
script makes that visible instead of hiding it.

It also sweeps the review-gate score threshold and reports the coverage /
selective-accuracy trade-off, plus bootstrap confidence intervals.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

NORMALIZE = lambda value: re.sub(r"[^A-Z0-9]", "", str(value).upper())
BOOTSTRAP_ROUNDS = 2000
APP_NAME = "AutoGuard AI"


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char_left != char_right)))
        previous = current
    return previous[-1]


def pick_column(rows: list[dict], explicit: str | None, kind: str) -> str:
    if explicit:
        if explicit not in rows[0]:
            raise SystemExit(f"Column not found: {explicit}")
        return explicit
    suffixes = sorted({key for row in rows for key in row if re.fullmatch(r"margin_[\d.]+_" + kind, key)})
    if suffixes:
        return suffixes[-1]
    fallback = "original_prediction" if kind == "prediction" else "original_score"
    if fallback in rows[0]:
        return fallback
    raise SystemExit(f"Cannot find a {kind} column. Use --{kind}-key.")


def wilson(errors: int, total: int) -> list[float]:
    """95% Wilson interval; stable for small or extreme samples."""
    if total == 0:
        return [0.0, 0.0]
    import math
    z = 1.96
    phat = errors / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def bootstrap_plate_mean(per_plate: dict[str, list[bool]], rounds: int = BOOTSTRAP_ROUNDS) -> list[float]:
    """Resample plates, not frames, so a repeated plate cannot dominate the CI."""
    plates = list(per_plate.values())
    if not plates:
        return [0.0, 0.0]
    rng = random.Random(42)
    estimates = []
    for _ in range(rounds):
        sample = [plates[rng.randrange(len(plates))] for _ in plates]
        estimates.append(sum(sum(values) / len(values) for values in sample) / len(sample))
    estimates.sort()
    return [round(estimates[int(0.025 * rounds)], 4), round(estimates[int(0.975 * rounds) - 1], 4)]


def summarize(rows: list[dict], pred_key: str, score_key: str) -> dict:
    gold_key = "ground_truth"
    frame_exact = sum(row[pred_key] == row[gold_key] for row in rows)
    errors = sum(edit_distance(row[pred_key], row[gold_key]) for row in rows)
    characters = sum(max(1, len(row[gold_key])) for row in rows)

    by_plate: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        if row[gold_key]:
            by_plate[row[gold_key]].append(row[pred_key] == row[gold_key])

    per_plate_rates = {plate: sum(values) / len(values) for plate, values in by_plate.items()}
    plate_mean = sum(per_plate_rates.values()) / len(per_plate_rates) if per_plate_rates else 0.0
    plate_any = sum(1 for values in by_plate.values() if any(values)) / len(by_plate) if by_plate else 0.0

    counts = Counter(row[gold_key] for row in rows)
    dominant_plate, dominant_count = counts.most_common(1)[0] if counts else ("", 0)
    without_dominant = [row for row in rows if row[gold_key] != dominant_plate]
    frame_without = sum(row[pred_key] == row[gold_key] for row in without_dominant) / max(len(without_dominant), 1)

    singleton_rows = [row for row in rows if counts[row[gold_key]] == 1]
    frame_singletons = sum(row[pred_key] == row[gold_key] for row in singleton_rows) / max(len(singleton_rows), 1)

    return {
        "samples": len(rows),
        "unique_plates": len(by_plate),
        "frame_exact_match": round(frame_exact / len(rows), 4) if rows else 0.0,
        "frame_exact_match_ci95": wilson(frame_exact, len(rows)),
        "frame_character_error_rate": round(errors / max(characters, 1), 4),
        "plate_macro_exact_match": round(plate_mean, 4),
        "plate_macro_ci95": bootstrap_plate_mean(by_plate),
        "plate_any_crop_exact_match": round(plate_any, 4),
        "singleton_frame_exact_match": round(frame_singletons, 4),
        "singleton_samples": len(singleton_rows),
        "dominant_plate": dominant_plate,
        "dominant_plate_crops": dominant_count,
        "dominant_share_of_test": round(dominant_count / len(rows), 4) if rows else 0.0,
        "dominant_plate_accuracy": round(per_plate_rates.get(dominant_plate, 0.0), 4),
        "frame_exact_match_without_dominant": round(frame_without, 4),
    }


def gate_sweep(rows: list[dict], pred_key: str, score_key: str, is_common) -> list[dict]:
    sweep = []
    for step in range(50, 100):
        threshold = step / 100
        eligible = [row for row in rows if float(row[score_key]) >= threshold and is_common(row[pred_key])]
        if not eligible:
            sweep.append({"threshold": threshold, "coverage": 0.0, "selective_accuracy": None, "eligible": 0})
            continue
        correct = sum(row[pred_key] == row["ground_truth"] for row in eligible)
        sweep.append({
            "threshold": threshold,
            "coverage": round(len(eligible) / len(rows), 4),
            "selective_accuracy": round(correct / len(eligible), 4),
            "eligible": len(eligible),
        })
    return sweep


def choose_operating_point(sweep: list[dict], target: float, min_coverage: float) -> dict | None:
    feasible = [
        point for point in sweep
        if point["selective_accuracy"] is not None
        and point["selective_accuracy"] >= target
        and point["coverage"] >= min_coverage
    ]
    if not feasible:
        return None
    return max(feasible, key=lambda point: point["coverage"])


def to_markdown(summary: dict, baseline: dict | None) -> str:
    def pct(value: float) -> str:
        return f"{100 * value:.2f}%"

    lines = [
        "# Evaluation summary",
        "",
        "Generated by `scripts/evaluate_final.py` from saved predictions.",
        "",
        "| Metric | Value | 95% CI |",
        "|---|---:|---:|",
        f"| Frame-level exact match | {pct(summary['frame_exact_match'])} | {pct(summary['frame_exact_match_ci95'][0])} – {pct(summary['frame_exact_match_ci95'][1])} |",
        f"| Plate-level exact match (macro) | {pct(summary['plate_macro_exact_match'])} | {pct(summary['plate_macro_ci95'][0])} – {pct(summary['plate_macro_ci95'][1])} |",
        f"| Plate read on at least one crop | {pct(summary['plate_any_crop_exact_match'])} | — |",
        f"| Character error rate | {pct(summary['frame_character_error_rate'])} | — |",
        "",
        f"Test set: **{summary['samples']} crops / {summary['unique_plates']} unique plates**. "
        f"The most frequent plate `{summary['dominant_plate']}` supplies "
        f"**{summary['dominant_plate_crops']} crops ({pct(summary['dominant_share_of_test'])})** "
        f"and is read correctly {pct(summary['dominant_plate_accuracy'])} of the time. "
        f"Without it, frame-level exact match is **{pct(summary['frame_exact_match_without_dominant'])}**.",
        "",
        f"Plates that appear exactly once ({summary['singleton_samples']} crops) score "
        f"**{pct(summary['singleton_frame_exact_match'])}**. This is the closest estimate of "
        "performance on an unseen vehicle, because no plate can be counted twice.",
        "",
    ]
    if baseline:
        delta = 100 * (summary["frame_exact_match"] - baseline["frame_exact_match"])
        lines += [
            "## Change vs baseline",
            "",
            f"- Frame-level exact match: {pct(baseline['frame_exact_match'])} → {pct(summary['frame_exact_match'])} ({delta:+.2f} points)",
            f"- Plate macro exact match: {pct(baseline['plate_macro_exact_match'])} → {pct(summary['plate_macro_exact_match'])}",
            "",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Composition-aware OCR evaluation with confidence intervals.")
    parser.add_argument("--predictions", required=True, help="CSV with ground_truth and prediction columns.")
    parser.add_argument("--val-predictions", default=None, help="Validation CSV used to choose the gate threshold.")
    parser.add_argument("--pred-key", default=None)
    parser.add_argument("--score-key", default=None)
    parser.add_argument("--target", type=float, default=0.95, help="Selective-accuracy target for the gate.")
    parser.add_argument("--min-coverage", type=float, default=0.30)
    parser.add_argument("--baseline", default=None, help="Optional JSON with a previous summary to compare against.")
    parser.add_argument("--output", default="reports/final_evaluation.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    import sys
    sys.path.insert(0, str(root))
    from src.anpr.selection import is_common_format

    with (root / args.predictions).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit("Predictions CSV is empty")
    pred_key = pick_column(rows, args.pred_key, "prediction")
    score_key = pick_column(rows, args.score_key, "score")
    summary = summarize(rows, pred_key, score_key)
    summary["prediction_column"] = pred_key
    summary["score_column"] = score_key

    test_sweep = gate_sweep(rows, pred_key, score_key, is_common_format)
    summary["gate_test_sweep"] = [point for point in test_sweep if point["threshold"] in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)]

    if args.val_predictions:
        with (root / args.val_predictions).open(newline="", encoding="utf-8-sig") as stream:
            val_rows = list(csv.DictReader(stream))
        val_pred = pick_column(val_rows, args.pred_key, "prediction")
        val_score = pick_column(val_rows, args.score_key, "score")
        val_sweep = gate_sweep(val_rows, val_pred, val_score, is_common_format)
        summary["gate_validation_sweep"] = val_sweep
        summary["gate_recommended"] = choose_operating_point(val_sweep, args.target, args.min_coverage)

    baseline = None
    if args.baseline and (root / args.baseline).is_file():
        baseline = json.loads((root / args.baseline).read_text(encoding="utf-8"))

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "baseline": baseline}, indent=2), encoding="utf-8")
    markdown_path = output.with_suffix(".md")
    markdown_path.write_text(to_markdown(summary, baseline), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {output} and {markdown_path}")


if __name__ == "__main__":
    main()
