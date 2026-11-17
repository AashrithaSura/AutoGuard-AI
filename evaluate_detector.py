from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the final detector on the untouched test split.")
    parser.add_argument("--weights", default="models/plate_detector.pt")
    parser.add_argument("--data", default="data/prepared_corrected/detection/data.yaml")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    project = Path(__file__).resolve().parent
    weights = (project / args.weights).resolve()
    data = (project / args.data).resolve()
    if not weights.is_file():
        raise SystemExit(f"Weights not found: {weights}")
    if not data.is_file():
        raise SystemExit(f"Dataset YAML not found: {data}")

    model = YOLO(str(weights))
    metrics = model.val(
        data=str(data),
        split="test",
        imgsz=args.imgsz,
        device=args.device,
        project=str(project / "runs" / "eval"),
        name="plate_test",
        exist_ok=False,
    )
    print("Held-out detector metrics (box localization only):")
    for key in ("metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)", "metrics/mAP50-95(B)"):
        print(f"{key}: {metrics.results_dict.get(key)}")


if __name__ == "__main__":
    main()
