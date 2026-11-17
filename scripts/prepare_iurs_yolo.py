"""Convert the IURS COCO character dataset into a YOLO detection dataset.

Expected input:
    raw/train/_annotations.coco.json + images
    raw/valid/_annotations.coco.json + images
    raw/test/_annotations.coco.json  + images

Usage:
    python scripts/prepare_iurs_yolo.py --raw data/iurs/raw --out data/iurs/yolo --limit 500
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path


def convert_split(raw: Path, out: Path, split: str, limit: int | None, skip_vertical: bool) -> tuple[int, int]:
    annotation_path = raw / split / "_annotations.coco.json"
    if not annotation_path.is_file():
        print(f"skip {split}: missing {annotation_path}")
        return 0, 0
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    categories = [item for item in data.get("categories", []) if int(item["id"]) > 0]
    categories.sort(key=lambda item: int(item["id"]))
    cat_to_yolo = {int(item["id"]): index for index, item in enumerate(categories)}
    names = [item["name"] for item in categories]

    by_image: dict[int, list[dict]] = defaultdict(list)
    for annotation in data.get("annotations", []):
        if int(annotation["category_id"]) in cat_to_yolo:
            by_image[int(annotation["image_id"])].append(annotation)

    image_dir = out / "images" / split
    label_dir = out / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    boxes = 0
    for image in data.get("images", []):
        if limit is not None and written >= limit:
            break
        annotations = by_image.get(int(image["id"]), [])
        if not annotations:
            continue
        width = float(image["width"])
        height = float(image["height"])
        if width <= 0 or height <= 0:
            continue

        centers = []
        for annotation in annotations:
            x, y, w, h = [float(value) for value in annotation["bbox"]]
            centers.append((x + w / 2, y + h / 2))
        if skip_vertical and len(centers) >= 3:
            xs = [point[0] for point in centers]
            ys = [point[1] for point in centers]
            if (max(xs) - min(xs)) < 0.5 * (max(ys) - min(ys)):
                continue

        source = raw / split / image["file_name"]
        if not source.is_file():
            continue
        target = image_dir / source.name
        shutil.copy2(source, target)

        lines = []
        for annotation in annotations:
            x, y, w, h = [float(value) for value in annotation["bbox"]]
            cx = (x + w / 2) / width
            cy = (y + h / 2) / height
            nw = w / width
            nh = h / height
            cx = min(max(cx, 0.0), 1.0)
            cy = min(max(cy, 0.0), 1.0)
            nw = min(max(nw, 0.0), 1.0)
            nh = min(max(nh, 0.0), 1.0)
            cls = cat_to_yolo[int(annotation["category_id"])]
            lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        (label_dir / f"{source.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
        boxes += len(lines)

    print(f"{split}: images={written} boxes={boxes}")
    return written, boxes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/iurs/yolo"))
    parser.add_argument("--limit", type=int, default=None, help="Maximum images per split for a pilot")
    parser.add_argument("--skip-vertical", action="store_true", help="Skip likely 90-degree-rotated images")
    args = parser.parse_args()

    raw = args.raw.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    totals = {}
    names = []
    for split in ("train", "valid", "test"):
        count, boxes = convert_split(raw, out, split, args.limit, args.skip_vertical)
        totals[split] = (count, boxes)
        annotation_path = raw / split / "_annotations.coco.json"
        if not names and annotation_path.is_file():
            data = json.loads(annotation_path.read_text(encoding="utf-8"))
            categories = [item for item in data["categories"] if int(item["id"]) > 0]
            categories.sort(key=lambda item: int(item["id"]))
            names = [item["name"] for item in categories]

    yaml_lines = [
        f"path: {out.as_posix()}",
        "train: images/train",
        "val: images/valid",
        "test: images/test",
        "names:",
    ]
    yaml_lines += [f"  {index}: '{name}'" for index, name in enumerate(names)]
    (out / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    print(f"data.yaml written: {out / 'data.yaml'}")
    print(f"total: {totals}")


if __name__ == "__main__":
    main()
