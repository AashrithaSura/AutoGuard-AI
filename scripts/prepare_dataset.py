from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SOURCE_DIRS = ("google_images", "State-wise_OLX", "video_images")
# Visually audited: these labels/boxes identify decorative model-name plates, not registration plates.
NON_PLATE_TEXT = {"CRETA", "DUSTER", "TERRANO"}
OCR_SUSPECT_TEXT = {"BLUR", "HP2020TR6255G"}
# Manually reviewed source corrections. Keep original XML files untouched.
# These two annotations were made against a differently sized image; their
# coordinates already match the current image pixels, so do not rescale them.
BOX_COORDS_ALREADY_IMAGE_PIXELS = {
    "State-wise_OLX/AN/AN2.jpg",
    "State-wise_OLX/AN/AN6.jpg",
}
# Human-verified correction from the test-crop review.
PLATE_TEXT_OVERRIDES = {
    "State-wise_OLX/DL/DL30.jpg": "DL10C0S520",
}


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def normalize_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def resolve_image(xml_path: Path, filename: str, image_index: dict[tuple[Path, str], Path]) -> Path | None:
    candidate = (xml_path.parent / filename).resolve()
    if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTS:
        return candidate
    # Some Pascal VOC XML files contain stale absolute paths or a wrong filename.
    # Match only within the same source folder using the XML basename.
    return image_index.get((xml_path.parent.resolve(), xml_path.stem.lower()))


def read_record(xml_path: Path, raw_root: Path, image_index, issues: list[dict]) -> dict | None:
    try:
        annotation = ET.parse(xml_path).getroot()
    except Exception as exc:
        issues.append({"kind": "xml_parse_error", "file": xml_path.relative_to(raw_root).as_posix(), "detail": str(exc)})
        return None

    filename = (annotation.findtext("filename") or "").strip()
    image_path = resolve_image(xml_path, filename, image_index)
    if image_path is None:
        issues.append({"kind": "unmatched_annotation", "file": xml_path.relative_to(raw_root).as_posix(), "detail": filename})
        return None

    image = cv2.imread(str(image_path))
    if image is None:
        issues.append({"kind": "unreadable_image", "file": image_path.relative_to(raw_root).as_posix(), "detail": ""})
        return None
    height, width = image.shape[:2]
    relative_image = image_path.relative_to(raw_root).as_posix()
    size_node = annotation.find("size")
    declared_w = int(size_node.findtext("width", width)) if size_node is not None else width
    declared_h = int(size_node.findtext("height", height)) if size_node is not None else height
    sx = width / declared_w if declared_w else 1.0
    sy = height / declared_h if declared_h else 1.0
    if relative_image in BOX_COORDS_ALREADY_IMAGE_PIXELS:
        sx = sy = 1.0
        issues.append({"kind": "manual_box_coordinate_override", "file": relative_image, "detail": "XML box coordinates match the current image pixels; dimension scaling disabled after visual review."})

    objects = []
    for obj in annotation.findall("object"):
        raw_text = (obj.findtext("name") or "").strip().upper()
        override = PLATE_TEXT_OVERRIDES.get(relative_image)
        if override and raw_text != override:
            issues.append({"kind": "manual_plate_text_override", "file": relative_image, "detail": f"XML={raw_text}; reviewed={override}"})
            raw_text = override
        text = normalize_text(raw_text)
        box = obj.find("bndbox")
        try:
            # Pascal VOC coordinates are 1-based and max corners are inclusive.
            x1 = max(0, round((int(box.findtext("xmin")) - 1) * sx))
            y1 = max(0, round((int(box.findtext("ymin")) - 1) * sy))
            x2 = min(width, round(int(box.findtext("xmax")) * sx))
            y2 = min(height, round(int(box.findtext("ymax")) * sy))
        except Exception as exc:
            issues.append({"kind": "invalid_box", "file": image_path.relative_to(raw_root).as_posix(), "detail": str(exc)})
            continue
        if x2 <= x1 or y2 <= y1:
            issues.append({"kind": "invalid_box", "file": image_path.relative_to(raw_root).as_posix(), "detail": f"{x1},{y1},{x2},{y2}"})
            continue
        if declared_w != width or declared_h != height:
            issues.append({"kind": "xml_image_size_mismatch", "file": image_path.relative_to(raw_root).as_posix(), "detail": f"xml={declared_w}x{declared_h}; actual={width}x{height}"})
        is_nonplate = text in NON_PLATE_TEXT
        if is_nonplate:
            issues.append({"kind": "visually_confirmed_nonplate_annotation", "file": image_path.relative_to(raw_root).as_posix(), "detail": f"{raw_text} box excluded from positive detection labels"})
        ocr_ok = bool(re.fullmatch(r"[A-Z0-9]{6,12}", text)) and any(ch.isdigit() for ch in text) and text not in OCR_SUSPECT_TEXT
        if not ocr_ok and not is_nonplate:
            issues.append({"kind": "ocr_label_needs_review", "file": image_path.relative_to(raw_root).as_posix(), "detail": raw_text})
        objects.append({
            "raw_text": raw_text,
            "text": text,
            "box": [x1, y1, x2, y2],
            "nonplate": is_nonplate,
            "ocr_ok": ocr_ok,
        })

    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    return {
        "image": image_path,
        "relative": image_path.relative_to(raw_root).as_posix(),
        "sha256": digest,
        "width": width,
        "height": height,
        "objects": objects,
    }


def make_groups(records: list[dict]) -> list[list[int]]:
    uf = UnionFind(len(records))
    by_text: dict[str, int] = {}
    by_hash: dict[str, int] = {}
    for i, record in enumerate(records):
        prior = by_hash.setdefault(record["sha256"], i)
        uf.union(i, prior)
        for obj in record["objects"]:
            text = obj["text"]
            if text:
                prior = by_text.setdefault(text, i)
                uf.union(i, prior)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(records)):
        groups[uf.find(i)].append(i)
    return list(groups.values())


def assign_splits(records: list[dict], groups: list[list[int]], seed: int) -> dict[int, str]:
    total = len(records)
    targets = {"train": total * 0.80, "val": total * 0.10, "test": total * 0.10}
    counts = Counter()
    rng = random.Random(seed)
    groups = list(groups)
    rng.shuffle(groups)
    groups.sort(key=len, reverse=True)
    assigned: dict[int, str] = {}
    for group in groups:
        split = min(targets, key=lambda s: (counts[s] / targets[s], counts[s], ("train", "val", "test").index(s)))
        for index in group:
            assigned[index] = split
        counts[split] += len(group)
    return assigned


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit, deduplicate, group-split, and prepare the ANPR2 Pascal VOC dataset.")
    parser.add_argument("--raw-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "prepared")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    raw_root = args.raw_root.resolve()
    output = args.output.resolve()
    if any((raw_root / name).is_dir() is False for name in SOURCE_DIRS):
        raise SystemExit(f"Expected source folders {SOURCE_DIRS} under {raw_root}")
    if output.exists() and any(output.iterdir()):
        if not args.overwrite:
            raise SystemExit(f"Output is not empty: {output}; choose another output or pass --overwrite.")
        shutil.rmtree(output)

    image_index: dict[tuple[Path, str], Path] = {}
    for source_name in SOURCE_DIRS:
        for image_path in (raw_root / source_name).rglob("*"):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTS:
                image_index[(image_path.parent.resolve(), image_path.stem.lower())] = image_path.resolve()

    issues: list[dict] = []
    xml_paths = [p for source_name in SOURCE_DIRS for p in (raw_root / source_name).rglob("*.xml")]
    parsed = [read_record(p, raw_root, image_index, issues) for p in xml_paths]
    parsed = [record for record in parsed if record is not None]

    # Deduplicate exact image copies. If copies disagree about annotation text or boxes, stop for manual review.
    unique_by_hash: dict[str, dict] = {}
    duplicate_copies = 0
    for record in parsed:
        prior = unique_by_hash.get(record["sha256"])
        if prior is None:
            unique_by_hash[record["sha256"]] = record
            continue
        duplicate_copies += 1
        prior_objects = sorted(prior["objects"], key=lambda o: (o["text"], o["nonplate"]))
        current_objects = sorted(record["objects"], key=lambda o: (o["text"], o["nonplate"]))
        prior_keys = [(o["text"], o["nonplate"]) for o in prior_objects]
        current_keys = [(o["text"], o["nonplate"]) for o in current_objects]
        if prior_keys != current_keys:
            raise SystemExit(f"Exact duplicate images have conflicting plate labels: {prior['relative']} and {record['relative']}")
        # Duplicate annotations agree on text but can differ by a few pixels.
        # Merge their boxes to retain the full plate region consistently.
        for old_obj, new_obj in zip(prior_objects, current_objects):
            old_obj["box"] = [
                min(old_obj["box"][0], new_obj["box"][0]),
                min(old_obj["box"][1], new_obj["box"][1]),
                max(old_obj["box"][2], new_obj["box"][2]),
                max(old_obj["box"][3], new_obj["box"][3]),
            ]
        issues.append({"kind": "exact_duplicate_removed", "file": record["relative"], "detail": f"duplicate of {prior['relative']}; compatible boxes merged"})
    records = list(unique_by_hash.values())
    if not records:
        raise SystemExit("No usable image/annotation pairs were found.")

    group_list = make_groups(records)
    assignment = assign_splits(records, group_list, args.seed)
    split_names = ("train", "val", "test")
    for split in split_names:
        (output / "detection" / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "detection" / "labels" / split).mkdir(parents=True, exist_ok=True)
        (output / "ocr" / split / "images").mkdir(parents=True, exist_ok=True)

    image_counts = Counter()
    ocr_counts = Counter()
    crop_manifest = {split: [] for split in split_names}
    all_manifest = []
    name_counts = Counter()
    for index, record in enumerate(records):
        split = assignment[index]
        image_counts[split] += 1
        relative_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", record["relative"].replace("/", "__"))
        stem = f"{Path(relative_key).stem}_{record['sha256'][:10]}"
        name_counts[stem] += 1
        if name_counts[stem] > 1:
            stem += f"_{name_counts[stem]}"
        ext = record["image"].suffix.lower()
        copied_image = output / "detection" / "images" / split / f"{stem}{ext}"
        shutil.copy2(record["image"], copied_image)

        det_lines = []
        image = cv2.imread(str(record["image"]))
        height, width = image.shape[:2]
        for obj_index, obj in enumerate(record["objects"], start=1):
            x1, y1, x2, y2 = obj["box"]
            if not obj["nonplate"]:
                xc = ((x1 + x2) / 2) / width
                yc = ((y1 + y2) / 2) / height
                bw = (x2 - x1) / width
                bh = (y2 - y1) / height
                det_lines.append(f"0 {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}")
            if obj["ocr_ok"]:
                pad_x = max(2, round((x2 - x1) * 0.04))
                pad_y = max(2, round((y2 - y1) * 0.12))
                xa, ya = max(0, x1 - pad_x), max(0, y1 - pad_y)
                xb, yb = min(width, x2 + pad_x), min(height, y2 + pad_y)
                crop = image[ya:yb, xa:xb]
                crop_name = f"{stem}_p{obj_index}.jpg"
                crop_path = output / "ocr" / split / "images" / crop_name
                if crop.size and cv2.imwrite(str(crop_path), crop):
                    crop_row = {
                        "crop_path": crop_path.relative_to(output).as_posix(),
                        "plate_text": obj["text"],
                        "source_image": record["relative"],
                        "split": split,
                        "box_xyxy": f"{x1},{y1},{x2},{y2}",
                    }
                    crop_manifest[split].append(crop_row)
                    ocr_counts[split] += 1
            all_manifest.append({
                "source_image": record["relative"],
                "split": split,
                "sha256": record["sha256"],
                "plate_text": obj["text"],
                "raw_label": obj["raw_text"],
                "box_xyxy": f"{x1},{y1},{x2},{y2}",
                "used_for_detection": not obj["nonplate"],
                "used_for_ocr": obj["ocr_ok"],
            })
        label_path = output / "detection" / "labels" / split / f"{stem}.txt"
        label_path.write_text("\n".join(det_lines) + ("\n" if det_lines else ""), encoding="utf-8")

    yaml_path = output / "detection" / "data.yaml"
    yaml_path.write_text(
        f"path: {(output / 'detection').as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: license_plate\n",
        encoding="utf-8",
    )
    for split in split_names:
        csv_path = output / "ocr" / f"{split}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["crop_path", "plate_text", "source_image", "split", "box_xyxy"])
            writer.writeheader()
            writer.writerows(crop_manifest[split])
    with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_image", "split", "sha256", "plate_text", "raw_label", "box_xyxy", "used_for_detection", "used_for_ocr"])
        writer.writeheader()
        writer.writerows(all_manifest)
    with (output / "issues.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kind", "file", "detail"])
        writer.writeheader()
        writer.writerows(issues)

    summary = {
        "raw_root": str(raw_root),
        "usable_unique_images": len(records),
        "source_xml_files": len(xml_paths),
        "exact_duplicate_copies_removed": duplicate_copies,
        "plate_text_group_count": len(group_list),
        "detection_images_by_split": dict(image_counts),
        "ocr_crops_by_split": dict(ocr_counts),
        "ocr_unique_texts_by_split": {
            split: len({row["plate_text"] for row in crop_manifest[split]}) for split in split_names
        },
        "issue_counts": dict(Counter(issue["kind"] for issue in issues)),
        "seed": args.seed,
        "grouping": "Exact-image hash and normalized plate text connected components are kept within one split.",
        "raw_data_modified": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()



