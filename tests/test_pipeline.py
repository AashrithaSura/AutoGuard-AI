"""Pipeline integration test with injected detector/reader fakes.

This test needs OpenCV and NumPy but not Ultralytics, EasyOCR or PyTorch.
It is skipped automatically on a minimal install.
"""
from __future__ import annotations

import unittest

try:
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:  # pragma: no cover
    HAS_CV = False

from src.anpr.pipeline import SelfHealingANPR


class Value:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def __getitem__(self, index):
        return Value(self.value[index])

    def tolist(self):
        return self.value

    def __float__(self):
        return float(self.value)


class FakeBox:
    def __init__(self, coords, confidence=0.9):
        self.xyxy = Value([coords])
        self.conf = Value([confidence])


class FakeDetections:
    def __init__(self, boxes):
        self.boxes = boxes or None


class FakeDetector:
    def __init__(self, boxes):
        self.boxes = boxes

    def predict(self, image, **kwargs):
        return [FakeDetections(self.boxes)]


class FakeReader:
    def __init__(self):
        self.calls = 0

    def readtext(self, image, **kwargs):
        self.calls += 1
        text, score = ("TS09AB12", 0.42) if self.calls == 1 else ("TS09AB1234", 0.93)
        return [([[0, 0], [20, 0], [20, 8], [0, 8]], text, score)]


@unittest.skipUnless(HAS_CV, "OpenCV and NumPy are not installed")
class PipelineTests(unittest.TestCase):
    def test_recovery_selects_format_valid_candidate(self):
        image = np.full((360, 640, 3), 185, dtype=np.uint8)
        cv2.rectangle(image, (120, 140), (520, 220), (30, 30, 30), -1)
        cv2.putText(image, "TS09AB12", (150, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (250, 250, 250), 3)
        pipeline = SelfHealingANPR(
            detector=FakeDetector([FakeBox([120, 140, 520, 220], 0.91)]),
            reader=FakeReader(),
        )
        result = pipeline.process(image)
        self.assertEqual(len(result["plates"]), 1)
        plate = result["plates"][0]
        self.assertTrue(plate["retry_attempted"])
        self.assertEqual(plate["ocr_prediction"], "TS09AB1234")
        self.assertEqual(plate["selected_method"], "enhanced + upscaled")
        self.assertEqual(plate["review_status"], "candidate_passed_validation_gate")
        self.assertTrue(plate["crop_preview"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(result["annotated_image"].startswith("data:image/jpeg;base64,"))

    def test_split_boxes_merge_into_one_plate(self):
        image = np.full((360, 640, 3), 185, dtype=np.uint8)
        cv2.rectangle(image, (120, 140), (520, 220), (30, 30, 30), -1)
        cv2.putText(image, "TS09AB12", (150, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (250, 250, 250), 3)
        pipeline = SelfHealingANPR(
            detector=FakeDetector([
                FakeBox([120, 140, 322, 220], 0.88),
                FakeBox([318, 142, 520, 221], 0.81),
            ]),
            reader=FakeReader(),
        )
        result = pipeline.process(image)
        self.assertEqual(len(result["plates"]), 1)
        plate = result["plates"][0]
        self.assertEqual(plate["merged_detections"], 2)
        self.assertEqual(result["detection"]["merged_pairs"], 1)
        self.assertEqual(plate["box_xyxy"], [120, 140, 520, 221])
        self.assertGreater(plate["crop_box_xyxy"][2] - plate["crop_box_xyxy"][0], 400)

    def test_padded_crop_and_rectified_preview(self):
        image = np.full((360, 640, 3), 185, dtype=np.uint8)
        cv2.rectangle(image, (120, 140), (520, 220), (30, 30, 30), -1)
        pipeline = SelfHealingANPR(
            detector=FakeDetector([FakeBox([120, 140, 520, 220], 0.91)]),
            reader=FakeReader(),
        )
        plate = pipeline.process(image)["plates"][0]
        x1, y1, x2, y2 = plate["box_xyxy"]
        cx1, cy1, cx2, cy2 = plate["crop_box_xyxy"]
        self.assertLessEqual(cx1, x1)
        self.assertLessEqual(cy1, y1)
        self.assertGreaterEqual(cx2, x2)
        self.assertGreaterEqual(cy2, y2)
        self.assertTrue(plate["rectified_preview"].startswith("data:image/jpeg;base64,"))

    def test_no_detections_returns_empty_list(self):
        image = np.full((200, 300, 3), 120, dtype=np.uint8)
        pipeline = SelfHealingANPR(detector=FakeDetector([]), reader=FakeReader())
        result = pipeline.process(image)
        self.assertEqual(result["plates"], [])
        self.assertIn("annotated_image", result)


if __name__ == "__main__":
    unittest.main()
