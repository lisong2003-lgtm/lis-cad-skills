#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""待人工确认清单：影响量分档、去重合并和确认动作。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_review_checklist as checklist  # noqa: E402


def sample_report() -> dict:
    return {
        "schema": "cad-quantity-report/v0.22",
        "floor_label": "首层",
        "direct_outputs": {
            "slab_seam_band_volume_m3": 4.2468,
            "slab_opening_review_volume_upper_bound_m3": 6.1994,
            "grade_ledger_needs_review_m3": 0.9548,
            "beam_dedup_missing_instance_volume_m3": 6.6603,
            "beam_dedup_double_count_volume_m3": 9.4174,
            "glodon_prefab_sublayer_double_count_m3": 21.4132,
        },
        "beam_schedule": [
            {"code": "KL1(2)", "quantity_status": "clear-span-review",
             "section": "200x500", "support_count": 2, "gross_volume_m3": 1.2,
             "clear_volume_m3": 1.0, "x": 1.0, "y": 2.0, "source": "h1"},
            {"code": "KL2(1)", "quantity_status": "counted",
             "gross_volume_m3": 5.0, "clear_volume_m3": 4.0},
        ],
        "slab_schedule": [
            {"code": "B1", "net_area_m2": 100.0, "thickness_mm": 130.0,
             "source": "default-note", "opening_status": "review",
             "opening_area_m2": 2.0, "opening_count": 3, "status": "candidate"},
        ],
        "concrete": {"ledger": {
            "special_member_localization": {
                "TL2": {"status": "localized",
                        "volume_status": "reference-only-not-independent-cad-quantity",
                        "reference": {"volume_m3": 0.4118}}},
            "edge_member_spatial_attribution": {
                "status": "component-attributed-not-closed",
                "outside_total_m2": 1.451, "outside_review_tolerance_m2": 0.001,
                "fully_outside_member_count": 14, "edge_member_count": 114}}},
        "anomalies": [{"severity": "warning", "member_type": "beam",
                       "code": "KL1(2)", "message": "支座候选需复核",
                       "area": "model", "status": "model-issue"}],
        "closure_dashboard": {"gates": [
            {"id": "slab-thickness-evidence", "title": "板厚证据链",
             "status": "fail", "evidence": "49% 取自说明默认", "action": "回图"},
            {"id": "identity", "title": "恒等式", "status": "pass",
             "evidence": "0", "action": "-"}]},
    }


class ReviewChecklistTest(unittest.TestCase):
    def setUp(self):
        self.payload = checklist.build_checklist(sample_report())

    def test_rows_merge_by_category_and_item(self):
        keys = [(row["category"], row["item"]) for row in self.payload["rows"]]
        self.assertEqual(len(keys), len(set(keys)))
        beam = [row for row in self.payload["rows"]
                if row["category"] == "beam" and row["item"] == "KL1(2)"]
        self.assertEqual(len(beam), 1)
        self.assertIn("支座", beam[0]["issue"])

    def test_closed_items_are_left_out(self):
        items = {row["item"] for row in self.payload["rows"]}
        self.assertNotIn("KL2(1)", items)
        self.assertNotIn("identity", items)

    def test_risk_and_scope_items_are_not_added_into_total(self):
        summary = self.payload["summary"]
        additive = [row for row in self.payload["rows"] if row["countable"]]
        self.assertEqual(summary["total_impact_m3"],
                         round(sum(row["impact_m3"] for row in additive), 4))
        self.assertGreater(summary["non_additive_m3"], 0.0)
        scope = [row for row in self.payload["rows"]
                 if row["category"] == "prefab-scope"]
        self.assertEqual(scope[0]["countable"], False)

    def test_every_row_names_an_action(self):
        for row in self.payload["rows"]:
            self.assertTrue(row["ask"], row["item"])

    def test_special_member_and_edge_areas_are_listed(self):
        items = {row["item"] for row in self.payload["rows"]}
        self.assertIn("TL2", items)
        self.assertIn("边缘构件合计", items)
        edge = [row for row in self.payload["rows"]
                if row["item"] == "边缘构件合计"][0]
        self.assertIn("1.4510 m2", edge["issue"])


class DeductionLedgerItemsTest(unittest.TestCase):
    def test_ledger_replaces_blanket_opening_upper_bound(self):
        report = {"direct_outputs": {
            "slab_opening_review_volume_upper_bound_m3": 6.1994,
            "deduction_aperture_cad_confirmed_m3": 0.3588,
            "deduction_node_unresolved_m3": 0.099,
        }}
        rows = checklist.collect_open_quantities(report)
        keys = {row["item"] for row in rows}
        self.assertNotIn("slab_opening_review_volume_upper_bound_m3", keys)
        self.assertIn("deduction_aperture_cad_confirmed_m3", keys)
        self.assertIn("deduction_node_unresolved_m3", keys)
        opening = [row for row in rows
                   if row["item"] == "deduction_aperture_cad_confirmed_m3"][0]
        self.assertEqual(opening["category"], "slab-opening")
        self.assertAlmostEqual(opening["impact_m3"], 0.3588, places=4)

    def test_without_ledger_the_upper_bound_still_shows(self):
        report = {"direct_outputs": {
            "slab_opening_review_volume_upper_bound_m3": 6.1994,
        }}
        keys = {row["item"] for row in checklist.collect_open_quantities(report)}
        self.assertIn("slab_opening_review_volume_upper_bound_m3", keys)


if __name__ == "__main__":
    unittest.main()
