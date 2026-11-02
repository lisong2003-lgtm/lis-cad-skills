#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""extract/merge_floor.py —— 跨图按楼层归并成项目级表。

方案定位（§五 阶段1）：cad_batch 按目录逐张扫，不懂「哪张是三层梁图」；
本模块补上串联——多份 cad_scan.json 归并成「楼层 × 类别 × 编号」项目级表。

楼层来源（优先级）：
  1. --floor-map 显式指定：文件名=楼层名，如 "s5_2=2.800梁板"
  2. cad_scan.meta.floor_label（s5 流水线写入时自带）
  3. 文件名/图名中识别「±?\d+(\.\d+)?」标高样式（8.600 / -0.100 / 屋面）

归并规则（同楼层同类别同编号）：
  规格一致 → 合并计数（跨图重复标注自动去重）
  规格冲突 → state=conflict，列出各图规格（审计发现，不硬凑）
  单图独有 → 正常收录

输出 json/csv/md，final_quantity=false。

用法
  python3 extract/merge_floor.py --scan s5_1/cad_scan.json,s5_2/cad_scan.json \
      --out-prefix 项目归并
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from io import StringIO
from pathlib import Path

FLOOR_DECIMAL_RE = re.compile(r"[-±+]?\d+\.\d+")
FLOOR_INT_RE = re.compile(r"[-±+]?\d+")
SECTION_NORM = str.maketrans({"X": "x", "×": "x", " ": "", "Ｘ": "x", "＊": "x"})


def norm_section(s: str) -> str:
    """截面归一：大小写/乘号/空格（与 cad_member_audit 同口径）。"""
    return str(s or "").strip().translate(SECTION_NORM)


def floor_of(path: Path, scan: dict, floor_map: dict[str, str] | None) -> str:
    fm = floor_map or {}
    if path.name in fm:
        return fm[path.name]
    label = (scan.get("meta") or {}).get("floor_label")
    if label:
        return str(label)
    m = FLOOR_DECIMAL_RE.search(path.stem)
    if m:
        return m.group(0)
    ints = FLOOR_INT_RE.findall(path.stem)
    return ints[-1] if ints else path.stem


def _iter_members(scan: dict):
    """yield (类别, 编号, info)。"""
    for cat, codes in (scan.get("members") or {}).items():
        if isinstance(codes, dict):
            for code, info in codes.items():
                if isinstance(info, dict):
                    yield str(cat), str(code), info


def merge(scans: dict[str, dict], floor_map: dict[str, str] | None = None) -> dict:
    """scans: {文件名: cad_scan dict} → 项目级归并。"""
    # (楼层, 类别, 编号) → {图名: 规格}
    index: dict[tuple[str, str, str], dict[str, str]] = {}
    counts: dict[tuple[str, str, str], int] = {}
    for fname, scan in scans.items():
        if fname in (floor_map or {}):
            floor = floor_map[fname]  # 全路径键优先
        else:
            floor = floor_of(Path(fname), scan, floor_map)
        for cat, code, info in _iter_members(scan):
            key = (floor, cat, code)
            sizes = [norm_section(s) for s in (info.get("sizes") or []) if s]
            spec = sizes[0] if sizes else ""
            prev = index.setdefault(key, {})
            if spec and spec not in prev:
                prev[fname] = spec
            counts[key] = counts.get(key, 0) + int(info.get("count") or 0)
    rows = []
    conflict_n = 0
    for (floor, cat, code), specs in sorted(index.items()):
        uniq = sorted(set(specs.values()))
        if len(uniq) > 1:
            state = "conflict"
            conflict_n += 1
        else:
            state = "ok" if uniq else "no_spec"
        rows.append({
            "楼层": floor, "构件类别": cat, "编号": code,
            "规格": uniq[0] if len(uniq) == 1 else " / ".join(uniq),
            "状态": state,
            "涉及图数": len(specs),
            "标注计数": counts.get((floor, cat, code), 0),
            "冲突明细": ";".join(f"{k}={v}" for k, v in sorted(specs.items()))
            if state == "conflict" else "",
        })
    floors = sorted({r["楼层"] for r in rows})
    summary = {
        "文件数": len(scans),
        "楼层数": len(floors),
        "楼层": floors,
        "编号行数": len(rows),
        "冲突数": conflict_n,
        "无规格数": sum(1 for r in rows if r["状态"] == "no_spec"),
        "final_quantity": False,
    }
    return {"summary": summary, "rows": rows}


def render_md(out: dict, title: str) -> str:
    md = StringIO()
    s = out["summary"]
    md.write(f"# {title}（跨图楼层归并）\n\n")
    md.write("> final_quantity=false；conflict=同编号跨图规格不一致，需人工复核。\n\n")
    md.write(f"- 文件 **{s['文件数']}** 份 → 楼层 **{s['楼层数']}** 层"
             f"（{'、'.join(s['楼层'][:8])}{'…' if len(s['楼层']) > 8 else ''}），"
             f"编号 **{s['编号行数']}** 个；冲突 **{s['冲突数']}**，无规格 **{s['无规格数']}**\n\n")
    if not out["rows"]:
        md.write("（无构件行）\n")
        return md.getvalue()
    cols = ["楼层", "构件类别", "编号", "规格", "状态", "涉及图数", "标注计数"]
    md.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
    for r in out["rows"]:
        md.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
    return md.getvalue()


def build(scan_paths: list[str], out_prefix: str,
          floor_map: dict[str, str] | None = None) -> Path:
    scans: dict[str, dict] = {}
    for p in scan_paths:
        for one in str(p).split(","):
            one = one.strip()
            if one:
                scans[one] = json.load(open(one, encoding="utf-8"))
    if not scans:
        raise SystemExit("❌ 没有可归并的 cad_scan.json")
    out = merge(scans, floor_map)
    out_base = Path(out_prefix)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    Path(str(out_base) + ".json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(str(out_base) + ".csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out["rows"][0].keys()) if out["rows"]
                           else ["楼层", "构件类别", "编号", "规格", "状态"])
        w.writeheader()
        w.writerows(out["rows"])
    Path(str(out_base) + ".md").write_text(render_md(out, out_base.name), encoding="utf-8")
    s = out["summary"]
    print(f"[楼层归并] {s['文件数']} 文件 → {s['楼层数']} 层 {s['编号行数']} 编号；"
          f"冲突 {s['冲突数']} 无规格 {s['无规格数']}")
    return out_base


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Merge multi-drawing scans into per-floor project table")
    ap.add_argument("--scan", required=True, help="cad_scan.json，多个用逗号分隔")
    ap.add_argument("--floor-map", default=None,
                    help='显式楼层映射，如 "s5_2.json=2.800梁板" 多个用逗号分隔')
    ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args()
    fm = None
    if a.floor_map:
        fm = {}
        for pair in a.floor_map.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                fm[k.strip()] = v.strip()
    build([a.scan], a.out_prefix, floor_map=fm)


if __name__ == "__main__":
    main()
