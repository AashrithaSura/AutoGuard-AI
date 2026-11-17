from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8n for Indian plate detection.")
    parser.add_argument("--data", default="data/prepared_corrected/detection/data.yaml")
    parser.add_argument("--model", default="models/yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=7)
    args = parser.parse_args()

    project = Path(__file__).resolve().parent
    data_yaml = (project / args.data).resolve()
    model_path = (project / args.model).resolve()
    if not data_yaml.is_file():
        raise SystemExit(f"Dataset config not found: {data_yaml}")
    if not model_path.is_file():
        raise SystemExit(f"Initialization weights not found: {model_path}")

    model = YOLO(str(model_path))
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        seed=42,
        deterministic=True,
        cache=False,
        project=str(project / "runs" / "detect"),
        name="plate_yolov8n",
        exist_ok=False,
        plots=True,
        verbose=True,
    )
    best = Path(model.trainer.best)
    destination = project / "models" / "plate_detector.pt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, destination)
    print(f"Best validation checkpoint copied to: {destination}")


if __name__ == "__main__":
    main()
