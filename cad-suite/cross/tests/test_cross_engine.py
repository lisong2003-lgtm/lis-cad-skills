#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross/engine P0 单元测试（synthetic）。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import CrossEngine, Member, norm_grid  # noqa: E402


def wall(grid, name, attrs=None, bbox=None, source=""):
    return Member("J地块", "8.600", grid, name, "墙", attrs=attrs,
                  bbox=bbox, source=source)


class TestNormGrid(unittest.TestCase):
    def test_case_and_separator(self):
        self.assertEqual(norm_grid("A-C/1-3"), norm_grid("a~c／1~3").upper()
                         if False else norm_grid("a-c/1~3"))
        self.assertEqual(norm_grid("A-C/1-3"), norm_grid("a~c/1~3"))
        self.assertEqual(norm_grid(" 1-3 "), norm_grid("1-3"))
        self.assertEqual(norm_grid(""), "?")


class TestPlaceView(unittest.TestCase):
    def test_missing_key_warns(self):
        e = CrossEngine()
        r = e.compare([wall("A", "Q1")], [wall("B", "Q2")], "建筑", "结构")
        c = r.counts()
        self.assertEqual(c["warn"], 2)  # 两侧各一个缺口
        self.assertEqual(c["conflict"], 0)

    def test_far_same_name_residual(self):
        e = CrossEngine(place_tol=1000)
        a = wall("A", "Q1", bbox=[0, 0, 400, 300], source="建筑图")
        b = wall("A", "Q1", bbox=[90000, 0, 90400, 300], source="结构图")
        r = e.compare([a], [b], "建筑", "结构")
        warns = [it for it in r.items if it["severity"] == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("位置偏差", warns[0]["message"])
        self.assertTrue(warns[0]["residualReason"])

    def test_near_same_name_pass(self):
        e = CrossEngine(place_tol=1000)
        a = wall("A", "Q1", bbox=[0, 0, 400, 300])
        b = wall("A", "Q1", bbox=[100, 100, 500, 400])
        r = e.compare([a], [b], "建筑", "结构")
        passes = [it for it in r.items if it["severity"] == "pass"
                  and it["view"] == "place"]
        self.assertEqual(len(passes), 1)

    def test_no_bbox_downgrades_with_residual(self):
        e = CrossEngine()
        r = e.compare([wall("A", "Q1")], [wall("A", "Q1")], "建筑", "结构")
        it = [x for x in r.items if x["view"] == "place"][0]
        self.assertEqual(it["severity"], "pass")
        self.assertIn("no_evidence", it["residualReason"])


class TestAttrView(unittest.TestCase):
    def test_attr_conflict(self):
        e = CrossEngine()
        a = wall("A", "Q1", attrs={"混凝土标号": "C30"})
        b = wall("A", "Q1", attrs={"混凝土标号": "C35"})
        r = e.compare([a], [b], "建筑", "结构")
        conflicts = [it for it in r.items if it["severity"] == "conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertIn("C30", conflicts[0]["message"])
        self.assertIn("C35", conflicts[0]["message"])

    def test_shared_only(self):
        e = CrossEngine()
        a = wall("A", "Q1", attrs={"厚度": 200, "专用": 1})
        b = wall("A", "Q1", attrs={"厚度": 200, "独有": 2})
        r = e.compare([a], [b], "建筑", "结构")
        self.assertEqual(r.counts()["conflict"], 0)  # 只比共享属性


class TestRelateView(unittest.TestCase):
    def test_dangling_reference(self):
        e = CrossEngine()
        a = wall("A", "Q1")
        r = e.compare([a], [], "建筑", "结构",
                      relations=[{"from": ("J地块", "8.600", "A", "Q1"),
                                  "to": ("J地块", "8.600", "A", "D1"),
                                  "from_source": "建筑图"}])
        warns = [it for it in r.items if it["view"] == "relate"]
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["severity"], "warn")
        self.assertIn("落空", warns[0]["message"])

    def test_closed_reference_pass(self):
        e = CrossEngine()
        a = wall("A", "Q1")
        b = wall("A", "D1")
        r = e.compare([a], [b], "建筑", "结构",
                      relations=[{"from": ("J地块", "8.600", "A", "Q1"),
                                  "to": ("J地块", "8.600", "A", "D1")}])
        rel = [it for it in r.items if it["view"] == "relate"]
        self.assertEqual(rel[0]["severity"], "pass")


class TestOutput(unittest.TestCase):
    def test_to_json_boundary(self):
        e = CrossEngine()
        r = e.compare([], [], "A", "B")
        d = r.to_json()
        self.assertEqual(d["schema"], "cad-cross-compare/v1")
        self.assertFalse(d["final_quantity"])
        self.assertIn("非 BIM 碰撞检测", d["boundary"])

    def test_to_md_orders_conflict_first(self):
        e = CrossEngine()
        a = wall("A", "Q1", attrs={"标号": "C30"})
        b = wall("A", "Q1", attrs={"标号": "C35"})
        r = e.compare([a], [b], "建筑", "结构")
        md = r.to_md()
        lines = md.splitlines()
        idx_conflict = next(i for i, l in enumerate(lines) if "conflict" in l)
        idx_pass = next((i for i, l in enumerate(lines) if "pass" in l), 10**9)
        self.assertLess(idx_conflict, idx_pass)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCompareCli(unittest.TestCase):
    """cross/compare.py CLI 接线：加载器 + 端到端。"""

    def test_load_side_list_form(self):
        import compare as cli
        from pathlib import Path as P
        import tempfile, json as J
        with tempfile.TemporaryDirectory() as td:
            f = P(td) / "side.json"
            f.write_text(J.dumps([{"project": "P", "floor": "1", "grid": "A",
                                   "name": "KL1", "category": "梁"}]),
                         encoding="utf-8")
            src, members, rels = cli.load_side(f)
            self.assertEqual(members[0].name, "KL1")
            self.assertEqual(rels, [])

    def test_load_side_full_form(self):
        import compare as cli
        from pathlib import Path as P
        import tempfile, json as J
        payload = {"source": "结构", "members": [{"project": "P", "floor": "1",
                    "grid": "A-C/1-3", "name": "KL1", "category": "梁",
                    "attrs": {"截面": "300x600"}, "bbox": [0, 0, 1, 1]}],
                   "relations": [{"from": ["P", "1", "A", "KL1"],
                                  "to": ["P", "1", "A", "洞1"]}]}
        with tempfile.TemporaryDirectory() as td:
            f = P(td) / "side.json"
            f.write_text(J.dumps(payload, ensure_ascii=False), encoding="utf-8")
            src, members, rels = cli.load_side(f)
            self.assertEqual(src, "结构")
            self.assertEqual(members[0].attrs["截面"], "300x600")
            self.assertEqual(len(rels), 1)


class TestAdapt(unittest.TestCase):
    """cross/adapt.py 识图产物 → 清单。"""

    def _adapt(self):
        import adapt as ad
        data = {
            "source_file": "demo.dwg",
            "grids": [{"type": "axis", "value": "1轴", "x": 0.0, "y": 0.0, "sheet": 1},
                      {"type": "axis", "value": "A轴", "x": 0.0, "y": 60000.0, "sheet": 1}],
            "members": [
                {"name": "KL1", "category": "steel_beam", "system": "steel_structure",
                 "x": 3000.0, "y": 2000.0, "sheet": 1},
                {"name": "GZ1", "category": "steel_column", "x": 70000.0, "y": 61000.0,
                 "sheet": 1},
            ],
            "components": [
                {"raw": "DN300", "category": "pipe", "system": "water_supply",
                 "x": 1000.0, "y": 1000.0, "sheet": 1, "pipe_size": "DN300"},
            ],
        }
        return ad, ad.adapt(data, project="演示项目")

    def test_axis_and_bucket_and_attrs(self):
        ad, cl = self._adapt()
        self.assertEqual(cl["source"], "演示项目")
        m = {x["name"]: x for x in cl["members"]}
        self.assertEqual(m["KL1"]["grid"], "1轴")          # 近轴号
        self.assertEqual(m["GZ1"]["grid"], "pos:x1y1")     # 远轴号→坐标桶
        self.assertEqual(m["DN300"]["attrs"]["管径"], "DN300")
        self.assertEqual(m["DN300"]["attrs"]["系统"], "water_supply")

    def test_member_types_filter(self):
        ad, _ = self._adapt()
        cl2 = ad.adapt({"source_file": "d", "members": [{"name": "KL1", "x": 0, "y": 0}]},
                       member_types=["members"])
        self.assertEqual([x["name"] for x in cl2["members"]], ["KL1"])
