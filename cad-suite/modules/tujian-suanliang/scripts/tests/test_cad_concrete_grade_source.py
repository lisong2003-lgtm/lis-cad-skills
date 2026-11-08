#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图面等级表提取：表头定位、逐层绑定、合并单元格继承与规则草稿。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import cad_concrete_grade_source as kernel  # noqa: E402

TOL = 60.0


def cell(text, x, y, handle=None, layer="A-TEXT"):
    return {"handle": handle or f"H{abs(hash((text, x, y))) % 100000}",
            "layer": layer, "kind": "TEXT", "x": float(x), "y": float(y),
            "text": text}


STORY_HEADER = [cell("楼层", 0, 1000), cell("标高", 400, 1000),
                cell("层高", 800, 1000), cell("墙、柱、连梁", 1300, 1000),
                cell("梁、板、楼梯", 1900, 1000)]
STORY_ROWS = [
    cell("1", 0, 900), cell("-1.060", 400, 900), cell("3.870", 800, 900),
    cell("C40", 1300, 900), cell("C30", 1900, 900),
    cell("2", 0, 800), cell("2.810", 400, 800), cell("3.600", 800, 800),
    cell("C35", 1300, 800), cell("C30", 1900, 800),
    cell("3", 0, 700), cell("6.410", 400, 700), cell("3.600", 800, 700),
    cell("C30", 1900, 700),
]

MATERIAL_HEADER = [cell("构件部位", 0, 500), cell("混凝土强度", 600, 500)]
MATERIAL_ROWS = [cell("主楼梁、板、楼梯", 0, 400), cell("C30", 600, 400),
                 cell("主楼柱、墙", 0, 300), cell("详主楼层高表", 600, 300),
                 cell("圈梁、构造柱", 0, 200), cell("C25", 600, 200)]

STORY_REGION = {"name": "层高表", "role": "story-height-table",
                "bbox": [-200, 600, 2400, 1100]}
MATERIAL_REGION = {"name": "材料表", "role": "material-table",
                   "bbox": [-200, 100, 1200, 600]}


class GradeSourceTest(unittest.TestCase):
    def _bind(self, records, regions, inherit=True):
        return kernel.build_bindings(records, regions, TOL, inherit)

    def test_story_table_binds_each_floor_column(self):
        table = self._bind(STORY_HEADER + STORY_ROWS, [STORY_REGION])
        self.assertEqual(len(table["headers"]), 1)
        self.assertEqual(table["headers"][0]["columns"],
                         ["beam-slab", "label", "vertical"])
        first = [row for row in table["bindings"] if row["row_label"] == "1"]
        self.assertEqual({row["member_group"]: row["grade"] for row in first},
                         {"vertical": "C40", "beam-slab": "C30"})
        self.assertFalse(any(row["inherited"] for row in first))

    def test_merged_cell_is_inherited_and_flagged(self):
        table = self._bind(STORY_HEADER + STORY_ROWS, [STORY_REGION])
        third = [row for row in table["bindings"] if row["row_label"] == "3"
                 and row["member_group"] == "vertical"]
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0]["grade"], "C35")
        self.assertTrue(third[0]["inherited"])
        # C40/C35 两档中点落在 2 层与 3 层之间，分档被表结构唯一确定
        self.assertTrue(third[0]["interval_confirmed"])
        self.assertFalse(third[0]["needs_review"])
        self.assertEqual(third[0]["inherited_from_row"],
                         max(row["row_index"] for row in table["bindings"]
                             if row["member_group"] == "vertical"
                             and not row["inherited"]))

    def test_boundary_on_a_floor_line_stays_under_review(self):
        """两档中点正好压在某一行的行线上：那一行归谁都说不清，必须复核。"""
        header = [cell("层号", 0, 1400), cell("标高", 300, 1400),
                  cell("墙、柱、连梁", 1300, 1400), cell("梁、板", 1900, 1400)]
        body = [cell("1", 0, 1300), cell("10.000", 300, 1300),
                cell("2", 0, 1100), cell("8.000", 300, 1100),
                cell("3", 0, 900), cell("6.000", 300, 900),
                cell("C40", 1300, 1250), cell("C35", 1300, 950),
                cell("C30", 1900, 1100)]
        region = {"name": "层高表", "role": "story-height-table",
                  "bbox": [-200, 800, 2400, 1500]}
        table = self._bind(header + body, [region])
        vertical = {row["row_label"]: row for row in table["bindings"]
                    if row["member_group"] == "vertical"}
        self.assertFalse(vertical["2"]["interval_confirmed"])
        self.assertTrue(vertical["2"]["needs_review"])
        self.assertTrue(vertical["1"]["interval_confirmed"])
        self.assertFalse(vertical["1"]["needs_review"])
        # 3 层在模糊边界之外，仍按 C35 档确定归属
        self.assertEqual(vertical["3"]["grade"], "C35")

    def test_no_inherit_drops_inferred_rows(self):
        table = self._bind(STORY_HEADER + STORY_ROWS, [STORY_REGION],
                           inherit=False)
        self.assertFalse(any(row["inherited"] for row in table["bindings"]))
        self.assertFalse(any(row["row_label"] == "3" and row["member_group"] == "vertical"
                             for row in table["bindings"]))

    def test_header_cells_never_become_bindings(self):
        story = self._bind(STORY_HEADER + STORY_ROWS, [STORY_REGION])
        material = self._bind(MATERIAL_HEADER + MATERIAL_ROWS, [MATERIAL_REGION])
        for table in (story, material):
            labels = {row["row_label"] for row in table["bindings"]}
            for noise in ("楼层", "标高", "层高", "构件部位", "混凝土强度"):
                self.assertNotIn(noise, labels)

    def test_merged_cell_drawn_at_range_center_splits_by_distance(self):
        """合并格的等级画在格中间：按列带 y 距离归属，跨档边界取最近值。"""
        header = [cell("层号", 0, 1700), cell("标高", 300, 1700),
                  cell("墙、柱、连梁", 1300, 1700), cell("梁、板", 1900, 1700)]
        body = []
        for floor, y in ((1, 1400), (2, 1100), (3, 800), (4, 500), (5, 200)):
            body.append(cell(str(floor), 0, y))
            body.append(cell(str(y / 1000.0), 300, y))
        # 合并格文字落在楼层行之间：锚点行只当证据源，不冒充楼层行
        body += [cell("C40", 1300, 1300), cell("C35", 1300, 600),
                 cell("C30", 1900, 800)]
        region = {"name": "层高表", "role": "story-height-table",
                  "bbox": [-200, 100, 2400, 1800]}
        table = self._bind(header + body, [region])
        vertical = {row["row_label"]: row for row in table["bindings"]
                    if row["member_group"] == "vertical"}
        self.assertEqual({key: row["grade"] for key, row in vertical.items()},
                         {"1": "C40", "2": "C40", "3": "C35", "4": "C35",
                          "5": "C35"})
        self.assertTrue(all(row["inherited"] for row in vertical.values()))
        self.assertTrue(all(row["interval_confirmed"] for row in vertical.values()))
        self.assertFalse(any(row["needs_review"] for row in vertical.values()))
        self.assertEqual(vertical["1"]["band_gap_mm"], 100.0)
        horizontal = {row["row_label"]: row for row in table["bindings"]
                      if row["member_group"] == "beam-slab"}
        self.assertEqual({key: row["grade"] for key, row in horizontal.items()},
                         {key: "C30" for key in ("1", "2", "3", "4", "5")})
        self.assertFalse(horizontal["3"]["inherited"])  # 落在本行的格算直取
        self.assertTrue(horizontal["1"]["inherited"])
        self.assertNotIn("层号", {row["row_label"] for row in table["bindings"]})

    def test_material_table_maps_part_to_member_group(self):
        table = self._bind(MATERIAL_HEADER + MATERIAL_ROWS, [MATERIAL_REGION])
        by_label = {row["row_label"]: row for row in table["bindings"]}
        self.assertEqual(by_label["主楼梁、板、楼梯"]["grade"], "C30")
        self.assertEqual(by_label["主楼梁、板、楼梯"]["member_group"], "beam-slab")
        self.assertEqual(by_label["圈梁、构造柱"]["grade"], "C25")
        self.assertEqual(by_label["圈梁、构造柱"]["member_group"], "secondary")
        self.assertNotIn("主楼柱、墙", by_label)  # "详主楼层高表"无等级值，材料表不继承
        table2 = self._bind(MATERIAL_HEADER + MATERIAL_ROWS, [MATERIAL_REGION])
        self.assertEqual([row for row in table2["bindings"] if row["inherited"]], [])

    def test_rules_draft_keeps_unbound_group_unknown(self):
        table = self._bind(STORY_HEADER + STORY_ROWS, [STORY_REGION])
        draft = kernel.rules_draft(table["bindings"], [
            {"component": "墙柱", "member_group": "vertical", "volume_m3": 120.0},
            {"component": "主梁", "member_group": "beam", "volume_m3": 20.0},
            {"component": "残差", "member_group": "other", "volume_m3": 1.0},
        ], "首层", 141.0)
        rows = {row["component"]: row for row in draft["rows"]}
        self.assertEqual(rows["主梁"]["grade"], "C30")
        self.assertEqual(rows["主梁"]["source_type"], "design-booklet-table")
        self.assertEqual(rows["残差"]["grade"], "未定")
        self.assertTrue(rows["残差"]["needs_review"])
        self.assertEqual(draft["expected_total_m3"], 141.0)
        # 竖向档只有 C40/C35 两档，取需复核最低的那档
        self.assertIn(rows["墙柱"]["grade"], {"C40", "C35"})
        self.assertEqual(sum(row["volume_m3"] for row in draft["rows"]), 141.0)

    def test_grade_token_parsing(self):
        self.assertEqual(kernel.grade_in("C40"), "C40")
        self.assertEqual(kernel.grade_in("混凝土 C 30"), "C30")
        self.assertIsNone(kernel.grade_in("详主楼层高表"))
        self.assertIsNone(kernel.grade_in("GC300"))

    def test_region_parser_rejects_missing_corner(self):
        parsed = kernel.parse_region("name=层高表,x0=0,y0=0,x1=1,y1=1,role=material-table")
        self.assertEqual(parsed["bbox"], [0.0, 0.0, 1.0, 1.0])
        self.assertEqual(parsed["role"], "material-table")
        with self.assertRaises(ValueError):
            kernel.parse_region("name=x,x0=0,y0=0")


if __name__ == "__main__":
    unittest.main()


class GradeSourceGateTest(unittest.TestCase):
    def _summary(self, bindings):
        return {"binding_count": len(bindings), "inherited_count": sum(
            1 for row in bindings if row["inherited"]),
            "needs_review_count": sum(1 for row in bindings
                                      if row["needs_review"])}

    def test_confirmed_inheritance_passes_the_gate(self):
        rows = [{"inherited": True, "interval_confirmed": True,
                 "needs_review": False},
                {"inherited": False, "interval_confirmed": True,
                 "needs_review": False}]
        gates = {row["id"]: row["status"]
                 for row in kernel.build_gates(rows, [{"region": "层高表"}],
                                               self._summary(rows))}
        self.assertEqual(gates["merged-cells-flagged"], "pass")
        self.assertEqual(gates["source-table-located"], "pass")
        self.assertEqual(gates["label-coverage"], "pass")

    def test_unconfirmed_inheritance_without_review_fails(self):
        rows = [{"inherited": True, "interval_confirmed": False,
                 "needs_review": False}]
        gates = {row["id"]: row["status"]
                 for row in kernel.build_gates(rows, [{"region": "层高表"}],
                                               self._summary(rows))}
        self.assertEqual(gates["merged-cells-flagged"], "fail")

    def test_no_header_fails_location_gate(self):
        gates = {row["id"]: row["status"]
                 for row in kernel.build_gates([], [], self._summary([]))}
        self.assertEqual(gates["source-table-located"], "fail")
