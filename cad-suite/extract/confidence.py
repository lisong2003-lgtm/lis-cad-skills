#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/confidence.py —— 三档占比统计与复核清单（「准不准」的可度量基线）。

方案定位（§五 阶段1）：跑真图统计 confirmed/inferred/review 三档占比，
这是提取准确性的第一个可度量基线；复核档导出成清单交人工。

与 normalize.py 的分工：
  normalize  单批 contract → 一张结构化表（数据交付）
  confidence 多批 contract/scan → 项目级占比基线 + 复核清单（质量度量）

口径（与 contract 一致）：
  confirmed  confidence>=0.85 且无 review_reasons
  inferred   其余无 review_reasons
  review     有 review_reasons 或 status=review
基线 JSON 落盘后可作为后续版本回归对比（--baseline 上次基线 → 输出变化）。

用法
  python3 extract/confidence.py --contract a.json,b.json --out-prefix 置信基线
  python3 extract/confidence.py --contract new.json --baseline 置信基线.json --out-prefix 置信基线2
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import CONFIRMED_MIN, tier_of  # noqa: E402


def load_rows(contract_path: str) -> list[dict]:
    """读一份 contract，展平候选行（复用 normalize 的口径）。"""
    import normalize as N
    data = json.load(open(contract_path, encoding="utf-8"))
    return N.load_candidates(data)


def baseline(rows_by_file: dict[str, list[dict]]) -> dict:
    """项目级三档占比基线 + 复核清单。"""
    all_rows = []
    per_file = {}
    for f, rows in rows_by_file.items():
        cnt = {"confirmed": 0, "inferred": 0, "review": 0}
        for r in rows:
            cnt[r["tier"]] += 1
        n = len(rows)
        per_file[f] = {
            "候选行数": n,
            "三档占比": {k: round(v / n, 3) if n else 0.0 for k, v in cnt.items()},
        }
        for r in rows:
            d = dict(r)
            d["file"] = f
            all_rows.append(d)
    n = len(all_rows)
    cnt = {"confirmed": 0, "inferred": 0, "review": 0}
    for r in all_rows:
        cnt[r["tier"]] += 1
    review_rows = [
        {"文件": r["file"], "类别": r["kind"] or r["section"], "原文": r["text"],
         "置信": r["confidence"], "复核原因": ";".join(r["review_reasons"])}
        for r in all_rows if r["tier"] == "review"
    ]
    return {
        "schema": "cad-extract/confidence-v1",
        "final_quantity": False,
        "总量": n,
        "三档占比": {k: round(v / n, 3) if n else 0.0 for k, v in cnt.items()},
        "分文件": per_file,
        "review_清单": review_rows,
    }


def diff(new: dict, old: dict) -> dict:
    """与上次基线对比三档占比变化（正=变好方向按档位语义）。"""
    d = {}
    for k in ("confirmed", "inferred", "review"):
        d[k] = round(new["三档占比"][k] - old.get("三档占比", {}).get(k, 0.0), 3)
    return d


def render_md(out: dict, title: str, delta: dict | None = None) -> str:
    md = StringIO()
    md.write(f"# {title}（三档占比基线）\n\n")
    md.write("> 口径：confirmed>=0.85 且无复核原因；有 review_reasons/status=review 归复核档。"
             "final_quantity=false。\n\n")
    r = out["三档占比"]
    md.write(f"- 总候选 **{out['总量']}** 行：confirmed **{r['confirmed']:.1%}**"
             f" / inferred **{r['inferred']:.1%}** / review **{r['review']:.1%}**\n")
    if delta:
        md.write(f"- 对比上次基线：confirmed {delta['confirmed']:+.1%}"
                 f" / inferred {delta['inferred']:+.1%} / review {delta['review']:+.1%}\n")
    md.write(f"- 复核清单 **{len(out['review_清单'])}** 条（详见 csv）\n\n")
    md.write("| 文件 | 行数 | confirmed | inferred | review |\n|---|---|---|---|---|\n")
    for f, s in out["分文件"].items():
        p = s["三档占比"]
        md.write(f"| {f} | {s['候选行数']} | {p['confirmed']:.0%} | "
                 f"{p['inferred']:.0%} | {p['review']:.0%} |\n")
    return md.getvalue()


def build(contract_paths: list[str], out_prefix: str,
          baseline_path: str | None = None) -> Path:
    rows_by_file: dict[str, list[dict]] = {}
    for p in contract_paths:
        for one in str(p).split(","):
            one = one.strip()
            if one:
                rows_by_file[Path(one).name] = load_rows(one)
    if not rows_by_file:
        raise SystemExit("❌ 没有可统计的 contract 文件")
    out = baseline(rows_by_file)
    delta = None
    if baseline_path:
        old = json.load(open(baseline_path, encoding="utf-8"))
        delta = diff(out, old)
        out["对比上次基线"] = delta
    out_base = Path(out_prefix)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    Path(str(out_base) + ".json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    with Path(str(out_base) + "_复核清单.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["文件", "类别", "原文", "置信", "复核原因"])
        w.writeheader()
        w.writerows(out["review_清单"])
    Path(str(out_base) + ".md").write_text(
        render_md(out, out_base.name, delta), encoding="utf-8")
    r = out["三档占比"]
    print(f"[置信基线] {out['总量']} 行：confirmed {r['confirmed']:.1%} / "
          f"inferred {r['inferred']:.1%} / review {r['review']:.1%}"
          f"（复核 {len(out['review_清单'])} 条）")
    return out_base


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Confidence baseline: tier ratio + review checklist")
    ap.add_argument("--contract", required=True,
                    help="contract JSON，多个用逗号分隔")
    ap.add_argument("--baseline", default=None, help="上次基线 JSON（可选，输出对比）")
    ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args()
    build([a.contract], a.out_prefix, baseline_path=a.baseline)


if __name__ == "__main__":
    main()
