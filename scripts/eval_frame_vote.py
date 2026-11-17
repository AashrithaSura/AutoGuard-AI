"""Multi-frame majority-vote experiment over saved OCR predictions.

The scan desk accepts up to eight frames per vehicle. This script estimates
what temporal voting would buy by grouping the evaluation crops that share a
ground-truth plate (i.e. multiple views of the same vehicle) and voting per
character position, the same way Laroca et al. combine video frames.

Nothing here is used by the API at inference time; it is an offline check.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

NORMALIZE = lambda value: re.sub(r"[^A-Z0-9]", "", str(value).upper())
APP_NAME = "AutoGuard AI"


def wilson(successes: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    import math
    z = 1.96
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def majority_vote(predictions: list[str], scores: list[float]) -> str:
    """Character-wise majority vote; ties go to the highest-scoring frame."""
    order = sorted(range(len(predictions)), key=lambda index: -scores[index])
    length = max((len(prediction) for prediction in predictions), default=0)
    result = []
    for position in range(length):
        counts = Counter(
            prediction[position]
            for prediction in predictions
            if position < len(prediction) and prediction[position]
        )
        if not counts:
            break
        best = max(counts.values())
        tied = {char for char, count in counts.items() if count == best}
        if len(tied) == 1:
            result.append(tied.pop())
            continue
        result.append(next(
            predictions[index][position]
            for index in order
            if position < len(predictions[index]) and predictions[index][position] in tied
        ))
    return "".join(result)


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


def rate_block(correct: int, total: int) -> dict:
    return {
        "correct": correct,
        "samples": total,
        "rate": round(correct / total, 4) if total else 0.0,
        "ci95": wilson(correct, total),
    }


def evaluate(groups: dict[str, list[dict]], gate: float) -> dict:
    first_correct = vote_correct = any_correct = gated_correct = 0
    first_correct_multi = vote_correct_multi = any_correct_multi = 0
    multi_plates = 0
    multi_frames = 0
    for truth, rows in groups.items():
        predictions = [row["prediction"] for row in rows]
        scores = [row["score"] for row in rows]
        vote = majority_vote(predictions, scores)
        eligible = [row for row in rows if row["score"] >= gate] or rows
        gated = majority_vote([row["prediction"] for row in eligible], [row["score"] for row in eligible])

        first_correct += predictions[0] == truth
        vote_correct += vote == truth
        any_correct += any(prediction == truth for prediction in predictions)
        gated_correct += gated == truth
        if len(rows) > 1:
            multi_plates += 1
            multi_frames += len(rows)
            first_correct_multi += predictions[0] == truth
            vote_correct_multi += vote == truth
            any_correct_multi += any(prediction == truth for prediction in predictions)

    plates = len(groups)
    singletons = plates - multi_plates
    singleton_correct = (first_correct - first_correct_multi)
    return {
        "plates": plates,
        "frames": sum(len(rows) for rows in groups.values()),
        "all_plates": {
            "first_frame": rate_block(first_correct, plates),
            "majority_vote": rate_block(vote_correct, plates),
            "any_crop": rate_block(any_correct, plates),
            "gated_vote": rate_block(gated_correct, plates),
        },
        "multi_frame_plates": {
            "plates": multi_plates,
            "frames": multi_frames,
            "first_frame": rate_block(first_correct_multi, multi_plates),
            "majority_vote": rate_block(vote_correct_multi, multi_plates),
            "any_crop": rate_block(any_correct_multi, multi_plates),
        },
        "singleton_plates": {
            "plates": singletons,
            "first_frame": rate_block(singleton_correct, singletons),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Frame-level majority vote over saved predictions.")
    parser.add_argument("--predictions", default="reports/ocr_final_test_v2.csv")
    parser.add_argument("--pred-key", default=None)
    parser.add_argument("--score-key", default=None)
    parser.add_argument("--gate", type=float, default=0.81)
    parser.add_argument("--min-length", type=int, default=6, help="Skip rows with shorter ground truth (partial labels).")
    parser.add_argument("--output", default="reports/frame_vote_v2.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    with (root / args.predictions).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit("Predictions CSV is empty")
    pred_key = pick_column(rows, args.pred_key, "prediction")
    score_key = pick_column(rows, args.score_key, "score")

    groups: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for row in rows:
        truth = NORMALIZE(row.get("ground_truth", ""))
        if len(truth) < args.min_length:
            skipped += 1
            continue
        groups[truth].append({
            "prediction": NORMALIZE(row.get(pred_key, "")),
            "score": float(row.get(score_key) or 0.0),
        })

    result = evaluate(groups, args.gate)
    result.update({
        "app": APP_NAME,
        "source": args.predictions,
        "prediction_column": pred_key,
        "score_column": score_key,
        "gate_threshold": args.gate,
        "skipped_partial_labels": skipped,
        "note": (
            "Groups crops that share a ground-truth plate (multiple views of one vehicle), "
            "votes per character position, and compares against the first frame. "
            "Only plates with full labels are counted."
        ),
    })

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    def line(label: str, block: dict) -> str:
        return f"  {label:<34} {100 * block['rate']:5.1f}%  [{100 * block['ci95'][0]:5.1f}–{100 * block['ci95'][1]:5.1f}]  n={block['samples']}"

    print(f"{APP_NAME} · frame-vote experiment ({args.predictions})")
    print(f"  {result['plates']} plates · {result['frames']} frames · gate {args.gate:.2f} · skipped {skipped} partial labels")
    print(line("All plates · first frame", result["all_plates"]["first_frame"]))
    print(line("All plates · majority vote", result["all_plates"]["majority_vote"]))
    print(line("All plates · any crop", result["all_plates"]["any_crop"]))
    print(line("All plates · gated vote", result["all_plates"]["gated_vote"]))
    print(line("Multi-frame plates · first frame", result["multi_frame_plates"]["first_frame"]))
    print(line("Multi-frame plates · vote", result["multi_frame_plates"]["majority_vote"]))
    print(line("Multi-frame plates · any crop", result["multi_frame_plates"]["any_crop"]))
    print(line("Singleton plates · first frame", result["singleton_plates"]["first_frame"]))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
