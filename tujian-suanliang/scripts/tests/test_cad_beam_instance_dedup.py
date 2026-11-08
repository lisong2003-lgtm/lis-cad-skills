#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_beam_instance_dedup as dedup  # noqa: E402

OPTIONS = {"code_axis_tolerance_mm": 5000.0, "geometry_axis_tolerance_mm": 400.0,
           "min_overlap_ratio": 0.5, "length_tolerance_mm": 200.0,
           "gap_tolerance_mm": 400.0, "self_overlap_axis_tolerance_mm": 400.0,
           "conflict_tolerance_m3": 0.05}


def _run(run_id, code, orientation, axis, lo, hi, section="200x500",
         evidence="leader-target"):
    length = hi - lo
    return {"id": run_id, "matched_code": code, "orientation": orientation,
            "axis_mm": axis, "start_mm": lo, "end_mm": hi,
            "length_mm": length, "section": section,
            "volume_m3": round(length * int(section.split("x")[1]) * 200 / 1e9, 4),
            "code_assignment_status": evidence, "confidence": "high"}


def _beam(beam_id, code, orientation, axis, lo, hi, section="200x500"):
    start = [lo, axis] if orientation == "H" else [axis, lo]
    end = [hi, axis] if orientation == "H" else [axis, hi]
    length = hi - lo
    return {"id": beam_id, "code": code, "section": section,
            "gross_volume_m3": round(length * int(section.split("x")[1]) * 200 / 1e9, 4),
            "quantity_status": "clear-span-review",
            "centerline": {"start": start, "end": end,
                           "orientation": orientation, "length_basis": "local"}}


def _model(runs, beams):
    return {"run_registry": {"runs": runs},
            "members": {"beams": beams}}


class DedupTests(unittest.TestCase):
    def test_axis_offset_between_grid_and_edge_axis_still_same_instance(self):
        model = _model([_run("R0001", "KL1(1)", "V", -1448314.5, 760940.5, 767040.5)],
                       [_beam("B0001", "KL1(1)", "V", -1450500.0, 760940.5, 767040.5)])
        result = dedup.build_dedup(model, OPTIONS)
        row = result["links"][0]
        self.assertEqual(row["status"], "same-instance-1to1")
        self.assertEqual(row["run_ids"], ["R0001"])
        self.assertAlmostEqual(row["axis_offset_max_mm"], 2185.5, places=1)
        self.assertAlmostEqual(result["summary"]["double_count_volume_m3"], 0.61,
                               places=4)
        self.assertEqual(result["summary"]["unmatched_run_count"], 0)

    def test_code_absent_beam_is_the_only_net_new_candidate(self):
        model = _model([_run("R0001", "KL8(1)", "H", 758440.5, -1444314.5,
                             -1439414.5, "200x510")],
                       [_beam("B0001", "KL8(1)", "H", 757740.5, -1444314.5,
                              -1439414.5, "200x510"),
                        _beam("B0002", "L5(1)", "V", -1443495.5, 769640.5,
                              773440.5, "200x400")])
        result = dedup.build_dedup(model, OPTIONS)
        summary = result["summary"]
        self.assertEqual(summary["beam_only_class_count"]["code-absent"], 1)
        self.assertEqual(summary["beam_only_codes"], ["L5(1)"])
        self.assertAlmostEqual(summary["model_beam_net_new_volume_m3"], 0.304,
                               places=4)
        self.assertTrue(result["closure"]["gates"]["beam-only-evidence-classified"])

    def test_same_code_elsewhere_is_attribution_conflict_not_addition(self):
        model = _model([_run("R0001", "KL11(1)", "H", 768440.5, -1438964.5,
                             -1435664.5, "200x620")],
                       [_beam("B0001", "KL11(1)", "H", 766500.0, -1443714.5,
                              -1441064.5, "200x620")])
        result = dedup.build_dedup(model, OPTIONS)
        row = result["links"][0]
        self.assertEqual(row["status"], "beam-only")
        self.assertEqual(row["beam_only_class"], "attribution-conflict")
        self.assertEqual(row["unpaired_same_code_run_ids"], ["R0001"])
        self.assertAlmostEqual(
            result["summary"]["model_beam_net_new_volume_m3"], 0.0, places=4)
        self.assertAlmostEqual(
            result["summary"]["beam_only_class_volume_m3"]["attribution-conflict"],
            0.3286, places=4)

    def test_mirror_only_runs_reported_by_evidence_tier(self):
        model = _model([_run("R0001", "KL8(1)", "H", 758440.5, -1444314.5,
                             -1439414.5, "200x510"),
                        _run("R0002", "KL8(1)", "H", 758440.5, -1416274.5,
                             -1411374.5, "200x510", evidence="mirror-label")],
                       [_beam("B0001", "KL8(1)", "H", 757740.5, -1444314.5,
                              -1439414.5, "200x510")])
        result = dedup.build_dedup(model, OPTIONS)
        self.assertEqual(result["summary"]["unmatched_run_count"], 1)
        self.assertEqual(result["unmatched_runs"][0]["id"], "R0002")
        self.assertEqual(result["summary"]["unpaired_run_volume_by_evidence"],
                         {"mirror-label": [1, 0.4998]})
        self.assertIn("KL8(1)", result["summary"]["extra_instance_codes"])
        table = {row["code"]: row for row in result["instance_table"]}
        self.assertEqual(table["KL8(1)"]["instance_delta"], 1)

    def test_multi_run_continuation_covers_one_beam(self):
        model = _model([_run("R0001", "KL5(1)", "H", 768940.5, -1442064.5,
                             -1440014.5, "200x400"),
                        _run("R0002", "KL5(1)", "H", 768940.5, -1440014.5,
                             -1437514.5, "200x400")],
                       [_beam("B0001", "KL5(1)", "H", 768000.0, -1442064.5,
                              -1437514.5, "200x400")])
        result = dedup.build_dedup(model, OPTIONS)
        row = result["links"][0]
        self.assertEqual(row["status"], "same-instance-multi-run")
        self.assertEqual(sorted(row["run_ids"]), ["R0001", "R0002"])
        self.assertAlmostEqual(row["coverage_ratio"], 1.0, places=3)

    def test_orientation_mismatch_never_pairs(self):
        model = _model([_run("R0001", "KL12(2)", "H", 769540.5, -1447414.5,
                             -1443264.5)],
                       [_beam("B0001", "KL12(2)", "V", -1445014.5, 764990.5,
                              773440.5)])
        result = dedup.build_dedup(model, OPTIONS)
        self.assertEqual(result["links"][0]["status"], "beam-only")
        self.assertEqual(result["links"][0]["beam_only_class"],
                         "attribution-conflict")


    def test_unpaired_run_triage_separates_three_verdicts(self):
        runs = [_run("R0001", "KL1(1)", "V", -1448314.5, 760940.5, 767040.5),
                _run("R0002", "KL1(1)", "V", -1448314.5, 767240.5, 770240.5),
                _run("R0003", "KL2(1)", "H", 765000.0, -1445000.0, -1440000.0),
                _run("R0004", "KL9(1)", "V", -1200000.0, 100000.0, 105000.0)]
        beams = [_beam("B0001", "KL1(1)", "V", -1448314.5, 760940.5, 767040.5),
                 _beam("B0002", "KL3(1)", "H", 765000.0, -1445000.0, -1440000.0)]
        result = dedup.build_dedup(_model(runs, beams), OPTIONS)
        verdicts = {row["run_id"]: row["verdict"]
                    for row in result["unpaired_run_triage"]}
        self.assertEqual(verdicts["R0002"], "continuation-candidate")
        self.assertEqual(verdicts["R0003"], "attribution-conflict")
        self.assertEqual(verdicts["R0004"], "model-missing-instance")
        self.assertEqual(result["summary"]["unpaired_run_verdict_count"],
                         {"attribution-conflict": 1, "continuation-candidate": 1,
                          "model-missing-instance": 1})
        self.assertEqual(
            result["summary"]["unpaired_run_verdict_volume_m3"]
            ["continuation-candidate"], 0.3)

    def test_run_self_overlap_gate(self):
        model = _model([_run("R0001", "KL1(1)", "V", -1448314.5, 760940.5,
                             767040.5),
                        _run("R0002", "KL1(1)", "V", -1448314.5, 766040.5,
                             770240.5)],
                       [_beam("B0001", "KL1(1)", "V", -1448314.5, 760940.5,
                              767040.5)])
        result = dedup.build_dedup(model, OPTIONS)
        scan = result["run_self_overlap"]
        self.assertEqual(scan["pair_count"], 1)
        self.assertEqual(scan["pairs"][0]["run_ids"], ["R0001", "R0002"])
        self.assertAlmostEqual(scan["pairs"][0]["overlap_mm"], 1000.0, places=1)
        self.assertGreater(scan["overlapped_volume_m3"], 0.0)
        self.assertFalse(result["closure"]["gates"]["run-population-no-self-overlap"])
        clean = dedup.build_dedup(_model([_run("R0001", "KL1(1)", "V",
                                               -1448314.5, 760940.5, 767040.5)],
                                         [_beam("B0001", "KL1(1)", "V", -1448314.5,
                                                760940.5, 767040.5)]), OPTIONS)
        self.assertEqual(clean["summary"]["run_self_overlap_pair_count"], 0)
        self.assertTrue(
            clean["closure"]["gates"]["run-population-no-self-overlap"])

    def test_cli_writes_four_artifacts(self):
        model = _model([_run("R0001", "KL1(1)", "V", -1448314.5, 760940.5,
                             767040.5)],
                       [_beam("B0001", "KL1(1)", "V", -1450500.0, 760940.5,
                              767040.5)])
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "model.json"
            src.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "dedup"
            argv = ["cad_beam_instance_dedup.py", "--model-json", str(src),
                    "--floor-label", "首层", "-o", str(out)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(dedup.main(), 0)
            for name in (".json", ".csv", ".md", ".sha256"):
                self.assertTrue(out.with_name(out.name + name).exists(), name)
            digest = out.with_name(out.name + ".sha256").read_text(encoding="utf-8")
            self.assertEqual(len(digest.strip().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
