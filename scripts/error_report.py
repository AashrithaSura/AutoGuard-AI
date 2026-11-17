"""Build a visual failure report from saved OCR predictions.

Classifies every wrong reading into a small taxonomy, flags readings that are
probably annotation errors rather than model errors, and writes a self-contained
HTML page with the crop thumbnails so the cases can be inspected by eye.

The category worth acting on is ``likely_label_error``: a high engine score
disagreeing with the label usually means the annotation is incomplete or wrong,
not that the recogniser failed.  Those caps on accuracy that no amount of
training can fix, so they should be corrected in the dataset first.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import cv2

NORMALIZE = lambda value: re.sub(r"[^A-Z0-9]", "", str(value).upper())


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char_left != char_right)))
        previous = current
    return previous[-1]


def thumbnail(path: Path, width: int = 420) -> str:
    image = cv2.imread(str(path))
    if image is None:
        return ""
    height = max(1, int(image.shape[0] * width / image.shape[1]))
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_CUBIC)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")


def classify(row: dict, distance: int, score: float) -> str:
    if score >= 0.90 and distance >= 3:
        return "likely_label_error"
    if distance == 1:
        return "single_character"
    if distance == 2:
        return "two_characters"
    if score < 0.50:
        return "low_confidence"
    if abs(len(row["prediction"]) - len(row["ground_truth"])) >= 3:
        return "structural"
    return "other"


def load_manifest(root: Path, paths: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                mapping[row["source_image"]] = row["crop_path"]
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual failure and label-quality report.")
    parser.add_argument("--predictions", default="reports/ocr_final_test_v2.csv")
    parser.add_argument("--pred-key", default=None)
    parser.add_argument("--score-key", default=None)
    parser.add_argument("--data-root", default="data/prepared_corrected")
    parser.add_argument("--manifest", nargs="*", default=["data/prepared_corrected/ocr/test.csv"])
    parser.add_argument("--output", default="reports/error_report.html")
    parser.add_argument("--json-output", default="reports/error_report.json")
    parser.add_argument("--show-correct", type=int, default=0, help="Include this many correct examples too.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    with (root / args.predictions).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit("No predictions found")

    if args.pred_key:
        pred_key = args.pred_key
    else:
        keys = sorted({key for row in rows for key in row if re.fullmatch(r"margin_[\d.]+_prediction", key)})
        pred_key = keys[-1] if keys else "original_prediction"
    if args.score_key:
        score_key = args.score_key
    else:
        keys = sorted({key for row in rows for key in row if re.fullmatch(r"margin_[\d.]+_score", key)})
        score_key = keys[-1] if keys else "original_score"

    manifest = load_manifest(root, args.manifest)

    records = []
    for row in rows:
        truth = NORMALIZE(row["ground_truth"])
        prediction = NORMALIZE(row[pred_key])
        score = float(row[score_key])
        distance = edit_distance(prediction, truth)
        crop_relative = row.get("crop_path") or manifest.get(row.get("source_image", ""), "")
        records.append({
            "ground_truth": truth,
            "prediction": prediction,
            "score": round(score, 4),
            "distance": distance,
            "correct": prediction == truth,
            "category": "correct" if prediction == truth else classify({"prediction": prediction, "ground_truth": truth}, distance, score),
            "crop_path": crop_relative,
        })

    failures = [record for record in records if not record["correct"]]
    categories = Counter(record["category"] for record in failures)
    substitutions = Counter()
    for record in failures:
        if len(record["prediction"]) == len(record["ground_truth"]):
            for truth_char, pred_char in zip(record["ground_truth"], record["prediction"]):
                if truth_char != pred_char:
                    substitutions[f"{truth_char}->{pred_char}"] += 1
    per_plate = defaultdict(lambda: [0, 0])
    for record in records:
        per_plate[record["ground_truth"]][0] += int(record["correct"])
        per_plate[record["ground_truth"]][1] += 1

    summary = {
        "samples": len(records),
        "failures": len(failures),
        "failure_rate": round(len(failures) / len(records), 4),
        "categories": dict(categories),
        "top_substitutions": substitutions.most_common(25),
        "worst_plates": sorted(
            ({"plate": plate, "correct": correct, "crops": total, "accuracy": round(correct / total, 3)}
             for plate, (correct, total) in per_plate.items() if total >= 2),
            key=lambda item: item["accuracy"],
        )[:15],
    }

    order = ["likely_label_error", "single_character", "two_characters", "low_confidence", "structural", "other"]
    sections = []
    for category in order:
        items = [record for record in failures if record["category"] == category]
        if not items:
            continue
        items.sort(key=lambda item: -item["score"])
        cards = []
        for record in items:
            crop_path = root / args.data_root / record["crop_path"] if record["crop_path"] else None
            image = thumbnail(crop_path) if crop_path and crop_path.is_file() else ""
            cards.append(f"""
            <article class="card">
              <div class="img">{'<img src="' + image + '" alt="">' if image else '<span class="missing">crop not found</span>'}</div>
              <div class="meta">
                <div class="row"><span class="label">truth</span><code class="truth">{html.escape(record['ground_truth'])}</code></div>
                <div class="row"><span class="label">read</span><code class="pred">{html.escape(record['prediction']) or '&mdash;'}</code></div>
                <div class="row small">score {record['score']:.3f} &middot; edit distance {record['distance']}</div>
                <div class="row small path">{html.escape(record['crop_path'] or '')}</div>
              </div>
            </article>""")
        sections.append(f"""
        <section>
          <h2>{html.escape(category.replace('_', ' '))} <span class="count">{len(items)}</span></h2>
          <div class="grid">{''.join(cards)}</div>
        </section>""")

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Failure report</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; padding:32px; background:#0f1115; color:#e6e8ee;
         font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
  h1 {{ font-size:26px; margin:0 0 6px; }}
  h2 {{ font-size:18px; margin:34px 0 12px; text-transform:capitalize; }}
  .count {{ font-size:12px; background:#242838; color:#9aa4bf; padding:2px 8px; border-radius:999px; vertical-align:2px; }}
  .lead {{ color:#9aa4bf; margin:0 0 8px; }}
  .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:18px 0 8px; }}
  .stat {{ background:#161a23; border:1px solid #242a37; border-radius:10px; padding:12px 14px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:#8c96ad; font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(360px,1fr)); gap:14px; }}
  .card {{ background:#161a23; border:1px solid #242a37; border-radius:12px; overflow:hidden; }}
  .img {{ background:#0a0c10; display:flex; align-items:center; justify-content:center; min-height:96px; }}
  .img img {{ width:100%; display:block; }}
  .missing {{ color:#5b6478; font-size:12px; padding:30px; }}
  .meta {{ padding:10px 12px; display:grid; gap:4px; }}
  .row {{ display:flex; align-items:center; gap:8px; }}
  .label {{ color:#7f8aa3; font-size:11px; text-transform:uppercase; letter-spacing:.06em; width:38px; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:15px; letter-spacing:.04em; }}
  .truth {{ color:#7ee2a8; }}
  .pred {{ color:#ffb454; }}
  .small {{ color:#8c96ad; font-size:12px; }}
  .path {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
</style></head><body>
<h1>OCR failure report</h1>
<p class="lead">{html.escape(args.predictions)} &middot; {len(records)} crops &middot; {len(failures)} wrong
({100 * len(failures) / len(records):.1f}%)</p>
<div class="summary">
  <div class="stat"><b>{len(failures)}</b><span>wrong readings</span></div>
  <div class="stat"><b>{categories.get('likely_label_error', 0)}</b><span>likely label errors</span></div>
  <div class="stat"><b>{categories.get('single_character', 0)}</b><span>one character off</span></div>
  <div class="stat"><b>{len({r['ground_truth'] for r in records})}</b><span>unique plates</span></div>
</div>
{''.join(sections)}
</body></html>"""

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    (root / args.json_output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2)[:2500])
    print(f"\nWrote {output} and {root / args.json_output}")


if __name__ == "__main__":
    main()
