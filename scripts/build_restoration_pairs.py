"""Build HR/LR/ESRGAN triplets for plate-refiner training and evaluation."""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from src.anpr.restoration import RestorationEngine  # noqa: E402

HR_W, HR_H = 256, 96


def degrade(image: np.ndarray, rng: random.Random) -> np.ndarray:
    blurred = cv2.GaussianBlur(image, (5, 5), rng.uniform(0.7, 1.2))
    low = cv2.resize(blurred, (HR_W // 4, HR_H // 4), interpolation=cv2.INTER_CUBIC)
    noise = np.random.normal(0, rng.uniform(7, 13), low.shape).astype(np.float32)
    low = np.clip(low.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", low, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(42, 58)])
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR) if ok else low


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "restoration")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, default=0, help="Optional limit per split for a quick test.")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    np.random.seed(args.seed)
    engine = RestorationEngine(device="cpu")
    if not engine.ready:
        raise SystemExit("RealESRGAN_x4plus.pth is missing from models/")
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for split in ("train", "val", "test"):
        source = ROOT / "data" / "prepared_corrected" / "ocr" / f"{split}.csv"
        with source.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        if args.limit:
            rows = rows[: args.limit]
        for index, row in enumerate(rows, 1):
            crop = ROOT / "data" / "prepared_corrected" / row["crop_path"]
            image = cv2.imread(str(crop))
            if image is None:
                continue
            hr = cv2.resize(image, (HR_W, HR_H), interpolation=cv2.INTER_CUBIC)
            lr = degrade(hr, rng)
            sr = engine._run_esrgan(lr)
            if sr.shape[1] != HR_W or sr.shape[0] != HR_H:
                sr = cv2.resize(sr, (HR_W, HR_H), interpolation=cv2.INTER_CUBIC)
            for name, picture in (("hr", hr), ("lr", lr), ("esrgan", sr)):
                directory = out / split / name
                directory.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(directory / f"{index:05d}.png"), picture)
            manifest.append({
                "split": split,
                "stem": f"{index:05d}",
                "plate_text": row["plate_text"],
                "hr": str((out / split / "hr" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
                "lr": str((out / split / "lr" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
                "esrgan": str((out / split / "esrgan" / f"{index:05d}.png").relative_to(ROOT)).replace("\\", "/"),
            })
            if index % 50 == 0:
                print(f"{split} {index}/{len(rows)}", flush=True)
    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0].keys()))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"wrote {len(manifest)} triplets to {out / 'manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

