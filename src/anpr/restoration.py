"""Plate restoration / super-resolution for the AutoGuard Restoration Lab.

Attribution:
- Real-ESRGAN by Xintao Wang et al. (BSD-3-Clause), loaded via spandrel.
- RefineNet architecture adapted from
  https://github.com/yashchavan11/indian-license-plate-restoration (MIT).
  The refiner here is trained on this project's real plate crops.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import MODEL_DIR

MAX_INPUT_DIM = 320
DEFAULT_SCALE = 4


class _ResBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
            nn.ReLU(True),
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.relu(self.body(x) + x, inplace=True)


class RefineNet(nn.Module):
    """Lightweight residual refinement network (~300K parameters)."""

    def __init__(self, num_blocks: int = 4, channels: int = 64) -> None:
        super().__init__()
        self.head = nn.Sequential(nn.Conv2d(3, channels, 3, padding=1), nn.ReLU(True))
        self.body = nn.Sequential(*[_ResBlock(channels) for _ in range(num_blocks)])
        self.tail = nn.Conv2d(channels, 3, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.clamp(x + self.tail(self.body(self.head(x))), 0.0, 1.0)


@dataclass
class RestoredImage:
    name: str
    image: np.ndarray
    data_url: str
    sharpness: float
    width: int
    height: int
    method: str


def encode_jpeg(image: np.ndarray, quality: int = 92) -> str:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")


def sharpness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)


class RestorationEngine:
    def __init__(self, weights_dir: str | Path | None = None, device: str = "cpu") -> None:
        self.weights_dir = Path(weights_dir) if weights_dir else MODEL_DIR
        self.device = device
        self._esrgan = None
        self._refiner = None
        self._scale = DEFAULT_SCALE

    @property
    def esrgan_path(self) -> Path:
        return self.weights_dir / "RealESRGAN_x4plus.pth"

    @property
    def refiner_path(self) -> Path:
        return self.weights_dir / "refine_net_l1.pth"

    @property
    def ready(self) -> bool:
        return self.esrgan_path.is_file()

    @property
    def has_refiner(self) -> bool:
        return self.refiner_path.is_file()

    def _load_esrgan(self) -> None:
        if self._esrgan is not None:
            return
        if not self.esrgan_path.is_file():
            raise FileNotFoundError(f"Real-ESRGAN weights not found: {self.esrgan_path}")
        from spandrel import ModelLoader

        descriptor = ModelLoader(device=torch.device(self.device)).load_from_file(str(self.esrgan_path))
        self._esrgan = descriptor.model.eval()
        self._scale = int(descriptor.scale or 4)

    def _load_refiner(self) -> None:
        if self._refiner is not None or not self.refiner_path.is_file():
            return
        checkpoint = torch.load(self.refiner_path, map_location=self.device, weights_only=False)
        config = checkpoint.get("config", {})
        model = RefineNet(
            num_blocks=int(config.get("num_blocks", 4)),
            channels=int(config.get("channels", 64)),
        ).to(self.device).eval()
        model.load_state_dict(checkpoint["model_state_dict"])
        self._refiner = model

    def _run_esrgan(self, image: np.ndarray) -> np.ndarray:
        self._load_esrgan()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        tensor = tensor.to(self.device)
        height, width = tensor.shape[2], tensor.shape[3]
        pad_h = (8 - height % 8) % 8
        pad_w = (8 - width % 8) % 8
        if pad_h or pad_w:
            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode="reflect")
        with torch.no_grad():
            output = self._esrgan(tensor)
        output = output[:, :, : height * self._scale, : width * self._scale]
        result = output.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
        result = (result * 255).astype(np.uint8)
        return cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

    def _run_refiner(self, image: np.ndarray) -> np.ndarray | None:
        self._load_refiner()
        if self._refiner is None:
            return None
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb.copy()).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        with torch.no_grad():
            output = self._refiner(tensor.to(self.device))
        result = output.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
        result = (result * 255).astype(np.uint8)
        return cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

    @staticmethod
    def _limit_input(image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        if max(height, width) <= MAX_INPUT_DIM:
            return image
        ratio = MAX_INPUT_DIM / max(height, width)
        return cv2.resize(image, (max(1, int(width * ratio)), max(1, int(height * ratio))), interpolation=cv2.INTER_AREA)

    def restore_all(self, image: np.ndarray) -> dict[str, Any]:
        source = self._limit_input(image)
        started = time.perf_counter()
        height, width = source.shape[:2]
        bicubic = cv2.resize(
            source,
            (width * self._scale, height * self._scale),
            interpolation=cv2.INTER_CUBIC,
        )
        sr = self._run_esrgan(source)
        refined = self._run_refiner(sr)
        elapsed = round((time.perf_counter() - started) * 1000, 1)

        variants = [
            RestoredImage("bicubic", bicubic, encode_jpeg(bicubic), sharpness(bicubic), bicubic.shape[1], bicubic.shape[0], "Bicubic 4×"),
            RestoredImage("esrgan", sr, encode_jpeg(sr), sharpness(sr), sr.shape[1], sr.shape[0], "Real-ESRGAN 4×"),
        ]
        if refined is not None:
            variants.append(
                RestoredImage("refined", refined, encode_jpeg(refined), sharpness(refined), refined.shape[1], refined.shape[0], "Real-ESRGAN + RefineNet")
            )
        return {
            "source": {
                "data_url": encode_jpeg(source),
                "width": width,
                "height": height,
                "sharpness": sharpness(source),
            },
            "variants": [
                {
                    "name": item.name,
                    "label": item.method,
                    "data_url": item.data_url,
                    "sharpness": item.sharpness,
                    "width": item.width,
                    "height": item.height,
                }
                for item in variants
            ],
            "images": {"source": source, **{item.name: item.image for item in variants}},
            "scale": self._scale,
            "processing_ms": elapsed,
            "refiner_available": refined is not None,
        }
