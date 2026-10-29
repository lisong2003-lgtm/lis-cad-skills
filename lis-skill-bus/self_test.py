#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lis-skill-bus 自测：纯 stdlib，无网络，不污染真实 SKILLBUS_STATE_DIR。

用法：python3 self_test.py   # 或用本包 requirements.txt 提供的 pytest
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import skillbus  # noqa: E402


class IsolationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="skillbus-selftest-")
        self._root = Path(self._tmp.name)
        self._old_state_dir = os.environ.get("SKILLBUS_STATE_DIR")
        os.environ["SKILLBUS_STATE_DIR"] = str(self._root)
        # 让 skillbus 模块重新读取状态目录
        skillbus.STATE_DIR = Path(os.environ["SKILLBUS_STATE_DIR"])
        skillbus.STATE_FILE = skillbus.STATE_DIR / "state.json"

    def tearDown(self) -> None:
        if self._old_state_dir is None:
            os.environ.pop("SKILLBUS_STATE_DIR", None)
        else:
            os.environ["SKILLBUS_STATE_DIR"] = self._old_state_dir
        self._tmp.cleanup()

    def test_empty_state_no_file(self) -> None:
        st = skillbus._load_state()
        self.assertEqual(st["state_version"], 1)
        self.assertEqual(st["projects"], {})

    def test_push_and_get_roundtrip_provenance(self) -> None:
        got = skillbus.get_project_state("酒店A", building="5#", floor="三层")
        self.assertEqual(got["entries"], {})
        pushed = skillbus.push_project_state(
            "酒店A", {"schema": "qto-project/v1", "draft_type": "概算底稿", "_id": "c1"},
            building="5#", floor="三层", source_skill="tujian-suanliang")
        self.assertTrue(pushed["saved"])
        self.assertEqual(pushed["project_key"], "酒店A__slash__5#__slash__三层")
        raw = json.loads(skillbus.STATE_FILE.read_text(encoding="utf-8"))
        entry = raw["projects"]["酒店A__slash__5#__slash__三层"]["c1"]
        self.assertEqual(entry["_provenance"]["source_skill"], "tujian-suanliang")
        self.assertEqual(entry["_provenance"]["schema"], "qto-project/v1")

    def test_corrupted_state_degrades_without_clobber(self) -> None:
        skillbus.STATE_DIR.mkdir(parents=True, exist_ok=True)
        skillbus.STATE_FILE.write_text("{broken", encoding="utf-8")
        st = skillbus._load_state()
        self.assertEqual(st.get("_corrupted"), str(skillbus.STATE_FILE))
        # 读坏文件不覆盖原文件
        self.assertEqual(skillbus.STATE_FILE.read_text(encoding="utf-8"), "{broken")

    def test_list_skills_missing_dir_empty(self) -> None:
        self.assertEqual(skillbus.list_skills(self._root / "nonexistent"), [])

    def test_resolve_contract_registered_and_unknown(self) -> None:
        ok = skillbus.resolve_contract("cad-file-reader/v0")
        self.assertTrue(ok["resolved"])
        self.assertEqual(ok["spec"], "cad-file-reader/v0")
        ok2 = skillbus.resolve_contract("qto-project/v1")
        self.assertTrue(ok2["resolved"])
        no = skillbus.resolve_contract("unknown-skill")
        self.assertFalse(no["resolved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
