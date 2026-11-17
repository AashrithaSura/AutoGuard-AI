"""Build restoration triplets for one split and write its manifest incrementally."""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.anpr.restoration import RestorationEngine  # noqa: E402

HR_W, HR_H = 256, 96


def degrade(image, rng):
    blurred = cv2.GaussianBlur(image, (5, 5), rng.uniform(0.7, 1.2))
    low = cv2.resize(blurred, (HR_W // 4, HR_H // 4), interpolation=cv2.INTER_CUBIC)
    noise = np.random.normal(0, rng.uniform(7, 13), low.shape).astype(np.float32)
    low = np.clip(low.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", low, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(42, 58)])
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR) if ok else low


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["train", "val", "test"], required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "restoration")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rng = random.Random(123)
    np.random.seed(123)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    source = ROOT / "data" / "prepared_corrected" / "ocr" / f"{args.split}.csv"
    with source.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if args.limit:
        rows = rows[: args.limit]
    engine = RestorationEngine(device="cpu")
    if not engine.ready:
        raise SystemExit("RealESRGAN_x4plus.pth is missing")
    manifest = []
    for index, row in enumerate(rows, 1):
        crop = ROOT / "data" / "prepared_corrected" / row["crop_path"]
        image = cv2.imread(str(crop))
        if image is None:
            continue
        hr = cv2.resize(image, (HR_W, HR_H), interpolation=cv2.INTER_CUBIC)
        lr = degrade(hr, rng)
        sr = engine._run_esrgan(lr)
        if sr.shape[:2] != (HR_H, HR_W):
            sr = cv2.resize(sr, (HR_W, HR_H), interpolation=cv2.INTER_CUBIC)
        for name, picture in (("hr", hr), ("lr", lr), ("esrgan", sr)):
            directory = out / args.split / name
            directory.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(directory / f"{index:05d}.png"), picture)
        manifest.append({
            "split": args.split,
            "stem": f"{index:05d}",
            "plate_text": row["plate_text"],
            "hr": str((out / args.split / "hr" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
            "lr": str((out / args.split / "lr" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
            "esrgan": str((out / args.split / "esrgan" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
        })
        if index % 25 == 0:
            print(f"{args.split} {index}/{len(rows)}", flush=True)
    path = out / f"manifest_{args.split}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0].keys()))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"wrote {len(manifest)} to {path}")


if __name__ == "__main__":
    main()
