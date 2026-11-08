#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广联达清单口径与构件实物量口径对账内核的回归测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cad_glb_indicator_scope as scope  # noqa: E402


def _write_indicator(path: Path) -> None:
    import openpyxl

    book = openpyxl.Workbook()
    part = book.active
    part.title = "混凝土-部位楼层指标表"
    part.append(["部位楼层名称", "清单工程量（m3）", "建筑面积（m2）", "指标"])
    part.append([" 混凝土总量", 90.0, 1000.0, 0.09])
    part.append(["  首层", 90.0, 0, "-"])
    part.append(["  第2层", 55.0, 0, "-"])
    types = book.create_sheet("混凝土-构件类型楼层指标表")
    types.append(["楼层（构件）名称", "清单工程量（m3）", "建筑面积（m2）", "指标"])
    types.append([" 混凝土总量", 90.0, 1000.0, 0.09])
    types.append(["梁", 60.0, 1000.0, 0.06])
    types.append(["  梁", 50.0, 1000.0, 0.05])
    types.append(["    首层", 50.0, 0, "-"])
    types.append(["    第2层", 10.0, 0, "-"])
    types.append(["板", 30.0, 1000.0, 0.03])
    types.append(["  现浇板", 30.0, 1000.0, 0.03])
    types.append(["    首层", 30.0, 0, "-"])
    types.append(["零星", 10.0, 1000.0, 0.01])
    types.append(["  散水", 10.0, 1000.0, 0.01])
    types.append(["    首层", 10.0, 0, "-"])
    book.save(str(path))


EXPORT = {
    "schema": "cad-glb-concrete-reference/v0.1",
    "sheets": {
        "梁": {"first_floor_rows": [
            {"楼层": "首层", "名称": "KL1(1)", "体积(m3)": "50.0"}]},
        "现浇板": {"first_floor_rows": [
            {"楼层": "首层", "名称": "B-120", "是否叠合板后浇": "否",
             "体积(m3)": "30.0", "投影面积(m2)": "20.0"}]},
        "叠合板(整厚)": {"first_floor_rows": [
            {"楼层": "首层", "名称": "DHB-1", "体积(m3)": "10.0",
             "数量(块)": "1", "投影面积(m2)": "12.0"}]},
        "叠合板(预制底板)": {"first_floor_rows": [
            {"楼层": "首层", "名称": "YDB-01",
             "预制部分体积（按模型）(m3)": "6.0", "数量(块)": "1",
             "投影面积(m2)": "10.0"}]},
        "板缝": {"first_floor_rows": [
            {"楼层": "首层", "类别": "后浇接缝", "体积(m3)": "2.0"}]},
    },
}


class IndicatorScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        root = Path(self._dir.name)
        self.indicator = root / "指标报表.xlsx"
        _write_indicator(self.indicator)
        self.export = root / "按构件导出.json"
        self.export.write_text(json.dumps(EXPORT, ensure_ascii=False),
                              encoding="utf-8")
        sheets, areas, counts, slab_rows = scope.read_component_export(
            EXPORT, "首层")
        total, schedule = scope.read_indicator(self.indicator, "首层")
        self.result = scope.reconcile(total, schedule, sheets, areas, counts,
                                      slab_rows, {
            "floor": "首层", "reference_total_m3": 98.0,
            "cad_slab_volume_m3": 36.0, "cad_beam_independent_m3": 50.0,
            "cad_vertical_candidate_m3": 30.0,
            "cad_outline_count": 4, "cad_outline_area_m2": 18.3})

    def tearDown(self) -> None:
        self._dir.cleanup()

    def test_indicator_parser_keeps_only_target_floor_rows(self):
        schedule = scope.read_indicator(self.indicator, "首层")[1]
        self.assertEqual(
            schedule, {("梁", "梁"): 50.0, ("板", "现浇板"): 30.0,
                       ("零星", "散水"): 10.0})
        self.assertEqual(scope.read_indicator(self.indicator, "首层")[0], 90.0)

    def test_prefab_area_ratio_and_block_size_support_caliber_a(self):
        summary = self.result["summary"]
        self.assertEqual(summary["prefab_area_m2"], 10.0)
        self.assertEqual(summary["whole_thickness_area_m2"], 12.0)
        self.assertEqual(summary["prefab_over_whole_area_ratio"], 0.8333)
        self.assertEqual(summary["prefab_mean_block_area_m2"], 10.0)
        self.assertEqual(summary["whole_mean_block_area_m2"], 12.0)
        self.assertEqual(summary["cad_outline_mean_block_area_m2"], 4.575)
        self.assertTrue(self.result["closure"][
            "prefab-sublayer-ratio-consistent"])
        checks = self.result["slab_caliber"]["checks"]
        self.assertTrue(checks["area_ratio_consistent"])
        self.assertFalse(checks["cad_outline_is_prefab_layer"])
        self.assertTrue(self.result["slab_caliber"]["verdict"].startswith("A"))

    def test_cross_caliber_residual_is_rounding_only(self):
        summary = self.result["summary"]
        self.assertEqual(summary["export_first_floor_total_m3"], 98.0)
        self.assertEqual(summary["cross_caliber_residual_m3"], 0.0)
        self.assertTrue(
            self.result["closure"]["cross-caliber-reconciled"])

    def test_prefab_sublayer_is_not_additive(self):
        summary = self.result["summary"]
        self.assertEqual(summary["main_structure_m3"], 80.0)
        self.assertEqual(summary["assembly_slab_m3"], 18.0)
        self.assertEqual(summary["prefab_sublayer_m3"], 6.0)
        self.assertEqual(summary["de_duped_reference_total_m3"], 92.0)
        self.assertFalse(
            self.result["closure"]["prefab-sublayer-deduplicated"])
        gate = next(row for row in self.result["gates"]
                    if row["id"] == "prefab-sublayer-double-count")
        self.assertEqual(gate["status"], "fail")

    def test_slab_cast_caliber_and_cad_independent_are_computed(self):
        summary = self.result["summary"]
        self.assertEqual(summary["slab_cast_in_place_caliber_A_m3"], 36.0)
        self.assertEqual(summary["cad_independent_verifiable_m3"], 80.0)
        self.assertEqual(summary["cad_independent_with_slab_m3"], 116.0)
        self.assertEqual(summary["cad_vs_slab_caliber_A_diff_m3"], 0.0)
        self.assertTrue(self.result["slab_caliber"]["verdict"].startswith("A"))

    def test_bucket_sum_closes_and_scope_is_declared(self):
        self.assertTrue(self.result["identity_checks"][
            "bucket_sum_equals_export_total"])
        scopes = {row["cad_scope"] for row in self.result["scope_buckets"]}
        self.assertIn("out-of-scope", scopes)
        self.assertIn("in-scope-material-split", scopes)

    def test_cast_row_thickness_anomaly_is_flagged(self):
        anomalies = self.result["slab_caliber"][
            "cast_row_thickness_anomalies"]
        self.assertIn("B-120", anomalies)
        self.assertEqual(anomalies["B-120"]["implied_thickness_mm"], 1500.0)
        self.assertTrue(self.result["identity_checks"][
            "all_cast_in_place_rows_not_composite_topping"])

    def test_outputs_are_written_with_checksums(self):
        root = Path(self._dir.name)
        out = root / "报告/口径分解"
        code = json.dumps(EXPORT)
        self.assertTrue(code)
        sys.argv = [
            "cad_glb_indicator_scope", "--indicator-xlsx", str(self.indicator),
            "--component-export-json", str(self.export), "--floor", "首层",
            "--reference-total-m3", "98.0", "--cad-slab-volume-m3", "36.0",
            "--cad-outline-count", "4", "--cad-outline-area-m2", "18.3",
            "--cad-beam-independent-m3", "50.0", "--cad-vertical-candidate-m3",
            "30.0", "-o", str(out)]
        self.assertEqual(scope.main(), 0)
        for suffix in (".json", ".csv", ".md"):
            self.assertTrue(out.with_suffix(suffix).exists(), suffix)
        checksums = out.with_name(out.name + ".sha256").read_text(
            encoding="utf-8").strip().splitlines()
        self.assertEqual(len(checksums), 3)


if __name__ == "__main__":
    unittest.main()
