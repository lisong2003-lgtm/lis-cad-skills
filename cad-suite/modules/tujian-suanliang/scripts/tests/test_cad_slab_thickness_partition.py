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

import cad_slab_thickness_partition as P  # noqa: E402

NOTE_TEXT = "2、未标注的板厚为130mm，未标注的板受力钢筋均为%%1328@200。"
FILL_140 = "图中        填充部分未标注的板厚为140mm，板配筋为双层双向%%1328@150;"


def _rect(x_lo, y_lo, x_hi, y_hi):
    return [[x_lo, y_lo], [x_hi, y_lo], [x_hi, y_hi], [x_lo, y_hi]]


def _area(points):
    return ((points[2][0] - points[0][0]) * (points[2][1] - points[0][1])) / 1.0e6


def _panel(pid, points, thickness, source, extra=""):
    return {"id": pid, "points": points, "area_m2": _area(points) + _number(extra),
            "thickness_mm": thickness, "thickness_source": source,
            "material_system": "cast-candidate"}


def _number(value):
    return float(value or 0)


def _hatch(hid, handle, rule, points):
    return {"id": hid, "handle": handle, "fill_rule": rule, "points": points,
            "layer": "S-板-降板填充"}


def _text(value, x, y, layer="S-板-板厚"):
    return {"text": value, "model_x": x, "model_y": y, "layer": layer}


def _model(panels, hatches):
    return {"floor": "首层", "members": {"slab_panels": panels},
            "topology": {"hatch_regions": hatches},
            "phase15": {"legend": [
                {"handle": "22223", "semantic": "thickness", "thickness_mm": 140,
                 "source_text": FILL_140}]}}


NOTES = [{"handle": "N1", "text": NOTE_TEXT, "thickness_mm": 130, "x": 0, "y": 0},
         {"handle": "N2", "text": FILL_140, "thickness_mm": 140, "x": 0, "y": 0}]


class PartitionIdentityTest(unittest.TestCase):
    def test_grade_areas_equal_panel_area_for_every_panel(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL),
                  _panel("P2", _rect(6000, 0, 10000, 4000), 130, P.NOTE)]
        hatches = [_hatch("H1", "407569", "140", _rect(6000, 0, 8000, 4000))]
        payload = P.build_partition(_model(panels, hatches), NOTES,
                                    {"panel_texts": [_text("h=130", 2000, 2000)]})
        for row in payload["panels"]:
            self.assertAlmostEqual(row["identity_residual_m2"], 0.0, places=4)
        self.assertAlmostEqual(payload["summary"]["identity_residual_m2"], 0.0, places=4)
        self.assertEqual(payload["summary"]["evidence_coverage_ratio"], 1.0)

    def test_drop_30_fill_never_changes_thickness(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.NOTE)]
        hatches = [_hatch("H1", "407573", "drop-30", _rect(0, 0, 4000, 2000))]
        payload = P.build_partition(_model(panels, hatches), NOTES, {})
        row = payload["panels"][0]
        self.assertAlmostEqual(row["volume_partitioned_m3"], row["volume_as_assigned_m3"],
                               places=6)
        self.assertGreater(row["elevation_only_area_m2"], 0.0)
        self.assertEqual(payload["summary"]["elevation_only_area_m2"], 8.0)


class LabelOwnershipTest(unittest.TestCase):
    def test_label_inside_panel_verifies_the_dimension_label_claim(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL)]
        payload = P.build_partition(_model(panels, []), NOTES,
                                    {"panel_texts": [_text("h=130", 2000, 2000)]})
        self.assertEqual(payload["panels"][0]["label_claim"], "verified")
        self.assertEqual(payload["summary"]["label_claim_unverified_count"], 0)
        self.assertEqual(payload["summary"]["area_by_evidence_m2"]["dimension-label"], 16.0)

    def test_one_label_cannot_back_two_panels(self):
        # 标注落在 P1 内、同时贴着 P2 的边：只给 P1 当证据，P2 降级为说明默认档
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL),
                  _panel("P2", _rect(4000, 0, 8000, 4000), 130, P.LABEL)]
        payload = P.build_partition(_model(panels, []), NOTES,
                                    {"panel_texts": [_text("h=130", 3990, 2000)],
                                     "label_verify_radius_mm": 1000.0})
        rows = {row["id"]: row for row in payload["panels"]}
        self.assertEqual(rows["P1"]["label_claim"], "verified")
        self.assertEqual(rows["P2"]["label_claim"], "unverified")
        self.assertEqual(rows["P2"]["assigned_source"], P.NOTE)
        self.assertEqual(payload["summary"]["label_claim_unverified_count"], 1)
        self.assertEqual(payload["summary"]["label_claim_unverified_area_m2"], 16.0)

    def test_label_of_another_thickness_does_not_verify(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL)]
        payload = P.build_partition(_model(panels, []), NOTES,
                                    {"panel_texts": [_text("h=150", 2000, 2000)]})
        self.assertEqual(payload["panels"][0]["label_claim"], "unverified")

    def test_dimension_layer_numbers_are_not_thickness_labels(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL)]
        payload = P.build_partition(
            _model(panels, []), NOTES,
            {"panel_texts": [_text("1300", 2000, 2000, layer="S-DIM"),
                             _text("C12@130", 2000, 2000, layer="S-板-文字")]})
        self.assertEqual(payload["panels"][0]["label_claim"], "unverified")

    def test_missing_text_ledger_downgrades_to_warn_not_silent_pass(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL)]
        payload = P.build_partition(_model(panels, []), NOTES, {})
        self.assertEqual(payload["panels"][0]["label_claim"], "no-text-ledger")
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["slab-label-claim-ownership"], "warn")


class PriorityTest(unittest.TestCase):
    def test_legend_fill_splits_a_panel_without_a_label(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.NOTE)]
        hatches = [_hatch("H1", "407569", "140", _rect(0, 0, 4000, 2000))]
        payload = P.build_partition(_model(panels, hatches), NOTES, {})
        row = payload["panels"][0]
        self.assertEqual(row["partition_conflict"], True)
        self.assertAlmostEqual(row["volume_partitioned_m3"],
                               8.0 * 140 / 1000.0 + 8.0 * 130 / 1000.0, places=4)

    def test_verified_label_beats_legend_fill(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL)]
        hatches = [_hatch("H1", "407569", "140", _rect(0, 0, 4000, 2000))]
        texts = [_text("h=130", 2000, 2000)]
        label_first = P.build_partition(_model(panels, hatches), NOTES,
                                        {"panel_texts": texts, "label_priority": True})
        fill_first = P.build_partition(_model(panels, hatches), NOTES,
                                       {"panel_texts": texts, "label_priority": False})
        self.assertAlmostEqual(label_first["summary"]["volume_partitioned_total_m3"],
                               16.0 * 130 / 1000.0, places=4)
        self.assertGreater(fill_first["summary"]["volume_partitioned_total_m3"],
                           label_first["summary"]["volume_partitioned_total_m3"])

    def test_gates_all_pass_when_three_evidence_tiers_have_sources(self):
        panels = [_panel("P1", _rect(0, 0, 4000, 4000), 130, P.LABEL),
                  _panel("P2", _rect(6000, 0, 10000, 4000), 130, P.NOTE)]
        hatches = [_hatch("H1", "407569", "140", _rect(6000, 0, 8000, 4000))]
        payload = P.build_partition(_model(panels, hatches), NOTES,
                                    {"panel_texts": [_text("h=130", 2000, 2000)]})
        for row in payload["gates"]:
            self.assertEqual(row["status"], "pass", row["id"])


if __name__ == "__main__":
    unittest.main()
