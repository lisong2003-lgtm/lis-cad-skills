#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_beam_centerline_support as sup  # noqa: E402

OPTIONS = {"axis_slack_mm": 250.0, "face_tolerance_mm": 150.0,
           "width_tolerance_mm": 40.0, "pair_min_overlap_mm": 300.0,
           "default_width_mm": 200.0, "verified_ratio": 0.90,
           "partial_ratio": 0.50, "min_gap_report_mm": 200.0}


def _seg(handle, orientation, axis, lo, hi, layer="S-梁-实线"):
    if orientation == "H":
        start, end = [lo, axis], [hi, axis]
    else:
        start, end = [axis, lo], [axis, hi]
    return {"handle": handle, "layer": layer, "start": start, "end": end,
            "orientation": orientation, "length_mm": hi - lo, "axis_mm": axis,
            "start_mm": lo, "end_mm": hi}


def _instance(rid, code, axis, lo, hi, orientation="H", width=200.0, volume=0.4):
    return {"id": rid, "code": code, "basis": "run", "orientation": orientation,
            "axis_mm": axis, "start_mm": lo, "end_mm": hi, "length_mm": hi - lo,
            "width_mm": width, "volume_m3": volume}


def _model(runs, beams):
    return {"run_registry": {"runs": runs}, "members": {"beams": beams}}


class SupportStatusTest(unittest.TestCase):
    def test_paired_lines_give_verified(self):
        segs = [_seg("A1", "H", 1000.0, 0.0, 5000.0),
                _seg("A2", "H", 1200.0, 0.0, 5000.0)]
        row = sup._support(_instance("R1", "KL1(1)", 1100.0, 0.0, 5000.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.VERIFIED)
        self.assertEqual(row["pair_support_ratio"], 1.0)
        self.assertEqual(sorted(row["support_handles"]), ["A1", "A2"])
        self.assertFalse(row["ledger_excluded"])

    def test_axis_real_but_span_uncovered_is_length_gap(self):
        segs = [_seg("B1", "H", 1000.0, 0.0, 2000.0),
                _seg("B2", "H", 1200.0, 0.0, 2000.0),
                _seg("C1", "H", 1000.0, 6000.0, 9000.0),
                _seg("C2", "H", 1200.0, 6000.0, 9000.0)]
        row = sup._support(_instance("R2", "KL2(1)", 1100.0, 2500.0, 5500.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.LENGTH_GAP)
        self.assertGreater(row["axis_pair_span_count"], 0)
        self.assertEqual(row["pair_supported_length_mm"], 0.0)
        self.assertTrue(row["ledger_excluded"])

    def test_no_line_on_axis_is_phantom_with_nearest_pair(self):
        segs = [_seg("D1", "H", 2000.0, 0.0, 5000.0),
                _seg("D2", "H", 2200.0, 0.0, 5000.0)]
        row = sup._support(_instance("R3", "KL3(1)", 3000.0, 0.0, 5000.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.PHANTOM)
        self.assertEqual(row["nearest_pair_axis_mm"], 2100.0)
        self.assertEqual(row["axis_correction_mm"], -900.0)

    def test_single_face_line_only_is_single_line(self):
        segs = [_seg("E1", "H", 1050.0, 0.0, 5000.0)]
        row = sup._support(_instance("R4", "KL4(1)", 1100.0, 0.0, 5000.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.SINGLE)
        self.assertEqual(row["pair_support_ratio"], 0.0)

    def test_far_line_does_not_count_as_single_support(self):
        segs = [_seg("F1", "H", 1800.0, 0.0, 5000.0)]
        row = sup._support(_instance("R5", "KL5(1)", 1100.0, 0.0, 5000.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.PHANTOM)
        self.assertEqual(row["single_support_ratio"], 0.0)

    def test_partial_coverage_stays_in_ledger(self):
        segs = [_seg("G1", "H", 1000.0, 0.0, 7000.0),
                _seg("G2", "H", 1200.0, 0.0, 7000.0),
                _seg("G3", "H", 1000.0, 9000.0, 10000.0),
                _seg("G4", "H", 1200.0, 9000.0, 10000.0)]
        row = sup._support(_instance("R6", "KL6(1)", 1100.0, 0.0, 10000.0), segs, dict(OPTIONS))
        self.assertEqual(row["centerline_status"], sup.PARTIAL)
        self.assertTrue(row["unsupported_intervals"])
        self.assertFalse(row["ledger_excluded"])


class BuildSupportTest(unittest.TestCase):
    def setUp(self):
        self.segs = [_seg("H1", "H", 1000.0, 0.0, 5000.0),
                     _seg("H2", "H", 1200.0, 0.0, 5000.0)]
        runs = [{"id": "R1", "matched_code": "KL1(1)", "orientation": "H",
                 "axis_mm": 1100.0, "start_mm": 0.0, "end_mm": 5000.0,
                 "paired_width_mm": 200.0, "volume_m3": 0.2}]
        beams = [{"id": "B1", "code": "KL9(1)", "section_b_mm": 200.0,
                  "gross_volume_m3": 0.3,
                  "centerline": {"orientation": "H", "start": [0.0, 3000.0],
                                 "end": [5000.0, 3000.0]}}]
        self.payload = sup.build_support(_model(runs, beams), self.segs, dict(OPTIONS))

    def test_run_basis_verified_and_model_phantom_separated(self):
        summary = self.payload["summary"]
        self.assertEqual(summary["verified_run_ratio"], 1.0)
        self.assertEqual(summary["phantom_run_count"], 0)
        self.assertEqual(summary["phantom_model_count"], 1)
        self.assertEqual(summary["ledger_excluded_run_volume_m3"], 0.0)
        self.assertEqual(summary["ledger_excluded_model_volume_m3"], 0.3)

    def test_gates_report_pass_for_supported_runs(self):
        gates = {row["id"]: row["status"] for row in self.payload["gates"]}
        self.assertEqual(gates["centerline-support-closed"], "pass")
        self.assertFalse(self.payload["applied_to_formal_quantity"])

    def test_options_have_no_cache_leak_and_csv_rows_shape(self):
        self.assertNotIn("_pair_cache", self.payload["options"])
        rows = sup.csv_rows(self.payload)
        self.assertEqual(len(rows[0]), len(rows[-1]))
        self.assertIn("最近实测线对轴mm", rows[0])

    def test_markdown_renders_without_traceback(self):
        text = sup.render_markdown(self.payload)
        self.assertIn("梁实例中心线图面支撑审计", text)
        self.assertIn("centerline-axis-phantom", text)


if __name__ == "__main__":
    unittest.main()
