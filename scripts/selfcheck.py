"""Offline self-check for the service layer.

Runs without FastAPI, OpenCV, EasyOCR or PyTorch.  Use it after cloning to
verify the database, analytics, RAG index and assistant before installing the
heavy ML stack.

    python scripts/selfcheck.py
"""
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.anpr.assistant import Assistant  # noqa: E402
from src.anpr.db import Database  # noqa: E402
from src.anpr.rag import KnowledgeBase  # noqa: E402


def main() -> int:
    work = ROOT / "_selfcheck_tmp" / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    try:
        db = Database(work / "check.db")
        seeded = db.seed_demo(days=7)
        summary = db.summary(days=30)
        assert seeded > 0, "demo seed failed"
        assert summary["total_plates"] == seeded, "summary count mismatch"
        assert summary["review"] > 0, "no review queue generated"
        assert summary["recovered"] > 0, "no recovered rows generated"
        plate = db.list_plates(status="review", limit=1)["items"][0]
        verified = db.verify_plate(plate["id"], "TS09AB1234", "corrected")
        assert verified and verified["verification_status"] == "corrected"

        kb = KnowledgeBase().load()
        matches = kb.search("why does motion blur hurt OCR", k=3)
        assert matches, "RAG index returned no matches"

        assistant = Assistant(db)
        stats = assistant.chat("How many vehicles were analysed today?")
        assert stats["intent"] == "stats" and "analyses" in stats["reply"]
        why = assistant.chat(f"Why did plate {plate['id']} fail?")
        assert why["intent"] == "why_fail" and why["citations"]
        print("PASS: database, analytics, verification, RAG and assistant")
        print(f"  demo rows: {seeded}")
        print(f"  review queue: {summary['review']}")
        print(f"  recovered: {summary['recovered']}")
        print(f"  knowledge chunks: {len(kb.chunks)}")
        return 0
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
