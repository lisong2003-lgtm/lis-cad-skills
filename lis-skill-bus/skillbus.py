#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lis-skill-bus v0.1.0 —— 本地 Skill 联动总线（纯 stdlib，无网络，跨平台）。

职责：
  1) 统一存取项目状态（断点续上）
  2) 解析 skill 契约 schema（resolve_contract）
  3) 枚举本机已安装 skill 与版本（list_skills）

双模式：
  python3 skillbus.py serve            # MCP stdio server（新行分隔 JSON-RPC）
  python3 skillbus.py <CLI 子命令>     # 不装 MCP 时直接命令行降级可用

红线：不访问网络；公司数据只落本机 SKILLBUS_STATE_DIR。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

VERSION = "0.1.0"

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
DEFAULT_SKILLS_DIR = CODEX_HOME / "skills"
STATE_DIR = Path(os.environ.get("SKILLBUS_STATE_DIR", CODEX_HOME / "skills" / ".skillbus"))
STATE_FILE = STATE_DIR / "state.json"
REGISTRY = {
    "cad-file-reader": "cad-file-reader/v0",
    "shangwu-suanliang": "qto-project/v1",
    "tujian-suanliang": "qto-project/v1",
    "anzhuang-suanliang": "qto-project/v1",
    "zhuangshi-suanliang": "qto-project/v1",
    "yuanlin-suanliang": "qto-project/v1",
}
CONTRACT_SCHEMA_CATALOG = {
    "cad-file-reader/v0": {
        "spec": "cad-file-reader/v0",
        "description": "识图候选契约：置信分层 + 复核原因 + 证据坐标 + 来源文件；不含最终工程量。",
        "required_top": ["schema", "producer", "source"],
        "note": "详见 cad-file-reader/scripts/cad_contract.py 的 CONTRACT_SCHEMA；详细字段以完整包为准。",
    },
    "qto-project/v1": {
        "spec": "qto-project/v1",
        "description": "算量五件套联动契约：项目主键/草稿类型/专业 + cad-file-reader 候选。",
        "required_top": ["qto_spec", "project_key", "draft_type", "specialty"],
        "note": "详见 cad-file-reader/schemas/qto-project-v1.schema.json。",
    },
}


# --------------------------------------------------------------------------- #
# 状态文件（原子写，简单可靠）
# --------------------------------------------------------------------------- #
def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"state_version": 1, "projects": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # 状态损坏时降级为空库，不覆盖原文件；调用方自行决定是否重写。
        return {"state_version": 1, "projects": {}, "_corrupted": str(STATE_FILE)}


def _project_key(state: dict, project: str, building: str = "", floor: str = "") -> str:
    parts = [p for p in (project, building, floor) if p]
    return "__slash__".join(parts) if parts else "__project__"


def get_project_state(project: str, building: str = "", floor: str = "") -> dict:
    state = _load_state()
    key = _project_key(state, project, building, floor)
    return {"project_key": key, "entries": state["projects"].get(key, {})}


def push_project_state(project: str, entry: dict, building: str = "", floor: str = "",
                       source_skill: str = "unknown", replace: bool = False) -> dict:
    state = _load_state()
    key = _project_key(state, project, building, floor)
    bucket = state["projects"].setdefault(key, {})
    entry = dict(entry or {})
    entry.setdefault("_provenance", {})
    entry["_provenance"].update({
        "source_skill": source_skill,
        "schema": entry.get("schema") or REGISTRY.get(source_skill, "unknown"),
        "pushed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    # 以 entry._id 为粒度；没有 _id 时整条替换/合并。
    eid = entry.get("_id")
    if eid:
        old = bucket.get(eid)
        bucket[eid] = entry if replace else {**(old or {}), **entry}
        entry = bucket[eid]
    elif replace:
        bucket["_last"] = entry
    else:
        latest = bucket.get("_last", {})
        entry = {**latest, **entry}
        bucket["_last"] = entry
    _atomic_write_text(STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))
    return {"project_key": key, "saved": True, "entry_id": eid or "_last", "count": len(bucket)}


def list_skills(skills_dir: Path = DEFAULT_SKILLS_DIR) -> list:
    out = []
    if not skills_dir.exists():
        return out
    for child in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        name = child.name
        ver = ""
        man = child / "manifest.json"
        if man.exists():
            try:
                data = json.loads(man.read_text(encoding="utf-8"))
                ver = str(data.get("version", ""))
                name = str(data.get("name", child.name))
            except (json.JSONDecodeError, OSError):
                pass
        out.append({"name": name, "version": ver, "path": str(child),
                    "contract": REGISTRY.get(child.name, "")})
    return out


def resolve_contract(name: str, version: str = "") -> dict:
    key = name
    if version and version not in name:
        key = f"{name}/{version}"
    cat = CONTRACT_SCHEMA_CATALOG.get(name) or CONTRACT_SCHEMA_CATALOG.get(key)
    if cat is None:
        return {"resolved": False, "name": name, "version": version,
                "reason": "未登记契约；可在平台完整包 schemas/ cad-contract-catalog.json 查询"}
    return {"resolved": True, "name": name, "version": version, "spec": cat.get("spec"),
            "description": cat.get("description"), "required_top": cat.get("required_top"),
            "note": cat.get("note")}


# --------------------------------------------------------------------------- #
# 简易 stdio MCP server（行分隔 JSON-RPC，兼容当前 MCP stdio 传输）
# --------------------------------------------------------------------------- #
def _reply(req: dict, result: dict = None, error: dict = None) -> str:
    body = {"jsonrpc": "2.0", "id": req.get("id")}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    return json.dumps(body, ensure_ascii=False)


def _tool_router(name: str, args: dict) -> dict:
    if name == "list_skills":
        return {"skills": list_skills()}
    if name == "get_project_state":
        return get_project_state(str(args.get("project", "")),
                                 str(args.get("building", "")),
                                 str(args.get("floor", "")))
    if name == "push_project_state":
        return push_project_state(
            str(args.get("project", "")),
            args.get("entry") or {},
            building=str(args.get("building", "")),
            floor=str(args.get("floor", "")),
            source_skill=str(args.get("source_skill", "unknown")),
            replace=bool(args.get("replace", False)),
        )
    if name == "resolve_contract":
        return resolve_contract(str(args.get("name", "")), str(args.get("version", "") or ""))
    raise ValueError(f"unknown tool: {name}")


def serve() -> int:
    tools = [
        {"name": "list_skills", "description": "枚举本机已安装 Skill 与版本", "inputSchema": {"type": "object"}},
        {"name": "get_project_state", "description": "读取指定项目的共享状态", "inputSchema": {
            "type": "object", "properties": {
                "project": {"type": "string"}, "building": {"type": "string"}, "floor": {"type": "string"}}}},
        {"name": "push_project_state", "description": "写入指定项目的共享状态（原子写）", "inputSchema": {
            "type": "object", "properties": {
                "project": {"type": "string"}, "building": {"type": "string"}, "floor": {"type": "string"},
                "source_skill": {"type": "string"}, "replace": {"type": "boolean"}, "entry": {"type": "object"}}}},
        {"name": "resolve_contract", "description": "解析 skill 契约 schema 元数据", "inputSchema": {
            "type": "object", "properties": {"name": {"type": "string"}, "version": {"type": "string"}}}},
    ]
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = req.get("method")
        if method == "initialize":
            sys.stdout.write(_reply(req, {"protocolVersion": "2024-11-05",
                                          "capabilities": {"tools": {}},
                                          "serverInfo": {"name": "lis-skill-bus", "version": VERSION}}))
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            sys.stdout.write(_reply(req, {"tools": tools}))
        elif method == "tools/call":
            try:
                r = _tool_router(req.get("params", {}).get("name", ""),
                                 req.get("params", {}).get("arguments") or {})
                sys.stdout.write(_reply(req, {"content": [{"type": "text",
                                                           "text": json.dumps(r, ensure_ascii=False, indent=2)}],
                                             "isError": False}))
            except Exception as exc:  # noqa: BLE001
                sys.stdout.write(_reply(req, error={"code": -32000, "message": str(exc)}))
        sys.stdout.flush()
    return 0


# --------------------------------------------------------------------------- #
# CLI 降级模式
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="lis-skill-bus CLI 降级入口")
    ap.add_argument("command", choices=["serve", "list-skills", "get-project-state",
                                        "push-project-state", "resolve-contract"])
    ap.add_argument("--project", default="", help="项目标识")
    ap.add_argument("--building", default="", help="楼栋（可选）")
    ap.add_argument("--floor", default="", help="楼层（可选）")
    ap.add_argument("--skill", default="", help="skill 名称")
    ap.add_argument("--contract", default="", help="契约名，如 cad-file-reader/v0")
    ap.add_argument("--entry-file", default="", help="push 模式的状态 JSON 文件")
    args = ap.parse_args()

    if args.command == "serve":
        return serve()
    if args.command == "list-skills":
        print(json.dumps(list_skills(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "get-project-state":
        print(json.dumps(get_project_state(args.project, args.building, args.floor),
                         ensure_ascii=False, indent=2))
        return 0
    if args.command == "resolve-contract":
        print(json.dumps(resolve_contract(args.contract), ensure_ascii=False, indent=2))
        return 0
    if args.command == "push-project-state":
        if not args.entry_file:
            print(json.dumps({"error": "需要 --entry-file"}, ensure_ascii=False), file=sys.stderr)
            return 2
        entry = json.loads(Path(args.entry_file).read_text(encoding="utf-8"))
        print(json.dumps(push_project_state(args.project, entry, args.building, args.floor,
                                            source_skill=args.skill), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
