#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""runtime_env.sh / .sh 入口回归：缺解释器时必须干净失败，不能 exec 空路径。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
EXAMPLE = SKILL / "examples" / "minimal.steel.json"
BASH = shutil.which("bash") or "/bin/bash"


def _env(path_value=None, extra=None):
    keys = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SystemRoot", "ComSpec")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    if path_value is not None:
        env["PATH"] = path_value
    env.update(extra or {})
    return env


def _run(args, cwd=SKILL, path_value=None, extra=None):
    return subprocess.run(
        [BASH, *map(str, args)], cwd=str(cwd), env=_env(path_value, extra),
        capture_output=True, text=True, timeout=180, errors="replace")


def _fake_bin(td: Path, fake_python_version: str | None = None) -> Path:
    """只保留 dirname（runtime_env 解析路径要用），可选放一个假 python3。"""
    bindir = td / "bin"
    bindir.mkdir()
    (bindir / "dirname").symlink_to("/usr/bin/dirname")
    if fake_python_version:
        py = bindir / "python3"
        py.write_text('#!/bin/sh\necho "%s"\n' % fake_python_version, encoding="ascii")
        py.chmod(0o755)
    return bindir


@unittest.skipIf(sys.platform == "win32", "shell entry points are POSIX only")
class TestRuntimeEnv(unittest.TestCase):
    def test_missing_python_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            bindir = _fake_bin(Path(td))
            p = _run([SCRIPTS / "steel_tonnage.sh", "--check-deps"],
                     path_value=str(bindir))
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertIn("未找到 Python 3.9+", p.stderr)
            self.assertNotIn("not found", p.stderr)
            self.assertEqual(p.stdout.strip(), "")

    def test_python_too_old_is_reported_with_version(self):
        with tempfile.TemporaryDirectory() as td:
            bindir = _fake_bin(Path(td), "2.7.18")
            p = _run([SCRIPTS / "steel_tonnage.sh", "--check-deps"],
                     path_value=str(bindir))
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertIn("未找到 Python 3.9+", p.stderr)
            self.assertIn("修复：", p.stderr)
            self.assertNotIn("not found", p.stderr)

    def test_statesync_missing_python_exits_2_without_exec_error(self):
        with tempfile.TemporaryDirectory() as td:
            bindir = _fake_bin(Path(td))
            p = _run([SCRIPTS / "gangjiegou_statesync.sh", "pull", "--project", "probe"],
                     path_value=str(bindir))
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertIn("运行时不可用", p.stderr)
            self.assertNotIn("not found", p.stderr)

    def test_normal_path_resolves_python_and_runs(self):
        p = _run([SCRIPTS / "steel_tonnage.sh", "--validate", EXAMPLE])
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertIn("契约体检", p.stdout)

    def test_source_exports_python_bin_even_under_set_u(self):
        snippet = ('set -u; source "%s"; printf "%%s|%%s" "$PYTHON_BIN" "$PYTHON_VERSION"'
                   % (SCRIPTS / "runtime_env.sh"))
        p = subprocess.run([BASH, "-c", snippet], capture_output=True, text=True,
                           timeout=60, errors="replace")
        self.assertEqual(p.returncode, 0, p.stderr)
        binary, _, version = p.stdout.partition("|")
        self.assertTrue(binary and os.path.isabs(binary), p.stdout)
        self.assertRegex(version, r"^3\.\d+\.")


class TestPackageCheck(unittest.TestCase):
    """--check-package：manifest 声明与包内文件必须一致（SkillHub 评估扣分点）。"""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "steel_tonnage.py"), "--check-package", *args],
            cwd=str(SKILL), env=_env(), capture_output=True, text=True,
            timeout=120, errors="replace")

    def test_real_skill_tree_is_complete(self):
        p = self._run()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("缺失 0 项", p.stdout)

    def test_missing_declared_file_is_reported(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SKILL.md").write_text("---\nversion: 9.9.9\n---\n", encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({
                "version": "9.9.9",
                "entry": "SKILL.md",
                "scripts": ["scripts/never_there.cmd"],
            }), encoding="utf-8")
            p = self._run("--package-root", str(root))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("scripts/never_there.cmd", p.stdout)

    def test_windows_optional_entry_is_hint_not_error(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "SKILL.md").write_text("---\nversion: 9.9.9\n---\n", encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({
                "version": "9.9.9",
                "entry": "SKILL.md",
                "scripts": ["SKILL.md"],
                "scripts_windows_optional": ["scripts/steel_tonnage.cmd"],
            }), encoding="utf-8")
            p = self._run("--package-root", str(root))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("Windows 入口未随包", p.stdout)


class TestToolScope(unittest.TestCase):
    def test_skill_declares_tool_scope(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        self.assertIn("allowed-tools: Read, Write, Bash", frontmatter)
        self.assertIn("不联网、不上传、不调用外部 API", text)


class TestStatesyncCoreLoading(unittest.TestCase):
    def test_environment_cannot_inject_core_module(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "injected.txt"
            fake = root / "fake-core"
            fake.mkdir()
            (fake / "cad_statesync_core.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
                "class Core:\n"
                "    pass\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["CAD_FILE_READER_SCRIPTS"] = str(fake)
            p = subprocess.run(
                [sys.executable, str(SCRIPTS / "gangjiegou_statesync.py"), "--help"],
                cwd=str(SKILL), env=env, capture_output=True, text=True,
                timeout=60, errors="replace",
            )
            self.assertFalse(marker.exists(), p.stdout + p.stderr)
            self.assertNotIn("CAD_FILE_READER_SCRIPTS", p.stderr)


if __name__ == "__main__":
    unittest.main()
