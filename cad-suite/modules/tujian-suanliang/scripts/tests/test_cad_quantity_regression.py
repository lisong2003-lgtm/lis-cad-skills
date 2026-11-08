#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归比对守护：量值漂移必须报错，标题变化与容差内浮点不算漂。"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import cad_quantity_regression as regression  # noqa: E402

IGNORE = re.compile(regression.DEFAULT_IGNORE)


def _compare(base, cur, tolerance=1e-6, quantities_only=False):
    return regression.compare(
        regression.flatten(base), regression.flatten(cur),
        tolerance, IGNORE, quantities_only)


class QuantityRegressionTest(unittest.TestCase):
    BASE = {
        "title": "P1 报告",
        "direct_outputs": {"concrete_candidate_total_m3": 273.2436,
                           "beam_count": 90},
        "beam_schedule": [{"code": "KL1", "gross_volume_m3": 1.5}],
    }

    def test_identical_report_passes(self):
        result = _compare(self.BASE, dict(self.BASE))
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["missing_keys"], [])
        self.assertEqual(result["compared_keys"], 4)  # title 被忽略

    def test_title_change_is_ignored(self):
        current = dict(self.BASE, title="P2 报告")
        self.assertEqual(_compare(self.BASE, current)["drift"], [])

    def test_quantity_drift_is_caught(self):
        current = dict(self.BASE, direct_outputs=dict(
            self.BASE["direct_outputs"], concrete_candidate_total_m3=273.25))
        result = _compare(self.BASE, current)
        self.assertEqual(len(result["drift"]), 1)
        self.assertEqual(result["summary"]["quantity_drift_count"], 1)

    def test_float_noise_within_tolerance_is_not_drift(self):
        current = dict(self.BASE, direct_outputs=dict(
            self.BASE["direct_outputs"], concrete_candidate_total_m3=273.24360001))
        self.assertEqual(_compare(self.BASE, current)["drift"], [])

    def test_row_removed_is_reported_as_missing_key(self):
        current = dict(self.BASE, beam_schedule=[])
        result = _compare(self.BASE, current)
        self.assertIn("beam_schedule[0].code", result["missing_keys"])

    def test_quantities_only_skips_text_columns(self):
        current = dict(self.BASE, beam_schedule=[{"code": "KL9",
                                                  "gross_volume_m3": 1.5}])
        wide = _compare(self.BASE, current)
        narrow = _compare(self.BASE, current, quantities_only=True)
        self.assertEqual(len(wide["drift"]), 1)
        self.assertEqual(narrow["drift"], [])


if __name__ == "__main__":
    unittest.main()
