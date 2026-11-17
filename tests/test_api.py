"""HTTP contract tests.

These require FastAPI + httpx.  They are skipped on a minimal service-only
install so the core analytics/assistant tests still run everywhere.
"""
from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False

TEST_ROOT = Path(__file__).resolve().parents[1] / "_test_tmp" / "api"
TEST_DB = TEST_ROOT / "api.db"
os.environ.setdefault("AUTOGUARD_DB", str(TEST_DB))


@unittest.skipUnless(HAS_FASTAPI, "FastAPI/httpx are not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        from api import main

        main.DB_PATH = TEST_DB
        main._db = None
        main._assistant = None
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        try:
            TEST_ROOT.parent.rmdir()
        except OSError:
            pass

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("status", body)
        self.assertIn("features", body)

    def test_demo_and_analytics(self):
        seeded = self.client.post("/api/demo/seed", json={"days": 5, "confirm": True})
        self.assertEqual(seeded.status_code, 200)
        self.assertGreater(seeded.json()["seeded"], 0)
        summary = self.client.get("/api/analytics/summary?days=30")
        self.assertEqual(summary.status_code, 200)
        self.assertGreater(summary.json()["total_plates"], 0)
        series = self.client.get("/api/analytics/timeseries?days=7")
        self.assertEqual(len(series.json()["items"]), 7)
        breakdown = self.client.get("/api/analytics/breakdown?days=30")
        self.assertIn("failures", breakdown.json())

    def test_plate_list_verify_and_explain(self):
        listing = self.client.get("/api/plates?status=review&limit=1")
        self.assertEqual(listing.status_code, 200)
        item = listing.json()["items"][0]
        verified = self.client.post(
            f"/api/plates/{item['id']}/verify",
            json={"verified_text": "TS09AB1234", "status": "corrected"},
        )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["verified_text"], "TS09AB1234")
        explained = self.client.get(f"/api/plates/{item['id']}/explain")
        self.assertEqual(explained.status_code, 200)
        self.assertIn("reply", explained.json())

    def test_assistant_chat_and_history(self):
        response = self.client.post("/api/assistant/chat", json={"message": "How many vehicles were analysed today?"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["session_id"])
        self.assertIn("reply", body)
        history = self.client.get(f"/api/assistant/session/{body['session_id']}")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["messages"]), 2)

    def test_upload_validation(self):
        response = self.client.post(
            "/api/analyze",
            files={"image": ("notes.txt", b"not an image", "text/plain")},
        )
        self.assertEqual(response.status_code, 415)

    def test_analytics_export(self):
        response = self.client.get("/api/analytics/export?days=30")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("ocr_text", response.text)

    def test_gate_curve(self):
        response = self.client.get("/api/analytics/gate-curve")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("recommended", body)
        self.assertIn("validation_curve", body)
        self.assertGreaterEqual(len(body["validation_curve"]), 10)

    def test_llm_connect_rejects_remote_host(self):
        response = self.client.post(
            "/api/assistant/llm",
            json={"provider": "ollama", "url": "http://example.com:11434", "model": ""},
        )
        self.assertEqual(response.status_code, 422)

    def test_benchmark_intervals_and_workload(self):
        response = self.client.get("/api/analytics/benchmark")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["ocr"]["exact_match_ci95"]), 2)
        self.assertIn("auto_pass_per_100", body["ocr"]["workload"])
        self.assertIn("unique_plates", body["composition"])
        self.assertIn("all_plates", body["frame_vote"])

    def test_assistant_status_reports_auto_connect(self):
        body = self.client.get("/api/assistant/status").json()
        self.assertIn("auto_connect", body)
        auto = body["auto_connect"]
        self.assertIn("enabled", auto)
        self.assertIn("url", auto)
        self.assertIn("models", auto)
        self.assertIsInstance(auto["models"], list)

    def test_assistant_detect_rejects_remote_host(self):
        response = self.client.get("/api/assistant/detect?url=http://example.com:11434")
        self.assertEqual(response.status_code, 422)

    def test_llm_disconnect_pauses_auto_connect(self):
        response = self.client.post("/api/assistant/llm", json={"provider": "off"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["connected"])
        self.assertFalse(body["auto_connect"]["enabled"])
        status = self.client.get("/api/assistant/status").json()
        self.assertFalse(status["auto_connect"]["enabled"])


if __name__ == "__main__":
    unittest.main()
