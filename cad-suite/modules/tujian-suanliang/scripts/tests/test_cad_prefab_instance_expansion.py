#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_prefab_instance_expansion as X  # noqa: E402

OUTLINE = "S-PC-叠合板轮廓"
LABEL = "S-PC-编号"


def _poly(handle: str, x0: float, y0: float, w: float, h: float) -> List[str]:
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    lines = ["  0", "LWPOLYLINE", "  5", handle, "  8", OUTLINE, " 70", "1"]
    for x, y in pts:
        lines += [" 10", "%.1f" % x, " 20", "%.1f" % y]
    return lines


def _text(handle: str, layer: str, x: float, y: float, value: str) -> List[str]:
    return ["  0", "TEXT", "  5", handle, "  8", layer, "  1", value,
            " 10", "%.1f" % x, " 20", "%.1f" % y]


def _dxf(entities: List[str]) -> str:
    body = ["  0", "SECTION", "  2", "ENTITIES"] + entities + [
        "  0", "ENDSEC", "  0", "EOF"]
    return "\n".join(body) + "\n"


def _params(**over: Any) -> Dict[str, Any]:
    params = {"dxf": "test.dxf", "material_ledger": "ledger.json",
              "outline_layer": OUTLINE, "label_layer": LABEL,
              "title_keys": ["预制底板平面布置图"],
              "frame_title_key": "预制底板平面布置图",
              "frame_half_width_mm": 45000.0, "label_link_mm": 1500.0,
              "mirror_tolerance_mm": 400.0, "min_outline_area_m2": 0.2,
              "unit_area_tolerance_m2": 0.01, "identity_tolerance_m2": 0.05,
              "floor": "首层", "title": "测试"}
    params.update(over)
    return params


def _ledger(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"schema": "cad-composite-slab-material-ledger/v0.1",
            "component_reconciliation": rows}


def _row(code: str, model_count: int, unit: float) -> Dict[str, Any]:
    return {"code": code, "model_count": model_count,
            "model_unit_area_m2": unit,
            "model_area_m2": round(model_count * unit, 4)}


class GeometryTest(unittest.TestCase):
    def test_ring_area_uses_square_millimetres(self):
        self.assertAlmostEqual(
            X.ring_area([(0, 0), (1000, 0), (1000, 1000), (0, 1000)]), 1.0, places=6)

    def test_clean_text_strips_mtext_format_codes(self):
        self.assertEqual(X.clean_text(r"{\f仿宋|b0;YDB-2{\H1.2x;}"), "YDB-2")

    def test_code_pattern_splits_mirror_suffix(self):
        hit = X.CODE_PATTERN.match("YDB-2(W)")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.group(1), "YDB-2")
        self.assertEqual(hit.group(2), "(W)")
        self.assertIsNone(X.CODE_PATTERN.match("吊环"))


class ExpansionTest(unittest.TestCase):
    """两块镜像板的图框：模型每编号 2 块、图面 1 块，倍率必须由编号数量重构。"""

    def _build(self, entities, rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sheet.dxf"
            path.write_text(_dxf(entities), encoding="utf-8")
            collected = X.collect(str(path), outline_layer=OUTLINE, label_layer=LABEL,
                                  title_keys=["预制底板平面布置图"], min_area=0.2)
        return X.build_expansion(collected, _ledger(rows), _params())

    def test_two_board_mirror_frame_reconciles_by_count_ratio(self):
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        # 2000x2000mm = 4 m2，镜像轴 x=0，两块互镜
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)
        entities += _poly("2", 1000.0, 0.0, 2000.0, 2000.0)
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-2")
        entities += _text("4", LABEL, 2000.0, 1000.0, "YDB-2")
        payload = self._build(entities, [_row("YDB-2", 4, 4.0)])
        summary = payload["summary"]
        self.assertEqual(summary["cad_owned_outline_count"], 2)
        self.assertEqual(summary["model_instance_count"], 4)
        self.assertEqual(summary["count_ratio_expanded_area_m2"], 16.0)
        self.assertEqual(summary["expansion_area_residual_m2"], 0.0)
        self.assertTrue(payload["mirror_audit"]["unpaired"] == [])
        self.assertFalse(payload["mirror_audit"]["explains_doubling"])
        self.assertEqual(
            {row["id"]: row["status"] for row in payload["gates"]},
            {"prefab-unit-area-self-evidence": "pass",
             "prefab-expansion-area-identity": "pass",
             "prefab-instance-count-cad-evidence": "warn"})

    def test_half_frame_mirror_explains_the_count_gap(self):
        # 只画半幅：两块板错开在不同 y 上，任何镜像轴都配不成对
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)
        entities += _poly("2", -5000.0, 3000.0, 2000.0, 2000.0)
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-2")
        entities += _text("4", LABEL, -4000.0, 4000.0, "YDB-2")
        payload = self._build(entities, [_row("YDB-2", 4, 4.0)])
        self.assertEqual(payload["mirror_audit"]["paired_count"], 0)
        self.assertEqual(len(payload["mirror_audit"]["unpaired"]), 2)
        gate = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gate["prefab-instance-count-cad-evidence"], "pass")

    def test_labelless_outline_is_not_counted(self):
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)
        entities += _poly("2", 1000.0, 0.0, 2000.0, 2000.0)
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-2")
        payload = self._build(entities, [_row("YDB-2", 2, 4.0)])
        self.assertEqual(payload["summary"]["cad_owned_outline_count"], 1)
        self.assertEqual(payload["summary"]["unlabeled_outline_count"], 1)

    def test_unit_area_swap_pair_is_reported_once(self):
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)      # 4.0
        entities += _poly("2", 1000.0, 0.0, 2600.0, 2000.0)       # 5.2
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-4")
        entities += _text("4", LABEL, 2000.0, 1000.0, "YDB-5")
        payload = self._build(entities, [_row("YDB-4", 2, 5.2), _row("YDB-5", 2, 4.0)])
        swaps = payload["unit_area_swap_candidates"]
        self.assertEqual(len(swaps), 1)
        self.assertEqual(sorted(swaps[0]["codes"]), ["YDB-4", "YDB-5"])
        self.assertEqual(swaps[0]["status"], "code-outline-swapped-pair")
        gate = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gate["prefab-unit-area-self-evidence"], "pass")

    def test_identity_residual_fails_the_gate(self):
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-2")
        ledger_row = _row("YDB-2", 5, 4.0)
        ledger_row["model_area_m2"] = 24.0  # 模型行自身对不上，恒等式必须报错
        payload = self._build(entities, [ledger_row])
        self.assertAlmostEqual(payload["summary"]["expansion_area_residual_m2"], -4.0,
                               places=4)
        gate = {row["id"]: row["status"] for row in payload["gates"]}
        self.assertEqual(gate["prefab-expansion-area-identity"], "fail")

    def test_csv_and_markdown_render_without_keyerror(self):
        entities = _text("A1", "图名", -10000.0, -5000.0, "标准层预制底板平面布置图")
        entities += _poly("1", -3000.0, 0.0, 2000.0, 2000.0)
        entities += _text("3", LABEL, -2000.0, 1000.0, "YDB-2")
        payload = self._build(entities, [_row("YDB-2", 2, 4.0)])
        self.assertTrue(any(row and row[0] == "编号" for row in X.csv_rows(payload)))
        self.assertIn("YDB-2", X.render_markdown(payload))


if __name__ == "__main__":
    unittest.main()
