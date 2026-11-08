#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "cad_civil_defense_checklist.py"


class CivilDefenseChecklistTest(unittest.TestCase):
    def test_extracts_special_checklist_without_quantities(self):
        detail = {
            "files": [{"name": "国贸酒店人防结构.dwg"}],
            "text_records": [
                {"text": "人防顶梁平法施工图", "layer": "TEXT", "sheet": 1},
                {"text": "9.8.5 门框墙边柱上下端支承处顶板厚度小于300时设柱端帽板", "layer": "TEXT", "sheet": 1},
                {"text": "带*墙体为人防防护墙体兼平时剪力墙", "layer": "PUB_TEXT", "sheet": 1},
                {"text": "口部一进风口设滤毒室和防毒通道", "layer": "TEXT", "sheet": 2},
                {"text": "战时给排水、人防电气、防爆波电缆井需预留", "layer": "TEXT", "sheet": 3},
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "detail.json"
            out = Path(td) / "checklist.json"
            src.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPT), str(src), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(out.read_text(encoding="utf-8"))
            ids = {row["id"] for row in data["checklist"] if row["status"] == "evidence_found"}
            self.assertIn("door_frame_wall", ids)
            self.assertIn("shell_wall", ids)
            self.assertIn("opening", ids)
            self.assertIn("mep_interfaces", ids)
            self.assertFalse(data["formal_ready"])
            self.assertIn("不输出", data["boundary"])


if __name__ == "__main__":
    unittest.main()
