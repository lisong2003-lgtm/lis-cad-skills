#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cad-suite 从零安装自检。

验收口径（方案 §五 阶段3）：从零安装单一包，无外部依赖即可跑通核心用例。
检查项：
  1. 顶层 manifest.json 合法且登记的模块/脚本/测试都存在
  2. 七个 modules 目录齐全（lis-skill-bus 无 scripts/ 按根目录探测）
  3. extract 三个模块可 import
  4. extract 全部测试通过
  5. 嵌套模块的 SKILL.md 与 manifest 可被找到（模块完整性）

退出码 0=通过；任何一项失败非零并打印明细。
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent
EXPECTED_MODULES = ["cad-file-reader", "tujian-suanliang", "zhuangshi-suanliang",
                    "anzhuang-suanliang", "yuanlin-suanliang", "lis-skill-bus",
                    "cad-clash-check"]


def main() -> int:
    fails: list[str] = []

    # 1. manifest
    mf_path = SUITE / "manifest.json"
    try:
        mf = json.loads(mf_path.read_text(encoding="utf-8"))
        print(f"[1] manifest.json OK（v{mf['version']}，红线 {len(mf.get('red_lines', []))} 条）")
    except Exception as e:
        print(f"[1] manifest.json FAIL: {e}")
        return 1

    # 2. 七模块
    missing = [m for m in mf.get("modules", []) if not (SUITE / m["entry"]).exists()]
    for exp in EXPECTED_MODULES:
        if not (SUITE / "modules" / exp).exists():
            missing.append(f"modules/{exp}")
    if missing:
        fails.append(f"模块缺失: {missing}")
    else:
        print(f"[2] 七模块齐全（{len(EXPECTED_MODULES)} 个）")

    # 3. extract import
    sys.path.insert(0, str(SUITE / "extract"))
    for mod in ("normalize", "confidence", "merge_floor", "benchmark"):
        try:
            __import__(mod)
        except Exception as e:
            fails.append(f"extract/{mod} import 失败: {e}")
    if not any("import 失败" in f for f in fails):
        print("[3] extract 四模块 import OK")

    # 4. 测试
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=SUITE / "extract", capture_output=True, text=True, timeout=300)
    tail = (r.stderr or r.stdout).strip().splitlines()
    ran = next((ln for ln in tail if ln.startswith("Ran")), "Ran ?")
    ok = r.returncode == 0
    print(f"[4] extract 测试 {ran} {'OK' if ok else 'FAILED'}")
    if not ok:
        fails.append("extract 测试未全绿")

    # 5. 模块完整性
    incomplete = []
    for m in EXPECTED_MODULES:
        base = SUITE / "modules" / m
        if not (base / "SKILL.md").exists():
            incomplete.append(f"{m}/SKILL.md")
        if m != "lis-skill-bus" and not (base / "manifest.json").exists():
            incomplete.append(f"{m}/manifest.json")
    if incomplete:
        fails.append(f"模块文件不完整: {incomplete}")
    else:
        print("[5] 模块 SKILL.md/manifest 完整（lis-skill-bus 按根目录探测）")

    if fails:
        print("\n❌ 自检未通过：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n✅ cad-suite 从零安装自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
