"""Train the lightweight RefineNet on real plate crops with synthetic degradation."""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.anpr.restoration import RefineNet  # noqa: E402


class PairDataset(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        hr = cv2.imread(str(ROOT / row["hr"]))
        sr = cv2.imread(str(ROOT / row["esrgan"]))
        hr = cv2.cvtColor(hr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        sr = cv2.cvtColor(sr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return torch.from_numpy(sr).permute(2, 0, 1), torch.from_numpy(hr).permute(2, 0, 1)


def psnr(prediction, target):
    mse = torch.mean((prediction - target) ** 2).item()
    return 99.0 if mse <= 1e-10 else 10 * math.log10(1.0 / mse)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "data" / "restoration" / "manifest.csv")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "models" / "refine_net_l1.pth")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()
    if args.threads:
        torch.set_num_threads(args.threads)
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    train_rows = [row for row in rows if row["split"] == "train"]
    val_rows = [row for row in rows if row["split"] == "val"]
    print(f"train={len(train_rows)} val={len(val_rows)}", flush=True)
    train_loader = DataLoader(PairDataset(train_rows), batch_size=args.batch, shuffle=True, num_workers=0)
    val_loader = DataLoader(PairDataset(val_rows), batch_size=args.batch, shuffle=False, num_workers=0)
    model = RefineNet(num_blocks=4, channels=64)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.L1Loss()
    best = float("inf")
    stale = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for sr, hr in train_loader:
            optimizer.zero_grad(set_to_none=True)
            output = model(sr)
            loss = criterion(output, hr)
            loss.backward()
            optimizer.step()
            total += float(loss.detach())
        model.eval()
        val_loss = 0.0
        val_psnr = 0.0
        with torch.no_grad():
            for sr, hr in val_loader:
                output = model(sr)
                val_loss += float(criterion(output, hr))
                val_psnr += psnr(output, hr)
        val_loss /= max(len(val_loader), 1)
        val_psnr /= max(len(val_loader), 1)
        record = {
            "epoch": epoch,
            "train_l1": round(total / max(len(train_loader), 1), 6),
            "val_l1": round(val_loss, 6),
            "val_psnr": round(val_psnr, 3),
        }
        history.append(record)
        print(json.dumps(record), flush=True)
        if val_loss < best:
            best = val_loss
            stale = 0
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "config": {"num_blocks": 4, "channels": 64},
                "metrics": record,
                "source": "trained on AutoGuard real plate crops with synthetic LR degradation",
            }, args.checkpoint)
        else:
            stale += 1
        if stale >= args.patience:
            print("early stop", flush=True)
            break
    (ROOT / "reports" / "restoration_training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(f"saved {args.checkpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
