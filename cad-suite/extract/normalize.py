#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/normalize.py —— 三档候选 → 结构化表（主航道第一步）。

方案定位（§五 阶段1）：用户要的是表，不是报告。本模块把
cad-file-reader contract（cad-file-reader/v0）的 confirmed/inferred/review
三档候选收敛成「类别 × 规格 × 数量」的干净结构化表（json/csv/md）。

置信档口径（confidence 为 contract _confidence 归一后的 0~1 浮点）：
  confirmed  无 review_reasons 且 confidence >= 0.85（或 status=candidate 且高置信）
  inferred   无 review_reasons 且 confidence < 0.85
  review     有 review_reasons 或 status=review —— 永不进数量合计，只进复核清单

红线：输出标 final_quantity=false；数量合计只统计 confirmed（inferred 单列），
不把候选毛量冒充结算量。

输入
  --contract   cad-file-reader contract JSON（可多个，逗号分隔）
  --scan       可选，cad_scan.json（members 的 count/est 作为图面索引旁证列）
  --out-prefix 输出前缀（.json/.csv/.md）

用法
  python3 extract/normalize.py --contract a.json,b.json --out-prefix 提取表
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path

CONFIRMED_MIN = 0.85


def tier_of(cand: dict) -> str:
    """按契约口径判三档。review 永远优先。"""
    if cand.get("status") == "review" or cand.get("review_reasons"):
        return "review"
    conf = cand.get("confidence")
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.0
    return "confirmed" if conf >= CONFIRMED_MIN else "inferred"


def load_candidates(contract: dict) -> list[dict]:
    """从 contract JSON 展平候选行（candidates + review_candidates）。"""
    c = contract.get("contract") if isinstance(contract.get("contract"), dict) else contract
    rows: list[dict] = []
    for section, payload in (c.get("sections") or {}).items() if isinstance(c.get("sections"), dict) else []:
        for cand in (payload.get("candidates") or []):
            rows.append(_row(section, cand))
    for cand in (c.get("candidates") or []):
        rows.append(_row(str(cand.get("section") or cand.get("kind") or "未分类"), cand))
    for cand in (c.get("review_candidates") or []):
        r = _row(str(cand.get("section") or cand.get("kind") or "未分类"), cand)
        r["tier"] = "review"
        rows.append(r)
    return rows


def _row(section: str, cand: dict) -> dict:
    conf = cand.get("confidence")
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "section": section,
        "kind": str(cand.get("kind") or ""),
        "text": str(cand.get("text") or ""),
        "value": cand.get("value"),
        "unit": str(cand.get("unit") or ""),
        "confidence": conf,
        "status": cand.get("status") or "",
        "review_reasons": list(cand.get("review_reasons") or []),
        "tier": tier_of(cand),
        "source": str(cand.get("source") or ""),
    }


def _spec_key(r: dict) -> tuple[str, str, str]:
    """规格 = text（识别原文）。类别 = kind 优先、section 兜底。"""
    kind = r["kind"] or r["section"] or "未分类"
    return (kind, r["text"], r["unit"])


def aggregate(rows: list[dict]) -> dict:
    """按（类别，规格，单位）归并：confirmed 计数、inferred 计数、review 计数。"""
    agg: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        key = _spec_key(r)
        rec = agg.setdefault(key, {"confirmed": 0, "inferred": 0, "review": 0,
                                   "values": [], "review_reasons": set(),
                                   "confidence_max": 0.0, "sources": set()})
        rec[r["tier"]] += 1
        if r["tier"] != "review" and isinstance(r["value"], (int, float)) \
                and not isinstance(r["value"], bool):
            rec["values"].append(float(r["value"]))
        rec["review_reasons"].update(r["review_reasons"])
        rec["confidence_max"] = max(rec["confidence_max"], r["confidence"])
        if r["source"]:
            rec["sources"].add(r["source"])
    out_rows = []
    for (kind, spec, unit), rec in sorted(agg.items()):
        vals = rec["values"]
        out_rows.append({
            "构件类别": kind,
            "规格": spec,
            "单位": unit,
            "确认次数": rec["confirmed"],
            "推断次数": rec["inferred"],
            "复核次数": rec["review"],
            "数量合计": round(sum(vals), 3) if vals else None,
            "最高置信": round(rec["confidence_max"], 2),
            "复核原因": ";".join(sorted(rec["review_reasons"])),
            "来源": ";".join(sorted(rec["sources"]))[:120],
        })
    summary = {
        "候选行数": len(rows),
        "类别数": len({r["kind"] or r["section"] for r in rows}) if rows else 0,
        "三档占比": _tier_ratio(rows),
        "final_quantity": False,
    }
    return {"summary": summary, "rows": out_rows}


def _tier_ratio(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"confirmed": 0.0, "inferred": 0.0, "review": 0.0}
    cnt = {"confirmed": 0, "inferred": 0, "review": 0}
    for r in rows:
        cnt[r["tier"]] += 1
    return {k: round(v / n, 3) for k, v in cnt.items()}


def render_md(out: dict, title: str) -> str:
    md = StringIO()
    s = out["summary"]
    md.write(f"# {title}（三档候选 → 结构化表）\n\n")
    md.write("> **口径声明**：final_quantity=false。数量合计只累计带数值的确认档候选；"
             "复核档永不进合计，仅进复核原因列。\n\n")
    r = s["三档占比"]
    md.write(f"- 候选行数 **{s['候选行数']}**，类别数 **{s['类别数']}**；"
             f"三档占比 confirmed **{r['confirmed']:.0%}** / inferred **{r['inferred']:.0%}**"
             f" / review **{r['review']:.0%}**\n\n")
    if not out["rows"]:
        md.write("（无候选）\n")
        return md.getvalue()
    cols = ["构件类别", "规格", "单位", "确认次数", "推断次数", "复核次数",
            "数量合计", "最高置信", "复核原因"]
    md.write("| " + " | ".join(cols) + " |\n")
    md.write("|" + "---|" * len(cols) + "\n")
    for row in out["rows"]:
        cells = []
        for c in cols:
            v = row.get(c)
            cells.append("" if v is None else str(v))
        md.write("| " + " | ".join(cells) + " |\n")
    return md.getvalue()


def build(contract_paths: list[str], out_prefix: str,
          scan_path: str | None = None, fmt: str = "all") -> Path:
    rows: list[dict] = []
    n_files = 0
    for p in contract_paths:
        for one in str(p).split(","):
            one = one.strip()
            if not one:
                continue
            data = json.load(open(one, encoding="utf-8"))
            rows.extend(load_candidates(data))
            n_files += 1
    if not rows:
        raise SystemExit("❌ contract 里没有任何候选（candidates/review_candidates 均为空）")
    out = aggregate(rows)
    out["summary"]["来源文件数"] = n_files
    if scan_path:
        scan = json.load(open(scan_path, encoding="utf-8"))
        members = scan.get("members") or {}
        scan_idx = {}
        for cat, codes in members.items():
            if isinstance(codes, dict):
                for code, info in codes.items():
                    if isinstance(info, dict):
                        scan_idx[(cat, code)] = info.get("count") or info.get("est") or 0
        out["summary"]["图面索引编号数"] = len(scan_idx)
    out_base = Path(out_prefix)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("all", "json"):
        Path(str(out_base) + ".json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if fmt in ("all", "csv"):
        with Path(str(out_base) + ".csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(out["rows"][0].keys()) if out["rows"] else ["构件类别"])
            w.writeheader()
            w.writerows(out["rows"])
    if fmt in ("all", "md"):
        Path(str(out_base) + ".md").write_text(
            render_md(out, out_base.name), encoding="utf-8")
    r = out["summary"]["三档占比"]
    print(f"[提取成表] 候选 {out['summary']['候选行数']} 行 → {len(out['rows'])} 条规格；"
          f"三档 confirmed {r['confirmed']:.0%} / inferred {r['inferred']:.0%} / review {r['review']:.0%}")
    return out_base


def main() -> None:
    raw = sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Extract normalize: contract candidates -> clean table")
    ap.add_argument("--contract", required=True,
                    help="cad-file-reader contract JSON，多个用逗号分隔")
    ap.add_argument("--scan", default=None, help="可选 cad_scan.json 旁证")
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--fmt", default="all", choices=["all", "json", "csv", "md"])
    a = ap.parse_args(raw)
    build([a.contract], a.out_prefix, scan_path=a.scan, fmt=a.fmt)


if __name__ == "__main__":
    main()
