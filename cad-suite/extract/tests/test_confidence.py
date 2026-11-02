#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/confidence 单元测试。"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import confidence as C
import normalize as N


def cand(text, kind="梁", conf=0.95, reasons=None, status="candidate"):
    c = {"kind": kind, "text": text, "confidence": conf, "status": status, "unit": "个"}
    if reasons:
        c["review_reasons"] = reasons
    return c


def write_contract(path, candidates):
    Path(path).write_text(json.dumps(
        {"contract": {"schema": "cad-file-reader/v0",
                      "candidates": candidates, "review_candidates": []}},
        ensure_ascii=False), encoding="utf-8")


class TestBaseline(unittest.TestCase):
    def test_ratio_and_review_list(self):
        rows = {
            "a.json": N.load_candidates({"contract": {"candidates": [
                cand("KL1", conf=0.95), cand("L1", conf=0.6),
                cand("KL9", conf=0.99, reasons=["missing_scale"])]}}),
            "b.json": N.load_candidates({"contract": {"candidates": [
                cand("KL2", conf=0.9)]}}),
        }
        out = C.baseline(rows)
        self.assertEqual(out["总量"], 4)
        self.assertAlmostEqual(out["三档占比"]["confirmed"], 0.5)
        self.assertAlmostEqual(out["三档占比"]["inferred"], 0.25)
        self.assertAlmostEqual(out["三档占比"]["review"], 0.25)
        self.assertEqual(len(out["review_清单"]), 1)
        self.assertEqual(out["review_清单"][0]["文件"], "a.json")
        self.assertIn("missing_scale", out["review_清单"][0]["复核原因"])

    def test_per_file(self):
        rows = {
            "a.json": N.load_candidates({"contract": {"candidates": [cand("x", conf=0.95)]}}),
            "b.json": N.load_candidates({"contract": {"candidates": [cand("y", conf=0.4)]}}),
        }
        out = C.baseline(rows)
        self.assertEqual(out["分文件"]["a.json"]["候选行数"], 1)
        self.assertAlmostEqual(out["分文件"]["b.json"]["三档占比"]["inferred"], 1.0)

    def test_diff(self):
        new = {"三档占比": {"confirmed": 0.8, "inferred": 0.1, "review": 0.1}}
        old = {"三档占比": {"confirmed": 0.7, "inferred": 0.1, "review": 0.2}}
        d = C.diff(new, old)
        self.assertAlmostEqual(d["confirmed"], 0.1)
        self.assertAlmostEqual(d["review"], -0.1)

    def test_empty_safe(self):
        out = C.baseline({"a.json": []})
        self.assertEqual(out["总量"], 0)
        self.assertEqual(out["三档占比"]["confirmed"], 0.0)


class TestBuildEndToEnd(unittest.TestCase):
    def test_build_and_diff(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = Path(td) / "one.json"
            write_contract(f1, [cand("KL1", conf=0.95),
                                cand("KL9", conf=0.99, reasons=["missing_scale"])])
            base = C.build([str(f1)], str(Path(td) / "基线"))
            for ext in ("json", "md"):
                self.assertTrue(Path(str(base) + "." + ext).exists())
            self.assertTrue(Path(str(base) + "_复核清单.csv").exists())
            # 第二轮：review 减少 → diff 为负
            f2 = Path(td) / "two.json"
            write_contract(f2, [cand("KL1", conf=0.95)])
            b2 = C.build([str(f2)], str(Path(td) / "基线2"),
                         baseline_path=str(base) + ".json")
            data = json.loads(Path(str(b2) + ".json").read_text(encoding="utf-8"))
            self.assertLess(data["对比上次基线"]["review"], 0)

    def test_empty_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                C.build([""], str(Path(td) / "x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
