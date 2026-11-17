"""Tests for the conservative hybrid OCR rescue policy."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src.anpr.recovery import RESCUE_SCORE_THRESHOLD, build_rescue_pool, read_candidates, rotated_variants, select_with_rescue
from src.anpr.selection import OCRCandidate, choose_candidate


class _RowReader:
    def __init__(self, rows):
        self._rows = rows

    def readtext(self, *_args, **_kwargs):
        return self._rows


def _box(x):
    return [[x, 0], [x + 90, 0], [x + 90, 30], [x, 30]]


class RescuePolicyTests(unittest.TestCase):
    def test_common_high_score_is_trusted(self):
        base = OCRCandidate("TN21AT0492", 0.91, "upscaled original")
        with patch("src.anpr.recovery.read_direct") as direct:
            pool, trusted = build_rescue_pool(None, None, base, [base], None, None)
        self.assertTrue(trusted)
        self.assertEqual(pool, [base])
        direct.assert_not_called()

    def test_low_score_common_is_rescued(self):
        base = OCRCandidate("TN21AT0492", RESCUE_SCORE_THRESHOLD - 0.05, "upscaled original")
        alternate = OCRCandidate("TN21AT0492", 0.90, "direct CRNN")
        with patch("src.anpr.recovery.read_direct", side_effect=[alternate, alternate, alternate]):
            pool, trusted = build_rescue_pool(None, object(), base, [base], object(), object())
        self.assertFalse(trusted)
        self.assertIn("direct CRNN", {candidate.method for candidate in pool})

    def test_rotation_recovers_suffix_first_reading(self):
        candidates = [OCRCandidate("21AT0492TN", 0.88, "upscaled original")]
        variants = rotated_variants(candidates)
        self.assertTrue(any(candidate.text == "TN21AT0492" for candidate in variants))

    def test_rescue_selection_returns_corrected_reading(self):
        base = OCRCandidate("21AT0492TN", 0.88, "upscaled original")
        direct = OCRCandidate("TN21AT0492", 0.90, "direct CRNN")
        with patch("src.anpr.recovery.read_direct", side_effect=[direct, direct, direct]):
            selection = select_with_rescue(None, object(), base, [base], object(), object())
        self.assertTrue(selection.attempted)
        self.assertEqual(selection.selected.text, "TN21AT0492")
        self.assertIn("hybrid rescue", selection.reason)

    def test_rotation_does_not_rewrite_already_common_reading(self):
        candidates = [OCRCandidate("MH12DE1433", 0.95, "upscaled original")]
        self.assertEqual(rotated_variants(candidates), [])

    def test_clean_row_survives_concatenation(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        reader = _RowReader([
            (_box(0), "GC08C0C011410810", 0.08),
            (_box(10), "KA03MX5058", 0.878),
        ])
        candidates = read_candidates(reader, np.zeros((40, 160, 3), dtype=np.uint8), "upscaled original")
        self.assertEqual(candidates[0].text, "GC08C0C011410810KA03MX5058")
        self.assertIn("KA03MX5058", [candidate.text for candidate in candidates])
        selected, _ = choose_candidate(candidates[0], candidates)
        self.assertEqual(selected.text, "KA03MX5058")
        self.assertGreater(selected.score, candidates[0].score)


if __name__ == "__main__":
    unittest.main()
