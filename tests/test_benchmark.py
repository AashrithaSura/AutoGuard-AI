"""Benchmark payload contract tests (no HTTP stack needed)."""
from __future__ import annotations

import unittest

from src.anpr.benchmark import benchmark_summary, wilson_interval, workload


class WilsonTests(unittest.TestCase):
    def test_empty_sample(self):
        self.assertEqual(wilson_interval(0, 0), [0.0, 0.0])

    def test_interval_brackets_estimate(self):
        low, high = wilson_interval(68, 100)
        self.assertLess(low, 0.68)
        self.assertGreater(high, 0.68)
        self.assertAlmostEqual(high - low, 0.18, delta=0.02)

    def test_interval_stays_inside_unit_range(self):
        for successes, total in ((0, 10), (10, 10), (1, 3)):
            low, high = wilson_interval(successes, total)
            self.assertGreaterEqual(low, 0.0)
            self.assertLessEqual(high, 1.0)


class WorkloadTests(unittest.TestCase):
    def test_per_hundred_plates(self):
        data = workload(0.6, 0.9)
        self.assertEqual(data["auto_pass_per_100"], 60.0)
        self.assertEqual(data["review_per_100"], 40.0)
        self.assertEqual(data["residual_errors_per_100"], 6.0)

    def test_full_coverage(self):
        data = workload(1.0, 1.0)
        self.assertEqual(data["review_per_100"], 0.0)
        self.assertEqual(data["residual_errors_per_100"], 0.0)


class BenchmarkSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = benchmark_summary()
        if not cls.data.get("ocr", {}).get("samples"):
            raise unittest.SkipTest("evaluation reports are not present")

    def test_accuracy_carries_interval_and_similarity(self):
        ocr = self.data["ocr"]
        self.assertEqual(len(ocr["exact_match_ci95"]), 2)
        self.assertAlmostEqual(ocr["similarity"], 1 - ocr["cer"], places=4)
        self.assertAlmostEqual(
            ocr["workload"]["auto_pass_per_100"],
            round(100 * ocr["gate_coverage"], 1),
            places=1,
        )
        self.assertGreaterEqual(ocr["workload"]["residual_errors_per_100"], 0)

    def test_external_iurs_reports_workload(self):
        external = self.data["external_iurs"]
        self.assertGreater(external["samples"], 0)
        self.assertEqual(len(external["exact_match_ci95"]), 2)
        self.assertIn("review_per_100", external["workload"])

    def test_composition_totals_are_consistent(self):
        composition = self.data["composition"]
        self.assertGreater(composition["unique_plates"], 0)
        self.assertLessEqual(composition["unique_plates"], composition["samples"])
        self.assertGreater(composition["dominant_plate_crops"], 0)
        self.assertLessEqual(composition["dominant_share_of_test"], 1)

    def test_frame_vote_never_hurts_aggregate(self):
        vote = self.data["frame_vote"]
        plates = vote["all_plates"]
        self.assertGreaterEqual(plates["majority_vote"]["rate"], plates["first_frame"]["rate"])
        self.assertGreaterEqual(plates["any_crop"]["rate"], plates["majority_vote"]["rate"])
        self.assertIn("iurs", vote)


if __name__ == "__main__":
    unittest.main()
