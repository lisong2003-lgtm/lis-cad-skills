#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/normalize 单元测试。"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import normalize as N


def cand(text, kind="梁", conf=0.95, status="candidate", value=None,
         unit="个", reasons=None, section=None):
    c = {"kind": kind, "text": text, "confidence": conf, "status": status,
         "unit": unit}
    if value is not None:
        c["value"] = value
    if reasons:
        c["review_reasons"] = reasons
    if section:
        c["section"] = section
    return c


def contract(candidates=None, review=None):
    return {"contract": {"schema": "cad-file-reader/v0",
                         "candidates": candidates or [],
                         "review_candidates": review or []}}


class TestTier(unittest.TestCase):
    def test_confirmed(self):
        self.assertEqual(N.tier_of(cand("KL1", conf=0.95)), "confirmed")

    def test_inferred(self):
        self.assertEqual(N.tier_of(cand("KL2", conf=0.6)), "inferred")

    def test_review_by_reasons(self):
        r = cand("KL3", conf=0.99, reasons=["missing_scale"])
        self.assertEqual(N.tier_of(r), "review")

    def test_review_by_status(self):
        r = cand("KL4", conf=0.99, status="review")
        self.assertEqual(N.tier_of(r), "review")

    def test_bad_confidence_is_inferred(self):
        self.assertEqual(N.tier_of(cand("KL5", conf=None)), "inferred")


class TestLoadAndAggregate(unittest.TestCase):
    def test_load_flattens_review_tier(self):
        data = contract(
            candidates=[cand("KL1(1) 200x400", conf=0.95),
                        cand("L2(1)", conf=0.5)],
            review=[cand("KL9 缺比例", conf=0.99, reasons=["missing_scale"])])
        rows = N.load_candidates(data)
        self.assertEqual(len(rows), 3)
        tiers = {r["tier"] for r in rows}
        self.assertEqual(tiers, {"confirmed", "inferred", "review"})

    def test_aggregate_counts(self):
        data = contract(candidates=[
            cand("KL1 200x400", conf=0.95),
            cand("KL1 200x400", conf=0.9),
            cand("KL1 200x400", conf=0.5),
            cand("KL2 250x500", conf=0.9, reasons=["missing_scale"]),
        ])
        out = N.aggregate(N.load_candidates(data))
        by_spec = {r["规格"]: r for r in out["rows"]}
        self.assertEqual(by_spec["KL1 200x400"]["确认次数"], 2)
        self.assertEqual(by_spec["KL1 200x400"]["推断次数"], 1)
        self.assertEqual(by_spec["KL2 250x500"]["复核次数"], 1)
        self.assertIn("missing_scale", by_spec["KL2 250x500"]["复核原因"])

    def test_value_sum_confirmed_only_marks_final_false(self):
        data = contract(candidates=[
            cand("板 B3", value=3.2, conf=0.95),
            cand("板 B3", value=1.1, conf=0.6),
            cand("板 B9", value=9.9, conf=0.99, reasons=["missing_scale"]),
        ])
        out = N.aggregate(N.load_candidates(data))
        by_spec = {r["规格"]: r for r in out["rows"]}
        self.assertAlmostEqual(by_spec["板 B3"]["数量合计"], 4.3)
        self.assertIsNone(by_spec["板 B9"]["数量合计"])  # review 不进合计
        self.assertFalse(out["summary"]["final_quantity"])

    def test_tier_ratio(self):
        data = contract(candidates=[
            cand("a", conf=0.95), cand("b", conf=0.5),
            cand("c", conf=0.99, reasons=["missing_scale"])])
        out = N.aggregate(N.load_candidates(data))
        r = out["summary"]["三档占比"]
        self.assertAlmostEqual(r["confirmed"], 1 / 3, places=2)
        self.assertAlmostEqual(r["inferred"], 1 / 3, places=2)
        self.assertAlmostEqual(r["review"], 1 / 3, places=2)

    def test_empty_ratio(self):
        self.assertEqual(N._tier_ratio([])["confirmed"], 0.0)


class TestBuildEndToEnd(unittest.TestCase):
    def test_build_writes_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps(contract(
                candidates=[cand("KL1 200x400", conf=0.95, value=2)],
                review=[cand("KL9 缺比例", conf=0.99, reasons=["missing_scale"])]),
            ensure_ascii=False), encoding="utf-8")
            prefix = Path(td) / "提取表"
            N.build([str(src)], str(prefix))
            for ext in ("json", "csv", "md"):
                self.assertTrue(Path(str(prefix) + "." + ext).exists(), ext)
            with Path(str(prefix) + ".csv").open(encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            md = Path(str(prefix) + ".md").read_text(encoding="utf-8")
            self.assertIn("final_quantity=false", md)
            self.assertIn("50%", md)  # 1 confirmed + 1 review

    def test_empty_raises(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "c.json"
            src.write_text(json.dumps(contract()), encoding="utf-8")
            with self.assertRaises(SystemExit):
                N.build([str(src)], str(Path(td) / "x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
