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

import cad_wall_edge_closeout as W  # noqa: E402

OPTIONS = {"attach_tolerance_mm": 250.0, "closure_tolerance_m2": 0.001}


def _rect(x_lo, x_hi, y_lo, y_hi):
    """墙带矩形按 model_bbox_mm 的真实存法：[x_min, x_max, y_min, y_max]。"""
    return {"id": f"WR{x_lo}", "model_bbox_mm": [x_lo, x_hi, y_lo, y_hi]}


def _member(mid, x0, x1, y0, y1):
    return {"id": mid, "area_m2": (x1 - x0) * (y1 - y0) / 1_000_000.0,
            "points_mm": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}


def _geometry(rects, members):
    return {"planar_faces": [], "wall_strip_rectangles": rects,
            "edge_member_polygons": members}


def _ledger(outside=0.0, special=None):
    return {"floor": "首层",
            "edge_member_spatial_attribution": {
                "outside_total_m2": outside, "members": []},
            "special_member_localization": special or {}}


class RectLayoutTest(unittest.TestCase):
    def test_strip_rectangle_bbox_component_order_is_respected(self):
        # 墙带在 x[0,1000] y[2000,3000]；构件在 y[1000,2000] 完全在墙外
        rects = [_rect(0.0, 1000.0, 2000.0, 3000.0)]
        members = [_member("EM1", 0.0, 1000.0, 1800.0, 2000.0)]
        payload = W.build_closeout(_geometry(rects, members), _ledger(), dict(OPTIONS))
        row = payload["members"][0]
        self.assertAlmostEqual(row["outside_area_m2"], 0.2, places=4)
        self.assertAlmostEqual(row["wall_region_overlap_m2"], 0.0, places=6)
        # 紧贴墙带下边（距离 0）→ 贴墙端
        self.assertEqual(row["verdict"], W.CELL_ATTACHED)

    def test_far_member_stays_unattributed(self):
        rects = [_rect(0.0, 1000.0, 9000.0, 10000.0)]
        members = [_member("EM1", 0.0, 1000.0, 1800.0, 2000.0)]
        payload = W.build_closeout(_geometry(rects, members), _ledger(), dict(OPTIONS))
        row = payload["members"][0]
        self.assertEqual(row["verdict"], W.CELL_UNATTRIBUTED)
        self.assertTrue(row["unattributed_cells"])
        closure = {gate["id"]: gate["status"] for gate in payload["gates"]}
        self.assertEqual(closure["wall-edge-spatial-closure"], "fail")

    def test_overlap_part_is_not_counted_as_outside(self):
        rects = [_rect(0.0, 2000.0, 0.0, 2000.0)]
        members = [_member("EM1", 1000.0, 3000.0, 0.0, 1000.0)]
        payload = W.build_closeout(_geometry(rects, members), _ledger(), dict(OPTIONS))
        row = payload["members"][0]
        self.assertAlmostEqual(row["wall_region_overlap_m2"], 1.0, places=4)
        self.assertAlmostEqual(row["outside_area_m2"], 1.0, places=4)


class AccountingTest(unittest.TestCase):
    def setUp(self):
        rects = [_rect(0.0, 1000.0, 2000.0, 3000.0),
                 _rect(5000.0, 6000.0, 2000.0, 3000.0)]
        members = [_member("EM1", 0.0, 1000.0, 1800.0, 2000.0),
                   _member("EM2", 5000.0, 6000.0, 1800.0, 2000.0)]
        special = {"TL2": {"volume_status": "reference-only-not-independent-cad-quantity",
                           "reference": {"volume_m3": 0.4118, "axis_length_mm": 9160.0},
                           "cad_evidence": {"traces": [{"handle": "7C84", "length_mm": 5220.0},
                                                       {"handle": "7C85", "length_mm": 5220.0}]},
                           "geometry_axis_length_mm": 9160.0,
                           "basis": "平面轨迹"}}
        self.payload = W.build_closeout(
            _geometry(rects, members), _ledger(outside=0.4, special=special), dict(OPTIONS))

    def test_outside_area_identity_closes(self):
        s = self.payload["summary"]
        self.assertAlmostEqual(s["accounting_residual_m2"], 0.0, places=9)
        self.assertAlmostEqual(
            s["outside_total_m2"],
            s["attached_area_m2"] + s["unattributed_area_m2"], places=9)
        gates = {gate["id"]: gate["status"] for gate in self.payload["gates"]}
        self.assertEqual(gates["wall-edge-accounting-identity"], "pass")
        self.assertEqual(gates["wall-edge-spatial-closure"], "pass")

    def test_special_members_get_bucket_status_without_additive_volume(self):
        rows = self.payload["special_members"]
        self.assertTrue(rows)
        self.assertTrue(all(row["volume_status"]
                            == "counted-in-reference-beam-bucket-not-additive"
                            for row in rows))
        self.assertTrue(all(row["additive_volume_m3"] == 0.0 for row in rows))

    def test_markdown_and_csv_render(self):
        text = W.render_markdown(self.payload)
        self.assertIn("墙身空间闭合与特殊构件定档", text)
        rows = W.csv_rows(self.payload)
        self.assertEqual(len(rows[0]), len(rows[-1]))


class LedgerGateReplacementTest(unittest.TestCase):
    def test_report_gate_uses_closeout_when_present(self):
        import cad_quantity_report as R
        special = {"TL2": {"volume_status": "reference-only-not-independent-cad-quantity",
                           "reference": {"volume_m3": 0.4118},
                           "cad_evidence": {"traces": [{"handle": "7C84", "length_mm": 5220.0}]},
                           "geometry_axis_length_mm": 9160.0,
                           "basis": "平面轨迹"}}
        rects = [_rect(0.0, 1000.0, 2000.0, 3000.0)]
        members = [_member("EM1", 0.0, 1000.0, 1900.0, 2000.0)]
        ledger = _ledger(outside=0.1, special=special)
        closeout = W.build_closeout(_geometry(rects, members), ledger, dict(OPTIONS))
        before = R._special_member_closeout_gate(ledger)
        after = R._special_member_closeout_gate(ledger, closeout)
        self.assertEqual(before["status"], "fail")
        self.assertEqual(after["status"], "pass")
        self.assertIn("贴墙端", after["evidence"])


if __name__ == "__main__":
    unittest.main()
