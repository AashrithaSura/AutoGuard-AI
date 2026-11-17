"""Fast 128x48 fine-tune of RefineNet from the 256x96 checkpoint."""
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

WIDTH, HEIGHT = 128, 48


class Pairs(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        hr = cv2.imread(str(ROOT / row["hr"]))
        sr = cv2.imread(str(ROOT / row["esrgan"]))
        hr = cv2.resize(hr, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
        sr = cv2.resize(sr, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
        hr = cv2.cvtColor(hr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        sr = cv2.cvtColor(sr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return torch.from_numpy(sr).permute(2, 0, 1), torch.from_numpy(hr).permute(2, 0, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--source", type=Path, default=ROOT / "models" / "refine_net_l1.pth")
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "refine_net_candidate.pth")
    args = parser.parse_args()
    torch.set_num_threads(8)
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    with (ROOT / "data" / "restoration" / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    train = [row for row in rows if row["split"] == "train"]
    val = [row for row in rows if row["split"] == "val"]
    train_loader = DataLoader(Pairs(train), batch_size=args.batch, shuffle=True)
    val_loader = DataLoader(Pairs(val), batch_size=args.batch, shuffle=False)
    model = RefineNet(4, 64)
    source = args.source
    best = float("inf")
    if source.is_file():
        checkpoint = torch.load(source, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["model_state_dict"])
        best = float((checkpoint.get("metrics") or {}).get("val_l1", float("inf")))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.L1Loss()
    stale = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for sr, hr in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(sr), hr)
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
                mse = torch.mean((output - hr) ** 2).item()
                val_psnr += 99.0 if mse <= 1e-10 else 10 * math.log10(1.0 / mse)
        val_loss /= max(len(val_loader), 1)
        val_psnr /= max(len(val_loader), 1)
        record = {"epoch": epoch, "train_l1": round(total / max(len(train_loader), 1), 6), "val_l1": round(val_loss, 6), "val_psnr": round(val_psnr, 3)}
        history.append(record)
        print(json.dumps(record), flush=True)
        if val_loss < best:
            best = val_loss
            stale = 0
            torch.save({
                "model_state_dict": model.state_dict(),
                "config": {"num_blocks": 4, "channels": 64},
                "metrics": record,
                "source": "AutoGuard RefineNet, fast 128x48 fine-tune on real plate crops with synthetic LR degradation",
            }, args.output)
        else:
            stale += 1
        if stale >= args.patience:
            break
    (ROOT / "reports" / "restoration_training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    print(f"saved candidate {args.output}")


if __name__ == "__main__":
    main()
