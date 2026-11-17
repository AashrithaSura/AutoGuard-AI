from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

STATE_CODES = (
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HR", "HP", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TG", "TN", "TR", "TS",
    "UA", "UK", "UP", "WB",
)
STATE_PLATE_FORMAT = re.compile(r"^(?:" + "|".join(STATE_CODES) + r")\d{1,2}[A-Z]{0,3}\d{1,4}$")
BH_PLATE_FORMAT = re.compile(r"^\d{2}BH\d{4}[A-Z]{1,2}$")
class PlateFormat:
    @staticmethod
    def fullmatch(text: str):
        return STATE_PLATE_FORMAT.fullmatch(text) or BH_PLATE_FORMAT.fullmatch(text)
PLATE_FORMAT = PlateFormat()
COMMON_STATE_PLATE_FORMAT = re.compile(r"^(?:" + "|".join(STATE_CODES) + r")\d{2}[A-Z]{0,3}\d{4}$")
COMMON_BH_PLATE_FORMAT = re.compile(r"^\d{2}BH\d{4}[A-Z]{1,2}$")
def is_common_format(text: str) -> bool:
    return bool(COMMON_STATE_PLATE_FORMAT.fullmatch(text) or COMMON_BH_PLATE_FORMAT.fullmatch(text))
DEFAULT_RETRY_MARGIN = 0.25
# Calibrated on validation predictions by scripts/calibrate_gate.py so accepted
# readings stay at or below an 8% selective-error ceiling (reports/gate_curve.json).
REVIEW_SCORE_THRESHOLD = 0.81

@dataclass(frozen=True)
class OCRCandidate:
    text: str
    score: float
    method: str

def review_status(text: str, score: float) -> str:
    """Apply a validation-selected review gate; score is not a correctness probability."""
    if is_common_format(text) and score >= REVIEW_SCORE_THRESHOLD:
        return "candidate_passed_validation_gate"
    return "needs_manual_review"


def choose_candidate(original: OCRCandidate, candidates: Iterable[OCRCandidate], margin: float = DEFAULT_RETRY_MARGIN) -> tuple[OCRCandidate, str]:
    """Prefer a standard-format reading; avoid small-score changes between valid candidates."""
    pool = list(candidates)
    valid = [item for item in pool if PLATE_FORMAT.fullmatch(item.text)]
    common = [item for item in valid if is_common_format(item.text)]
    if is_common_format(original.text):
        alternatives = [item for item in common if item.text != original.text]
        if not alternatives:
            return original, "kept original: no distinct standard-format alternative"
        challenger = max(alternatives, key=lambda item: item.score)
        if challenger.score - original.score < margin:
            return original, f"kept original: alternative score gain below {margin:.2f}"
        return challenger, f"selected standard-format alternative: score gain at least {margin:.2f}"
    if common:
        challenger = max(common, key=lambda item: item.score)
        return challenger, "preferred standard Indian plate structure over legacy-shaped candidate"
    if valid:
        return max(valid, key=lambda item: item.score), "selected highest-scoring format-valid candidate"
    if pool:
        return max(pool, key=lambda item: item.score), "no format-valid candidate; selected highest engine score"
    return original, "no OCR candidate available"

