#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import cad_concrete_grade as G  # noqa: E402


def _rules():
    return {"floor": "首层", "rows": [
        {"component": "现浇板", "member_group": "slab-cast", "volume_m3": 51.0770,
         "grade": "C30", "source_type": "drawing-table", "treatment": "slab-cast"},
        {"component": "叠合板板缝", "member_group": "seam", "volume_m3": 6.0708,
         "grade": "C30", "source_type": "drawing-table", "treatment": "seam"},
        {"component": "叠合板整厚", "member_group": "composite-whole", "volume_m3": 35.4068,
         "grade": "C30", "source_type": "drawing-table", "treatment": "composite-whole"},
        {"component": "预制底板（子层）", "member_group": "prefab-sublayer",
         "volume_m3": 21.4132, "grade": "未定", "source_type": "unknown",
         "treatment": "prefab-sublayer"},
        {"component": "竖向", "member_group": "vertical", "volume_m3": 126.5772,
         "grade": "C40", "source_type": "design-booklet-table", "treatment": "vertical"},
    ]}


SPLIT = {"summary": {"prefab_sublayer_m3": 21.4132,
                     "slab_cast_in_place_caliber_A_m3": 71.1414,
                     "slab_caliber_A_total_m3": 92.5546}}


class PrefabSplitTest(unittest.TestCase):
    def test_without_split_input_gate_fails(self):
        payload = G.build_ledger(_rules(), {}, None)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["prefab-sublayer-dedup-applied"], "fail")
        self.assertAlmostEqual(payload["by_grade"]["C30"], 92.5546, places=4)

    def test_split_moves_prefab_out_of_cast_total(self):
        payload = G.build_ledger(_rules(), {}, None, "cli", SPLIT)
        summary = payload["summary"]
        self.assertAlmostEqual(summary["cast_in_place_total_m3"], 197.7186, places=4)
        self.assertAlmostEqual(summary["composite_cast_layer_m3"], 13.9936, places=4)
        self.assertAlmostEqual(summary["composite_prefab_sublayer_m3"], 21.4132, places=4)
        self.assertAlmostEqual(summary["slab_cast_caliber_m3"], 71.1414, places=4)
        # 行级剔除与拆分剔除是同一笔体积，不得相加
        self.assertAlmostEqual(summary["excluded_sublayer_m3"], 21.4132, places=4)
        self.assertAlmostEqual(summary["prefab_sublayer_split_excluded_m3"], 21.4132, places=4)

    def test_split_keeps_row_value_and_identity(self):
        payload = G.build_ledger(_rules(), {}, None, "cli", SPLIT)
        row = next(r for r in payload["rows"] if r["member_group"] == "composite-whole")
        self.assertAlmostEqual(row["volume_m3"], 35.4068, places=4)
        self.assertAlmostEqual(row["cast_in_place_volume_m3"], 13.9936, places=4)
        self.assertAlmostEqual(row["prefab_sublayer_volume_m3"], 21.4132, places=4)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["grade-ledger-identity"], "pass")
        self.assertEqual(gates["prefab-sublayer-dedup-applied"], "pass")
        self.assertEqual(payload["summary"]["identity_residual_m3"], 0.0)

    def test_bad_split_is_rejected_not_silently_passed(self):
        broken = {"summary": {"prefab_sublayer_m3": 30.0,
                              "slab_cast_in_place_caliber_A_m3": 71.1414}}
        payload = G.build_ledger(_rules(), {}, None, "cli", broken)
        gates = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gates["prefab-sublayer-dedup-applied"], "fail")

if __name__ == "__main__":
    unittest.main()
