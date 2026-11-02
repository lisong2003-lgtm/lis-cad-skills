#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAD 融合流程调度器（cad-suite）。

一条命令走完 7 个阶段：
    s0 发现图纸 → s1 识图与契约 → s2 图纸关系 → s3 跨图聚合
    → s4 跨专业对照 → s5 算量派发（交接单） → s6 出表与置信说明

设计边界（很重要）
------------------
本脚本**只做流程调度与契约汇总**，不复制任何业务算法：
- 识图在 modules/cad-file-reader/scripts
- 四个专业的算量在 modules/*-suanliang
每个阶段通过子进程调用模块自己的入口，模块内部一行不改；靠 `Path(__file__)` 定位模块，
因此整个 cad-suite 目录可以整体搬走。

阶段失败不中断流程：该阶段标 degraded/unavailable 并写明原因，后续能跑的继续跑，
最终报告里如实列出降级项——绝不把「没跑」写成「通过」。

红线
----
- 图纸字节不出本机、不上云；所有产出落本机目录。
- 算量阶段只出「交接单」，不在这里产出或伪造工程量；final_quantity 恒 false。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

SUITE_DIR = Path(__file__).resolve().parents[1]
MODULES = SUITE_DIR / "modules"
SCHEMA = "cad-suite-run/v1"


# ---------------------------------------------------------------- 基础工具

def module_path(name: str, *parts: str) -> Path | None:
    path = MODULES / name / "scripts"
    for part in parts:
        path = path / part
    return path if path.exists() else None


def run(cmd: list[str], timeout: float = 900.0, cwd: Path | None = None) -> dict[str, Any]:
    """跑一个子进程，永远返回结果字典，不抛异常。"""
    started = time.time()
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                            cwd=str(cwd) if cwd else None)
    except subprocess.TimeoutExpired:
        return {"ok": False, "elapsed": round(time.time() - started, 2),
                "error": f"超时 {timeout:.0f}s", "stdout": "", "stderr": ""}
    except Exception as exc:  # 找不到解释器/权限等
        return {"ok": False, "elapsed": round(time.time() - started, 2),
                "error": f"{type(exc).__name__}: {exc}", "stdout": "", "stderr": ""}
    return {"ok": cp.returncode == 0, "elapsed": round(time.time() - started, 2),
            "error": "" if cp.returncode == 0 else (cp.stderr or "").strip().splitlines()[-1:] or "",
            "stdout": cp.stdout or "", "stderr": cp.stderr or ""}


def stage_record(stages: list[dict[str, Any]], name: str, status: str, detail: str, **extra) -> None:
    stages.append({"stage": name, "status": status, "detail": detail, **extra})


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def drawing_stem(path: Path) -> str:
    stem = path.stem
    for suffix in ("_detail", "_structural", "_scan"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def unique_stem_map(paths: list[Path]) -> dict[Path, str]:
    """给每张图一个**不会互相覆盖**的产物名。

    不同专业的图纸经常同名：实测 J 地块「建筑/某项目二区J-5#楼（改消防）.dwg」与
    「电气/某项目二区J-5#楼（改消防）.dwg」完全同名，产物按图名命名就会互相覆盖——
    61 张图只出 59 份识图产物，丢掉的恰好是建筑图，跨专业对照于是配不上 J-5/J-8。

    只在同名冲突时加父目录前缀（建筑_xxx / 电气_xxx），不冲突的保持原名，
    既有产物与回归基线不受影响。
    """
    counts = Counter(drawing_stem(p) for p in paths)
    unique: dict[Path, str] = {}
    for path in paths:
        stem = drawing_stem(path)
        if counts[stem] <= 1:
            unique[path] = stem
            continue
        # 父目录名已在图名里就不再重复（「J-5#楼_J-5#楼（改消防）」这种念着别扭）；
        # 只保留真正能区分的那一侧前缀
        prefix = path.parent.name
        unique[path] = stem if prefix and prefix in stem else f"{prefix}_{stem}"
    return unique


def classify_prebuilt(paths: list[str]) -> dict[str, list[Path]]:
    """把既有产物分成 detail（s1a 产物）与 structural（s1b 产物）两类。

    为什么要这个入口：真实施工图动辄 13 张、单张解图数分钟，调聚合规则或出表格式时
    反复解图纯属浪费。让已有产物直接接到下游阶段，是「快速提取数据」这条主线的基本要求。

    判据优先看内容再看文件名——文件名是给人看的，schema 才是事实。
    """
    out: dict[str, list[Path]] = {"detail": [], "structural": [], "unknown": []}
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            out["unknown"].append(path)
            continue
        kind = ""
        try:
            data = load_json(path)
            if isinstance(data, dict):
                if "text_records" in data or "text_total" in data:
                    kind = "detail"
                elif isinstance(data.get("members"), list) or "rebar_summary" in data:
                    kind = "structural"
        except Exception:
            kind = ""
        if not kind:
            # 实际命名既可能是 x_structural.json，也可能是 x_detail.structural.json（s1b 的产物）
            name = path.name.lower()
            if name.endswith("_detail.json"):
                kind = "detail"
            elif name.endswith("_structural.json") or name.endswith(".structural.json"):
                kind = "structural"
        out[kind or "unknown"].append(path)
    return out


# ---------------------------------------------------------------- 各阶段

def stage_discover(roots: list[str], out_dir: Path, stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """s0：扫描挂载盘上的图纸（--roots 才会跑；否则跳过，明细交 drawing_source）。"""
    if not roots:
        stage_record(stages, "s0-discover", "skipped", "未指定 --roots，跳过扫描（也可直接用 --inputs 给图纸）")
        return []
    script = module_path("cad-file-reader", "drawing_source.py")
    if not script:
        stage_record(stages, "s0-discover", "unavailable", "modules/cad-file-reader/scripts/drawing_source.py 不存在")
        return []
    listing = out_dir / "drawings.json"
    cmd = [sys.executable, str(script), "--roots", *roots, "--json-out", str(listing)]
    result = run(cmd, timeout=1800)
    if not result["ok"] or not listing.exists():
        stage_record(stages, "s0-discover", "degraded", f"扫描失败：{result['error']}", elapsed=result["elapsed"])
        return []
    data = load_json(listing)
    items = data.get("items") or []
    stage_record(stages, "s0-discover", "ok", f"发现图纸 {len(items)} 张（清单 {listing.name}）",
                 elapsed=result["elapsed"], counts=data.get("counts"))
    return items


def _bus_cache_hit(src: Path, detail: Path, bus: dict) -> bool:
    """用 bus 缓存命中时直接把已解析的 detail 落盘，避免同一张图再解一次。

    bus = {"find": callable, "project": str, "building": str, "floor": str}
    """
    try:
        r = bus["find"](str(src), project=bus["project"], building=bus.get("building", ""),
                        floor=bus.get("floor", ""))
    except Exception:  # noqa: BLE001
        return False
    data = (r or {}).get("data") if isinstance(r, dict) else None
    if not data or not data.get("hit"):
        return False
    entry = data.get("entry") or {}
    contract = entry.get("contract")
    if isinstance(contract, dict):
        detail.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    return False


def _bus_push_detail(src: Path, detail: Path, bus: dict) -> dict:
    """解图完成后把 cad-contract/v1 推到 bus，供后续算量共享（同图只解析一次）。"""
    state_script = module_path("cad-file-reader", "cad_statesync.py")
    if not state_script or not bus.get("project"):
        return {"ok": False, "reason": "缺少 statesync 或 --project"}
    cmd = [sys.executable, str(state_script), "push", "--detail-json", str(detail),
           "--project", bus["project"], "--building", bus.get("building", ""),
           "--floor", bus.get("floor", ""), "--source-file", str(src),
           "--skill", "cad-file-reader"]
    return run(cmd, timeout=600)


def stage_scan(drawings: list[Path], out_dir: Path, stages: list[dict[str, Any]],
               with_geom: bool = True, use_bus: bool = False,
               bus: dict | None = None) -> list[Path]:
    """s1a：cad_scan 逐张解图，产出 detail JSON。

    use_bus=True 时会先查 bus 缓存：来源图 sha256 已解析过则直接复用 detail，
    不重复解图；新解出的图随后推到 bus（同图只解析一次 + 溯源）。
    """
    script = module_path("cad-file-reader", "cad_scan.py")
    if not script:
        stage_record(stages, "s1a-scan", "unavailable", "modules/cad-file-reader/scripts/cad_scan.py 不存在")
        return []
    scan_dir = out_dir / "scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    details: list[Path] = []
    elapsed = 0.0
    reused = 0
    stems = unique_stem_map(drawings)
    bus = bus or {}
    for src in drawings:
        detail = scan_dir / f"{stems[src]}_detail.json"
        if use_bus and detail.exists():
            # 本输出目录已解过：直接复用
            details.append(detail)
            reused += 1
            stage_record(stages, "s1a-cache", "reused",
                         f"{src.name} 已在本输出目录解析过，跳过 cad_scan", drawing=src.name)
            continue
        if use_bus and detail.exists() is False and _bus_cache_hit(src, detail, bus):
            details.append(detail)
            reused += 1
            stage_record(stages, "s1a-cache", "reused",
                         f"{src.name} bus 缓存命中（sha256），不再重复解图", drawing=src.name)
            continue
        cmd = [sys.executable, str(script), str(src), "--detail-json", str(detail)]
        if with_geom:
            cmd += ["--with-geom", "--with-geom-layer"]
        result = run(cmd, timeout=1200)
        elapsed += result["elapsed"]
        if result["ok"] and detail.exists():
            details.append(detail)
            if use_bus:
                push = _bus_push_detail(src, detail, bus)
                stage_record(stages, "s1a-bus-push", "ok" if push.get("ok") else "degraded",
                             f"{src.name} 契约已入 bus" if push.get("ok") else f"{src.name} 入 bus 失败：{push.get('error')}",
                             drawing=src.name, elapsed=push.get("elapsed"))
        else:
            stage_record(stages, "s1a-scan", "degraded", f"{src.name} 解图失败：{result['error']}",
                         elapsed=result["elapsed"], drawing=src.name)
    ok_count = len(details)
    status = "ok" if ok_count == len(drawings) and drawings else ("degraded" if ok_count else "unavailable")
    note = f"解图成功 {ok_count}/{len(drawings)} 张" + (f"（bus 复用/缓存命中 {reused} 张）" if reused else "")
    stage_record(stages, "s1a-scan", status, note, elapsed=round(elapsed, 2), reused=reused)
    return details


def stage_interpret(details: list[Path], out_dir: Path, stages: list[dict[str, Any]],
                    pack: str = "structural") -> list[Path]:
    """s1b：按专业 pack 生成识图候选与契约。当前接结构识图；其它 pack 同样按此模式扩展。"""
    if not details:
        stage_record(stages, "s1b-interpret", "unavailable", "没有可用的 detail JSON")
        return []
    script_map = {
        "structural": ("cad_structural_geometry.py", "structural"),
    }
    script_name, tag = script_map.get(pack, script_map["structural"])
    script = module_path("cad-file-reader", script_name)
    if not script:
        stage_record(stages, "s1b-interpret", "unavailable", f"{script_name} 不存在")
        return []
    target = out_dir / f"{tag}"
    target.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(script), *[str(d) for d in details], "--out-dir", str(target)]
    result = run(cmd, timeout=1800)
    outputs = sorted(target.glob(f"*.{tag}.json"))
    status = "ok" if result["ok"] and outputs else "degraded"
    stage_record(stages, "s1b-interpret", status, f"{tag} 识图产物 {len(outputs)} 份",
                 elapsed=result["elapsed"], error=result["error"] or None)
    return outputs


def stage_relation(interpreted: list[Path], out_dir: Path, stages: list[dict[str, Any]]) -> Path | None:
    """s2：图纸关系（聚类/楼层序列/专业/配对建议）。"""
    if not interpreted:
        stage_record(stages, "s2-relation", "unavailable", "没有识图产物")
        return None
    script = module_path("cad-file-reader", "drawing_relation.py")
    if not script:
        stage_record(stages, "s2-relation", "unavailable", "drawing_relation.py 不存在")
        return None
    out = out_dir / "relation.json"
    cmd = [sys.executable, str(script), "--inputs", *[str(p) for p in interpreted],
           "--out", str(out), "--md-out", str(out_dir / "relation.md")]
    result = run(cmd, timeout=600)
    if not out.exists():
        stage_record(stages, "s2-relation", "degraded", f"关系推断失败：{result['error']}", elapsed=result["elapsed"])
        return None
    summary = load_json(out).get("summary") or {}
    stage_record(stages, "s2-relation", "ok",
                 f"单体 {summary.get('clusters')} 个 / 楼层 {summary.get('floor_series')} 个 / 配对 {summary.get('pairs')} 组",
                 elapsed=result["elapsed"])
    return out


def stage_aggregate(interpreted: list[Path], out_dir: Path, stages: list[dict[str, Any]],
                    details: list[Path] | None = None) -> Path | None:
    """s3：跨图聚合（楼层×构件规格表 / 钢筋型号表）。

    先跑 rebar_grade 从本批图纸的说明表反解「符号→牌号」，再带 `--legend` 聚合。
    拿不到说明表时映射为空，聚合层照旧把牌号写成 unknown——不给牌号也不编牌号。

    **映射优先从 detail 产物取**：说明表是整段文字，只存在于 cad_scan 的 text_records；
    structural 产物只保留构件附近的证据片段，里面没有说明表。只给 structural 时
    映射必然为空，这里会明确说出来，而不是让用户以为牌号功能坏了。
    """
    if not interpreted:
        stage_record(stages, "s3-aggregate", "unavailable", "没有识图产物")
        return None
    script = module_path("cad-file-reader", "project_aggregate.py")
    if not script:
        stage_record(stages, "s3-aggregate", "unavailable", "project_aggregate.py 不存在")
        return None

    legend_path = out_dir / "rebar-legend.json"
    grade_script = module_path("cad-file-reader", "rebar_grade.py")
    grade_sources = list(details or []) or list(interpreted or [])
    legend_arg: list[str] = []
    grade_elapsed = 0.0
    if grade_script:
        g = run([sys.executable, str(grade_script),
                 "--inputs", *[str(p) for p in grade_sources],
                 "--out", str(legend_path),
                 "--md-out", str(out_dir / "rebar-legend.md")], timeout=300)
        grade_elapsed = g["elapsed"]
        if g["ok"] and legend_path.exists():
            lg = load_json(legend_path)
            n_direct = sum(1 for m in (lg.get("mapping") or []) if m.get("basis") == "direct")
            n_bridge = len(lg.get("bridges") or [])
            if n_direct or n_bridge:
                legend_arg = ["--legend", str(legend_path)]
                stage_record(stages, "s3a-grade", "ok",
                             f"牌号映射：说明表直接 {n_direct} 条 / 尾号外推 {n_bridge} 条",
                             elapsed=g["elapsed"])
            elif not details:
                stage_record(stages, "s3a-grade", "degraded",
                             "只有 structural 产物、没有 detail，说明表整段文字不可得，牌号无法回填；"
                             "需要牌号请把 scan/*_detail.json 一起用 --prebuilt 传入", elapsed=g["elapsed"])
            else:
                stage_record(stages, "s3a-grade", "skipped",
                             "本批图纸没有可识别的钢筋说明表，牌号保持未标注", elapsed=g["elapsed"])
        else:
            stage_record(stages, "s3a-grade", "degraded", f"牌号映射提取失败：{g['error']}",
                         elapsed=g["elapsed"])
    else:
        stage_record(stages, "s3a-grade", "unavailable", "rebar_grade.py 不存在")

    out = out_dir / "aggregate.json"
    cmd = [sys.executable, str(script), "--inputs", *[str(p) for p in interpreted],
           "--out", str(out), "--md-out", str(out_dir / "aggregate.md"),
           "--csv-out", str(out_dir / "aggregate.csv"), *legend_arg]
    result = run(cmd, timeout=900)
    if not out.exists():
        stage_record(stages, "s3-aggregate", "degraded", f"聚合失败：{result['error']}", elapsed=result["elapsed"])
        return None
    summary = load_json(out).get("summary") or {}
    grade_stat = summary.get("rebar_grade") or {}
    detail = f"构件 {summary.get('member_groups')} 组 / 钢筋型号 {summary.get('rebar_groups')} 组"
    if grade_stat:
        known = grade_stat.get("direct", 0) + grade_stat.get("bridged", 0) + grade_stat.get("literal", 0)
        detail += f"（牌号 {known}/{grade_stat.get('total', 0)} 条）"
    stage_record(stages, "s3-aggregate", "ok", detail, elapsed=round(result["elapsed"] + grade_elapsed, 2))
    return out


def stage_compare(relation: Path | None, out_dir: Path, stages: list[dict[str, Any]]) -> dict[str, Any]:
    """s4：跨专业对照。有同层/同楼栋的建筑+结构才配对；只有单专业时如实报缺。"""
    if not relation or not relation.exists():
        stage_record(stages, "s4-compare", "unavailable", "缺少关系推断结果")
        return {}
    data = load_json(relation)
    pairs = data.get("pairs") or []
    # 配对范围不再只是「楼层」：楼层判不出来时按楼栋配（成套楼栋图覆盖全楼各层），
    # 大样档按整簇汇总。计数口径必须跟着变，否则「8 个楼层」会误导成 8 层。
    scopes = {(p.get("scope_kind") or "楼层", p.get("scope") or p.get("floor")) for p in pairs}
    strong = [p for p in pairs if p.get("match_quality") == "strong"]
    missing = [r for r in (data.get("review") or [])
               if r.get("type") in ("missing_architecture", "structure_without_architecture")]
    # 配对 ≠ 对上了。s2 会再比一次轴网（grid_check），「数据不可信 / 样本不足 / 无法比对」
    # 都说明这次核对没给出结论——不能把「配了 10 组」说成「10 组可对照」。
    gc = [p.get("grid_check") or {} for p in pairs]
    ok_n = sum(1 for g in gc if g.get("verdict") == "轴网一致")
    bad_n = sum(1 for g in gc if g.get("verdict") == "轴网不对应")
    unknown_n = len(pairs) - ok_n - bad_n
    plan = {"pairs": pairs, "missing": missing,
            "grid_verified": ok_n, "grid_mismatch": bad_n, "grid_inconclusive": unknown_n,
            "note": ("配对只是指出「哪两张图该放一起看」，轴网核对通过（轴网一致）才说明是同一片区域，"
                     "可逐项对照构件位置/标高/洞口。"
                     "数据不可信/样本不足/无法比对的配对必须人工看图确认后再对照。"
                     "缺建筑图时对照无法进行，需补图。"
                     "match_quality=weak 表示某一侧图名没识别出图种，配对仍可用但需人工确认")}
    (out_dir / "compare-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if not pairs:
        stage_record(stages, "s4-compare", "degraded",
                     f"无可用配对（缺建筑图 {len(missing)} 处），对照未进行")
    elif ok_n:
        stage_record(stages, "s4-compare", "ok",
                     f"{len(scopes)} 个对照范围已配对（{len(pairs)} 组，强配对 {len(strong)} 组），"
                     f"轴网核对通过 {ok_n} 组、不对应 {bad_n} 组、判不了 {unknown_n} 组")
    else:
        # 配了但一组都没通过轴网核对：出的是「对照计划」，不是「对照结果」。
        # 记 ok 会让下游以为构件级比对已经做完，这是最容易出的假进度。
        stage_record(stages, "s4-compare", "degraded",
                     f"{len(scopes)} 个对照范围已配对（{len(pairs)} 组，强配对 {len(strong)} 组），"
                     f"但轴网核对无一通过（不对应 {bad_n} / 判不了 {unknown_n}）："
                     f"构件级对照未执行，需人工看图核对")
    return plan


def stage_qty_handoff(aggregate: Path | None, relation: Path | None, out_dir: Path,
                      stages: list[dict[str, Any]], targets: list[str],
                      details: list[Path] | None = None,
                      story_height_mm: float = 3600.0) -> Path | None:
    """s5：算量。先把「按哪个图框算、板厚多少」定下来，再调专项技能跑它的流水线。

    为什么要先定图框：算量技能的 `--floor-label` 实际是**图框标题**，按标题精确
    比对找梁标注。传楼层号（`-1F`）会一条梁都取不到，混凝土量恒为 0——这不是
    算量技能算错，是入口参数给错了。图框标题只有识图侧知道，所以由 s5 先算。

    为什么不算量在这里：土建/装饰/安装/园林各是多步流水线（归并、闭合、去重、
    扣减、损耗），复制进融合层会立刻分叉。这里只负责把入口参数给对、把结果收回来。
    """
    if not aggregate or not aggregate.exists():
        stage_record(stages, "s5-qty", "unavailable", "缺少聚合结果，无法准备算量入口")
        return None

    agg = load_json(aggregate)
    rel = load_json(relation) if relation and relation.exists() else {}
    handoff = {
        "schema": "cad-suite-qty-handoff/v2",
        "clearance": "本单为提取结果与算量入口，不是可结算工程量；final_quantity=false",
        "floors": [f.get("label") for f in (agg.get("floors") or [])],
        "drawings": [i.get("drawing") for i in (agg.get("inputs") or [])],
        "clusters": [c.get("id") for c in (rel.get("clusters") or [])],
        "member_table": agg.get("members") or [],
        "rebar_table": agg.get("rebars") or [],
        "rebar_by_floor": agg.get("rebar_by_floor") or [],
        "targets": [{"skill": t, "status": "pending", "entry": f"modules/{t}/SKILL.md"}
                    for t in targets],
        "note": "算量由专项技能按自身流水线执行；本单给出图框标题、板厚、构件与钢筋表。",
    }

    # ---- 1) 图框与板厚：这一层决定算量能不能出数 ----
    prep_path = out_dir / "qty-prepare.json"
    prep: dict[str, Any] = {}
    prep_script = module_path("cad-file-reader", "qty_prepare.py")
    if prep_script and details:
        result = run([sys.executable, str(prep_script),
                      "--inputs", *[str(p) for p in details],
                      "--out", str(prep_path)], timeout=300)
        if prep_path.exists():
            prep = load_json(prep_path)
            s = prep.get("summary") or {}
            stage_record(stages, "s5a-sheet", "ok",
                         f"可算量图框 {s.get('ready')}/{s.get('drawings')} 张"
                         f"（梁图框 {s.get('with_beam_sheet')} 张）", elapsed=result["elapsed"])
        else:
            stage_record(stages, "s5a-sheet", "degraded", f"图框定位失败：{result['error']}")
    else:
        stage_record(stages, "s5a-sheet", "unavailable", "缺少 detail 产物或 qty_prepare.py")

    # ---- 2) 真跑算量（只对定位到图框的图）----
    runs: list[dict[str, Any]] = []
    if "tujian-suanliang" in targets and prep.get("drawings"):
        runs = _run_tujian(prep, out_dir, story_height_mm)
        handoff["qty_runs"] = runs
        ok = [r for r in runs if r["status"] == "ok"]
        missing = [r for r in runs if r["status"] == "missing_dwg"]
        total = sum(float(r.get("concrete_net_m3") or 0) for r in ok)
        if ok:
            stage_record(stages, "s5-qty", "ok",
                         f"{len(ok)}/{len(runs)} 张算出量，混凝土净候选合计 {total:.2f} m3")
        elif missing and len(missing) == len(runs):
            # 这不是算量失败，是没给原始图纸路径：--prebuilt 复用产物时 s0 被跳过，
            # drawings.json 不存在。说清怎么补，别让人以为算量技能不行。
            stage_record(stages, "s5-qty", "degraded",
                         f"{len(runs)} 张都缺原始图纸路径，未进入算量。"
                         "复用了 --prebuilt 时 s0 被跳过、没有 drawings.json；"
                         "补 --roots <图纸目录> 或 --inputs <dwg> 即可真正算量")
        elif runs:
            stage_record(stages, "s5-qty", "degraded",
                         f"{len(runs)} 张尝试算量但都没出结果，原因见 qty-handoff.json")
        else:
            stage_record(stages, "s5-qty", "degraded", "没有可算量的图（图框都定位不到）")
    else:
        stage_record(stages, "s5-qty", "skipped",
                     f"未要求土建算量或没有可定位图框（targets={targets}）")

    out = out_dir / "qty-handoff.json"
    out.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# 算量报告里真正要看的字段：候选总量与净候选量分开列，别把毛量当结算量。
QTY_FIELDS = {
    "concrete_candidate_m3": "concrete_candidate_total_m3",
    "concrete_net_m3": "intersection_candidate_net_total_m3",
    "beam_count": "beam_schedule_count",
    "slab_count": "slab_schedule_count",
    "column_count": "column_schedule_count",
    "rebar_type_count": "rebar_type_count",
    "blocking_anomalies": "blocking_anomaly_count",
}


def _drawing_paths(out_dir: Path) -> dict[str, str]:
    """图纸名(不含后缀) -> 原始路径。算量要原始 dwg，detail 里只有名字。"""
    mapping: dict[str, str] = {}
    for name in ("drawings.json", "suite-drawings.json"):
        p = out_dir / name
        if not p.exists():
            continue
        try:
            for item in (load_json(p).get("items") or []):
                path = str(item.get("path") or "")
                if path:
                    mapping[Path(path).stem] = path
        except Exception:
            continue
    return mapping


def _run_tujian(prep: dict[str, Any], out_dir: Path,
                story_height_mm: float) -> list[dict[str, Any]]:
    """逐张调土建算量流水线。单张失败不影响其他张，失败原因原样记下。"""
    script = module_path("tujian-suanliang", "cad_quantity_pipeline.py")
    if not script:
        return [{"status": "unavailable", "error": "tujian cad_quantity_pipeline.py 不存在"}]
    paths = _drawing_paths(out_dir)
    runs: list[dict[str, Any]] = []
    for item in prep["drawings"]:
        rec = item.get("recommended")
        if not rec:
            continue
        stem = str(item.get("file") or "")
        for suffix in ("_detail.json", ".json"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        dwg = paths.get(stem)
        if not dwg or not Path(dwg).exists():
            runs.append({"drawing": stem, "status": "missing_dwg",
                         "error": "找不到原始图纸路径（drawings.json 里没有该图）"})
            continue

        slab = ((item.get("slab") or {}).get("default_mm")) or 0
        qty_out = out_dir / "qty" / stem
        qty_out.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(script),
               "--dwg", dwg,
               # 必须用等号形式：图框标题常以 "-0.050" 这类负号开头，空格分隔会被
               # argparse 当成选项，报 "expected one argument"。tujian 侧已同步修好。
               f"--floor-label={rec['title']}",
               f"--out={qty_out}",
               f"--story-height-mm={story_height_mm}"]
        if slab:
            cmd.append(f"--slab-thickness-mm={slab}")
        result = run(cmd, timeout=1800)
        run_rec: dict[str, Any] = {
            "drawing": stem, "sheet": rec["title"], "slab_mm": slab or None,
            "status": "failed", "elapsed": round(result["elapsed"], 2),
        }
        report = qty_out / "quantity_report.json"
        if report.exists():
            try:
                data = load_json(report)
                direct = data.get("direct_outputs") or {}
                for key, field in QTY_FIELDS.items():
                    if field in direct:
                        run_rec[key] = direct[field]
                run_rec["formal_ready"] = bool(data.get("formal_ready"))
                run_rec["rebar_models"] = sorted({
                    str(r.get("model") or "") for r in (data.get("rebar_schedule") or [])
                    if r.get("model")
                })[:20]
                run_rec["status"] = "ok"
            except Exception as exc:
                run_rec["error"] = f"算量报告解析失败：{exc}"
        else:
            run_rec["error"] = (result["error"] or "算量未产出 quantity_report.json")[:300]
        runs.append(run_rec)
    return runs


def stage_report(out_dir: Path, stages: list[dict[str, Any]], payloads: dict[str, Any]) -> Path:
    """s6：出表与置信说明。"""
    path = out_dir / "SUITE-REPORT.md"
    stage_record(stages, "s6-report", "ok", f"报告 {path.name}")
    lines = ["# cad-suite 运行报告", "",
             f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 输出目录：`{out_dir}`", "",
             "## 阶段执行情况", "", "| 阶段 | 状态 | 说明 | 耗时(s) |", "|---|---|---|---|"]
    for st in stages:
        elapsed = st.get("elapsed")
        lines.append(f"| {st['stage']} | {st['status']} | {st['detail']} | {'' if elapsed is None else elapsed} |")

    agg = payloads.get("aggregate") or {}
    if agg:
        s = agg.get("summary") or {}
        lines += ["", "## 提取结果概览", "",
                  f"- 图纸 {s.get('drawings')} 张 / 楼层 {s.get('floors')} 个",
                  f"- 构件归并 {s.get('member_groups')} 组（原始候选 {s.get('member_candidates')} 条）",
                  f"- 钢筋型号 {s.get('rebar_groups')} 组（原始候选 {s.get('rebar_candidates')} 条）", "",
                  "### 各型号钢筋", "", "| 直径 | 牌号 | 出现次数 | 涉及图纸数 |", "|---|---|---|---|"]
        for row in (agg.get("rebars") or [])[:20]:
            lines.append(f"| Φ{row['diameter']} | {row['grade']} | {row['count']} | {row['drawing_count']} |")
        lines += ["", "### 各层构件规格（前 20）", "", "| 楼层 | 分区 | 类别 | 规格 | 出现次数 |", "|---|---|---|---|---|"]
        for row in (agg.get("members") or [])[:20]:
            lines.append(f"| {row['floor']} | {row['zone']} | {row['category']} | {row['spec']} | {row['count']} |")
        conf = (agg.get("contract") or {}).get("summary") or {}
        if conf:
            lines += ["", "### 契约三档（聚合层）", "",
                      f"- confirmed_evidence {conf.get('confirmed_evidence')} / "
                      f"inferred_candidate {conf.get('inferred_candidate')} / "
                      f"review_required {conf.get('review_required')}"]

    degraded = [st for st in stages if st["status"] in ("degraded", "unavailable")]
    lines += ["", "## 降级与未执行项", ""]
    if degraded:
        lines += ["| 阶段 | 状态 | 原因 |", "|---|---|---|"]
        for st in degraded:
            lines.append(f"| {st['stage']} | {st['status']} | {st['detail']} |")
    else:
        lines.append("无")
    lines += ["", "> 全部结果均为识图/提取候选（final_quantity=false），不是工程量，不可直接用于结算。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 主流程

def main() -> int:
    parser = argparse.ArgumentParser(description="CAD 融合流程调度：发现→识图→关系→聚合→对照→算量派发→出表")
    parser.add_argument("--inputs", nargs="*", default=[], help="DWG/DXF 图纸路径")
    parser.add_argument("--roots", nargs="*", default=[], help="s0 扫描根（如 /Volumes/扩展），不给则跳过发现")
    parser.add_argument("--prebuilt", nargs="*", default=[],
                        help="复用既有产物（*_detail.json / *_structural.json），自动跳过已完成阶段")
    parser.add_argument("--out-dir", default="cad-suite-out")
    parser.add_argument("--pack", default="structural", choices=["structural"])
    parser.add_argument("--targets", nargs="*", default=["tujian-suanliang"],
                        help="算量派发目标技能；给空列表则跳过算量只出提取表")
    parser.add_argument("--story-height-mm", type=float, default=3600.0,
                        help="层高/mm，墙柱体积要用；图上取不到时按此默认值，报告会标注")
    parser.add_argument("--no-geom", action="store_true", help="解图时不取几何（更快，但几何类候选为空）")
    parser.add_argument("--json", action="store_true", help="把汇总以 JSON 打到 stdout")
    parser.add_argument("--use-bus", action="store_true",
                        help="走 lis-skill-bus 缓存/溯源：同图只解析一次，解图后推送契约")
    parser.add_argument("--project", default="", help="bus 项目标识（--use-bus 需要）")
    parser.add_argument("--building", default="", help="bus 楼栋（可选）")
    parser.add_argument("--floor", default="", help="bus 楼层（可选）")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}

    try:
        prebuilt = classify_prebuilt(args.prebuilt) if args.prebuilt else {"detail": [], "structural": [], "unknown": []}
        for bad in prebuilt["unknown"]:
            stage_record(stages, "s1a-prebuilt", "degraded", f"{bad.name} 不是可识别的识图产物，已忽略")
        has_prebuilt = bool(prebuilt["detail"] or prebuilt["structural"])

        if has_prebuilt:
            # 复用产物时不再扫描/解图，避免把几十分钟的活重跑一遍
            drawings: list[Path] = []
            discovered: list[dict[str, Any]] = []
            details = prebuilt["detail"]
            if args.roots:
                # 仍给了图纸根目录：只为算量补一份 drawings.json——
                # 算量要原始 dwg 路径，而 detail 产物里只有图纸名。
                discovered = stage_discover(args.roots, out_dir, stages)
            else:
                stage_record(stages, "s0-discover", "skipped",
                             "复用了既有产物，跳过扫描发现（算量需要原始图纸路径时补 --roots）")
            stage_record(stages, "s1a-scan", "skipped",
                         f"复用既有产物 {len(details)} 份 detail / {len(prebuilt['structural'])} 份 structural，"
                         "跳过解图")
        else:
            discovered = stage_discover(args.roots, out_dir, stages)
            drawings = [Path(p) for p in args.inputs]
            if not drawings and discovered:
                drawings = [Path(i["path"]) for i in discovered if not i.get("in_archive")]
            if not drawings:
                stage_record(stages, "s1a-scan", "unavailable", "没有输入图纸（--inputs 或 --roots 至少要给一个）")
            bus_info: dict | None = None
            if args.use_bus:
                import bus_bridge
                info = bus_bridge.detect_bus()
                if not info.get("hit"):
                    stage_record(stages, "s1a-bus-cache", "degraded",
                                 f"未找到 lis-skill-bus, --use-bus 忽略（{info.get('reason')}）")
                else:
                    state_dir = os.environ.get("SKILLBUS_STATE_DIR", "") or None
                    find = lambda src_file, project="", building="", floor="": (
                        bus_bridge.find_contract(project, src_file, building, floor, state_dir))
                    bus_info = {"find": find,
                                "project": args.project, "building": args.building, "floor": args.floor}
                    stage_record(stages, "s1a-bus-cache", "ok",
                                 f"bus 已接入：{info['root']}（marker={info['marker']}）")
            details = stage_scan(drawings, out_dir, stages, with_geom=not args.no_geom,
                                 use_bus=bool(args.use_bus), bus=bus_info)

        if prebuilt["structural"]:
            interpreted = prebuilt["structural"]
            stage_record(stages, "s1b-interpret", "skipped",
                         f"复用既有识图结果 {len(interpreted)} 份，跳过识图")
        else:
            interpreted = stage_interpret(details, out_dir, stages, pack=args.pack)
        relation = stage_relation(interpreted, out_dir, stages)
        aggregate = stage_aggregate(interpreted, out_dir, stages, details=details)
        stage_compare(relation, out_dir, stages)
        stage_qty_handoff(aggregate, relation, out_dir, stages, args.targets,
                          details=details, story_height_mm=args.story_height_mm)

        if aggregate:
            payloads["aggregate"] = load_json(aggregate)
        if relation:
            payloads["relation"] = load_json(relation)
        report = stage_report(out_dir, stages, payloads)
    except Exception:
        stage_record(stages, "fatal", "error", traceback.format_exc(limit=3))
        report = None

    summary = {
        "schema": SCHEMA,
        "out_dir": str(out_dir),
        "report": str(report) if report else None,
        "stages": stages,
        "ok": all(st["status"] in ("ok", "skipped") for st in stages),
        "degraded": [st["stage"] for st in stages if st["status"] in ("degraded", "unavailable", "error")],
    }
    (out_dir / "run-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"完成：{out_dir}")
        for st in stages:
            print(f"  [{st['status']:11s}] {st['stage']:18s} {st['detail']}")
        if summary["degraded"]:
            print(f"降级/未执行阶段：{', '.join(summary['degraded'])}")
    return 0 if summary["ok"] else 0  # 降级也返回 0：流程跑完了，问题写在报告里


if __name__ == "__main__":
    sys.exit(main())
