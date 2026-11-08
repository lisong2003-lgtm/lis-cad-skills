#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

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

import cad_beam_multispan_closure as multispan  # noqa: E402

OPTIONS = {"axis_tolerance_mm": 400.0, "gap_tolerance_mm": 200.0,
           "geometry_dxf": "beam.dxf"}


def _seg(handle, layer, orientation, cross, lo, hi):
    return {"handle": handle, "layer": layer, "orientation": orientation,
            "cross_mm": round(cross, 1), "lo_mm": round(lo, 1),
            "hi_mm": round(hi, 1), "length_mm": round(hi - lo, 1)}


def _beam(beam_id, code, axis, lo, hi, width=200.0, height=510.0,
          orientation="H"):
    start = [lo, axis] if orientation == "H" else [axis, lo]
    end = [hi, axis] if orientation == "H" else [axis, hi]
    return {"id": beam_id, "code": code, "section": f"{int(width)}x{int(height)}",
            "section_b_mm": width, "section_h_mm": height,
            "centerline_length_mm": hi - lo, "quantity_status": "clear-span-review",
            "centerline": {"start": start, "end": end, "orientation": orientation,
                           "length_basis": "local"}}


def _recon(code, single, selected=1):
    return {"beam_code_reconciliation": [{
        "code": code, "reference_single_axis_length_mm": single,
        "selected_equivalent_instance_count": selected,
        "current_code_difference_m3": -0.8823}]}


class HelperTests(unittest.TestCase):
    def test_span_count_from_code(self):
        self.assertEqual(2, multispan._span_count("WKL1(2)"))
        self.assertEqual(3, multispan._span_count("KL17(3)"))
        self.assertEqual(2, multispan._span_count("KL13(2A)"))
        self.assertEqual(1, multispan._span_count("KL13(1)"))
        self.assertEqual(1, multispan._span_count("L5"))

    def test_layer_classification(self):
        self.assertTrue(multispan._is_beam("S-梁-虚线"))
        self.assertFalse(multispan._is_beam("梁附加箍筋"))
        self.assertTrue(multispan._is_support("S-柱"))
        self.assertTrue(multispan._is_support("砼墙_醠"))
        self.assertFalse(multispan._is_support("S-剪力墙-连梁"))

    def test_load_segments_buckets_lines(self):
        import ezdxf
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "mini.dxf"
            doc = ezdxf.new()
            msp = doc.modelspace()
            msp.add_line((-1450914.5, 773740.5), (-1445264.5, 773740.5),
                         dxfattribs={"layer": "S-梁-虚线"})
            msp.add_line((-1445264.5, 773940.5), (-1444764.5, 773940.5),
                         dxfattribs={"layer": "S-柱"})
            msp.add_line((-1445000.0, 773800.0), (-1445000.0, 774400.0),
                         dxfattribs={"layer": "梁附加箍筋"})
            doc.saveas(str(path))
            buckets = multispan.load_segments(path)
            self.assertEqual(1, len(buckets["beam"]))
            self.assertEqual("H", buckets["beam"][0]["orientation"])
            self.assertAlmostEqual(773740.5, buckets["beam"][0]["cross_mm"])
            self.assertEqual(1, len(buckets["support"]))


class ClosureTests(unittest.TestCase):
    def _buckets(self):
        return {
            "beam": [_seg("1AA", "S-梁-虚线", "H", 773940.5, -1450914.5, -1445264.5),
                     _seg("1AC", "S-梁-虚线", "H", 773940.5, -1444764.5, -1441064.5),
                     _seg("1BB", "S-梁-虚线", "H", 773940.5, -1433564.5, -1430264.5)],
            "support": [_seg("260", "S-柱", "H", 773940.5, -1445264.5, -1444764.5),
                        _seg("263", "S-柱", "H", 773940.5, -1430264.5, -1429764.5)],
        }

    def test_continuation_through_support_at_end(self):
        result = multispan.close_one_chain(
            _beam("B0037", "WKL1(2)", 773940.5, -1450914.5, -1445264.5),
            self._buckets(), OPTIONS)
        self.assertEqual(1, result["extensions"])
        self.assertEqual(9850.0, result["continued_centerline_mm"])
        self.assertEqual(4200.0, result["added_axis_length_mm"])
        self.assertAlmostEqual(0.4284, result["added_volume_candidate_m3"], places=4)
        item = result["added_evidence"][0]
        self.assertEqual("end", item["side"])
        self.assertEqual("260", item["support_handle"])
        self.assertEqual("1AC", item["beam_handle"])

    def test_no_continuation_without_next_segment(self):
        buckets = self._buckets()
        buckets["beam"] = [row for row in buckets["beam"]
                           if row["handle"] != "1AC"]
        result = multispan.close_one_chain(
            _beam("B0037", "WKL1(2)", 773940.5, -1450914.5, -1445264.5),
            buckets, OPTIONS)
        self.assertEqual(0, result["extensions"])
        self.assertEqual(0.0, result["added_axis_length_mm"])

    def test_single_span_codes_are_skipped(self):
        model = {"floor": "首层", "members": {"beams": [
            _beam("B0001", "KL1(1)", 766500.0, -1440114.5, -1434914.5)]}}
        result = multispan.build_closure(model, self._buckets(),
                                         _recon("KL1(1)", 6500.0), OPTIONS)
        self.assertEqual([], result["beams"])
        self.assertEqual(0, result["summary"]["multispan_beam_count"])
        self.assertFalse(result["closure"]["gates"][
            "multispan-candidates-generated"])

    def test_build_closure_partial_verdict_and_candidate_only(self):
        model = {"floor": "首层", "members": {"beams": [
            _beam("B0037", "WKL1(2)", 773940.5, -1450914.5, -1445264.5),
            _beam("B0044", "WKL5(2)", 773940.5, -1429764.5, -1424114.5)]}}
        result = multispan.build_closure(model, self._buckets(),
                                         _recon("WKL1(2)", 10350.0), OPTIONS)
        summary = result["summary"]
        self.assertEqual(2, summary["multispan_beam_count"])
        self.assertEqual(2, summary["codes_covered"])
        self.assertEqual(2, summary["continued_beam_count"])
        self.assertEqual(0, summary["closed_beam_count"])
        self.assertAlmostEqual(0.816, summary["added_volume_candidate_m3"],
                               places=4)
        self.assertLess(summary["deficit_after_mm"],
                        summary["deficit_before_mm"])
        self.assertFalse(result["applied_to_formal_quantity"])
        self.assertFalse(result["formal_ready"])
        self.assertTrue(result["closure"]["gates"]["multispan-candidates-generated"])
        markdown = multispan.render_markdown(result)
        self.assertIn("多跨梁跨支座续接候选台账", markdown)
        self.assertIn("#1AC", markdown)
        self.assertTrue(multispan.csv_rows(result))

    def test_cli_writes_four_artifacts(self):
        model = {"floor": "首层", "members": {"beams": [
            _beam("B0037", "WKL1(2)", 773940.5, -1450914.5, -1445264.5)]}}
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            model_path = root / "model.json"
            recon_path = root / "recon.json"
            model_path.write_text(__import__("json").dumps(model), encoding="utf-8")
            recon_path.write_text(__import__("json").dumps(
                _recon("WKL1(2)", 10350.0)), encoding="utf-8")
            mini = root / "mini.dxf"
            import ezdxf
            doc = ezdxf.new()
            msp = doc.modelspace()
            msp.add_line((-1450914.5, 773940.5), (-1445264.5, 773940.5),
                         dxfattribs={"layer": "S-梁-虚线"})
            msp.add_line((-1445264.5, 773940.5), (-1444764.5, 773940.5),
                         dxfattribs={"layer": "S-柱"})
            msp.add_line((-1444764.5, 773940.5), (-1441064.5, 773940.5),
                         dxfattribs={"layer": "S-梁-虚线"})
            doc.saveas(str(mini))
            out = root / "续接候选"
            argv = ["cad_beam_multispan_closure", "--model-json", str(model_path),
                    "--geometry-dxf", str(mini), "--reconciliation-json",
                    str(recon_path), "-o", str(out)]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(0, multispan.main())
            for path in (out.with_suffix(".json"), out.with_suffix(".csv"),
                         out.with_suffix(".md"),
                         out.with_name(out.name + ".sha256")):
                self.assertTrue(path.exists(), path.name)
            digest = out.with_name(out.name + ".sha256").read_text(
                encoding="utf-8").split()[0]
            self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", digest))


if __name__ == "__main__":
    unittest.main()
