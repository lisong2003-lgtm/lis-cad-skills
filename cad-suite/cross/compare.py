#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross/compare.py —— 跨专业校对公共引擎 CLI 接线。

把 engine.CrossEngine 从纯库变成可执行入口：
吃两份（或以上）构件清单 JSON → 构造 Member → 全专业对两两比较 → 输出 json/md。

输入格式（每份一个文件，跨专业统一中间格式）：
    {
      "source": "结构-8.600梁平法施工图",
      "members": [
        {"project": "...", "floor": "8.600", "grid": "A-C/1-3",
         "name": "KL1", "category": "梁", "attrs": {"截面": "300x600"},
         "bbox": [x1, y1, x2, y2] | null, "source": "图框3"}
      ],
      "relations": [ {"from": [project, floor, grid, name],
                      "to": [project, floor, grid, name]} ]
    }
bbox / relations 均可省略（缺坐标时引擎自动降级为 key 级并标 no_evidence）。

用法
    python3 cross/compare.py a.json b.json [-o 输出前缀] [--place-tol 5000]
    python3 cross/compare.py a.json b.json --format md

诚实边界：2D 一致性倾向提示 / 校对辅助，非 BIM 碰撞检测；
输出疑似冲突清单 + 坐标证据，供人工复核，final_quantity=false。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import CrossEngine, Member  # noqa: E402


def load_side(path: Path) -> tuple[str, list[Member], list[dict]]:
    """读一份构件清单，返回 (来源名, members, relations)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):  # 允许直接给 members 数组
        data = {"source": path.stem, "members": data}
    src = str(data.get("source") or path.stem)
    members = [
        Member(
            m.get("project", ""), m.get("floor", ""), m.get("grid", ""),
            m.get("name", ""), m.get("category", ""),
            attrs=m.get("attrs"), source=m.get("source_text", ""),
            bbox=m.get("bbox"),
        )
        for m in data.get("members", [])
    ]
    return src, members, list(data.get("relations") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description="跨专业校对公共引擎 CLI（2D 一致性倾向提示，非 BIM 碰撞检测）")
    ap.add_argument("inputs", nargs="+", help="构件清单 JSON（2 份起，逐对两两比较）")
    ap.add_argument("-o", "--out-prefix", default=None, help="输出前缀（写 .json 与 .md；缺省只打印 md）")
    ap.add_argument("--place-tol", type=float, default=None,
                    help="位置核对容差，图形单位（默认引擎内置 5000）")
    args = ap.parse_args()

    if len(args.inputs) < 2:
        print("[错误] 至少需要 2 份构件清单才能两两比较", file=sys.stderr)
        return 2

    sides = [load_side(Path(p)) for p in args.inputs]
    print(f"[跨专业校对] {len(sides)} 侧，共 {sum(len(m) for _, m, _ in sides)} 构件，"
          f"比较 {len(sides) * (len(sides) - 1) // 2} 对")
    eng = CrossEngine(place_tol=args.place_tol)
    results = []
    for i in range(len(sides)):
        for j in range(i + 1, len(sides)):
            sa, ma, ra = sides[i]
            sb, mb, _ = sides[j]
            res = eng.compare(ma, mb, side_a=sa, side_b=sb, relations=ra)
            results.append(res)
            c = res.counts()
            print(f"  {sa} × {sb}: pass {c['pass']} / warn {c['warn']} / conflict {c['conflict']}")

    md = "\n".join(r.to_md() for r in results)
    payload = {"schema": "cad-cross-compare-batch/v1", "final_quantity": False,
               "pairs": [r.to_json() for r in results],
               "boundary": "2D 一致性倾向提示，非 BIM 碰撞检测；供人工复核"}
    if args.out_prefix:
        out = Path(args.out_prefix)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        out.with_suffix(".md").write_text(md, encoding="utf-8")
        print(f"已写出 {out}.json / {out.with_suffix('.md')}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
