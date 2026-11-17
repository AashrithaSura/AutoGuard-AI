"""Hybrid OCR rescue used by both the app and the evaluator.

The baseline pipeline runs EasyOCR's detector + recogniser on the original,
enhanced and thresholded crop.  Some plate crops are read better by feeding
the whole crop directly to the fine-tuned CRNN, without EasyOCR's text
detector splitting or reordering it.

The rescue is deliberately conservative:

* if the normal pipeline already produced a common-format reading with an
  engine score of at least 0.55, keep it;
* otherwise add direct-CRNN candidates and rotated format-valid variants and
  re-run the same format-aware selector.

Each EasyOCR row is also kept as its own candidate. Concatenating rows can glue
a logo or regional-script row to the plate and destroy an otherwise clean read.

On validation this recovered 11 additional exact plates without losing any
correct reading.  The threshold and policy were selected on validation data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ALPHANUMERIC = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

from .selection import DEFAULT_RETRY_MARGIN, OCRCandidate, choose_candidate, is_common_format

RESCUE_SCORE_THRESHOLD = 0.55
RESCUE_REASON = "non-standard or low-confidence reading"

_COLLATE_CACHE: dict[tuple[int, int], Any] = {}


def _collate(height: int = 64, width: int = 512):
    if (height, width) not in _COLLATE_CACHE:
        from easyocr.recognition import AlignCollate

        _COLLATE_CACHE[(height, width)] = AlignCollate(
            imgH=height, imgW=width, keep_ratio_with_pad=True
        )
    return _COLLATE_CACHE[(height, width)]


def _normalize(text: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())


def read_candidates(
    reader: Any,
    image: Any,
    method: str,
    *,
    decoder: str = "beamsearch",
    beam_width: int = 10,
) -> list[OCRCandidate]:
    """EasyOCR on an upscaled crop: the concatenated reading first, then each detected row.

    Row text is kept as its own candidate because concatenating rows can join a
    stray logo or script row to the plate; the clean row then disappears from
    the pool even though it was read correctly.
    """
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale = max(2.0, min(4.0, 160.0 / max(height, 1)))
    enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    rows = reader.readtext(
        cv2.cvtColor(enlarged, cv2.COLOR_BGR2RGB),
        detail=1,
        paragraph=False,
        allowlist=ALPHANUMERIC,
        decoder=decoder,
        beamWidth=beam_width,
        min_size=5,
        contrast_ths=0.08,
        adjust_contrast=0.7,
    )
    if width / max(height, 1) >= 3.0:
        rows.sort(key=lambda row: min(point[0] for point in row[0]))
    else:
        rows.sort(key=lambda row: (sum(point[1] for point in row[0]) / 4.0, min(point[0] for point in row[0])))
    text = _normalize("".join(str(row[1]) for row in rows))
    scores = [float(row[2]) for row in rows]
    candidates = [OCRCandidate(text, float(np.mean(scores)) if scores else 0.0, method)]
    for row in rows:
        row_text = _normalize(row[1])
        # Short rows are logos, state names or fragments, never a whole plate.
        if len(row_text) >= 8 and row_text != text:
            candidates.append(OCRCandidate(row_text, float(row[2]), method + " row"))
    return candidates


def read_direct(reader: Any, crop: Any, method: str = "direct CRNN") -> OCRCandidate:
    """Run the recogniser on the whole crop, bypassing text detection.

    EasyOCR's text detector can split a plate into multiple boxes, drop a
    character at the edge, or return boxes in an order that changes the
    reading.  A direct CRNN pass often fixes those cases.
    """
    if crop is None or getattr(crop, "size", 0) == 0:
        return OCRCandidate("", 0.0, method)
    import cv2
    import numpy as np
    import torch
    from PIL import Image

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    tensor = _collate()([Image.fromarray(gray, "L")])
    recognizer = reader.recognizer
    recognizer.eval()
    with torch.no_grad():
        logits = recognizer(tensor, torch.zeros((tensor.size(0), 31), dtype=torch.long))
        probabilities = logits.softmax(2)
        confidence, indices = probabilities.max(2)
        decoded = reader.converter.decode_greedy(
            indices.reshape(-1).cpu().numpy(),
            torch.IntTensor([logits.size(1)]),
        )[0]
    mask = indices[0] != 0
    score = float(confidence[0][mask].mean()) if bool(mask.any()) else 0.0
    return OCRCandidate(str(decoded).strip().upper(), score, method)


def rotated_variants(candidates: list[OCRCandidate]) -> list[OCRCandidate]:
    """Add cyclic rotations that satisfy a common Indian plate structure.

    A detector can return the suffix box before the state prefix.  Rotating
    the concatenated text is a cheap way to recover that ordering without
    guessing arbitrary character substitutions.
    """
    variants: list[OCRCandidate] = []
    for candidate in candidates:
        text = candidate.text
        if not text or is_common_format(text):
            continue
        for index in range(1, len(text)):
            rotated = text[index:] + text[:index]
            if is_common_format(rotated):
                variants.append(
                    OCRCandidate(rotated, candidate.score, candidate.method + " + rotated")
                )
                break
    return variants


def dedupe(candidates: list[OCRCandidate]) -> list[OCRCandidate]:
    best: dict[str, OCRCandidate] = {}
    for candidate in candidates:
        if not candidate.text:
            continue
        if candidate.text not in best or candidate.score > best[candidate.text].score:
            best[candidate.text] = candidate
    return list(best.values())


def build_rescue_pool(
    reader: Any,
    crop: Any,
    original: OCRCandidate,
    ranked: list[OCRCandidate],
    enhanced: Any,
    thresholded: Any,
) -> tuple[list[OCRCandidate], bool]:
    """Return the candidate pool and whether the base reading was trusted."""
    pool = list(ranked)
    selected, _ = choose_candidate(original, pool, DEFAULT_RETRY_MARGIN)
    trusted = bool(is_common_format(selected.text) and selected.score >= RESCUE_SCORE_THRESHOLD)
    if trusted:
        return pool, True
    direct = [
        read_direct(reader, crop, "direct CRNN"),
        read_direct(reader, enhanced, "direct CRNN + enhanced"),
        read_direct(reader, thresholded, "direct CRNN + thresholded"),
    ]
    pool.extend(direct)
    pool.extend(rotated_variants(pool))
    return dedupe(pool), False


@dataclass(frozen=True)
class RescueSelection:
    selected: OCRCandidate
    reason: str
    pool: list[OCRCandidate]
    attempted: bool


def select_with_rescue(
    reader: Any,
    crop: Any,
    original: OCRCandidate,
    ranked: list[OCRCandidate],
    enhanced: Any,
    thresholded: Any,
    margin: float = DEFAULT_RETRY_MARGIN,
) -> RescueSelection:
    pool, trusted = build_rescue_pool(reader, crop, original, ranked, enhanced, thresholded)
    selected, reason = choose_candidate(original, pool, margin)
    if trusted:
        return RescueSelection(selected, reason, pool, False)
    return RescueSelection(selected, "hybrid rescue: " + reason, pool, True)
