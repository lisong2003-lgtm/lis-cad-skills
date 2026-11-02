#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross/adapt.py —— 识图产物 → 跨专业校对清单适配器（转发层）。

0.2.4 起本文件不再自带实现，全部转发到 cad-clash-check/clash_adapt.py：
两侧曾各存一份，0.1.3 的 entity 通道只落到 clash 侧，导致同一对图纸
两个入口结果不一致。现在实现只留一份（唯一真相），本层只做 CLI 接线。

转发后行为与 cad-clash-check 完全一致，包括：
  ① 构件三分类 line / label / entity（entity = 圆等真几何实体）；
  ② geometry 线段取两端 bbox（不再退化成点）；
  ③ 设计说明句剔除（长文本 + 说明动词，避免大面积伪碰撞）；
  ④ 轴号就近 → 坐标桶的诚实分级。

用法
    python3 cross/adapt.py 识图.detail.structural.json -o 结构清单.json --project 某地块
    python3 cross/adapt.py 市政.detail.municipal.json -o 市政清单.json \
        --member-types components,municipal_geometry
    # 两个清单直接进比较：
    python3 cross/compare.py 结构清单.json 市政清单.json -o 对照结果

依赖 cad-clash-check；找不到时报错并给出安装指引，不静默降级。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clash_bridge  # noqa: E402


def _adapt():
    """取唯一实现的 adapt（延迟绑定，便于测试替换）。"""
    return clash_bridge.adapt_module().adapt


def adapt(data: dict, project: str = "", member_types: list[str] | None = None,
          axis_tol: float = None, bucket: float = None) -> dict:
    """识图产物 → {"source","members","relations"}（转发到 clash_adapt）。"""
    fn = _adapt()
    kw = {}
    if axis_tol is not None:
        kw["axis_tol"] = axis_tol
    if bucket is not None:
        kw["bucket"] = bucket
    return fn(data, project, member_types, **kw)


def main() -> int:
    ap = argparse.ArgumentParser(description="识图产物 → 跨专业校对清单 JSON（转发 cad-clash-check）")
    ap.add_argument("inputs", nargs="+", help="识图产物 JSON（structural/municipal 等）")
    ap.add_argument("-o", "--out-prefix", required=True, help="输出前缀（多输入时写 <前缀>-1.json …）")
    ap.add_argument("--project", default="", help="项目名（缺省取源文件名）")
    ap.add_argument("--member-types", default="members,components",
                    help="要转的构件数组字段，逗号分隔（默认 members,components）")
    ap.add_argument("--axis-tol", type=float, default=None, help="默认沿用 clash_adapt 内置值")
    ap.add_argument("--bucket", type=float, default=None, help="默认沿用 clash_adapt 内置值")
    args = ap.parse_args()

    try:
        home = clash_bridge.clash_home()
    except RuntimeError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2
    print(f"[cross/adapt] 实现来源：{home}")

    am = clash_bridge.adapt_module()
    types = [t.strip() for t in args.member_types.split(",") if t.strip()]
    for i, p in enumerate(args.inputs, 1):
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"[错误] 读 {p} 失败：{e}", file=sys.stderr)
            return 2
        kw = {}
        if args.axis_tol is not None:
            kw["axis_tol"] = args.axis_tol
        if args.bucket is not None:
            kw["bucket"] = args.bucket
        cl = am.adapt(data, args.project, types, **kw)
        suffix = f"-{i}" if len(args.inputs) > 1 else ""
        out = Path(f"{args.out_prefix}{suffix}.json")
        out.write_text(json.dumps(cl, ensure_ascii=False, indent=1), encoding="utf-8")
        n_axis = sum(1 for m in cl["members"] if not m["grid"].startswith("pos:"))
        n_kind = {}
        for m in cl["members"]:
            n_kind[m.get("kind", "?")] = n_kind.get(m.get("kind", "?"), 0) + 1
        kind_txt = " ".join(f"{k}{v}" for k, v in sorted(n_kind.items()))
        print(f"{p} → {out}：{len(cl['members'])} 构件"
              f"（真轴号 {n_axis} / 坐标桶 {len(cl['members']) - n_axis}"
              f"{'；' + kind_txt if kind_txt else ''}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
