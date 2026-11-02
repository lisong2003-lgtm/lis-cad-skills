#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/merge_floor 单元测试。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import merge_floor as M


def scan(members, floor_label=None):
    d = {"members": members}
    if floor_label:
        d["meta"] = {"floor_label": floor_label}
    return d


class TestFloorOf(unittest.TestCase):
    def test_meta_first(self):
        s = scan({}, floor_label="8.600梁板")
        self.assertEqual(M.floor_of(Path("x.json"), s, None), "8.600梁板")

    def test_floor_map_beats_meta(self):
        s = scan({}, floor_label="meta层")
        self.assertEqual(M.floor_of(Path("x.json"), s, {"x.json": "map层"}), "map层")

    def test_filename_elevation(self):
        self.assertEqual(M.floor_of(Path("s5_2.json"), {}, None), "2")
        self.assertEqual(M.floor_of(Path("j5_-0.100.json"), {}, None), "-0.100")

    def test_no_floor_uses_stem(self):
        self.assertEqual(M.floor_of(Path("roof.json"), {}, None), "roof")


class TestMerge(unittest.TestCase):
    def test_same_spec_merges(self):
        out = M.merge({
            "a.json": scan({"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 3}}}),
            "b.json": scan({"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 2}}}),
        }, floor_map={"a.json": "1层", "b.json": "1层"})
        self.assertEqual(len(out["rows"]), 1)
        r = out["rows"][0]
        self.assertEqual(r["状态"], "ok")
        self.assertEqual(r["标注计数"], 5)
        self.assertEqual(r["涉及图数"], 2)

    def test_conflict_detected(self):
        out = M.merge({
            "a.json": scan({"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 1}}}),
            "b.json": scan({"梁": {"KL1(1)": {"sizes": ["200X450"], "count": 1}}}),
        }, floor_map={"a.json": "1层", "b.json": "1层"})
        r = out["rows"][0]
        self.assertEqual(r["状态"], "conflict")
        self.assertIn("200x400", r["规格"])
        self.assertIn("200x450", r["规格"])
        self.assertEqual(out["summary"]["冲突数"], 1)

    def test_floors_separated(self):
        out = M.merge({
            "8.600.json": scan({"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 1}}}),
            "11.500.json": scan({"梁": {"KL1(1)": {"sizes": ["250x500"], "count": 1}}}),
        })
        self.assertEqual(out["summary"]["楼层数"], 2)
        self.assertEqual(out["summary"]["冲突数"], 0)  # 不同楼层不冲突

    def test_no_spec(self):
        out = M.merge({"a.json": scan({"梁": {"L2(1)": {"sizes": [], "count": 1}}})})
        self.assertEqual(out["rows"][0]["状态"], "no_spec")
        self.assertEqual(out["summary"]["无规格数"], 1)

    def test_multi_sizes_takes_first(self):
        out = M.merge({"a.json": scan({"梁": {"KL4(1)": {"sizes": ["200x400", "250x400"],
                                                        "count": 1}}})})
        self.assertEqual(out["rows"][0]["规格"], "200x400")


class TestBuildEndToEnd(unittest.TestCase):
    def test_build_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = Path(td) / "a.json"
            f1.write_text(json.dumps(scan(
                {"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 2}}}), ensure_ascii=False),
                encoding="utf-8")
            f2 = Path(td) / "b.json"
            f2.write_text(json.dumps(scan(
                {"梁": {"KL1(1)": {"sizes": ["200x400"], "count": 1}}}), ensure_ascii=False),
                encoding="utf-8")
            prefix = Path(td) / "项目归并"
            M.build([str(f1), str(f2)], str(prefix),
                    floor_map={"a.json": "1层", "b.json": "1层"})
            for ext in ("json", "csv", "md"):
                self.assertTrue(Path(str(prefix) + "." + ext).exists())
            data = json.loads(Path(str(prefix) + ".json").read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["编号行数"], 1)
            self.assertFalse(data["summary"]["final_quantity"])

    def test_empty_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                M.build([""], str(Path(td) / "x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
