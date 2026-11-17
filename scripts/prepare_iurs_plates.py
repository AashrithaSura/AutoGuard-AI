"""Turn the IURS/ANPRIND character-detection set into plate-level OCR crops.

The public dataset (``IURS Character Detection Dataset``) labels *characters*,
not plates: 8,168 images with 79,792 character boxes over 36 classes.  The
8,168 files are only 1,385 unique source images; Roboflow added flipped /
rotated copies and repeated sources across its own splits.

This script rebuilds plate-level examples from those character boxes:

1. cluster character boxes into plate groups;
2. read each group as lines of left-to-right characters (handles two-line plates);
3. keep only strings that satisfy an Indian plate grammar;
4. pick the crop orientation whose CRNN reading best matches the annotated
   text (Roboflow shipped flipped copies), and drop groups where no
   orientation reads close enough;
5. keep one crop per source image and cap repeats per plate text;
6. split by plate text, not by the source archive's split, so no plate leaks
   between train / validation / test;
7. split two-line plates into one row per line, matching how the pipeline's
   text detector hands each line to the recogniser.

Output is a normal OCR dataset that ``train_ocr.py`` can read.

    python scripts/prepare_iurs_plates.py
    python scripts/prepare_iurs_plates.py --no-orientation-check   # faster
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

STATES = "AN AP AR AS BR CG CH DD DL DN GA GJ HR HP JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK TG TN TR TS UA UK UP WB".split()
STATE_FORMAT = re.compile(r"^(?:" + "|".join(STATES) + r")\d{1,2}[A-Z]{0,3}\d{1,4}$")
BH_FORMAT = re.compile(r"^\d{2}BH\d{4}[A-Z]{0,2}$")
ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent / "IURS Character Detection Dataset"

import sys  # noqa: E402

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Group:
    source: str
    image_path: Path
    text: str
    box: tuple[int, int, int, int]
    lines: int
    char_height: int
    char_count: int
    roboflow_split: str
    segments: list[tuple[str, tuple[int, int, int, int]]]


def is_valid(text: str) -> bool:
    return bool(STATE_FORMAT.fullmatch(text) or BH_FORMAT.fullmatch(text))


def load_coco(split: str) -> tuple[dict, dict, dict[str, list[tuple[str, float, float, float, float]]]]:
    payload = json.loads((ARCHIVE / split / "_annotations.coco.json").read_text(encoding="utf-8"))
    names = {category["id"]: category["name"] for category in payload["categories"]}
    images = {image["id"]: image for image in payload["images"]}
    by_image: dict[int, list[tuple[str, float, float, float, float]]] = defaultdict(list)
    for annotation in payload["annotations"]:
        if annotation["category_id"] == 0:
            continue
        char = names.get(annotation["category_id"], "")
        if len(char) != 1 or not char.isalnum():
            continue
        x, y, w, h = annotation["bbox"]
        by_image[annotation["image_id"]].append((char.upper(), float(x), float(y), float(w), float(h)))
    return payload, images, by_image


def cluster_boxes(boxes: list[tuple], eps: float) -> list[list[tuple]]:
    count = len(boxes)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(count):
        for j in range(i + 1, count):
            ax, ay = boxes[i][1] + boxes[i][3] / 2, boxes[i][2] + boxes[i][4] / 2
            bx, by = boxes[j][1] + boxes[j][3] / 2, boxes[j][2] + boxes[j][4] / 2
            if abs(ax - bx) <= eps and abs(ay - by) <= eps:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    groups: dict[int, list[tuple]] = defaultdict(list)
    for index, box in enumerate(boxes):
        groups[find(index)].append(box)
    return list(groups.values())


def read_group(boxes: list[tuple]) -> tuple[str, int, tuple[int, int, int, int], int, list[tuple[str, tuple[int, int, int, int]]]]:
    boxes = sorted(boxes, key=lambda item: item[2] + item[4] / 2)
    heights = sorted(item[4] for item in boxes)
    median_height = heights[len(heights) // 2] or 1.0
    lines: list[list[tuple]] = [[boxes[0]]]
    for box in boxes[1:]:
        if (box[2] + box[4] / 2) - (lines[-1][-1][2] + lines[-1][-1][4] / 2) > 0.6 * median_height:
            lines.append([box])
        else:
            lines[-1].append(box)
    segments = []
    for line in lines:
        ordered = sorted(line, key=lambda item: item[1])
        text = "".join(item[0] for item in ordered)
        segments.append((text, (
            int(min(item[1] for item in ordered)),
            int(min(item[2] for item in ordered)),
            int(max(item[1] + item[3] for item in ordered)),
            int(max(item[2] + item[4] for item in ordered)),
        )))
    text = "".join(segment[0] for segment in segments)
    xs = [item[1] for item in boxes]
    ys = [item[2] for item in boxes]
    x2 = [item[1] + item[3] for item in boxes]
    y2 = [item[2] + item[4] for item in boxes]
    return text, len(lines), (int(min(xs)), int(min(ys)), int(max(x2)), int(max(y2))), int(median_height), segments


def collect(split: str) -> list[Group]:
    _, images, by_image = load_coco(split)
    groups: list[Group] = []
    for image_id, boxes in by_image.items():
        if len(boxes) < 6:
            continue
        image = images[image_id]
        source = (image.get("extra") or {}).get("name") or image["file_name"].split("_jpg.rf.")[0]
        median_height = float(np.median([box[4] for box in boxes]))
        for cluster in cluster_boxes(boxes, eps=max(24.0, 3.2 * median_height)):
            if len(cluster) < 6:
                continue
            text, line_count, box, char_height, segments = read_group(cluster)
            if not is_valid(text):
                continue
            if line_count > 2:
                continue
            x1, y1, x2, y2 = box
            width, height = x2 - x1, y2 - y1
            if width < 60 or height < 16:
                continue
            aspect = width / max(height, 1)
            if aspect < 1.2 or aspect > 8.0:
                continue
            groups.append(Group(source, ARCHIVE / split / image["file_name"], text, box, line_count, char_height, len(cluster), split, segments))
    return groups


def edit_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, outer in enumerate(left, 1):
        current = [i]
        for j, inner in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (outer != inner)))
        previous = current
    return previous[-1]


ORIENTATIONS = {
    "normal": lambda crop: crop,
    "flip-vertical": lambda crop: cv2.flip(crop, 0),
    "rotate-180": lambda crop: cv2.rotate(crop, cv2.ROTATE_180),
    "flip-horizontal": lambda crop: cv2.flip(crop, 1),
}


def orient(reader, crop: np.ndarray, expected: str) -> np.ndarray | None:
    """Return the upright copy whose CRNN reading matches the text rebuilt from
    character boxes, or None when no orientation reads close enough.

    Roboflow's archive includes flipped and rotated copies of the same source,
    and a 180-degree copy still passes grammar because character order stays
    left-to-right. Comparing all four orientations against the annotated text
    both repairs the flips and rejects crops the recogniser cannot read."""
    from src.anpr.recovery import read_direct

    tolerance = max(1, round(0.2 * len(expected)))
    best_crop, best_distance, best_score = None, len(expected) + 1, 0.0
    for name, transform in ORIENTATIONS.items():
        candidate = transform(crop)
        reading = read_direct(reader, candidate, "orientation check")
        distance = edit_distance(reading.text, expected)
        if distance < best_distance or (distance == best_distance and reading.score > best_score):
            best_crop, best_distance, best_score = candidate, distance, reading.score
        if distance == 0 and name == "normal":
            break
    return best_crop if best_distance <= tolerance else None


def split_bucket(text: str) -> int:
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def load_crop(image_path: Path, box: tuple[int, int, int, int]) -> np.ndarray | None:
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    x1, y1, x2, y2 = box
    pad_x, pad_y = int(0.06 * (x2 - x1)), int(0.10 * (y2 - y1))
    height, width = image.shape[:2]
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(width, x2 + pad_x), min(height, y2 + pad_y)
    crop = image[y1:y2, x1:x2]
    return crop if crop.size else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build plate-level OCR crops from the IURS character dataset.")
    parser.add_argument("--archive", default=str(ARCHIVE))
    parser.add_argument("--out", default="data/iurs_plates")
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--test-frac", type=float, default=0.15)
    parser.add_argument("--max-per-text", type=int, default=2)
    parser.add_argument("--no-orientation-check", action="store_true")
    parser.add_argument("--qa-sheet", default="reports/iurs_qa_sheet.png")
    args = parser.parse_args()

    archive = Path(args.archive)
    if not archive.is_dir():
        raise SystemExit(f"IURS archive not found: {archive}")

    groups: list[Group] = []
    for split in ("train", "valid", "test"):
        groups.extend(collect(split))
    print(f"candidate plate groups: {len(groups)} from {len({g.source for g in groups})} unique sources")

    by_source: dict[tuple[str, str], list[Group]] = defaultdict(list)
    for group in groups:
        by_source[(group.source, group.text)].append(group)

    reader = None
    if not args.no_orientation_check:
        import easyocr
        weights = ROOT / "models" / "plate_ocr.pth"
        reader = easyocr.Reader(["en"], gpu=False, quantize=not weights.is_file())
        if weights.is_file():
            import torch
            reader.recognizer.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
            reader.recognizer.eval()

    chosen: list[tuple[Group, list[tuple[str, tuple[int, int, int, int], np.ndarray]]]] = []
    for _, candidates in by_source.items():
        scores = []
        for group in candidates:
            pieces = []
            for text, box in group.segments:
                crop = load_crop(group.image_path, box)
                if crop is None:
                    break
                if reader is not None:
                    crop = orient(reader, crop, text)
                    if crop is None:
                        break
                pieces.append((text, box, crop))
            if len(pieces) != len(group.segments):
                continue
            x1, y1, x2, y2 = group.box
            aspect = (x2 - x1) / max(y2 - y1, 1)
            shape = 1.0 - abs(aspect - 3.6) / 4.0
            scores.append((group.char_height + 6.0 * shape, group, pieces))
        if not scores:
            continue
        scores.sort(key=lambda item: -item[0])
        chosen.append((scores[0][1], scores[0][2]))

    per_text: Counter = Counter()
    kept = []
    for group, pieces in sorted(chosen, key=lambda item: (-item[0].char_height, item[0].text)):
        if per_text[group.text] >= args.max_per_text:
            continue
        per_text[group.text] += 1
        bucket = split_bucket(group.text)
        if bucket < int(100 * (1 - args.val_frac - args.test_frac)):
            group.roboflow_split = "train"
        elif bucket < int(100 * (1 - args.test_frac)):
            group.roboflow_split = "val"
        else:
            group.roboflow_split = "test"
        kept.append((group, pieces))

    two_line_plates = sum(1 for group, _ in kept if group.lines > 1)

    out_root = ROOT / args.out
    for folder in ("crops", "ocr"):
        if (out_root / folder).exists():
            import shutil
            shutil.rmtree(out_root / folder)
    rows = []
    for group, pieces in sorted(kept, key=lambda item: (item[0].roboflow_split, item[0].text)):
        for index, (text, box, crop) in enumerate(pieces):
            suffix = f"_{index}" if len(pieces) > 1 else ""
            stem = hashlib.md5(f"{group.text}{suffix}".encode()).hexdigest()[:8]
            relative = Path(args.out) / "crops" / group.roboflow_split / f"{group.source.rsplit('.', 1)[0]}_{stem}{suffix}.jpg"
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(destination), crop, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                continue
            rows.append({
                "crop_path": relative.as_posix(),
                "plate_text": text,
                "source_image": group.image_path.name,
                "split": group.roboflow_split,
                "box_xyxy": ",".join(str(value) for value in box),
                "lines": 1,
            })

    counts = Counter(row["split"] for row in rows)
    for split in ("train", "val", "test"):
        subset = [row for row in rows if row["split"] == split]
        destination = out_root / "ocr" / f"{split}.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else ["crop_path"])
            writer.writeheader()
            writer.writerows(subset)

    summary = {
        "source_archive": str(archive),
        "source_images": len({g.source for g in groups}),
        "candidate_groups": len(groups),
        "kept_plates": len(kept),
        "kept_rows": len(rows),
        "unique_plates": len({group.text for group, _ in kept}),
        "splits": dict(counts),
        "two_line_plates": two_line_plates,
        "orientation_check": not args.no_orientation_check,
        "note": "Text is reconstructed from character boxes and validated against Indian plate grammar. "
                "Each crop is rotated/flipped to the orientation whose CRNN reading matches that text. "
                "Two-line plates become one row per line. Splits are assigned by plate text, not by the "
                "source archive split, so no plate crosses splits.",
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    # QA contact sheet so the reconstruction can be checked by eye.
    import random
    random.seed(7)
    samples = random.sample(rows, min(24, len(rows)))
    tiles = []
    for row in samples:
        image = cv2.imread(str(ROOT / row["crop_path"]))
        if image is None:
            continue
        image = cv2.resize(image, (300, 96))
        image = cv2.copyMakeBorder(image, 24, 3, 3, 3, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        color = (0, 220, 120) if row["split"] == "train" else (0, 180, 255)
        cv2.putText(image, f"{row['plate_text']} [{row['split']}]", (5, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        tiles.append(image)
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    sheets = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    if sheets:
        (ROOT / args.qa_sheet).parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(ROOT / args.qa_sheet), np.vstack(sheets))
        print(f"QA sheet: {args.qa_sheet}")


if __name__ == "__main__":
    main()
