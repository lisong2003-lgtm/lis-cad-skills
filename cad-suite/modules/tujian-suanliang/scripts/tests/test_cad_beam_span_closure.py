#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_beam_span_closure as closure  # noqa: E402


def _beam(beam_id, code, centerline, clear, width=200.0, height=500.0,
          inferred=(), supports=("wall-column", "wall-column")):
    evidence = [{"type": kind, "side": side}
                for kind, side in zip(supports, ("start", "end"))]
    return {"id": beam_id, "code": code, "section": f"{int(width)}x{int(height)}",
            "section_b_mm": width, "section_h_mm": height,
            "centerline_length_mm": centerline, "clear_length_mm": clear,
            "gross_volume_m3": width * height * centerline / 1e9,
            "clear_volume_m3": width * height * clear / 1e9,
            "support_count": 2, "expected_support_count": 2,
            "support_count_status": "exact",
            "endpoint_polygon_support_count": 2,
            "beam_intersection_support_count": 0,
            "support_evidence": evidence,
            "inferred_end_supports": [{"side": side, "assumed_width_mm": 500.0}
                                      for side in inferred],
            "support_selection": {"status": "expected-count-arbitrated",
                                  "rejected_cluster_count": 0},
            "quantity_status": "clear-span-inferred" if inferred
            else "clear-span-review",
            "centerline": {"start": [-1440114.5, 766500.0],
                           "end": [-1434914.5, 766500.0],
                           "length_basis": "axis-chain"}}


def _model(beams):
    return {"floor": "首层", "members": {"beams": beams}}


def _recon(code, single, span, selected, difference):
    return {"beam_code_reconciliation": [{
        "code": code, "reference_instance_count": 2,
        "reference_single_axis_length_mm": single,
        "cad_selected_span_mm": span,
        "selected_equivalent_instance_count": selected,
        "current_code_difference_m3": difference}]}


def _frame_index(rows):
    return {"code_index": [{"code": code, "classification": kind}
                           for code, kind in rows]}


OPTIONS = {"deficit_tolerance_mm": 100.0, "conflict_tolerance_m3": 0.05}


class VerdictTests(unittest.TestCase):
    def _run(self, beams, recon, kinds):
        return closure.build_closure(_model(beams), recon,
                                     _frame_index(kinds), None, OPTIONS)

    def test_deficit_explained_by_support_deduction(self):
        result = self._run(
            [_beam("B0003", "KL10(1)", 5200.0, 4200.0)],
            _recon("KL10(1)", 5600.0, 5200.0, 1, -0.2362),
            [("KL10(1)", "length-not-closed-in-same-beam")])
        row = result["code_closure"][0]
        self.assertEqual("deficit-within-support-deduction", row["verdict"])
        self.assertEqual(400.0, row["single_instance_deficit_mm"])
        self.assertEqual(1000.0,
                         row["model_support_deduction_per_instance_mm"])
        self.assertAlmostEqual(0.2362,
                               result["summary"][
                                   "support_deduction_caliber_volume_m3"],
                               places=4)

    def test_deficit_beyond_support_deduction_needs_geometry(self):
        result = self._run(
            [_beam("B0021", "WKL1(2)", 5650.0, 4950.0)],
            _recon("WKL1(2)", 10350.0, 5650.0, 1, -0.8823),
            [("WKL1(2)", "instance-or-length-missing")])
        self.assertEqual("deficit-exceeds-support-inference",
                         result["code_closure"][0]["verdict"])
        self.assertAlmostEqual(0.8823,
                               result["summary"]["needs_new_geometry_volume_m3"],
                               places=4)

    def test_chain_lost_when_recon_selected_nothing(self):
        result = self._run(
            [_beam("B0035", "L5(1)", 3800.0, 3300.0, height=400.0)],
            _recon("L5(1)", 1200.0, 0.0, 0, -0.134),
            [("L5(1)", "instance-or-length-missing")])
        self.assertEqual("chain-lost-in-reconciliation",
                         result["code_closure"][0]["verdict"])
        self.assertFalse(result["closure"]["gates"][
            "recon-chain-covers-modeled-beams"])

    def test_unstable_when_selected_differs_from_model_instances(self):
        result = self._run(
            [_beam("B0011", "KL13(1)", 3750.0, 2750.0)],
            _recon("KL13(1)", 3550.0, 3750.0, 2, -0.2278),
            [("KL13(1)", "instance-count-mismatch")])
        self.assertEqual("instance-count-caliber-unstable",
                         result["code_closure"][0]["verdict"])

    def test_matched_codes_are_skipped(self):
        result = self._run(
            [_beam("B0001", "KL2(1)", 8450.0, 7450.0)],
            _recon("KL2(1)", 4000.0, 8450.0, 2, 1.0536),
            [("KL2(1)", "volume-matched-or-over")])
        self.assertEqual([], result["code_closure"])
        self.assertEqual(0.0, result["summary"]["verdict_total_m3"])


class AggregateTests(unittest.TestCase):
    def test_span_caliber_conflict_against_intersection(self):
        beams = [_beam("B0003", "KL10(1)", 5200.0, 4200.0),
                 _beam("B0013", "KL18(3)", 9550.0, 8650.0,
                       inferred=("end",), supports=("wall-column",))]
        recon = {"beam_code_reconciliation": [
            dict(row, code=row["code"]) for row in (
                _recon("KL10(1)", 5600.0, 5200.0, 1, -0.2362)[
                    "beam_code_reconciliation"][0],
                _recon("KL18(3)", 10350.0, 9550.0, 1, -0.3983)[
                    "beam_code_reconciliation"][0])]}
        kinds = _frame_index([("KL10(1)", "length-not-closed-in-same-beam"),
                              ("KL18(3)", "length-not-closed-in-same-beam")])
        intersection = {"summary": {"beam_side_deduction_candidate_m3": 0.3211}}
        result = closure.build_closure(_model(beams), recon, kinds,
                                       intersection, OPTIONS)
        summary = result["summary"]
        self.assertAlmostEqual(1.9, summary["support_deduction_length_mm"] / 1000,
                               places=6)
        self.assertAlmostEqual(0.19, summary["span_caliber_difference_m3"],
                               places=4)
        self.assertAlmostEqual(-0.1311,
                               summary["span_caliber_vs_intersection_conflict_m3"],
                               places=4)
        self.assertFalse(result["closure"]["gates"][
            "span-caliber-conflict-quantified"])
        self.assertTrue(result["closure"]["gates"][
            "span-caliber-volume-flagged"])
        self.assertTrue(result["closure"]["gates"][
            "verdict-covers-reviewed-codes"])
        self.assertFalse(result["closure"]["gates"][
            "beam-support-confirmation-closed"])

    def test_cli_writes_four_artifacts(self):
        model = _model([_beam("B0003", "KL10(1)", 5200.0, 4200.0)])
        recon = _recon("KL10(1)", 5600.0, 5200.0, 1, -0.2362)
        kinds = _frame_index([("KL10(1)", "length-not-closed-in-same-beam")])
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            paths = {}
            for name, payload in (("model", model), ("recon", recon),
                                  ("kinds", kinds)):
                paths[name] = root / f"{name}.json"
                paths[name].write_text(json.dumps(payload, ensure_ascii=False),
                                       encoding="utf-8")
            out = root / "净跨对账"
            argv = ["cad_beam_span_closure", "--model-json", str(paths["model"]),
                    "--reconciliation-json", str(paths["recon"]),
                    "--frame-index-json", str(paths["kinds"]),
                    "--floor-label", "首层", "-o", str(out)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(0, closure.main())
            for path in (out.with_suffix(".json"), out.with_suffix(".csv"),
                         out.with_suffix(".md"),
                         out.with_name(out.name + ".sha256")):
                self.assertTrue(path.exists(), path.name)
            digest = out.with_name(out.name + ".sha256").read_text(
                encoding="utf-8").split()[0]
            self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))
            markdown = out.with_suffix(".md").read_text(encoding="utf-8")
            self.assertIn("梁净跨口径与支座扣减对账", markdown)
            self.assertIn("deficit-within-support-deduction", markdown)


if __name__ == "__main__":
    unittest.main()
