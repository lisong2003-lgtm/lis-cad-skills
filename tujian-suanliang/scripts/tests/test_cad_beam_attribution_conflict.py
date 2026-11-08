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

import cad_beam_attribution_conflict as conflict  # noqa: E402

OPTIONS = {"conflict_axis_tolerance_mm": 2500.0, "min_overlap_ratio": 0.5,
           "require_same_section": True,
           "strong_label_axis_tolerance_mm": 1000.0}


def _run(run_id, code, orientation, axis, lo, hi, section="200x500",
         leader_id=""):
    return {"id": run_id, "matched_code": code, "orientation": orientation,
            "axis_mm": axis, "start_mm": lo, "end_mm": hi,
            "section": section, "volume_m3": round((hi - lo) * 0.1 / 1000.0, 4),
            "matched_leader_id": leader_id,
            "code_assignment_status": "leader-target" if leader_id else "unresolved"}


def _beam(beam_id, code, orientation, axis, lo, hi, section="200x500"):
    start = [lo, axis] if orientation == "H" else [axis, lo]
    end = [hi, axis] if orientation == "H" else [axis, hi]
    return {"id": beam_id, "code": code, "base_code": code.split("(")[0],
            "section": section, "gross_volume_m3": round((hi - lo) * 0.1 / 1000.0, 4),
            "quantity_status": "clear-span-review",
            "centerline": {"start": start, "end": end, "orientation": orientation,
                           "axis_offset_mm": 0.0}}


def _leader(leader_id, codes, orientation, axis, point, lo, hi):
    x, y = (point, axis) if orientation == "H" else (axis, point)
    return leader_id, codes, {"orientation": orientation, "axis_mm": axis,
                              "x": x, "y": y, "start_mm": lo, "end_mm": hi}


def _model(runs, beams, leaders):
    return {
        "run_registry": {
            "runs": runs,
            "leader_codes": {row[0]: row[1] for row in leaders},
            "leader_targets": {row[0]: row[2] for row in leaders}},
        "members": {"beams": beams}}


class AttributionConflictTest(unittest.TestCase):
    def test_only_run_code_attested_by_leader(self):
        model = _model(
            [_run("R0001", "WKL4(1)", "V", -1445014.5, 764990.5, 773440.5,
                  leader_id="L0008")],
            [_beam("B0001", "KL12(2)", "V", -1445014.5, 764990.5, 773440.5)],
            [_leader("L0008", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5)])
        result = conflict.adjudicate(model, OPTIONS)
        row = result["conflicts"][0]
        self.assertEqual(row["verdict"], "run-label-holds")
        self.assertEqual(row["confidence"], "strong")
        self.assertTrue(row["same_axis"])
        self.assertAlmostEqual(row["double_count_risk_m3"], 0.845, places=4)
        self.assertEqual(
            result["summary"]["verdicts"]["run-label-holds"]["pair_count"], 1)

    def test_both_codes_attested_is_dual_label(self):
        model = _model(
            [_run("R0001", "KL12(2)", "H", 769540.5, -1447414.5, -1443264.5,
                  leader_id="L0009")],
            [_beam("B0001", "KL18(3)", "H", 769540.5, -1447414.5, -1443264.5)],
            [_leader("L0009", ["KL12"], "H", 769540.5, -1446000.0,
                     -1447414.5, -1443264.5),
             _leader("L0015", ["KL18"], "H", 769540.5, -1444000.0,
                     -1447414.5, -1443264.5)])
        result = conflict.adjudicate(model, OPTIONS)
        self.assertEqual(result["conflicts"][0]["verdict"],
                         "dual-label-same-line")
        self.assertFalse(
            result["closure"]["gates"]["no-unadjudicated-dual-label"])

    def test_only_beam_code_attested(self):
        model = _model(
            [_run("R0001", "KL13A(1)", "H", 771140.5, -1440564.5, -1439614.5)],
            [_beam("B0001", "KL13(1)", "H", 771940.5, -1440564.5, -1439614.5)],
            [_leader("L0019", ["KL13"], "H", 772500.0, -1440000.0,
                     -1444764.5, -1434064.5)])
        result = conflict.adjudicate(model, OPTIONS)
        row = result["conflicts"][0]
        self.assertEqual(row["verdict"], "beam-label-holds")
        self.assertTrue(row["same_line"])
        self.assertEqual(row["label_codes"], ["KL13"])

    def test_unattested_pair_has_no_label_evidence(self):
        model = _model(
            [_run("R0001", "KL7(1)", "H", 768540.5, -1435014.5, -1433764.5)],
            [_beam("B0001", "KL5(1)", "H", 768000.0, -1435014.5, -1433764.5)],
            [_leader("L0099", [], "H", 768200.0, -1434000.0,
                     -1435014.5, -1433764.5)])
        result = conflict.adjudicate(model, OPTIONS)
        self.assertEqual(result["conflicts"][0]["verdict"],
                         "no-label-evidence")

    def test_section_mismatch_and_same_code_are_not_conflicts(self):
        model = _model(
            [_run("R0001", "KL8(1)", "H", 758440.5, -1444314.5, -1439414.5,
                  section="200x510"),
             _run("R0002", "KL9(1)", "H", 759040.5, -1448214.5, -1445114.5,
                  section="200x480")],
            [_beam("B0001", "KL8(1)", "H", 757740.5, -1444314.5, -1439414.5,
                   section="200x510"),
             _beam("B0002", "KL7(1)", "H", 759000.0, -1448214.5, -1445114.5,
                   section="200x400")],
            [])
        strict = conflict.adjudicate(model, OPTIONS)
        self.assertEqual(strict["summary"]["conflict_pair_count"], 0)
        loose = conflict.adjudicate(dict(model, **{}) if False else {
            "run_registry": model["run_registry"],
            "members": model["members"]}, dict(OPTIONS, **{
                "require_same_section": False}))
        self.assertEqual(loose["summary"]["conflict_pair_count"], 1)

    def test_leader_outside_overlap_interval_is_ignored(self):
        model = _model(
            [_run("R0001", "WKL4(1)", "V", -1445014.5, 769640.5, 773440.5,
                  leader_id="L0008")],
            [_beam("B0001", "KL12(2)", "V", -1445014.5, 764990.5, 769440.5)],
            [_leader("L0008", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5)])
        result = conflict.adjudicate(model, OPTIONS)
        self.assertEqual(result["summary"]["conflict_pair_count"], 0)

    def test_parallel_neighbour_lines_are_not_conflicts(self):
        model = _model(
            [_run("R0001", "KL12(2)", "H", 769540.5, -1447414.5, -1443264.5,
                  leader_id="L0009")],
            [_beam("B0001", "KL18(3)", "H", 767240.5, -1450614.5, -1441064.5)],
            [_leader("L0009", ["KL12"], "H", 769540.5, -1445893.0,
                     -1447414.5, -1445014.5),
             _leader("L0006", ["KL18"], "H", 767240.5, -1447302.0,
                     -1448214.5, -1445014.5)])
        result = conflict.adjudicate(model, OPTIONS)
        row = result["conflicts"][0]
        self.assertEqual(row["verdict"], "parallel-distinct-lines")
        self.assertFalse(row["same_line"])
        self.assertAlmostEqual(row["label_pair_axis_gap_mm"], 2300.0, places=1)
        self.assertEqual(row["double_count_risk_m3"], 0.0)
        self.assertEqual(
            result["summary"]["double_count_risk_m3"], 0.0)
        self.assertEqual(result["summary"]["parallel_pair_count"], 1)

    def test_same_line_end_to_end_members_are_a_chain_defect(self):
        model = _model(
            [_run("R0001", "KL2(1)", "V", -1430014.5, 764990.5, 773440.5,
                  leader_id="L0036")],
            [_beam("B0001", "WKL4(1)", "V", -1431000.0, 767340.5, 773440.5)],
            [_leader("L0036", ["KL2"], "V", -1430014.5, 765446.0,
                     764990.5, 767140.5),
             _leader("L0035", ["WKL4"], "V", -1430014.5, 771767.0,
                     769640.5, 773440.5)])
        result = conflict.adjudicate(model, OPTIONS)
        row = result["conflicts"][0]
        self.assertEqual(row["verdict"], "same-line-different-spans")
        self.assertTrue(row["same_line"])
        self.assertEqual(row["label_pair_axis_gap_mm"], 0.0)
        self.assertEqual(row["span_split_interval_mm"], [767140.5, 769640.5])

    def test_cli_writes_four_artifacts(self):
        model = _model(
            [_run("R0001", "WKL4(1)", "V", -1445014.5, 764990.5, 773440.5,
                  leader_id="L0008")],
            [_beam("B0001", "KL12(2)", "V", -1445014.5, 764990.5, 773440.5)],
            [_leader("L0008", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5)])
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "model.json"
            src.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "conflict"
            argv = ["cad_beam_attribution_conflict.py", "--model-json", str(src),
                    "--floor-label", "首层", "-o", str(out)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(conflict.main(), 0)
            for suffix in (".json", ".csv", ".md", ".sha256"):
                self.assertTrue(out.with_name(out.name + suffix).exists(), suffix)
            text = out.with_name(out.name + ".md").read_text(encoding="utf-8")
            self.assertIn("梁编号归属冲突定责台账", text)



class OwnershipTest(unittest.TestCase):
    """归属层：定主只搬编号归属，逐编号增减必须对平，判不了的老实留 open。"""

    def _pair(self, leaders, run_leader="L0001", beam_codes=("KL12(2)",)):
        runs = [_run("R0001", "WKL4(1)", "V", -1445014.5, 764990.5, 773440.5,
                     leader_id=run_leader)]
        beams = [_beam("B0001", code, "V", -1445014.5, 764990.5, 773440.5)
                 for code in beam_codes]
        return _model(runs, beams, leaders)

    def test_run_label_holds_decides_owner_and_transfers_risk(self):
        result = conflict.adjudicate(self._pair(
            [_leader("L0001", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5)]), OPTIONS)
        owner = result["conflicts"][0]["ownership"]
        self.assertEqual(owner["status"], "owner-decided")
        self.assertEqual(owner["code"], "WKL4(1)")
        self.assertEqual(owner["transfer_m3"],
                         result["conflicts"][0]["double_count_risk_m3"])
        summary = result["summary"]
        self.assertEqual(summary["closed_double_count_risk_m3"],
                         summary["double_count_risk_m3"])
        self.assertEqual(summary["residual_double_count_risk_m3"], 0.0)
        self.assertEqual(summary["attribution_balance_residual_m3"], 0.0)
        self.assertEqual(round(sum(row["shift_m3"]
                                   for row in summary["code_attribution_shift"]), 6), 0.0)
        self.assertTrue(result["closure"]["gates"]["conflict-ownership-closed"])

    def test_loser_code_shows_negative_shift(self):
        result = conflict.adjudicate(self._pair(
            [_leader("L0001", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5)]), OPTIONS)
        shifts = {row["code"]: row["shift_m3"]
                  for row in result["summary"]["code_attribution_shift"]}
        self.assertGreater(shifts["WKL4(1)"], 0.0)
        self.assertLess(shifts["KL12(2)"], 0.0)

    def test_dual_label_stays_open_and_keeps_risk(self):
        result = conflict.adjudicate(self._pair([
            _leader("L0001", ["WKL4"], "V", -1445014.5, 771269.8,
                    769640.5, 773440.5),
            _leader("L0002", ["KL12"], "V", -1445014.5, 771269.8,
                    769640.5, 773440.5)]), OPTIONS)
        row = result["conflicts"][0]
        self.assertEqual(row["verdict"], "dual-label-same-line")
        owner = row["ownership"]
        self.assertEqual(owner["status"], "review-open")
        self.assertEqual(owner["transfer_m3"], 0.0)
        self.assertEqual(owner["residual_risk_m3"], row["double_count_risk_m3"])
        self.assertFalse(result["closure"]["gates"]["conflict-ownership-closed"])
        self.assertTrue(result["closure"]["gates"]["conflict-ownership-transfer-balanced"])

    def test_parallel_lines_resolve_without_any_transfer(self):
        runs = [_run("R0001", "KL1(1)", "V", -1000.0, 0.0, 9000.0, leader_id="L0001"),
                _run("R0002", "KL2(1)", "V", -3000.0, 0.0, 9000.0, leader_id="L0002")]
        beams = [_beam("B0001", "KL9(1)", "V", -1000.0, 0.0, 9000.0)]
        model = _model(runs, beams, [
            _leader("L0001", ["KL1"], "V", -1000.0, 4000.0, 0.0, 9000.0),
            _leader("L0002", ["KL2"], "V", -3000.0, 4000.0, 0.0, 9000.0)])
        result = conflict.adjudicate(model, OPTIONS)
        parallel = [row for row in result["conflicts"]
                    if row["verdict"] == "parallel-distinct-lines"]
        self.assertTrue(parallel, "该 fixture 应至少检出一对平行邻线")
        for row in parallel:
            self.assertEqual(row["ownership"]["status"], "resolved-separate-lines")
            self.assertEqual(row["ownership"]["transfer_m3"], 0.0)
            self.assertEqual(row["ownership"]["residual_risk_m3"], 0.0)
        summary = result["summary"]
        self.assertEqual(
            summary["attribution_transfer_m3"], summary["closed_double_count_risk_m3"])

    def test_mixed_model_keeps_total_risk_split_exactly(self):
        model = _model(
            [_run("R0001", "WKL4(1)", "V", -1445014.5, 764990.5, 773440.5,
                  leader_id="L0001")],
            [_beam("B0001", "KL12(2)", "V", -1445014.5, 764990.5, 773440.5),
             _beam("B0002", "KL13(2)", "V", -1445014.5, 773440.5, 782440.5)],
            [_leader("L0001", ["WKL4"], "V", -1445014.5, 771269.8,
                     769640.5, 773440.5),
             _leader("L0002", ["KL13"], "V", -1445014.5, 779000.0,
                     774000.0, 782000.0)])
        summary = conflict.adjudicate(model, OPTIONS)["summary"]
        self.assertAlmostEqual(
            summary["closed_double_count_risk_m3"]
            + summary["residual_double_count_risk_m3"],
            summary["double_count_risk_m3"], places=4)



if __name__ == "__main__":
    unittest.main()
