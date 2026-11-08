#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_deduction_ledger as L  # noqa: E402


def _intersection(cells, applied=0.3, unresolved_pairs=0.0):
    return {"net_quantity": {"applied_deduction_m3": applied, "decisions": cells},
            "overlaps": [{"pair_type": "vertical-vertical",
                          "potential_deduction_volume_m3": unresolved_pairs}],
            "floor": "首层"}


def _cell(rule, area, bbox):
    return {"owner_rule": rule, "area_m2": area, "bbox_mm": bbox,
            "codes": ["KL1(1)", "KZ1"], "pair_types": ["beam-vertical"],
            "deducted_member_ids": ["R0001"]}


def _opening(handles, status, envelope, deduct, thickness, review=False, bbox=None):
    return {"handles": handles, "status": status, "envelope_area_m2": envelope,
            "deduct_area_m2": deduct, "panel_thickness_mm": thickness,
            "panel_id": "P1", "review_required": review,
            "potential_volume_upper_bound_m3": round(envelope * thickness / 1000.0, 4),
            "bbox": bbox or [0.0, 0.0, 1000.0, 1000.0], "evidence": "测试"}


def _opening_book(records):
    return {"records": records, "floor": "首层"}


class NodeLedgerTest(unittest.TestCase):
    def test_node_volumes_sum_to_applied_deduction(self):
        cells = [_cell("vertical-member-retains-cell", 0.6, [0, 0, 1000, 1000]),
                 _cell("deepest-beam-retains-cell", 0.4, [2000, 0, 3000, 1000]),
                 _cell("vertical-ownership-unresolved", 0.2, [4000, 0, 4500, 500])]
        payload = L.build_ledger(_intersection(cells, applied=0.3), _opening_book([]),
                                 [], {}, {})
        rows = payload["rows"]
        self.assertAlmostEqual(sum(row["deduction_volume_m3"] for row in rows), 0.3, places=4)
        unresolved = [row for row in rows if row["rule"] == "node-ownership-unresolved"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["deduction_volume_m3"], 0.0)
        self.assertTrue(unresolved[0]["review_required"])

    def test_unresolved_vertical_keeps_gate_warn(self):
        cells = [_cell("vertical-ownership-unresolved", 0.2, [0, 0, 500, 400])]
        payload = L.build_ledger(_intersection(cells, applied=0.0, unresolved_pairs=0.099),
                                 _opening_book([]), [], {}, {})
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-ownership-single-rule"], "warn")
        self.assertEqual(payload["summary"]["node_ownership_unresolved_m3"], 0.099)


class ApertureLedgerTest(unittest.TestCase):
    def test_verdict_rules_are_mutually_exclusive(self):
        records = [
            _opening(["1A"], "rectangle-x", 1.5, 1.5, 130.0),
            _opening(["2A", "2B"], "panel-diagonal-chain", 3.61, 0.0, 130.0, review=True),
            _opening(["3A"], "open-chain", 5.25, 0.0, 130.0, review=True),
            _opening(["4A"], "standalone-line", 17.75, 0.0, 120.0, review=True),
            _opening(["5A"], "annotation-leader", 0.3, 0.0, 130.0),
        ]
        verdicts = [
            {"handles": ["2A", "2B"], "verdict": "opening", "applied_in_sheet": True},
            {"handles": ["3A"], "verdict": "opening", "applied_in_sheet": True},
            {"handles": ["4A"], "verdict": "not-opening", "applied_in_sheet": False},
        ]
        sheet = {"rows": [{"treatment": "deduction", "volume_m3": -1.1518}]}
        payload = L.build_ledger(_intersection([], applied=0.0), _opening_book(records),
                                 verdicts, sheet, {})
        rules = {row["rule"] for row in payload["rows"]}
        self.assertEqual(payload["summary"]["aperture_review_pending_count"], 0)
        self.assertEqual(payload["summary"]["aperture_unjudged_count"], 0)
        self.assertIn("aperture-cad-confirmed", rules)
        self.assertIn("aperture-explained-not-opening", rules)
        self.assertAlmostEqual(payload["summary"]["aperture_cad_confirmed_m3"], 0.195, places=4)
        self.assertAlmostEqual(payload["summary"]["aperture_user_confirmed_m3"],
                               0.4693 + 0.6825, places=4)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-aperture-verdict-closed"], "pass")
        self.assertEqual(gates["deduction-applied-once-across-books"], "pass")

    def test_missing_verdict_stays_review_and_blocks_closure(self):
        records = [_opening(["9A"], "open-chain", 5.0, 0.0, 130.0, review=True)]
        payload = L.build_ledger(_intersection([], applied=0.0), _opening_book(records),
                                 [], {}, {})
        self.assertEqual(payload["summary"]["aperture_review_pending_count"], 1)
        self.assertEqual(payload["summary"]["aperture_unjudged_count"], 1)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-aperture-verdict-closed"], "warn")

    def test_sheet_deduction_mismatch_fails(self):
        records = [_opening(["3A"], "open-chain", 5.25, 0.0, 130.0, review=True)]
        verdicts = [{"handles": ["3A"], "verdict": "opening", "applied_in_sheet": True}]
        sheet = {"rows": [{"treatment": "deduction", "volume_m3": -0.5}]}
        payload = L.build_ledger(_intersection([], applied=0.0), _opening_book(records),
                                 verdicts, sheet, {})
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-applied-once-across-books"], "fail")

    def test_cad_confirmed_aperture_not_in_sheet_stays_warn(self):
        records = [_opening(["1A"], "rectangle-x", 1.5, 1.5, 130.0)]
        payload = L.build_ledger(_intersection([], applied=0.0), _opening_book(records),
                                 [], {}, {"remaining_gap_m3": 1.2})
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-slab-opening-attribution-pending"], "warn")
        self.assertAlmostEqual(
            payload["summary"]["cad_confirmed_share_of_gap_ratio"], 0.1625, places=4)


class CrossBookGuardTest(unittest.TestCase):
    def test_aperture_overlapping_node_cell_is_flagged(self):
        cells = [_cell("vertical-member-retains-cell", 1.0, [0, 0, 1000, 1000])]
        records = [_opening(["1A"], "rectangle-x", 1.0, 1.0, 130.0,
                            bbox=[0, 0, 1000, 1000])]
        payload = L.build_ledger(_intersection(cells), _opening_book(records), [], {}, {})
        self.assertEqual(payload["summary"]["cross_book_overlap_pair_count"], 1)
        self.assertEqual(payload["summary"]["cross_book_double_deduct_m3"], 0.13)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-no-cross-book-double-count"], "fail")

    def test_disjoint_aperture_and_node_pass(self):
        cells = [_cell("vertical-member-retains-cell", 1.0, [0, 0, 1000, 1000])]
        records = [_opening(["1A"], "rectangle-x", 1.0, 1.0, 130.0,
                            bbox=[5000, 5000, 6000, 6000])]
        payload = L.build_ledger(_intersection(cells), _opening_book(records), [], {}, {})
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["deduction-no-cross-book-double-count"], "pass")

    def test_ledger_never_claims_formal_quantity(self):
        payload = L.build_ledger(_intersection([]), _opening_book([]), [], {}, {})
        self.assertFalse(payload["formal_ready"])
        self.assertFalse(payload["summary"]["applied_to_formal_quantity"])


if __name__ == "__main__":
    unittest.main()
