#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共用助手语义锁定：合并各内核重复实现时必须保持原语义。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cad_common  # noqa: E402


class CadCommonTest(unittest.TestCase):
    def test_to_number_never_raises(self):
        self.assertEqual(cad_common.to_number("12.5"), 12.5)
        self.assertEqual(cad_common.to_number(None), 0.0)
        self.assertEqual(cad_common.to_number("", 1.0), 1.0)
        self.assertEqual(cad_common.to_number("C30", -1.0), -1.0)

    def test_to_text_keeps_inner_and_edge_spaces(self):
        self.assertEqual(cad_common.to_text(None), "")
        self.assertEqual(cad_common.to_text(" 层 号 "), " 层 号 ")

    def test_to_label_strips_for_table_labels(self):
        self.assertEqual(cad_common.to_label(" 层 号 "), "层 号")
        self.assertEqual(cad_common.to_label(None), "")

    def test_round_number_defaults_to_four_digits(self):
        self.assertEqual(cad_common.round_number("273.24364"), 273.2436)
        self.assertEqual(cad_common.round_number(None), 0.0)
        self.assertEqual(cad_common.round_number(1.23456, 2), 1.23)

    def test_kernels_import_the_shared_helpers(self):
        migrated = 0
        for path in SCRIPTS_DIR.glob("cad_*.py"):
            if path.name == "cad_common.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "from cad_common import" in text:
                migrated += 1
                self.assertNotIn(
                    "def _number(value: Any, default: float = 0.0) -> float:", text)
        self.assertGreaterEqual(migrated, 14)


if __name__ == "__main__":
    unittest.main()
