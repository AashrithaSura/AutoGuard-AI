"""Read the project's measured evaluation artefacts for the dashboard."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, MODEL_DIR, REPORT_DIR, ROOT


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wilson_interval(successes: int, total: int) -> list[float]:
    """95% Wilson score interval for a proportion."""
    if total <= 0:
        return [0.0, 0.0]
    z = 1.96
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)]


def _interval(rate: float, samples: int) -> list[float]:
    return wilson_interval(round(float(rate) * samples), samples)


def workload(coverage: float, selective_accuracy: float) -> dict:
    """Review load and residual errors per 100 plates at the operating point."""
    coverage = float(coverage)
    selective = float(selective_accuracy)
    return {
        "auto_pass_per_100": round(100 * coverage, 1),
        "review_per_100": round(100 * (1 - coverage), 1),
        "residual_errors_per_100": round(100 * coverage * (1 - selective), 2),
    }


def detector_metrics() -> dict:
    path = ROOT / "runs" / "detect" / "plate_yolov8n" / "results.csv"
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return {}
        last = rows[-1]
        return {
            "epoch": int(float(last.get("epoch", 0))),
            "precision": round(float(last.get("metrics/precision(B)", 0)), 4),
            "recall": round(float(last.get("metrics/recall(B)", 0)), 4),
            "map50": round(float(last.get("metrics/mAP50(B)", 0)), 4),
            "map50_95": round(float(last.get("metrics/mAP50-95(B)", 0)), 4),
            "split": "validation",
        }
    except (OSError, ValueError, TypeError):
        return {}


def gate_calibration() -> dict:
    """Risk-targeted gate calibration written by scripts/calibrate_gate.py."""
    curve = _read_json(REPORT_DIR / "gate_curve.json")
    if not curve or not curve.get("recommended"):
        return {}
    recommended = curve["recommended"]
    tested = curve.get("test_at_recommended") or {}
    return {
        "threshold": recommended.get("threshold", 0.0),
        "target_error": curve.get("target_error", 0.0),
        "validation_coverage": recommended.get("coverage", 0.0),
        "validation_selective_accuracy": recommended.get("selective_accuracy", 0.0),
        "test_coverage": tested.get("coverage", 0.0),
        "test_selective_accuracy": tested.get("selective_accuracy", 0.0),
        "test_error": tested.get("selective_error", 0.0),
        "risk_target_met_on_test": bool(curve.get("risk_target_met_on_test")),
    }


def training_composition() -> dict:
    """Row counts and origin of the combined OCR training split."""
    data = _read_json(DATA_DIR / "combined_ocr" / "summary.json")
    splits = {}
    for name in ("train", "val", "test"):
        entry = data.get(name)
        if isinstance(entry, dict):
            splits[name] = {
                "rows": int(entry.get("rows", 0)),
                "origin": entry.get("origin", {}),
            }
    return splits


def external_iurs_evaluation() -> dict:
    """Held-out IURS plate crops, evaluated with the shipped checkpoint."""
    report = _read_json(REPORT_DIR / "ocr_iurs_test_v2.json")
    if not report:
        return {}
    margin = report.get("format_aware_by_margin", {}).get("0.25", {})
    gate = report.get("review_gate_by_margin", {}).get("0.25", {})
    baseline = report.get("original", {})
    samples = int(report.get("samples", 0))
    exact = round(float(margin.get("exact_match_accuracy", 0)), 4)
    cer = round(float(margin.get("character_error_rate", 0)), 4)
    coverage = round(float(gate.get("coverage", 0)), 4)
    selective = round(float(gate.get("exact_match_accuracy_when_eligible", 0)), 4)
    return {
        "samples": samples,
        "exact_match": exact,
        "exact_match_ci95": _interval(exact, samples),
        "cer": cer,
        "similarity": round(1 - cer, 4),
        "baseline_exact_match": round(float(baseline.get("exact_match_accuracy", 0)), 4),
        "baseline_cer": round(float(baseline.get("character_error_rate", 0)), 4),
        "gate_coverage": coverage,
        "gate_selective_accuracy": selective,
        "workload": workload(coverage, selective),
        "source": "reports/ocr_iurs_test_v2.json",
    }


def test_composition() -> dict:
    """Unique-plate composition written by scripts/evaluate_final.py."""
    summary = _read_json(REPORT_DIR / "final_evaluation.json").get("summary") or {}
    keys = (
        "samples",
        "unique_plates",
        "plate_macro_exact_match",
        "plate_macro_ci95",
        "plate_any_crop_exact_match",
        "singleton_frame_exact_match",
        "singleton_samples",
        "dominant_plate",
        "dominant_plate_crops",
        "dominant_share_of_test",
        "frame_exact_match_without_dominant",
    )
    result = {key: summary.get(key) for key in keys if key in summary}
    if result:
        result["source"] = "reports/final_evaluation.json"
    return result


def frame_vote_summary() -> dict:
    """Multi-frame majority vote written by scripts/eval_frame_vote.py."""
    internal = _read_json(REPORT_DIR / "frame_vote_v2.json")
    if not internal:
        return {}
    external = _read_json(REPORT_DIR / "frame_vote_iurs.json")
    if external:
        internal["iurs"] = external
    return internal


def _checkpoint(names: tuple[str, ...]) -> dict:
    for name in names:
        path = MODEL_DIR / name
        try:
            stat = path.stat()
        except OSError:
            continue
        return {
            "file": name,
            "size_mb": round(stat.st_size / 1_048_576, 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
        }
    return {}


def model_checkpoints() -> dict:
    return {
        "ocr": _checkpoint(("plate_ocr.pth",)),
        "detector": _checkpoint(("plate_detector.pt",)),
    }


def benchmark_summary() -> dict:
    """Latest frozen OCR evaluation plus detector validation metrics."""
    report_path = REPORT_DIR / "ocr_final_test_v2.json"
    report = _read_json(report_path)
    margin = report.get("format_aware_by_margin", {}).get("0.25", {})
    gate = report.get("review_gate_by_margin", {}).get("0.25", {})
    calibration = gate_calibration()
    gate_coverage = calibration.get("test_coverage") or gate.get("coverage", 0)
    gate_selective = calibration.get("test_selective_accuracy") or gate.get("exact_match_accuracy_when_eligible", 0)
    gate_threshold = calibration.get("threshold") or gate.get("score_threshold", 0.8)
    samples = int(report.get("samples", 0))
    exact = round(float(margin.get("exact_match_accuracy", 0)), 4)
    cer = round(float(margin.get("character_error_rate", 0)), 4)
    return {
        "ocr": {
            "samples": samples,
            "exact_match": exact,
            "exact_match_ci95": _interval(exact, samples),
            "cer": cer,
            "similarity": round(1 - cer, 4),
            "baseline_exact_match": round(float(report.get("original", {}).get("exact_match_accuracy", 0)), 4),
            "baseline_cer": round(float(report.get("original", {}).get("character_error_rate", 0)), 4),
            "gate_coverage": round(float(gate_coverage), 4),
            "gate_selective_accuracy": round(float(gate_selective), 4),
            "gate_threshold": gate_threshold,
            "workload": workload(gate_coverage, gate_selective),
            "rescue": report.get("rescue", {}),
            "risk_control": calibration,
        },
        "detector": detector_metrics(),
        "training": training_composition(),
        "external_iurs": external_iurs_evaluation(),
        "composition": test_composition(),
        "frame_vote": frame_vote_summary(),
        "models": model_checkpoints(),
        "note": (
            "Internal development result on 165 held-out crops; the split was "
            "seen during development. The external IURS check is a separate "
            "110-crop split."
        ),
        "source": f"reports/{report_path.name}",
    }
