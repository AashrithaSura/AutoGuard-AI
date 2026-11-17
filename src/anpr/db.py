"""SQLite persistence and analytics for AutoGuard AI.

The project deliberately uses SQLite instead of a hosted MongoDB instance:
the capstone must run offline on a laptop, the data volume is small, and a
single file is easy to back up or attach to a report.  The access layer is
kept behind :class:`Database`, so swapping in MongoDB later only changes this
module and not the API or assistant.
"""
from __future__ import annotations

import csv
import io
import json
import random
import re
import sqlite3
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import (
    DB_PATH,
    TIMEZONE,
    day_start_utc,
    to_local,
    utc_now_iso,
)
from .selection import is_common_format, review_status

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'upload',
    image_sha256 TEXT,
    width INTEGER,
    height INTEGER,
    plate_count INTEGER NOT NULL DEFAULT 0,
    processing_ms REAL,
    annotated_preview TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS plates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    plate_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    ocr_text TEXT NOT NULL DEFAULT '',
    original_text TEXT NOT NULL DEFAULT '',
    detector_confidence REAL NOT NULL DEFAULT 0,
    ocr_score REAL NOT NULL DEFAULT 0,
    original_score REAL NOT NULL DEFAULT 0,
    common_format INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'needs_manual_review',
    quality_flags TEXT NOT NULL DEFAULT '[]',
    brightness REAL,
    contrast REAL,
    blur_score REAL,
    retry_attempted INTEGER NOT NULL DEFAULT 0,
    retry_reasons TEXT NOT NULL DEFAULT '[]',
    selection_reason TEXT,
    selected_method TEXT,
    recovery_outcome TEXT NOT NULL DEFAULT 'not_attempted',
    candidates TEXT NOT NULL DEFAULT '[]',
    observations TEXT NOT NULL DEFAULT '[]',
    crop_preview TEXT,
    enhanced_preview TEXT,
    verified_text TEXT,
    verification_status TEXT NOT NULL DEFAULT 'unreviewed',
    verified_at TEXT,
    ground_truth TEXT,
    ground_truth_correct INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_source ON analyses(source);
CREATE INDEX IF NOT EXISTS idx_plates_analysis ON plates(analysis_id);
CREATE INDEX IF NOT EXISTS idx_plates_created ON plates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plates_review ON plates(review_status);
CREATE INDEX IF NOT EXISTS idx_plates_recovery ON plates(recovery_outcome);
CREATE INDEX IF NOT EXISTS idx_plates_text ON plates(ocr_text);
CREATE INDEX IF NOT EXISTS idx_plates_verification ON plates(verification_status);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
"""

PLATE_COLUMNS = """
    p.id, p.analysis_id, p.plate_index, p.created_at, p.ocr_text,
    p.original_text, p.detector_confidence, p.ocr_score, p.original_score,
    p.common_format, p.review_status, p.quality_flags, p.brightness,
    p.contrast, p.blur_score, p.retry_attempted, p.retry_reasons,
    p.selection_reason, p.selected_method, p.recovery_outcome,
    p.candidates, p.observations, p.crop_preview, p.enhanced_preview,
    p.verified_text, p.verification_status, p.verified_at,
    p.ground_truth, p.ground_truth_correct, p.notes,
    a.filename, a.source, a.width, a.height, a.processing_ms,
    a.annotated_preview AS image_preview, a.created_at AS analysis_created_at
"""

JSON_FIELDS = (
    "quality_flags",
    "retry_reasons",
    "candidates",
    "observations",
)


def _json_load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _normalise_plate(text: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def derive_recovery_outcome(plate: dict) -> str:
    """Classify what the retry achieved from signals the app actually knows.

    Ground-truth-aware evaluation lives in the benchmark report, not here.
    This is deliberately conservative: a changed reading only counts as a
    recovery when it gains structure or a meaningful score margin.
    """
    if not plate.get("retry_attempted"):
        return "not_attempted"
    selected = _normalise_plate(plate.get("ocr_prediction"))
    original = _normalise_plate(plate.get("original_prediction"))
    if not selected:
        return "no_reading"
    if selected == original:
        return "unchanged"
    selected_score = _safe_float(plate.get("ocr_engine_score"))
    original_score = _safe_float(plate.get("original_ocr_score"))
    if is_common_format(selected) and not is_common_format(original):
        return "recovered"
    if selected_score - original_score >= 0.05:
        return "recovered"
    if selected_score - original_score <= -0.05:
        return "degraded"
    return "changed"


def derive_failure_reasons(plate: dict) -> list[str]:
    reasons: list[str] = []
    for raw in list(plate.get("retry_reasons") or []) + list(plate.get("quality_flags") or []):
        label = str(raw).strip().lower()
        if not label or label == "none detected" or label in reasons:
            continue
        reasons.append(label)
    return reasons


FAILURE_LABELS = {
    "possible blur": "Motion / focus blur",
    "low light": "Low light",
    "overexposed": "Overexposure",
    "low contrast": "Low contrast",
    "low ocr engine score": "Low OCR confidence",
    "format check failed": "Format check failed",
    "no plate detected": "No plate detected",
    "low detector score": "Low detector confidence",
    "tilted plate": "Tilt / perspective",
    "glare": "Glare / reflection",
}


def failure_label(raw: str) -> str:
    key = str(raw).strip().lower()
    return FAILURE_LABELS.get(key, raw.replace("_", " ").strip().title())


class Database:
    """Small, thread-safe-by-connection SQLite repository."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def save_analysis(
        self,
        result: dict,
        filename: str,
        *,
        source: str = "upload",
        processing_ms: float | None = None,
        image_sha256: str | None = None,
        width: int | None = None,
        height: int | None = None,
        notes: str | None = None,
    ) -> dict:
        plates = list(result.get("plates") or [])
        created = utc_now_iso()
        source = source if source in {"upload", "demo", "benchmark"} else "upload"
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO analyses
                    (created_at, filename, source, image_sha256, width, height,
                     plate_count, processing_ms, annotated_preview, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created,
                    filename or "upload",
                    source,
                    image_sha256,
                    width,
                    height,
                    len(plates),
                    processing_ms,
                    result.get("annotated_preview"),
                    notes,
                ),
            )
            analysis_id = int(cursor.lastrowid)
            plate_ids: list[int] = []
            for index, plate in enumerate(plates, start=1):
                plate_id = self._insert_plate(conn, analysis_id, index, created, plate)
                plate_ids.append(plate_id)
        return {"analysis_id": analysis_id, "plate_ids": plate_ids, "created_at": created}

    def _insert_plate(
        self,
        conn: sqlite3.Connection,
        analysis_id: int,
        index: int,
        created: str,
        plate: dict,
    ) -> int:
        selected_text = _normalise_plate(plate.get("ocr_prediction"))
        original_text = _normalise_plate(plate.get("original_prediction"))
        selected_score = _safe_float(plate.get("ocr_engine_score"))
        original_score = _safe_float(plate.get("original_ocr_score"))
        flags = [str(item) for item in (plate.get("quality_flags") or []) if str(item).strip()]
        retry_reasons = [str(item) for item in (plate.get("retry_reasons") or []) if str(item).strip()]
        candidates = list(plate.get("candidates") or [])
        selected_method = plate.get("selected_method") or ""
        if not selected_method:
            for candidate in candidates:
                if _normalise_plate(candidate.get("text")) == selected_text:
                    selected_method = str(candidate.get("method") or "")
                    break
        status = plate.get("review_status") or review_status(selected_text, selected_score)
        outcome = derive_recovery_outcome(plate)
        cursor = conn.execute(
            """
            INSERT INTO plates
                (analysis_id, plate_index, created_at, ocr_text, original_text,
                 detector_confidence, ocr_score, original_score, common_format,
                 review_status, quality_flags, brightness, contrast, blur_score,
                 retry_attempted, retry_reasons, selection_reason, selected_method,
                 recovery_outcome, candidates, observations, crop_preview,
                 enhanced_preview, verified_text, verification_status, verified_at,
                 ground_truth, ground_truth_correct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                index,
                created,
                selected_text,
                original_text,
                _safe_float(plate.get("detector_confidence")),
                selected_score,
                original_score,
                1 if (plate.get("common_format_match") or is_common_format(selected_text)) else 0,
                status,
                json.dumps(flags, ensure_ascii=False),
                _safe_float(plate.get("brightness")),
                _safe_float(plate.get("contrast")),
                _safe_float(plate.get("blur_score")),
                1 if plate.get("retry_attempted") else 0,
                json.dumps(retry_reasons, ensure_ascii=False),
                str(plate.get("selection_reason") or ""),
                selected_method,
                outcome,
                json.dumps(candidates, ensure_ascii=False),
                json.dumps([str(item) for item in (plate.get("observations") or [])], ensure_ascii=False),
                plate.get("crop_preview") or "",
                plate.get("enhanced_preview") or "",
                plate.get("verified_text") or None,
                plate.get("verification_status") or "unreviewed",
                plate.get("verified_at"),
                plate.get("ground_truth"),
                plate.get("ground_truth_correct"),
                plate.get("notes"),
            ),
        )
        return int(cursor.lastrowid)

    def verify_plate(
        self,
        plate_id: int,
        verified_text: str,
        status: str = "corrected",
    ) -> dict | None:
        allowed = {"confirmed", "corrected", "rejected"}
        if status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        text = _normalise_plate(verified_text)
        if status != "rejected" and not text:
            raise ValueError("verified_text is required unless the reading is rejected")
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM plates WHERE id = ?", (plate_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE plates
                   SET verified_text = ?, verification_status = ?, verified_at = ?
                 WHERE id = ?
                """,
                (text if status != "rejected" else "", status, utc_now_iso(), plate_id),
            )
        return self.get_plate(plate_id)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def clear_verification(self, plate_id: int) -> dict | None:
        """Undo a confirm/correct/reject and return the plate to review."""
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM plates WHERE id = ?", (plate_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE plates
                   SET verified_text = NULL,
                       verification_status = 'unreviewed',
                       verified_at = NULL
                 WHERE id = ?
                """,
                (plate_id,),
            )
        return self.get_plate(plate_id)

    def delete_plate(self, plate_id: int) -> bool:
        """Permanently remove a plate record and any now-empty analysis."""
        with self.connect() as conn:
            row = conn.execute("SELECT analysis_id FROM plates WHERE id = ?", (plate_id,)).fetchone()
            if row is None:
                return False
            analysis_id = int(row[0])
            conn.execute("DELETE FROM plates WHERE id = ?", (plate_id,))
            remaining = conn.execute(
                "SELECT COUNT(*) FROM plates WHERE analysis_id = ?", (analysis_id,)
            ).fetchone()[0]
            if remaining == 0:
                conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return True

    def get_plate(self, plate_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {PLATE_COLUMNS} FROM plates p JOIN analyses a ON a.id = p.analysis_id WHERE p.id = ?",
                (plate_id,),
            ).fetchone()
        return self._plate_row(row) if row else None

    def find_plates(self, text: str, limit: int = 5) -> list[dict]:
        query = _normalise_plate(text)
        if not query:
            return []
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {PLATE_COLUMNS}
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.ocr_text LIKE ? OR p.verified_text LIKE ?
                 ORDER BY p.created_at DESC
                 LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [self._plate_row(row) for row in rows]

    def list_plates(
        self,
        *,
        status: str = "all",
        query: str = "",
        days: int | None = None,
        limit: int = 20,
        offset: int = 0,
        include_demo: bool = True,
    ) -> dict:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        where: list[str] = []
        params: list[Any] = []
        if not include_demo:
            where.append("a.source != 'demo'")
        if days:
            where.append("p.created_at >= ?")
            params.append((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds"))
        if status == "review":
            where.append("p.review_status = 'needs_manual_review' AND p.verification_status = 'unreviewed'")
        elif status == "recovered":
            where.append("(p.recovery_outcome = 'recovered' OR p.verification_status IN ('confirmed', 'corrected'))")
        elif status == "passed":
            where.append("p.review_status = 'candidate_passed_validation_gate'")
        elif status == "failed":
            where.append("(p.ocr_text = '' OR p.review_status = 'needs_manual_review') AND p.verification_status = 'unreviewed'")
        elif status == "low_confidence":
            where.append("p.ocr_score < 0.81 AND p.ocr_text != '' AND p.verification_status = 'unreviewed'")
        elif status == "corrected":
            where.append("p.verification_status = 'corrected'")
        elif status == "rejected":
            where.append("p.verification_status = 'rejected'")
        elif status == "unverified":
            where.append("p.verification_status = 'unreviewed'")
        if query.strip():
            needle = f"%{query.strip()}%"
            where.append("(p.ocr_text LIKE ? OR p.verified_text LIKE ? OR a.filename LIKE ? OR CAST(p.id AS TEXT) = ?)")
            params.extend([needle, needle, needle, query.strip()])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self.connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM plates p JOIN analyses a ON a.id = p.analysis_id{clause}",
                    params,
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT {PLATE_COLUMNS}
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                  {clause}
                 ORDER BY p.created_at DESC, p.id DESC
                 LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return {
            "items": [self._plate_row(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }

    def recent_activity(self, limit: int = 8, include_demo: bool = True) -> list[dict]:
        return self.list_plates(limit=limit, include_demo=include_demo)["items"]

    def list_analyses(self, limit: int = 20, include_demo: bool = True) -> list[dict]:
        where = "" if include_demo else " WHERE source != 'demo'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, created_at, filename, source, plate_count, processing_ms
                  FROM analyses{where}
                 ORDER BY created_at DESC, id DESC LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, days: int = 30, include_demo: bool = True) -> dict:
        days = max(1, min(int(days), 365))
        since = day_start_utc(days - 1)
        prev_since = day_start_utc(days * 2 - 1)
        conditions = ["p.created_at >= ?"]
        params: list[Any] = [since]
        if not include_demo:
            conditions.append("a.source != 'demo'")
        where = " AND ".join(conditions)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total_plates,
                       SUM(CASE WHEN p.review_status = 'candidate_passed_validation_gate' THEN 1 ELSE 0 END) AS passed,
                       SUM(CASE WHEN p.review_status = 'needs_manual_review' AND p.verification_status = 'unreviewed' THEN 1 ELSE 0 END) AS review,
                       SUM(CASE WHEN p.ocr_text = '' THEN 1 ELSE 0 END) AS unreadable,
                       SUM(CASE WHEN p.retry_attempted = 1 THEN 1 ELSE 0 END) AS retries,
                       SUM(CASE WHEN p.recovery_outcome = 'recovered' THEN 1 ELSE 0 END) AS recovered,
                       SUM(CASE WHEN p.recovery_outcome = 'degraded' THEN 1 ELSE 0 END) AS degraded,
                       SUM(CASE WHEN p.verification_status != 'unreviewed' THEN 1 ELSE 0 END) AS verified,
                       SUM(CASE WHEN p.verification_status = 'corrected' THEN 1 ELSE 0 END) AS corrected,
                       SUM(CASE WHEN p.ocr_score < 0.81 THEN 1 ELSE 0 END) AS low_confidence,
                       AVG(p.ocr_score) AS avg_ocr,
                       AVG(p.detector_confidence) AS avg_detector,
                       AVG(a.processing_ms) AS avg_processing
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE {where}
                """,
                params,
            ).fetchone()
            analyses = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM analyses a WHERE a.created_at >= ?" + ("" if include_demo else " AND a.source != 'demo'"),
                    [since],
                ).fetchone()[0]
            )
            demo = int(conn.execute("SELECT COUNT(*) FROM analyses WHERE source = 'demo'").fetchone()[0])
            upload = int(conn.execute("SELECT COUNT(*) FROM analyses WHERE source = 'upload'").fetchone()[0])
            today_row = conn.execute(
                f"""
                SELECT COUNT(*) AS plates,
                       SUM(CASE WHEN p.review_status = 'candidate_passed_validation_gate' THEN 1 ELSE 0 END) AS passed
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.created_at >= ? {"AND a.source != 'demo'" if not include_demo else ""}
                """,
                [day_start_utc(0)],
            ).fetchone()
            prev = conn.execute(
                f"""
                SELECT COUNT(*) FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.created_at >= ? AND p.created_at < ? {"AND a.source != 'demo'" if not include_demo else ""}
                """,
                [prev_since, since],
            ).fetchone()
            last_row = conn.execute("SELECT MAX(created_at) FROM analyses").fetchone()
        total = int(row["total_plates"] or 0)
        passed = int(row["passed"] or 0)
        review = int(row["review"] or 0)
        retries = int(row["retries"] or 0)
        recovered = int(row["recovered"] or 0)
        verified = int(row["verified"] or 0)
        corrected = int(row["corrected"] or 0)
        yesterday_or_prev = int(prev[0] or 0)
        delta = None
        if yesterday_or_prev:
            delta = round((total - yesterday_or_prev) / yesterday_or_prev * 100, 1)
        return {
            "days": days,
            "since": since,
            "total_analyses": analyses,
            "total_plates": total,
            "passed": passed,
            "review": review,
            "unreadable": int(row["unreadable"] or 0),
            "retries": retries,
            "recovered": recovered,
            "degraded": int(row["degraded"] or 0),
            "verified": verified,
            "corrected": corrected,
            "low_confidence": int(row["low_confidence"] or 0),
            "avg_ocr_score": round(float(row["avg_ocr"] or 0), 4),
            "avg_detector_confidence": round(float(row["avg_detector"] or 0), 4),
            "avg_processing_ms": round(float(row["avg_processing"] or 0), 1),
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "review_rate": round(review / total, 4) if total else 0.0,
            "recovery_rate": round(recovered / retries, 4) if retries else 0.0,
            "correction_rate": round(corrected / verified, 4) if verified else 0.0,
            "today_plates": int(today_row["plates"] or 0),
            "today_passed": int(today_row["passed"] or 0),
            "previous_plates": yesterday_or_prev,
            "period_delta_pct": delta,
            "demo_analyses": demo,
            "upload_analyses": upload,
            "last_seen": last_row[0] if last_row else None,
        }

    def timeseries(self, days: int = 14, include_demo: bool = True) -> list[dict]:
        days = max(1, min(int(days), 90))
        since = day_start_utc(days - 1)
        demo_clause = "" if include_demo else " AND a.source != 'demo'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id AS analysis_id, p.created_at, p.review_status, p.recovery_outcome
                  FROM analyses a LEFT JOIN plates p ON p.analysis_id = a.id
                 WHERE a.created_at >= ?{demo_clause}
                """,
                [since],
            ).fetchall()
        buckets: dict[str, dict] = {}
        start_local = to_local(since)
        for offset in range(days):
            day = (start_local + timedelta(days=offset)).date().isoformat()
            buckets[day] = {
                "date": day,
                "analyses": set(),
                "plates": 0,
                "passed": 0,
                "review": 0,
                "recovered": 0,
            }
        for row in rows:
            local = to_local(row["created_at"])
            if local is None:
                continue
            key = local.date().isoformat()
            if key not in buckets:
                continue
            bucket = buckets[key]
            if row["analysis_id"] is not None:
                bucket["analyses"].add(row["analysis_id"])
            if row["review_status"] is None:
                continue
            bucket["plates"] += 1
            if row["review_status"] == "candidate_passed_validation_gate":
                bucket["passed"] += 1
            else:
                bucket["review"] += 1
            if row["recovery_outcome"] == "recovered":
                bucket["recovered"] += 1
        output = []
        for day in sorted(buckets):
            bucket = buckets[day]
            local_date = datetime.fromisoformat(day)
            output.append(
                {
                    "date": day,
                    "label": local_date.strftime("%d %b"),
                    "analyses": len(bucket["analyses"]),
                    "plates": bucket["plates"],
                    "passed": bucket["passed"],
                    "review": bucket["review"],
                    "recovered": bucket["recovered"],
                }
            )
        return output

    def failure_breakdown(self, days: int = 30, include_demo: bool = True) -> list[dict]:
        since = day_start_utc(max(1, days) - 1)
        demo_clause = "" if include_demo else " AND a.source != 'demo'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.retry_reasons, p.quality_flags
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.created_at >= ?{demo_clause}
                """,
                [since],
            ).fetchall()
            no_plate = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM analyses a WHERE a.plate_count = 0 AND a.created_at >= ?{demo_clause}",
                    [since],
                ).fetchone()[0]
            )
        counts: Counter[str] = Counter()
        for row in rows:
            reasons = _json_load(row["retry_reasons"], []) + _json_load(row["quality_flags"], [])
            labels = {
                failure_label(str(reason))
                for reason in reasons
                if failure_label(str(reason)).lower() != "none detected"
            }
            for label in labels:
                counts[label] += 1
        if no_plate:
            counts["No plate detected"] += no_plate
        total = sum(counts.values())
        return [
            {"reason": label, "count": count, "share": round(count / total, 4) if total else 0.0}
            for label, count in counts.most_common(8)
        ]

    def recovery_breakdown(self, days: int = 30, include_demo: bool = True) -> list[dict]:
        since = day_start_utc(max(1, days) - 1)
        demo_clause = "" if include_demo else " AND a.source != 'demo'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.recovery_outcome, COUNT(*) AS count
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.created_at >= ?{demo_clause}
                 GROUP BY p.recovery_outcome
                """,
                [since],
            ).fetchall()
        labels = {
            "not_attempted": "No retry needed",
            "recovered": "Recovered",
            "unchanged": "Unchanged after retry",
            "changed": "Changed, low margin",
            "degraded": "Degraded",
            "no_reading": "Still unreadable",
        }
        order = ["recovered", "unchanged", "changed", "degraded", "no_reading", "not_attempted"]
        found = {row["recovery_outcome"]: int(row["count"]) for row in rows}
        total = sum(found.values())
        return [
            {
                "outcome": key,
                "label": labels[key],
                "count": found.get(key, 0),
                "share": round(found.get(key, 0) / total, 4) if total else 0.0,
            }
            for key in order
            if found.get(key, 0) or key in {"recovered", "not_attempted"}
        ]

    def method_breakdown(self, days: int = 30, include_demo: bool = True) -> list[dict]:
        since = day_start_utc(max(1, days) - 1)
        demo_clause = "" if include_demo else " AND a.source != 'demo'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.selected_method, COUNT(*) AS count
                  FROM plates p JOIN analyses a ON a.id = p.analysis_id
                 WHERE p.created_at >= ?{demo_clause}
                 GROUP BY p.selected_method ORDER BY count DESC
                """,
                [since],
            ).fetchall()
        total = sum(int(row["count"]) for row in rows)
        return [
            {
                "method": row["selected_method"] or "unknown",
                "count": int(row["count"]),
                "share": round(int(row["count"]) / total, 4) if total else 0.0,
            }
            for row in rows
        ]

    def export_csv(self, days: int = 30, include_demo: bool = True) -> str:
        plates = self.list_plates(days=days, limit=100, include_demo=include_demo)
        # list_plates caps at 100; export in chunks
        rows: list[dict] = list(plates["items"])
        offset = len(rows)
        while plates["has_more"]:
            plates = self.list_plates(days=days, limit=100, offset=offset, include_demo=include_demo)
            rows.extend(plates["items"])
            offset += len(plates["items"])
            if not plates["items"]:
                break
        buffer = io.StringIO()
        columns = [
            "id", "created_at", "filename", "source", "ocr_text", "verified_text",
            "verification_status", "review_status", "recovery_outcome",
            "detector_confidence", "ocr_score", "original_text", "original_score",
            "common_format", "quality_flags", "retry_attempted", "retry_reasons",
            "selection_reason", "selected_method", "brightness", "contrast",
            "blur_score", "candidates", "observations", "ground_truth",
        ]
        writer = csv.writer(buffer)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column) for column in columns])
        return "\ufeff" + buffer.getvalue()

    # ------------------------------------------------------------------
    # Chat sessions
    # ------------------------------------------------------------------
    def create_session(self, title: str | None = None) -> str:
        session_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
                (session_id, now, now, title or "New conversation"),
            )
        return session_id

    def ensure_session(self, session_id: str | None, title: str | None = None) -> str:
        if session_id:
            with self.connect() as conn:
                row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if row:
                return session_id
        return self.create_session(title)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict | None = None,
    ) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, meta, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(meta or {}, ensure_ascii=False), now),
            )
            conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            return int(cursor.lastrowid)

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, meta, created_at
                  FROM chat_messages WHERE session_id = ?
                 ORDER BY id ASC LIMIT ?
                """,
                (session_id, max(1, limit)),
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["meta"] = _json_load(item.get("meta"), {})
            messages.append(item)
        return messages

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------
    def clear_demo(self) -> int:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM analyses WHERE source = 'demo'")
            return cursor.rowcount

    def seed_demo(self, days: int = 21, seed: int = 42) -> int:
        """Insert clearly-labelled demo records so a new dashboard is explorable.

        The rows carry ``source='demo'`` and the UI always shows a demo banner.
        They are never mixed silently into a real evaluation claim.
        """
        rng = random.Random(seed)
        plates = [
            "TS09AB1234", "DL10C0S520", "KA42TC1310", "MH12DE1433", "TN21AT0492",
            "AP39AB1234", "GJ05JK4321", "RJ14CV0001", "UP32KL9087", "WB06A1234",
            "KL11BN7788", "HR26DK8337", "MP09XY2468", "PB10GH1122", "OD02AB9090",
        ]
        reasons = [
            "possible blur", "low light", "low contrast", "low ocr engine score",
            "format check failed", "overexposed", "tilted plate",
        ]
        inserted = 0
        now_local = datetime.now(TIMEZONE)
        for day_offset in range(days - 1, -1, -1):
            for sequence in range(rng.randint(1, 3)):
                stamp = (now_local - timedelta(days=day_offset)).replace(
                    hour=rng.randint(7, 21),
                    minute=rng.randint(0, 59),
                    second=rng.randint(0, 59),
                    microsecond=0,
                )
                created = stamp.astimezone(timezone.utc).isoformat(timespec="seconds")
                filename = f"demo_{stamp:%Y%m%d}_{sequence + 1}.jpg"
                selected = rng.choice(plates)
                roll = rng.random()
                retry = roll < 0.38
                if roll < 0.60:
                    review = "candidate_passed_validation_gate"
                    score = rng.uniform(0.82, 0.99)
                elif roll < 0.88:
                    review = "needs_manual_review"
                    score = rng.uniform(0.30, 0.79)
                else:
                    review = "needs_manual_review"
                    score = 0.0
                chosen_reasons = rng.sample(reasons, k=rng.randint(1, 2)) if retry else []
                quality_reasons = list(chosen_reasons)
                if not quality_reasons and review == "needs_manual_review" and rng.random() < 0.62:
                    quality_reasons = rng.sample(reasons, k=rng.randint(1, 2))
                original = selected
                outcome = "not_attempted"
                if retry:
                    if review == "candidate_passed_validation_gate" and rng.random() < 0.72:
                        original = _corrupt_plate(selected, rng)
                        outcome = "recovered"
                    elif rng.random() < 0.45:
                        original = _corrupt_plate(selected, rng)
                        outcome = "changed"
                    elif rng.random() < 0.25:
                        original = selected
                        outcome = "degraded"
                    else:
                        original = selected
                        outcome = "unchanged"
                # Guarantee a visible recovery cohort in every seeded dashboard.
                if inserted % 6 == 0 and review == "candidate_passed_validation_gate":
                    retry = True
                    original = _corrupt_plate(selected, rng)
                    outcome = "recovered"
                    if not chosen_reasons:
                        chosen_reasons = rng.sample(reasons, k=2)
                        quality_reasons = list(chosen_reasons)
                original_score = round(max(0.0, score - rng.uniform(0.02, 0.25)), 4) if retry else score
                if outcome == "degraded":
                    original_score = round(min(0.99, score + 0.12), 4)
                candidates = [
                    {
                        "text": selected,
                        "score": round(score, 4),
                        "method": rng.choice(
                            ["enhanced + upscaled", "thresholded + upscaled", "upscaled original"]
                        ),
                    }
                ]
                if retry and original != selected:
                    candidates.append(
                        {
                            "text": original,
                            "score": round(max(0.01, score - rng.uniform(0.05, 0.35)), 4),
                            "method": "upscaled original",
                        }
                    )
                result = {
                    "annotated_image": "",
                    "plates": [
                        {
                            "ocr_prediction": selected if review != "needs_manual_review" or score > 0 else "",
                            "original_prediction": original if retry else "",
                            "ocr_engine_score": score,
                            "original_ocr_score": original_score,
                            "detector_confidence": round(rng.uniform(0.55, 0.98), 4),
                            "common_format_match": is_common_format(selected),
                            "review_status": review,
                            "quality_flags": quality_reasons or ["none detected"],
                            "retry_reasons": chosen_reasons,
                            "retry_attempted": retry,
                            "brightness": round(rng.uniform(40, 200), 1),
                            "contrast": round(rng.uniform(20, 80), 1),
                            "blur_score": round(rng.uniform(25, 240), 1),
                            "selection_reason": (
                                "selected standard-format alternative: score gain at least 0.25"
                                if outcome == "recovered"
                                else "kept original: alternative score gain below 0.25"
                            ),
                            "selected_method": candidates[0]["method"],
                            "candidates": candidates,
                            "observations": [
                                "Demo record generated by scripts/seed_demo.py.",
                                "OCR engine scores are ranking signals, not probabilities.",
                            ],
                            "crop_preview": "",
                            "enhanced_preview": "",
                        }
                    ],
                }
                saved = self.save_analysis(
                    result,
                    filename,
                    source="demo",
                    processing_ms=round(rng.uniform(380, 1650), 1),
                    width=1280,
                    height=720,
                    notes="Synthetic demo record. Delete with scripts/seed_demo.py --clear.",
                )
                with self.connect() as conn:
                    conn.execute("UPDATE analyses SET created_at = ? WHERE id = ?", (created, saved["analysis_id"]))
                    conn.execute(
                        "UPDATE plates SET created_at = ?, recovery_outcome = ? WHERE analysis_id = ?",
                        (created, outcome, saved["analysis_id"]),
                    )
                    if rng.random() < 0.24:
                        status = "confirmed" if rng.random() < 0.55 else "corrected"
                        verified = selected if status == "confirmed" else _corrupt_plate(selected, rng)
                        conn.execute(
                            "UPDATE plates SET verified_text = ?, verification_status = ?, verified_at = ? WHERE analysis_id = ?",
                            (verified, status, created, saved["analysis_id"]),
                        )
                inserted += 1
        return inserted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _plate_row(self, row: sqlite3.Row) -> dict:
        item = dict(row)
        for field in JSON_FIELDS:
            item[field] = _json_load(item.get(field), [])
        item["ocr_text"] = item.get("ocr_text") or ""
        item["original_text"] = item.get("original_text") or ""
        item["common_format"] = bool(item.get("common_format"))
        item["retry_attempted"] = bool(item.get("retry_attempted"))
        item["ocr_score"] = _safe_float(item.get("ocr_score"))
        item["original_score"] = _safe_float(item.get("original_score"))
        item["detector_confidence"] = _safe_float(item.get("detector_confidence"))
        item["recovery_delta"] = round(item["ocr_score"] - item["original_score"], 4)
        item["display_text"] = item.get("verified_text") or item.get("ocr_text") or "Unreadable"
        item["failure_reasons"] = derive_failure_reasons(item)
        item["is_demo"] = item.get("source") == "demo"
        return item


def _corrupt_plate(text: str, rng: random.Random) -> str:
    if not text:
        return text
    chars = list(text)
    for _ in range(rng.randint(1, 3)):
        index = rng.randrange(len(chars))
        if rng.random() < 0.55:
            chars[index] = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        else:
            chars[index] = ""
    return "".join(chars)
