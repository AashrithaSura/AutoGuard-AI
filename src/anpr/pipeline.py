"""Self-healing ANPR pipeline.

Heavy dependencies (Ultralytics, EasyOCR, PyTorch) are imported lazily so the
analytics API and assistant can start on a machine where the ML stack is not
installed.  The ``/api/analyze`` endpoint returns a clear 503 in that case.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:  # OpenCV and NumPy are needed only when an image is actually processed.
    import cv2
    import numpy as np

    from .rectify import rectify
except ImportError:  # pragma: no cover - exercised on a minimal install
    cv2 = None
    np = None
    rectify = None

from .recovery import RESCUE_REASON, read_candidates, select_with_rescue
from .selection import DEFAULT_RETRY_MARGIN, PLATE_FORMAT, review_status

# Detection and crop settings. 1280 px inference recovers small/far plates that
# the default 640 px pass misses; the padded crop gives the recogniser the plate
# border instead of clipping the first/last character.
DETECT_CONF = float(os.environ.get("ANPR_DETECT_CONF", "0.15"))
DETECT_IMGSZ = int(os.environ.get("ANPR_DETECT_IMGSZ", "1280"))
CROP_PAD = float(os.environ.get("ANPR_CROP_PAD", "0.06"))
CONTEXT_PAD = float(os.environ.get("ANPR_CONTEXT_PAD", "0.18"))
EDGE_MARGIN_PX = 2


@dataclass
class Candidate:
    text: str
    score: float
    method: str


class SelfHealingANPR:
    def __init__(
        self,
        detector_path: str | Path | None = None,
        gpu: bool = False,
        *,
        detector: Any | None = None,
        reader: Any | None = None,
        ocr_weights: str | Path | None = None,
    ) -> None:
        if cv2 is None or np is None:
            raise RuntimeError("OpenCV and NumPy are required for image processing. Install requirements.txt.")
        self.detector = detector
        if self.detector is None:
            if detector_path is None:
                raise FileNotFoundError("Detector weights not found: no path supplied")
            detector_file = Path(detector_path)
            if not detector_file.is_file():
                raise FileNotFoundError(f"Detector weights not found: {detector_file}")
            try:
                from ultralytics import YOLO
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("ultralytics is not installed. Run: pip install -r requirements.txt") from exc
            self.detector = YOLO(str(detector_file))

        base = Path(detector_path).parent if detector_path else Path(__file__).resolve().parents[2] / "models"
        weights = Path(ocr_weights) if ocr_weights else base / "plate_ocr.pth"
        self.reader = reader
        if self.reader is None:
            try:
                import easyocr
                import torch
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("easyocr and torch are not installed. Run: pip install -r requirements.txt") from exc
            self.reader = easyocr.Reader(["en"], gpu=gpu, quantize=not weights.is_file())
            if weights.is_file():
                state = torch.load(weights, map_location="cpu", weights_only=True)
                self.reader.recognizer.load_state_dict(state)
                self.reader.recognizer.eval()

    @staticmethod
    def _encode(image: Any) -> str:
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(buffer).decode("ascii")

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", text.upper())

    @staticmethod
    def _quality(crop: Any) -> tuple[float, float, float, list[str]]:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        flags = []
        if brightness < 65:
            flags.append("low light")
        elif brightness > 205:
            flags.append("overexposed")
        if contrast < 35:
            flags.append("low contrast")
        if blur < 75:
            flags.append("possible blur")
        return brightness, contrast, blur, flags

    @staticmethod
    def _expand_box(box: tuple[int, int, int, int], width: int, height: int, ratio: float) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        pad_x = int(round((x2 - x1) * ratio))
        pad_y = int(round((y2 - y1) * ratio))
        return max(0, x1 - pad_x), max(0, y1 - pad_y), min(width, x2 + pad_x), min(height, y2 + pad_y)

    @staticmethod
    def _same_plate(a: tuple, b: tuple) -> bool:
        """True when two boxes are split halves or duplicate detections of one plate."""
        ax1, ay1, ax2, ay2, _conf, _n = a
        bx1, by1, bx2, by2, _conf, _n = b
        aw, ah = ax2 - ax1, ay2 - ay1
        bw, bh = bx2 - bx1, by2 - by1
        if min(aw, ah, bw, bh) <= 0:
            return False
        vertical = min(ay2, by2) - max(ay1, by1)
        if vertical < 0.6 * min(ah, bh):
            return False
        if not 0.7 <= ah / bh <= 1.4:
            return False
        gap = max(ax1, bx1) - min(ax2, bx2)
        if gap > 0.12 * min(aw, bw):
            return False
        union_w = max(ax2, bx2) - min(ax1, bx1)
        union_h = max(ay2, by2) - min(ay1, by1)
        return union_w <= 2.4 * max(aw, bw) and union_h <= 1.25 * max(ah, bh)

    @classmethod
    def _merge_split_boxes(cls, boxes: list[tuple]) -> tuple[list[tuple], int]:
        """Union boxes that cover parts of the same plate. Returns boxes and merge count."""
        merged = list(boxes)
        merges = 0
        changed = True
        while changed:
            changed = False
            result: list[tuple] = []
            while merged:
                current = merged.pop(0)
                index = 0
                while index < len(merged):
                    other = merged[index]
                    if cls._same_plate(current, other):
                        current = (
                            min(current[0], other[0]),
                            min(current[1], other[1]),
                            max(current[2], other[2]),
                            max(current[3], other[3]),
                            max(current[4], other[4]),
                            current[5] + other[5],
                        )
                        merged.pop(index)
                        merges += 1
                        changed = True
                    else:
                        index += 1
                result.append(current)
            merged = result
        return merged, merges

    @staticmethod
    def _enhance(crop: Any, brightness: float) -> tuple[Any, Any]:
        corrected = crop.copy()
        if brightness < 90:
            gamma = min(2.0, max(1.15, 125.0 / max(brightness, 1.0)))
            lut = np.clip(((np.arange(256) / 255.0) ** (1.0 / gamma)) * 255, 0, 255).astype(np.uint8)
            corrected = cv2.LUT(corrected, lut)
        lab = cv2.cvtColor(corrected, cv2.COLOR_BGR2LAB)
        light, a, b = cv2.split(lab)
        light = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(light)
        corrected = cv2.cvtColor(cv2.merge((light, a, b)), cv2.COLOR_LAB2BGR)
        softened = cv2.GaussianBlur(corrected, (0, 0), 1.0)
        sharpened = cv2.addWeighted(corrected, 1.5, softened, -0.5, 0)
        gray = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        thresholded = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return sharpened, thresholded

    def _read_all(self, crop: Any, method: str) -> list[Candidate]:
        return [
            Candidate(text=item.text, score=item.score, method=item.method)
            for item in read_candidates(self.reader, crop, method)
        ]

    def _read(self, crop: Any, method: str) -> Candidate:
        return self._read_all(crop, method)[0]

    def process(self, image: Any) -> dict:
        if cv2 is None or np is None:
            raise RuntimeError("OpenCV and NumPy are required for image processing.")
        detections = self.detector.predict(
            image, conf=DETECT_CONF, imgsz=DETECT_IMGSZ, max_det=30, verbose=False
        )[0]
        height, width = image.shape[:2]
        plates = []
        annotated = image.copy()

        raw_boxes: list[tuple] = []
        if detections.boxes is not None:
            for box in detections.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
                raw_boxes.append((float(x1), float(y1), float(x2), float(y2), float(box.conf[0].cpu()), 1))
        merged_boxes, merge_count = self._merge_split_boxes(raw_boxes)

        for mx1, my1, mx2, my2, detector_score, box_count in merged_boxes:
            x1, x2 = max(0, int(round(mx1))), min(width, int(round(mx2)))
            y1, y2 = max(0, int(round(my1))), min(height, int(round(my2)))
            if x2 <= x1 or y2 <= y1:
                continue
            tight = image[y1:y2, x1:x2].copy()
            # Padding restores the plate border that a tight detector box clips;
            # quality is still measured on the tight crop so flags stay meaningful.
            cx1, cy1, cx2, cy2 = self._expand_box((x1, y1, x2, y2), width, height, CROP_PAD)
            crop = image[cy1:cy2, cx1:cx2].copy()
            edge_touching = (
                x1 <= EDGE_MARGIN_PX
                or y1 <= EDGE_MARGIN_PX
                or x2 >= width - EDGE_MARGIN_PX
                or y2 >= height - EDGE_MARGIN_PX
            )
            brightness, contrast, blur, flags = self._quality(tight)
            original_reads = self._read_all(crop, "upscaled original")
            original = original_reads[0]
            retry_reasons = list(flags)
            if original.score < 0.65:
                retry_reasons.append("low OCR engine score")
            if not PLATE_FORMAT.fullmatch(original.text):
                retry_reasons.append("format check failed")

            candidates = list(original_reads)
            enhanced, thresholded = self._enhance(crop, brightness)
            if retry_reasons:
                candidates.extend(self._read_all(enhanced, "enhanced + upscaled"))
                candidates.extend(self._read_all(thresholded, "thresholded + upscaled"))
                wx1, wy1, wx2, wy2 = self._expand_box((x1, y1, x2, y2), width, height, CONTEXT_PAD)
                if (wx1, wy1, wx2, wy2) != (cx1, cy1, cx2, cy2):
                    wider = image[wy1:wy2, wx1:wx2].copy()
                    candidates.extend(self._read_all(wider, "wider context crop"))
            warped = rectify(crop)
            if warped is not None:
                candidates.extend(self._read_all(warped, "rectified perspective"))
            distinct: dict[str, Candidate] = {}
            for candidate in candidates:
                if candidate.text and (candidate.text not in distinct or candidate.score > distinct[candidate.text].score):
                    distinct[candidate.text] = candidate
            ranked = sorted(distinct.values(), key=lambda item: item.score, reverse=True)
            rescue = select_with_rescue(
                self.reader,
                crop,
                original,
                ranked,
                enhanced,
                thresholded,
                DEFAULT_RETRY_MARGIN,
            )
            selected = rescue.selected
            selection_reason = rescue.reason
            ranked = [Candidate(text=item.text, score=item.score, method=item.method) for item in rescue.pool]
            if rescue.attempted and RESCUE_REASON not in retry_reasons:
                retry_reasons.append(RESCUE_REASON)
            observations = []
            if box_count > 1:
                observations.append(f"Merged {box_count} detector boxes into one plate region.")
            if edge_touching:
                observations.append("Plate may run past the frame edge.")
            if detector_score < 0.25:
                observations.append("Low detector score; verify that this region is a plate.")
            if flags:
                observations.append("Quality flags: " + ", ".join(flags) + ".")
            else:
                observations.append("No blur, lighting or contrast issue detected.")
            observations.append("Selection: " + selection_reason + ".")
            observations.append(f"Engine score {selected.score:.3f} — a ranking signal, not a probability.")
            status = review_status(selected.text, selected.score)
            if status == "needs_manual_review":
                observations.append("Manual review required: it did not pass the validation-set gate.")
            else:
                observations.append("Verify visually before use.")
            if retry_reasons:
                delta = selected.score - original.score
                triggers = [reason for reason in retry_reasons if reason != RESCUE_REASON] or retry_reasons
                observations.append("Retry triggers: " + ", ".join(triggers) + f" (engine score {delta:+.3f}).")
            else:
                observations.append("No retry needed at the configured thresholds.")

            result = {
                "box_xyxy": [x1, y1, x2, y2],
                "crop_box_xyxy": [cx1, cy1, cx2, cy2],
                "detector_confidence": detector_score,
                "merged_detections": box_count,
                "edge_touching": edge_touching,
                "ocr_prediction": selected.text,
                "ocr_engine_score": selected.score,
                "original_prediction": original.text,
                "original_ocr_score": original.score,
                "common_format_match": bool(PLATE_FORMAT.fullmatch(selected.text)),
                "review_status": status,
                "quality_flags": flags or ["none detected"],
                "brightness": round(brightness, 2),
                "contrast": round(contrast, 2),
                "blur_score": round(blur, 2),
                "retry_attempted": bool(retry_reasons),
                "retry_reasons": retry_reasons,
                "selection_reason": selection_reason,
                "selected_method": selected.method,
                "candidates": [asdict(candidate) for candidate in ranked],
                "observations": observations,
                "crop_preview": self._encode(crop),
                "enhanced_preview": self._encode(enhanced),
                "rectified_preview": self._encode(warped) if warped is not None else "",
            }
            plates.append(result)
            color = (40, 180, 60) if detector_score >= 0.25 else (20, 150, 240)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = selected.text or "UNREAD"
            cv2.putText(annotated, label, (x1, max(22, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        return {
            "annotated_image": self._encode(annotated),
            "plates": plates,
            "detection": {
                "confidence": DETECT_CONF,
                "imgsz": DETECT_IMGSZ,
                "raw_boxes": len(raw_boxes),
                "merged_boxes": len(merged_boxes),
                "merged_pairs": merge_count,
            },
        }
