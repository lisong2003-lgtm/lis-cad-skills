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

import cad_beam_candidate_attribution as attribution  # noqa: E402

OPTIONS = {"axis_tolerance_mm": 60.0, "joint_max_mm": 400.0,
           "width_tolerance_mm": 50.0, "section_delta_tolerance_m3": 0.0005,
           "unexplained_tolerance_m3": 0.05, "floor_label": "首层"}


def _run(run_id, code, section, length, axis=771140.5, start=-1412824.5,
         orientation="H", status="leader-target"):
    width, height = (float(part) for part in section.lower().split("x"))
    return {
        "id": run_id, "orientation": orientation, "axis_mm": axis,
        "start_mm": start, "end_mm": start + length, "length_mm": length,
        "paired_width_mm": width, "section_b_mm": width, "section_h_mm": height,
        "section": section, "volume_m3": width * height * length / 1e9,
        "matched_code": code, "code_assignment_status": status,
        "confidence": "high", "mirror_axis_mm": -1423294.5}


def _model(runs):
    return {"run_registry": {"runs": runs,
                             "mirror_axes": [{"axis_mm": -1423294.5,
                                              "match_count": 3}]}}


def _recon(code, section, runs, difference):
    return {"beam_code_reconciliation": [{
        "code": code,
        "reference_single_section": section,
        "selected_chains": [{
            "id": "CH0001", "span_mm": sum(row["length_mm"] for row in runs),
            "run_ids": [row["id"] for row in runs]}],
        "current_code_volume_m3": round(
            sum(row["volume_m3"] for row in runs), 4),
        "current_code_difference_m3": difference}]}


def _candidate(handles, length, axis=771140.5, start=-1411374.5, width=200.0,
               height=510.0, zone="inside-extraction-window", orientation="H"):
    return {"status": "uncovered-beam-candidate", "handles": handles,
            "orientation": orientation, "axis_mm": axis, "start_mm": start,
            "end_mm": start + length, "width_mm": width, "length_mm": length,
            "assumed_height_mm": height,
            "volume_m3": width * height * length / 1e9,
            "evidence": "两条未覆盖平行梁线", "view_zone": zone}


def _coverage(candidates, residual=1.0413, reported=0.4344):
    return {"schema": "cad-beam-coverage-audit/v0.1",
            "floor": "二层梁平法施工图",
            "summary": {"residual_gap_m3": residual,
                        "residual_still_unexplained_m3": reported,
                        "unexplained_tolerance_m3": 0.05,
                        "candidate_volume_mirror_pair_m3": 8.2478,
                        "candidate_volume_translated_view_m3": 1.3821},
            "candidates": candidates}


def _gap(rows):
    return {"schema": "cad-beam-gap-attribution/v0.1", "code_attribution": rows}


def _target(code, difference, needed, section="200x500"):
    return {"code": code, "reference_section": section,
            "difference_m3": difference, "needed_length_mm": needed,
            "missing_instance_count": 1, "unassigned_candidate_count": 0,
            "classification": "volume-under"}


class SectionCaliberTests(unittest.TestCase):
    def test_matching_sections_contribute_zero_volume(self):
        runs = [_run("R0001", "KL1(1)", "200x500", 6100.0)]
        result = attribution.recheck_section_caliber(
            _model(runs), _recon("KL1(1)", "200x500", runs, -0.0052), OPTIONS)
        self.assertEqual(0, result["run_mismatch_count"])
        self.assertEqual(0.0, result["run_recheck_delta_m3"])
        self.assertFalse(result["section_caliber_explains_gap"])

    def test_mismatched_section_height_is_recomputed(self):
        runs = [_run("R0001", "KL9(1)", "200x600", 10000.0)]
        result = attribution.recheck_section_caliber(
            _model(runs), _recon("KL9(1)", "200x500", runs, -0.2), OPTIONS)
        self.assertEqual(1, result["run_mismatch_count"])
        self.assertAlmostEqual(-0.2, result["run_recheck_delta_m3"], places=4)
        self.assertEqual("rechecked-mismatch", result["runs"][0]["status"])
        self.assertTrue(result["section_caliber_explains_gap"])

    def test_case_insensitive_code_lookup(self):
        runs = [_run("R0032", "KL13A(1)", "200x500", 1250.0)]
        result = attribution.recheck_section_caliber(
            _model(runs), _recon("KL13a(1)", "200x500", runs, 0.0644), OPTIONS)
        self.assertEqual(1, result["run_rechecked_count"])


class CandidateAttributionTests(unittest.TestCase):
    def test_continuation_segment_attributes_to_existing_code(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0)]
        rows = attribution.attribute_candidates(
            _model(runs), _coverage([_candidate(["271", "272"], 1900.0)]),
            OPTIONS)
        self.assertEqual("attributed", rows[0]["status"])
        self.assertEqual("KL13A(1)", rows[0]["matched_code"])
        self.assertAlmostEqual(0.19, rows[0]["attributed_volume_m3"], places=4)
        self.assertEqual(200.0, rows[0]["joint_gap_mm"])

    def test_segment_without_coaxial_run_stays_unattached(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0, axis=781140.5)]
        rows = attribution.attribute_candidates(
            _model(runs), _coverage([_candidate(["2A9"], 2600.0)]), OPTIONS)
        self.assertEqual("no-coaxial-run", rows[0]["status"])
        self.assertEqual(0.0, rows[0]["attributed_volume_m3"])

    def test_width_conflict_registers_without_volume(self):
        runs = [_run("R0031", "KL3(1)", "300x500", 1250.0)]
        rows = attribution.attribute_candidates(
            _model(runs), _coverage([_candidate(["271"], 1900.0)]), OPTIONS)
        self.assertEqual("section-conflict", rows[0]["status"])
        self.assertEqual(0.0, rows[0]["attributed_volume_m3"])

    def test_out_of_window_candidates_are_ignored(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0)]
        rows = attribution.attribute_candidates(
            _model(runs),
            _coverage([_candidate(["271"], 1900.0, zone="mirror-pair-outside-window")]),
            OPTIONS)
        self.assertEqual([], rows)


class DecompositionTests(unittest.TestCase):
    def test_identity_and_cross_check_hold(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0)]
        coverage = _coverage(
            [_candidate(["271", "272"], 1900.0),
             _candidate(["2A9", "2AA"], 2600.0, axis=765790.5,
                        start=-1412074.5)],
            reported=0.5823)
        rows = attribution.attribute_candidates(_model(runs), coverage, OPTIONS)
        section = attribution.recheck_section_caliber(
            _model(runs), _recon("KL13A(1)", "200x500", [runs[0]], 0.0), OPTIONS)
        result = attribution.decompose_residual(coverage, rows, section, OPTIONS)
        self.assertTrue(result["matches_identity"])
        self.assertAlmostEqual(0.19, result["attached_to_existing_code_m3"],
                               places=4)
        self.assertAlmostEqual(0.0038, result["caliber_adjustment_m3"], places=4)
        self.assertAlmostEqual(0.0, result["cross_check_delta_m3"], places=4)
        self.assertFalse(result["unexplained_within_tolerance"])


class CodeTargetTests(unittest.TestCase):
    def test_claim_is_exclusive_between_codes(self):
        rows = [{"handles": "2A9", "status": "no-coaxial-run", "width_mm": 200.0,
                 "length_mm": 2600.0, "candidate_volume_m3": 0.2652}]
        decomposition = {"unattached_length_mm": 2600.0,
                         "unattached_candidate_m3": 0.2652,
                         "residual_gap_m3": 1.0413}
        gap = _gap([_target("KL11(1)", -0.3112, 2510.0),
                    _target("KL10(1)", -0.2362, 2362.0),
                    _target("KL1(1)", -0.0052, 0.0)])
        result = attribution.build_code_targets(gap, rows, decomposition)
        claims = {row["code"]: row["classification"] for row in result["codes"]}
        self.assertEqual("claimed-in-frame", claims["KL11(1)"])
        self.assertEqual("needs-cross-frame-search", claims["KL10(1)"])
        self.assertEqual("count-only-caliber", claims["KL1(1)"])
        self.assertEqual(["2A9"], result["claimed_candidate_handles"])
        self.assertFalse(result["frame_can_close_all"])
        self.assertEqual(2362.0, result["cross_frame_needed_length_mm"])


class BuildTests(unittest.TestCase):
    def test_full_build_reports_gates_and_floor_label(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0)]
        result = attribution.build_attribution(
            _model(runs),
            _coverage([_candidate(["271", "272"], 1900.0)]),
            _recon("KL13a(1)", "200x500", [runs[0]], 0.0644),
            _gap([_target("KL13(1)", -0.2278, 2278.0)]), OPTIONS)
        self.assertEqual("cad-beam-candidate-attribution/v0.1", result["schema"])
        self.assertEqual("首层", result["floor"])
        self.assertFalse(result["formal_ready"])
        self.assertFalse(result["applied_to_formal_quantity"])
        self.assertEqual(1, result["closure"]["fail_count"])
        self.assertTrue(
            result["closure"]["gates"]["all-in-frame-candidates-attributed"])
        self.assertTrue(result["closure"]["gates"]["section-caliber-cleared"])
        self.assertIn("residual",
                      json.dumps(result["residual_decomposition"],
                                 ensure_ascii=False))

    def test_cli_writes_four_artifacts(self):
        runs = [_run("R0031", "KL13A(1)", "200x500", 1250.0)]
        model = _model(runs)
        coverage = _coverage([_candidate(["271", "272"], 1900.0)])
        recon = _recon("KL13a(1)", "200x500", [runs[0]], 0.0644)
        gap = _gap([_target("KL13(1)", -0.2278, 2278.0)])
        with tempfile.TemporaryDirectory() as work:
            directory = Path(work)
            paths = {}
            for name, payload in (("model", model), ("coverage", coverage),
                                  ("recon", recon), ("gap", gap)):
                paths[name] = directory / f"{name}.json"
                paths[name].write_text(json.dumps(payload, ensure_ascii=False),
                                       encoding="utf-8")
            out = directory / "report" / "候选归属.json"
            argv = ["cad_beam_candidate_attribution",
                    "--model-json", str(paths["model"]),
                    "--coverage-json", str(paths["coverage"]),
                    "--reconciliation-json", str(paths["recon"]),
                    "--gap-json", str(paths["gap"]),
                    "--floor-label", "首层", "-o", str(out)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(0, attribution.main())
            for path in (out, out.with_suffix(".csv"), out.with_suffix(".md"),
                         out.with_name(out.name + ".sha256")):
                self.assertTrue(path.exists(), path.name)
            digest = (directory / "report" / "候选归属.json.sha256").read_text(
                encoding="utf-8").split()[0]
            self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))


if __name__ == "__main__":
    unittest.main()
