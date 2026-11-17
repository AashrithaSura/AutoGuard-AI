"""Service-layer tests that run with the standard library only.

Run with:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.anpr.assistant import Assistant
from src.anpr.db import Database, derive_recovery_outcome
from src.anpr.rag import KnowledgeBase

TEST_ROOT = Path(__file__).resolve().parents[1] / "_test_tmp"


def tearDownModule():
    try:
        TEST_ROOT.rmdir()
    except OSError:
        pass


def sample_plate(**overrides):
    plate = {
        "ocr_prediction": "TS09AB1234",
        "original_prediction": "TS09AB12?4",
        "ocr_engine_score": 0.91,
        "original_ocr_score": 0.42,
        "detector_confidence": 0.88,
        "common_format_match": True,
        "review_status": "candidate_passed_validation_gate",
        "quality_flags": ["possible blur", "low contrast"],
        "retry_reasons": ["possible blur", "low contrast", "low OCR engine score"],
        "retry_attempted": True,
        "brightness": 74.0,
        "contrast": 31.0,
        "blur_score": 41.0,
        "selection_reason": "selected standard-format alternative: score gain at least 0.25",
        "selected_method": "enhanced + upscaled",
        "candidates": [
            {"text": "TS09AB12?4", "score": 0.42, "method": "upscaled original"},
            {"text": "TS09AB1234", "score": 0.91, "method": "enhanced + upscaled"},
        ],
        "observations": ["Recovery retry triggered by: possible blur, low contrast."],
        "crop_preview": "",
        "enhanced_preview": "",
    }
    plate.update(overrides)
    return plate


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TEST_ROOT / uuid.uuid4().hex
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.tmp / "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_summary_and_recovery(self):
        saved = self.db.save_analysis(
            {"plates": [sample_plate()]},
            "car.jpg",
            width=100,
            height=80,
            processing_ms=900,
        )
        self.assertEqual(saved["analysis_id"], 1)
        self.assertEqual(len(saved["plate_ids"]), 1)
        summary = self.db.summary(days=30)
        self.assertEqual(summary["total_plates"], 1)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["retries"], 1)
        self.assertEqual(summary["recovered"], 1)
        self.assertEqual(summary["avg_processing_ms"], 900)
        plate = self.db.get_plate(saved["plate_ids"][0])
        self.assertEqual(plate["ocr_text"], "TS09AB1234")
        self.assertEqual(plate["recovery_outcome"], "recovered")
        self.assertEqual(plate["selected_method"], "enhanced + upscaled")
        self.assertEqual(plate["failure_reasons"], ["possible blur", "low contrast", "low ocr engine score"])

    def test_review_queue_and_verification(self):
        saved = self.db.save_analysis(
            {"plates": [sample_plate(
                ocr_prediction="TS09AB12",
                review_status="needs_manual_review",
                ocr_engine_score=0.55,
            )]},
            "blurry.jpg",
        )
        plate_id = saved["plate_ids"][0]
        queue = self.db.list_plates(status="review")
        self.assertEqual(queue["total"], 1)
        updated = self.db.verify_plate(plate_id, "ts09ab1234", "corrected")
        self.assertEqual(updated["verified_text"], "TS09AB1234")
        self.assertEqual(updated["verification_status"], "corrected")
        self.assertEqual(self.db.summary()["corrected"], 1)
        self.assertEqual(self.db.list_plates(status="corrected")["total"], 1)
        self.assertEqual(self.db.list_plates(status="review")["total"], 0)
        self.assertEqual(self.db.list_plates(status="recovered")["total"], 1)
        self.assertEqual(self.db.summary()["review"], 0)
        self.db.verify_plate(plate_id, "", "rejected")
        self.assertEqual(self.db.list_plates(status="review")["total"], 0)
        self.assertEqual(self.db.list_plates(status="corrected")["total"], 0)

    def test_confirm_is_recovered_and_delete_removes(self):
        saved = self.db.save_analysis(
            {"plates": [sample_plate(
                ocr_prediction="KA01AB1234",
                review_status="needs_manual_review",
                ocr_engine_score=0.62,
            )]},
            "confirm.jpg",
        )
        plate_id = saved["plate_ids"][0]
        updated = self.db.verify_plate(plate_id, "KA01AB1234", "confirmed")
        self.assertEqual(updated["verification_status"], "confirmed")
        recovered = self.db.list_plates(status="recovered")
        self.assertEqual(recovered["total"], 1)
        self.assertEqual(recovered["items"][0]["id"], plate_id)
        self.assertTrue(self.db.delete_plate(plate_id))
        self.assertIsNone(self.db.get_plate(plate_id))
        self.assertEqual(self.db.list_plates(status="all")["total"], 0)
        self.assertFalse(self.db.delete_plate(plate_id))

    def test_low_confidence_filter(self):
        self.db.save_analysis({"plates": [sample_plate(ocr_engine_score=0.71)]}, "low.jpg")
        self.db.save_analysis({"plates": [sample_plate(ocr_engine_score=0.93)]}, "high.jpg")
        self.assertEqual(self.db.list_plates(status="low_confidence")["total"], 1)

    def test_demo_is_labelled_and_clearable(self):
        count = self.db.seed_demo(days=4)
        self.assertGreater(count, 0)
        summary = self.db.summary(days=30)
        self.assertEqual(summary["demo_analyses"], count)
        self.assertEqual(summary["upload_analyses"], 0)
        self.assertIn("demo", self.db.list_plates(limit=1)["items"][0]["filename"])
        self.assertEqual(self.db.clear_demo(), count)
        self.assertEqual(self.db.summary(days=30)["total_plates"], 0)

    def test_export_csv(self):
        self.db.save_analysis({"plates": [sample_plate()]}, "car.jpg")
        csv_text = self.db.export_csv(days=30)
        self.assertTrue(csv_text.startswith("\ufeffid,"))
        self.assertIn("TS09AB1234", csv_text)


class RecoveryOutcomeTests(unittest.TestCase):
    def test_labels(self):
        base = {"retry_attempted": True, "original_prediction": "TS09AB12?4", "ocr_prediction": "TS09AB1234",
                "original_ocr_score": 0.4, "ocr_engine_score": 0.9}
        self.assertEqual(derive_recovery_outcome(base), "recovered")
        self.assertEqual(derive_recovery_outcome({**base, "retry_attempted": False}), "not_attempted")
        self.assertEqual(derive_recovery_outcome({**base, "ocr_prediction": "TS09AB12?4"}), "unchanged")
        self.assertEqual(derive_recovery_outcome({**base, "ocr_prediction": "", "ocr_engine_score": 0}), "no_reading")


class KnowledgeTests(unittest.TestCase):
    def test_retrieval_finds_blur_document(self):
        kb = KnowledgeBase().load()
        results = kb.search("what causes motion blur and can sharpening fix it", k=3)
        self.assertTrue(results)
        self.assertTrue(any("Failure taxonomy" in item.title or "Preprocessing" in item.title for item in results))

    def test_retrieval_finds_gate_document(self):
        kb = KnowledgeBase().load()
        results = kb.search("review gate score threshold selective accuracy", k=3)
        self.assertTrue(results)
        self.assertTrue(any("gate" in item.section.lower() or "Metrics" in item.title for item in results))

    def test_section_text_returns_more_than_the_snippet(self):
        kb = KnowledgeBase().load()
        top = kb.search("LLM mode grounded context ollama", k=1)[0]
        self.assertIn("LLM mode", top.section)
        self.assertGreater(len(kb.section_text(top.doc, top.section)), len(top.snippet))


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TEST_ROOT / uuid.uuid4().hex
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.tmp / "test.db")
        self.db.seed_demo(days=10)
        self.assistant = Assistant(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stats_grounded_in_database(self):
        summary = self.db.summary(days=30)
        answer = self.assistant.chat("How many vehicles were analysed this month?")
        self.assertEqual(answer["intent"], "stats")
        self.assertIn(f"{summary['total_plates']:,}", answer["reply"])
        self.assertEqual(answer["mode"], "local")

    def test_review_queue_returns_plate_cards(self):
        answer = self.assistant.chat("Show me the plates that need manual review.")
        self.assertEqual(answer["intent"], "review")
        self.assertTrue(answer["plates"])
        self.assertTrue(all("id" in item for item in answer["plates"]))

    def test_why_failure_uses_stored_signals(self):
        queue = self.db.list_plates(status="review", limit=1)
        self.assertTrue(queue["items"])
        target = queue["items"][0]
        answer = self.assistant.chat(f"Why did plate {target['id']} fail?")
        self.assertEqual(answer["intent"], "why_fail")
        self.assertIn(str(target["id"]), answer["reply"])
        self.assertTrue(answer["citations"])

    def test_recovered_list_intent(self):
        answer = self.assistant.chat("Show me all successfully recovered number plates.")
        self.assertEqual(answer["intent"], "recovered")

    def test_llm_mode_question_explains_grounding(self):
        answer = self.assistant.chat("what is LLM?")
        self.assertEqual(answer["intent"], "llm_mode")
        self.assertIn("grounded", answer["reply"].lower())
        self.assertIn("no model is attached", answer["reply"].lower())
        self.assertTrue(answer["citations"])

    def test_general_answer_quotes_full_sections(self):
        answer = self.assistant.chat("tell me about plate localisation")
        self.assertEqual(answer["intent"], "general")
        self.assertNotIn("• **", answer["reply"])
        self.assertIn("**Five modules**", answer["reply"])
        self.assertTrue(answer["citations"])

    def test_privacy_answer(self):
        answer = self.assistant.chat("What happens to my uploaded image?")
        self.assertEqual(answer["intent"], "privacy")
        self.assertIn("memory", answer["reply"].lower())

    def test_session_history_is_persisted(self):
        first = self.assistant.chat("hello")
        second = self.assistant.chat("How many vehicles were analysed today?", first["session_id"])
        self.assertEqual(first["session_id"], second["session_id"])
        messages = self.db.get_messages(first["session_id"])
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
