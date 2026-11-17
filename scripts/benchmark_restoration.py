"""Benchmark restoration methods on the real test crops.

Compares LR, bicubic, Real-ESRGAN and RefineNet using PSNR/SSIM and OCR
exact-match / character error rate on synthetically degraded real plates.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from skimage.metrics import structural_similarity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.anpr.recovery import read_direct  # noqa: E402
from src.anpr.restoration import RefineNet  # noqa: E402
from src.anpr.selection import OCRCandidate  # noqa: E402


def edit_distance(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, ca in enumerate(left, 1):
        current = [i]
        for j, cb in enumerate(right, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (ca != cb)))
        row = current
    return row[-1]


def psnr(prediction, target):
    mse = float(np.mean((prediction.astype(np.float32) - target.astype(np.float32)) ** 2))
    return 99.0 if mse <= 1e-10 else 10 * np.log10(255.0 ** 2 / mse)


def metrics(rows, key):
    exact = sum(row[key] == row["truth"] for row in rows)
    errors = sum(edit_distance(row[key], row["truth"]) for row in rows)
    chars = sum(max(1, len(row["truth"])) for row in rows)
    return {
        "samples": len(rows),
        "exact_match": round(exact / max(len(rows), 1), 4),
        "character_error_rate": round(errors / max(chars, 1), 4),
        "exact_n": exact,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "restoration" / "manifest.csv")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "models" / "refine_net_l1.pth")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "restoration_benchmark.json")
    args = parser.parse_args()
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["split"] == "test"]
    import easyocr

    reader = easyocr.Reader(["en"], gpu=False, detector=False, recognizer=True, quantize=False)
    weights = ROOT / "models" / "plate_ocr.pth"
    if weights.is_file():
        reader.recognizer.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        reader.recognizer.eval()
    refiner = None
    if args.checkpoint.is_file():
        checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
        config = checkpoint.get("config", {})
        refiner = RefineNet(
            num_blocks=int(config.get("num_blocks", 4)),
            channels=int(config.get("channels", 64)),
        ).eval()
        refiner.load_state_dict(checkpoint["model_state_dict"])
    results = []
    for index, row in enumerate(rows, 1):
        hr = cv2.imread(str(ROOT / row["hr"]))
        lr = cv2.imread(str(ROOT / row["lr"]))
        esrgan = cv2.imread(str(ROOT / row["esrgan"]))
        bicubic = cv2.resize(lr, (hr.shape[1], hr.shape[0]), interpolation=cv2.INTER_CUBIC)
        if refiner is not None:
            rgb = cv2.cvtColor(esrgan, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            tensor = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0)
            with torch.no_grad():
                restored = refiner(tensor).squeeze(0).permute(1, 2, 0).clamp(0, 1).numpy()
            refined = cv2.cvtColor((restored * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        else:
            refined = esrgan
        variants = {"lr": lr, "bicubic": bicubic, "esrgan": esrgan, "refined": refined}
        record = {"truth": row["plate_text"], "file": row["stem"]}
        for name, image in variants.items():
            candidate = read_direct(reader, image, name)
            metric_image = image
            if metric_image.shape[1] != hr.shape[1] or metric_image.shape[0] != hr.shape[0]:
                metric_image = cv2.resize(
                    metric_image, (hr.shape[1], hr.shape[0]), interpolation=cv2.INTER_CUBIC
                )
            record[f"{name}_prediction"] = candidate.text
            record[f"{name}_score"] = round(candidate.score, 4)
            record[f"{name}_psnr"] = round(psnr(metric_image, hr), 3)
            record[f"{name}_ssim"] = round(
                float(
                    structural_similarity(
                        cv2.cvtColor(metric_image, cv2.COLOR_BGR2GRAY),
                        cv2.cvtColor(hr, cv2.COLOR_BGR2GRAY),
                    )
                ),
                4,
            )
        results.append(record)
        if index % 20 == 0 or index == len(rows):
            print(f"benchmarked {index}/{len(rows)}", flush=True)
    summary = {
        "samples": len(results),
        "methods": {
            name: {
                **metrics(results, f"{name}_prediction"),
                "psnr": round(float(np.mean([row[f"{name}_psnr"] for row in results])), 3),
                "ssim": round(float(np.mean([row[f"{name}_ssim"] for row in results])), 4),
            }
            for name in ("lr", "bicubic", "esrgan", "refined")
        },
        "note": "Test crops degraded synthetically (blur, 4x downsample, noise, JPEG). OCR uses the fine-tuned plate recogniser directly.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
