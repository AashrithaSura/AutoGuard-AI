"""Perspective correction for plate crops.

The detector returns axis-aligned boxes, so a plate photographed at an angle is
kept as a skewed crop.  This module estimates the plate's quadrilateral and
warps it to a rectangle.  It never replaces a reading: ``rectify`` returns
``None`` when the crop has no confident quadrilateral, and callers add the
warped copy as one more OCR candidate.
"""
from __future__ import annotations

import cv2
import numpy as np


def _order(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype="float32")
    ordered = np.zeros((4, 2), dtype="float32")
    total = points.sum(axis=1)
    ordered[0] = points[np.argmin(total)]
    ordered[2] = points[np.argmax(total)]
    delta = np.diff(points, axis=1).reshape(-1)
    ordered[1] = points[np.argmin(delta)]
    ordered[3] = points[np.argmax(delta)]
    return ordered


def _quad_from_mask(mask: np.ndarray, min_area_fraction: float = 0.2) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:15]
    image_area = mask.shape[0] * mask.shape[1]
    for contour in contours:
        if cv2.contourArea(contour) < min_area_fraction * image_area:
            break
        perimeter = cv2.arcLength(contour, True)
        for epsilon in (0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(contour, epsilon * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                return _order(approx.reshape(4, 2))
    return None


def find_quad(image: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 160)
    quad = _quad_from_mask(edges)
    if quad is not None:
        return quad
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return _quad_from_mask(otsu)


def rectify(image: np.ndarray, min_width: int = 40, min_aspect: float = 1.2, max_aspect: float = 10.0) -> np.ndarray | None:
    if image is None or getattr(image, "size", 0) == 0:
        return None
    quad = find_quad(image)
    if quad is None:
        return None
    top_left, top_right, bottom_right, bottom_left = quad
    width = max(
        float(np.linalg.norm(top_right - top_left)),
        float(np.linalg.norm(bottom_right - bottom_left)),
    )
    height = max(
        float(np.linalg.norm(bottom_left - top_left)),
        float(np.linalg.norm(bottom_right - top_right)),
    )
    if height < 8 or width < min_width:
        return None
    aspect = width / height
    if not min_aspect <= aspect <= max_aspect:
        return None
    source = np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")
    target = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(image, matrix, (int(round(width)), int(round(height))))
    return warped if warped.size else None
