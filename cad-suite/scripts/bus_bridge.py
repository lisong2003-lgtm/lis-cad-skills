#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cad-suite ↔ lis-skill-bus 融合桥（只做缓存/溯源，不复制算法）。

背景：lis-skill-bus 本身没有 scripts/ 目录，历史 deps.py marker 探测会失败。
本桥把所有定位逻辑收敛到这里：
  ① 无 scripts/ 也能探测（用根目录 SKILL.md / manifest.json / skillbus.py 兜底）；
  ② modules/<slug>/ 嵌套保留后直接复用 bus 的 skillbus_client.py；
  ③ find-contract 提供「同图只解析一次」判据，provenance 提供溯源。

用法（脚本内调）：
    from bus_bridge import find_bus, find_contract, push_contract
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def find_bus_dir() -> Path | None:
    """定位 bus 根目录；scripts/ 缺失也能探测（根目录 SKILL.md/manifest/skillbus.py）。"""
    env_home = os.environ.get("SKILLBUS_HOME", "").strip()
    cands: list[Path] = []
    if env_home:
        cands.append(Path(env_home).expanduser())
    cands += [
        enum_dir / "lis-skill-bus"
        for enum_dir in (
            CODEX_HOME / "mcp_servers",
            CODEX_HOME / "skills" / ".skillbus",
            CODEX_HOME / "skills",
            _SUITE / "modules",
            Path.home() / ".workbuddy" / "skills",
            Path.home() / "Documents" / "GitHub" / "lis-cad-skills",
        )
    ]
    seen: set[str] = set()
    for d in cands:
        try:
            r = d.resolve()
        except OSError:
            continue
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        if not d.is_dir():
            continue
        # 根目录兜底：即使没有 scripts/，只要有 SKILL.md 或 skillbus.py 就算命中
        if (d / "SKILL.md").is_file() or (d / "skillbus.py").is_file():
            return d
    return None


def find_bus_client() -> Path | None:
    d = find_bus_dir()
    if d is None:
        return None
    for sub in ("skillbus_client.py", "skillbus.py"):
        p = d / sub
        if p.is_file():
            return p
    return None


def _state_dir_arg(state_dir: str | None) -> dict[str, str]:
    env = dict(os.environ)
    if state_dir:
        env["SKILLBUS_STATE_DIR"] = str(Path(state_dir).resolve())
    return env


def run_bus(args: list[str], state_dir: str | None = None) -> dict:
    client = find_bus_client()
    if client is None:
        return {"ok": False, "error": "未找到 lis-skill-bus（可设 SKILLBUS_HOME 指向 bus 根目录）"}
    try:
        cp = subprocess.run(
            [sys.executable, str(client), *args], capture_output=True, text=True,
            timeout=120, env=_state_dir_arg(state_dir))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if cp.returncode != 0:
        return {"ok": False, "error": (cp.stderr or cp.stdout or "").strip()[:500]}
    try:
        data = json.loads(cp.stdout)
        return {"ok": True, "data": data}
    except json.JSONDecodeError:
        return {"ok": False, "error": f"非法 JSON 输出：{(cp.stdout or '')[:200]}"}


def detect_bus(state_dir: str | None = None) -> dict:
    d = find_bus_dir()
    if d is None:
        return {"hit": False, "reason": "bus 未找到"}
    marker = ("scripts/" if (d / "scripts").is_dir()
              else "SKILL.md" if (d / "SKILL.md").is_file()
              else "skillbus.py")
    return {"hit": True, "root": str(d), "marker": marker,
            "has_scripts": (d / "scripts").is_dir(),
            "client": str(find_bus_client()) if find_bus_client() else None}


def find_contract(project: str, source_file: str, building: str = "", floor: str = "",
                  state_dir: str | None = None) -> dict:
    r = run_bus(["find-contract", "--project", project,
                 "--building", building, "--floor", floor,
                 "--source-file", source_file], state_dir=state_dir)
    return r


def provenance_summary(entry: dict | None) -> dict | None:
    """把 bus 条目归一成溯源摘要（供报告作答）。"""
    if not isinstance(entry, dict):
        return None
    prov = entry.get("_provenance") or {}
    src = entry.get("source") or {}
    return {
        "source_skill": prov.get("source_skill"),
        "schema": prov.get("schema") or entry.get("schema"),
        "source_file": prov.get("source_file") or src.get("file"),
        "source_sha256": prov.get("source_sha256") or src.get("sha256"),
        "pushed_at": prov.get("pushed_at"),
        "final_quantity": bool((entry.get("producer") or {}).get("final_quantity", False)),
        "review_required": bool((entry.get("review") or {}).get("review_required", False)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="cad-suite ↔ lis-skill-bus 融合桥")
    ap.add_argument("command", choices=["detect", "find", "provenance"])
    ap.add_argument("--project", default="", help="项目标识")
    ap.add_argument("--building", default="", help="楼栋（可选）")
    ap.add_argument("--floor", default="", help="楼层（可选）")
    ap.add_argument("--source-file", default="", help="原始图纸路径")
    ap.add_argument("--entry-file", default="", help="provenance 用的契约条目 JSON")
    ap.add_argument("--state-dir", default="", help="隔离测试用 SKILLBUS_STATE_DIR")
    args = ap.parse_args()

    if args.command == "detect":
        print(json.dumps(detect_bus(args.state_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "find":
        r = find_contract(args.project, args.source_file, args.building, args.floor, args.state_dir)
        if not r.get("ok"):
            print(json.dumps(r, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(json.dumps(r["data"], ensure_ascii=False, indent=2))
        return 0
    if args.command == "provenance":
        entry = json.loads(Path(args.entry_file).read_text(encoding="utf-8"))
        print(json.dumps(provenance_summary(entry), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
