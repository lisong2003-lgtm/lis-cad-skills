#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR / "vendor"))
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_beam_frame_label_index as frame_index  # noqa: E402


def _entity(kind: str, layer: str, x: float, y: float, text: str) -> str:
    return (f"  0\n{kind}\n  8\n{layer}\n 10\n{x}\n 20\n{y}\n  1\n{text}\n")


def _dxf(texts: list[tuple[str, float, float, str]]) -> str:
    body = "".join(_entity("TEXT", layer, x, y, text)
                   for text, layer, x, y in texts)
    return "  0\nSECTION\n  2\nENTITIES\n" + body + "  0\nENDSEC\n  0\nEOF\n"


def _recon(code, single, cad_span, difference, ref_count=2, selected=1):
    return {"beam_code_reconciliation": [{
        "code": code, "reference_instance_count": ref_count,
        "selected_equivalent_instance_count": selected,
        "reference_single_axis_length_mm": single,
        "cad_selected_span_mm": cad_span,
        "current_code_difference_m3": difference}]}


class ScanTests(unittest.TestCase):
    def test_scan_labels_splits_codes_and_titles(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "sheet.dxf"
            path.write_text(_dxf([
                ("KL18(3) 300x500", "S-梁-配筋-集中标注", -1430000.0, 768000.0),
                ("二层梁平法施工图", "S-图名", -1426000.0, 746000.0),
                ("一层梁平法施工图", "S-图名", -1426000.0, 672000.0),
                ("说明：本工程抗震等级二级", "S-文字说明", -1426000.0, 660000.0),
            ]), encoding="utf-8")
            labels, titles = frame_index.scan_labels(path)
            self.assertEqual(1, len(labels))
            self.assertEqual("KL18(3)", labels[0]["code"])
            self.assertEqual({"一层梁平法施工图", "二层梁平法施工图"},
                             {row["text"] for row in titles})


class FrameTests(unittest.TestCase):
    def test_frames_are_ordered_by_y_inside_each_column(self):
        titles = [{"text": "三层~五层梁平法施工图", "x": -1426000.0, "y": 821000.0},
                  {"text": "二层梁平法施工图", "x": -1426000.0, "y": 746000.0},
                  {"text": "一层梁平法施工图", "x": -1426000.0, "y": 672000.0},
                  {"text": "二层梁平法施工图", "x": -1366000.0, "y": 737000.0}]
        frames = frame_index.build_frames(titles, {})
        main = [row for row in frames if row["column_x_mm"] == -1426000.0]
        self.assertEqual(["一层梁平法施工图", "二层梁平法施工图",
                          "三层~五层梁平法施工图"], [row["frame"] for row in main])
        self.assertEqual(746000.0, main[0]["y_max_mm"])
        self.assertEqual(1e12, main[-1]["y_max_mm"])

    def test_label_is_assigned_to_frame_title_below_it(self):
        frames = frame_index.build_frames([
            {"text": "一层梁平法施工图", "x": -1426000.0, "y": 672000.0},
            {"text": "二层梁平法施工图", "x": -1426000.0, "y": 746000.0}], {})
        labels = [{"code": "KL18(3)", "x": -1430000.0, "y": 768000.0},
                  {"code": "KL18(3)", "x": -1430000.0, "y": 690000.0},
                  {"code": "KL18(3)", "x": -1200000.0, "y": 768000.0}]
        rows = frame_index.assign_labels(labels, frames, {})
        self.assertEqual("二层梁平法施工图", rows[0]["frame"])
        self.assertEqual("一层梁平法施工图", rows[1]["frame"])
        self.assertEqual("", rows[2]["frame"])


class ClassificationTests(unittest.TestCase):
    def _build(self, code, single, cad_span, difference, label_y):
        ys = label_y if isinstance(label_y, (list, tuple)) else [label_y]
        labels = [{"code": code, "text": f"{code} 200x500",
                   "x": -1430000.0, "y": y} for y in ys]
        titles = [{"text": "一层梁平法施工图", "x": -1426000.0, "y": 672000.0},
                  {"text": "二层梁平法施工图", "x": -1426000.0, "y": 746000.0},
                  {"text": "三层~五层梁平法施工图", "x": -1426000.0, "y": 821000.0}]
        return frame_index.build_index(labels, titles, _recon(
            code, single, cad_span, difference),
            {"target_frame": "二层梁平法施工图"})

    def test_same_beam_length_not_closed(self):
        result = self._build("KL10(1)", 5600.0, 5200.0, -0.2362, 767000.0)
        row = result["code_index"][0]
        self.assertEqual("length-not-closed-in-same-beam", row["classification"])
        self.assertEqual(1, row["target_frame_label_count"])
        self.assertEqual(1, result["summary"]["classification_counts"][
            "length-not-closed-in-same-beam"])
        self.assertAlmostEqual(0.2362,
                               result["summary"]["length_closure_volume_m3"],
                               places=4)

    def test_instance_count_mismatch_when_chain_exceeds_single_instance(self):
        result = self._build("WKL4(1)", 6600.0, 8450.0, -0.9573,
                             [771000.0, 771800.0, 830000.0])
        row = result["code_index"][0]
        self.assertEqual("instance-count-mismatch", row["classification"])
        self.assertEqual(2, row["target_frame_label_count"])
        self.assertEqual({"三层~五层梁平法施工图": 1},
                         row["other_frame_label_counts"])
        self.assertEqual(1, row["other_frame_label_total"])

    def test_instance_or_length_missing_when_chain_below_threshold(self):
        result = self._build("L5(1)", 1200.0, 0.0, -0.1340, 771000.0)
        self.assertEqual("instance-or-length-missing",
                         result["code_index"][0]["classification"])

    def test_label_outside_target_frame_is_not_counted(self):
        result = self._build("L3(1)", 1850.0, 1750.0, -0.0736, 690000.0)
        row = result["code_index"][0]
        self.assertEqual(0, row["target_frame_label_count"])
        self.assertEqual("no-label-in-target-frame", row["classification"])
        self.assertEqual(1, result["summary"]["classification_counts"][
            "no-label-in-target-frame"])

    def test_markdown_and_csv_render(self):
        result = self._build("KL11(1)", 3938.0, 3300.0, -0.3112, 772000.0)
        markdown = frame_index.render_markdown(result)
        self.assertIn("梁编号图框标签索引", markdown)
        self.assertIn("length-not-closed-in-same-beam", markdown)
        self.assertFalse(result["formal_ready"])
        sections = {row[0] for row in frame_index.csv_rows(result)}
        self.assertEqual({"section", "frame", "code"}, sections)


if __name__ == "__main__":
    unittest.main()
