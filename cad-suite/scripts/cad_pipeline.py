#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cad_pipeline.py —— 批量生产总入口：图纸目录进 → 全专业分发算量 → 汇总一本账。

补齐 cad_batch（识图台账）之后的下游缺口：
  发现图纸 → 逐张识图（cad-file-reader）→ 专业判定 → 对应几何提取 →
  对应算量终点（钢结构吨位 / 市政管长 / 钢筋口径B）→ 可选跨专业碰撞 →
  汇总一本账（pipeline.json + 一本账.md）。

诚实边界：
  * 全部产物 final_quantity=false（概算/估算口径，不是结算）；
  * 钢筋批量只出**口径B标注谱**（无料单不出吨位带——不编造）；
  * 跨图合计 = 各图带简单相加，同构件出现在多张图会重复计，去重靠台账人工勾选；
  * 单图失败只记台账不中断整批；--resume 断点续跑。

用法
    python3 cad_pipeline.py 图纸目录/ -o 汇总 [--glob *.dwg] [--resume]
    python3 cad_pipeline.py a.detail.municipal.json b.detail.json -o 汇总  # 复用现成识图产物
    python3 cad_pipeline.py 图纸/ -o 汇总 --with-clash                    # 附带跨专业碰撞
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_BUDGET = 45.0

# 专业 → (几何提取脚本, 几何产物后缀)
# 提取器输出命名 = {输入 stem}.{后缀}.json（如 X.detail.json → X.detail.steel.json）
# 建筑暂无已接通的批量算量终点，判定后必须跳过；不要让建筑几何走市政管长链。
SPEC_GEOMETRY = {
    "结构": ("cad_steel_geometry.py", "steel"),
    "市政": ("cad_municipal_geometry.py", "municipal"),
    "给排水": ("cad_municipal_geometry.py", "municipal"),
}

SPEC_KEYWORDS = [
    ("市政", ["室外管网", "市政", "综合管线", "管线综合", "雨污水", "浇灌"]),
    ("给排水", ["给排水", "喷淋", "消防给水", "室内排水", "室内给水"]),
    ("结构", ["平法", "结构", "基础平面", "桩位", "模板图"]),
    ("建筑", ["建筑施工图", "建筑平面", "建筑设计", "总平面", "户型"]),
    ("电气", ["电气", "照明平面", "配电", "防雷"]),
    ("暖通", ["暖通", "空调", "通风", "防排烟"]),
]
SPEC_SCORE_MIN = 2


# ---------------------------------------------------------------- 定位依赖
def find_skill(skill: str, sub: str = "scripts") -> Path:
    suite_modules = Path(__file__).resolve().parents[1] / "modules"
    for base in (suite_modules,
                 Path.home() / ".workbuddy" / "skills",
                 Path.home() / ".codex" / "skills"):
        p = base / skill / sub
        if p.is_dir():
            return p
    raise FileNotFoundError(f"找不到 skill：{skill}（请先安装）")


# ---------------------------------------------------------------- 专业判定
def classify_detail(data: dict) -> str:
    """文字关键词优先，无文字时按产物结构回退（与 cad-clash-check 口径一致）。"""
    texts = [t.get("text", "") if isinstance(t, dict) else str(t)
             for t in data.get("text_records") or []]
    sample = [str(t) for t in texts[:3000]]
    best, best_n = "未知", 0
    for spec, kws in SPEC_KEYWORDS:
        n = sum(t.count(k) for t in sample for k in kws)
        if n > best_n:
            best, best_n = spec, n
    if best_n >= SPEC_SCORE_MIN:
        return best
    keys = set(data.keys())
    if "municipal_geometry" in keys or "pipe_candidates" in keys:
        return "市政"
    if "members" in keys or "steel_profiles" in keys or "connections" in keys:
        return "结构"
    return "未知"


# ---------------------------------------------------------------- 可测纯函数
def add_bands(bands: list[tuple[float, float]]) -> tuple[float, float]:
    """估算带相加：下限加下限、上限加上限（跨图合计口径）。"""
    lo = sum(b[0] for b in bands)
    hi = sum(b[1] for b in bands)
    return (round(lo, 2), round(hi, 2))


def state_key(path: Path) -> str:
    """断点续跑键：路径哈希 + 大小 + mtime。"""
    try:
        st = path.stat()
        raw = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        raw = str(path)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def aggregate_report(rows: list[dict]) -> dict:
    """按专业汇总一本账（纯函数，供测试）。rows = 每图一行。"""
    totals = {"钢筋口径B标注次数": 0, "钢结构吨位带t": None, "市政管长m": 0.0}
    steel_bands: list[tuple[float, float]] = []
    by_spec: dict[str, int] = {}
    for r in rows:
        if r.get("status") != "ok":
            continue
        by_spec[r.get("spec", "未知")] = by_spec.get(r.get("spec", "未知"), 0) + 1
        out = r.get("outputs") or {}
        if out.get("rebar"):
            totals["钢筋口径B标注次数"] += int(out["rebar"].get("total_count") or 0)
        if out.get("steel") and out["steel"].get("total_t"):
            steel_bands.append(tuple(out["steel"]["total_t"]))
        if out.get("pipe") and out["pipe"].get("total_m"):
            totals["市政管长m"] += float(out["pipe"]["total_m"])
    if steel_bands:
        totals["钢结构吨位带t"] = list(add_bands(steel_bands))
    return {"by_specialty": by_spec, "totals": totals,
            "note": "跨图合计=各图带简单相加；同构件多图重复计需台账人工去重"}


def render_md(report: dict) -> str:
    lines = ["# 批量算量一本账", "",
             "> final_quantity=false（概算/估算口径）；钢筋批量仅口径B标注谱"
             "（无料单不出吨位带）；跨图合计为各图带相加，多图重复计需人工去重。", ""]
    rep = report.get("totals", {})
    steel = rep.get("钢结构吨位带t")
    lines.append(f"- 图纸 {len(report.get('rows', []))} 张，专业分布："
                 + "、".join(f"{k}×{v}" for k, v in report.get("by_specialty", {}).items()))
    if rep.get("钢筋口径B标注次数"):
        lines.append(f"- 钢筋口径B：标注共 {rep['钢筋口径B标注次数']} 次（谱见 pipeline.json）")
    if steel:
        lines.append(f"- 钢结构吨位合计带：{steel[0]}~{steel[1]} t（±15% 估算）")
    if rep.get("市政管长m"):
        lines.append(f"- 市政管长合计：{rep['市政管长m']:.1f} m")
    lines.append("")
    lines.append("| 图纸 | 专业 | 状态 | 钢结构吨位带t | 市政管长m | 钢筋标注次数 | 碰撞候选 | 备注 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report.get("rows", []):
        out = r.get("outputs") or {}
        steel_t = out.get("steel", {}).get("total_t") if out.get("steel") else None
        pipe_m = out.get("pipe", {}).get("total_m") if out.get("pipe") else None
        rebar_n = out.get("rebar", {}).get("total_count") if out.get("rebar") else None
        clash = r.get("clash_total")
        lines.append(
            f"| {r.get('file', '')} | {r.get('spec', '')} | {r.get('status', '')} "
            f"| {f'{steel_t[0]}~{steel_t[1]}' if steel_t else '-'} "
            f"| {pipe_m if pipe_m is not None else '-'} "
            f"| {rebar_n if rebar_n is not None else '-'} "
            f"| {clash if clash is not None else '-'} "
            f"| {r.get('note', '') or r.get('error', '')} |")
    for s in report.get("skipped", []):
        lines.append("")
        lines.append(f"- ⚠️ 跳过 {s['file']}：{s['reason']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 子流程
def _fail_tail(r: subprocess.CompletedProcess) -> str:
    """失败原因取证：stderr 优先，空则看 stdout 尾部（部分脚本往 stdout 写错）。"""
    tail = (r.stderr or "").strip()[-300:]
    if not tail:
        tail = (r.stdout or "").strip()[-200:]
    return f"rc={r.returncode} {tail}".strip()


def run_scan(dwg: Path, workdir: Path, cfr: Path, budget: float) -> Path:
    detail = workdir / f"{dwg.stem}.detail.json"
    r = subprocess.run(
        [sys.executable, str(cfr / "cad_scan.py"), str(dwg),
         "--detail-json", str(detail), "--with-geom", "--with-geom-layer",
         "--budget", str(budget), "--format", "json",
         "-o", str(workdir / f"{dwg.stem}_scan")],
        capture_output=True, text=True, timeout=max(600, budget * 8))
    if r.returncode != 0 or not detail.exists():
        raise RuntimeError(f"识图失败: {_fail_tail(r)}")
    return detail


def run_geometry(detail: Path, spec: str, workdir: Path, cfr: Path) -> Path:
    script, suffix = SPEC_GEOMETRY[spec]
    geo = workdir / f"{detail.stem}_geo"
    r = subprocess.run(
        [sys.executable, str(cfr / script), str(detail), "--out-dir", str(geo)],
        capture_output=True, text=True, timeout=1800)
    out = geo / f"{detail.stem}.{suffix}.json"  # 提取器命名 = 输入stem.后缀
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"{spec}几何提取失败: {_fail_tail(r)}")
    return out


def run_steel(steel_json: Path, workdir: Path, tujian: Path) -> dict | None:
    prefix = workdir / f"{steel_json.stem}_steel"
    r = subprocess.run(
        [sys.executable, str(tujian / "steel_tonnage.py"),
         "--steel", str(steel_json), "--out-prefix", str(prefix)],
        capture_output=True, text=True, timeout=600)
    out = Path(str(prefix) + ".json")
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"steel_tonnage 失败: {_fail_tail(r)}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return {"total_t": d.get("total_t"), "length_basis": d.get("length_basis"),
            "rows": len(d.get("rows") or [])}


def run_pipe(mun_json: Path, workdir: Path, anz: Path) -> dict | None:
    prefix = workdir / f"{mun_json.stem}_pipe"
    r = subprocess.run(
        [sys.executable, str(anz / "municipal_pipe_length.py"),
         "--municipal", str(mun_json), "--out-prefix", str(prefix)],
        capture_output=True, text=True, timeout=600)
    out = Path(str(prefix) + ".json")
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"municipal_pipe_length 失败: {_fail_tail(r)}")
    d = json.loads(out.read_text(encoding="utf-8"))
    s = d.get("summary") or {}
    return {"total_m": s.get("总管长m"), "systems": s.get("系统数"),
            "rows": len(d.get("rows") or [])}


def run_rebar_profile(detail: Path, tujian: Path) -> dict | None:
    """钢筋口径B标注谱（导入复用，不落 xlsx）。无料单不出吨位带——诚实边界。"""
    try:
        sys.path.insert(0, str(tujian))
        import rebar_tonnage  # noqa: PLC0415
    except Exception:
        return None
    scan = json.loads(detail.read_text(encoding="utf-8"))
    if not (scan.get("rebar_summary") or {}).get("rebars"):
        return None
    agg = rebar_tonnage.aggregate_from_scan(scan)
    prof = rebar_tonnage.rebar_profile(agg)
    return {"total_count": prof.get("total_count"),
            "weighted_dia": prof.get("weighted_dia"),
            "rows": len(prof.get("rows") or []),
            "note": "口径B标注谱（无料单不出吨位带）"}


def run_clash_pair(a: Path, b: Path, workdir: Path, clash_script: Path, i: int) -> int | None:
    prefix = workdir / f"clash_{i}"
    r = subprocess.run(
        [sys.executable, str(clash_script), str(a), str(b), "-o", str(prefix)],
        capture_output=True, text=True, timeout=1800)
    out = Path(str(prefix))  # cad_clash_check 直接写前缀路径（无 .json 后缀）
    if not out.exists() and Path(str(prefix) + ".json").exists():
        out = Path(str(prefix) + ".json")
    if r.returncode != 0 or not out.exists():
        return None
    d = json.loads(out.read_text(encoding="utf-8"))
    return sum(p.get("clash_total") or 0 for p in d.get("pairs") or [])


# ---------------------------------------------------------------- 主流程
def discover(inputs: list[str], glob: str, recursive: bool) -> list[Path]:
    out: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob(glob) if recursive else p.glob(glob)
            out.extend(x for x in it if x.is_file())
        elif p.exists():
            out.append(p)
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="批量生产总入口：图纸目录进 → 全专业分发算量 → 汇总一本账"
                    "（final_quantity=false）")
    ap.add_argument("inputs", nargs="+", help="图纸目录 / DWG/DXF / 现成识图产物 JSON")
    ap.add_argument("-o", "--out", required=True, help="汇总输出目录（写 pipeline.json / 一本账.md）")
    ap.add_argument("--glob", default="*.dwg", help="目录扫描扩展名（默认 *.dwg）")
    ap.add_argument("--recursive", action="store_true", help="递归子目录")
    ap.add_argument("--resume", action="store_true", help="断点续跑（跳过已成功图纸）")
    ap.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="单图识图时间预算/秒")
    ap.add_argument("--with-clash", action="store_true", help="附带跨专业碰撞校对（需 cad-clash-check）")
    ap.add_argument("--max", type=int, default=0, help="最多处理 N 张（0=不限），试跑用")
    args = ap.parse_args()

    cfr = find_skill("cad-file-reader")
    tujian = find_skill("tujian-suanliang")
    anz = find_skill("anzhuang-suanliang")
    clash_script = None
    if args.with_clash:
        try:
            clash_script = find_skill("cad-clash-check") / "cad_clash_check.py"
        except FileNotFoundError:
            print("[warn] cad-clash-check 未安装，跳过碰撞", file=sys.stderr)

    outdir = Path(args.out)
    workdir = outdir / "_work"
    workdir.mkdir(parents=True, exist_ok=True)
    state_path = outdir / "_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if (
        args.resume and state_path.exists()) else {}
    # 断点续跑：已完成图的结果从上一次 pipeline.json 找回，保证一本账完整
    prev_path = outdir / "pipeline.json"
    prev_map = {}
    if args.resume and prev_path.exists():
        try:
            for r in json.loads(prev_path.read_text(encoding="utf-8")).get("rows", []):
                prev_map[r.get("file")] = r
        except Exception:
            prev_map = {}

    drawings = discover(args.inputs, args.glob, args.recursive)
    if args.max:
        drawings = drawings[:args.max]
    print(f"待处理 {len(drawings)} 个文件")

    rows: list[dict] = []
    skipped: list[dict] = []
    for i, f in enumerate(drawings, 1):
        key = state_key(f)
        if args.resume and state.get(key) == "ok" and f.name in prev_map:
            rows.append(prev_map[f.name])
            print(f"[{i}/{len(drawings)}] {f.name} 已完成，跳过")
            continue
        row = {"file": f.name, "spec": "", "status": "ok", "outputs": {}}
        try:
            if f.suffix.lower() in (".dwg", ".dxf"):
                w = workdir / f.stem
                detail = run_scan(f, w, cfr, args.budget)
            else:
                detail = f
            data = json.loads(detail.read_text(encoding="utf-8"))
            spec = classify_detail(data)
            row["spec"] = spec
            if spec not in SPEC_GEOMETRY:
                row["status"] = "skipped"
                row["note"] = f"专业判定「{spec}」，无对应算量链"
                skipped.append({"file": f.name, "reason": row["note"]})
                rows.append(row)
                state[key] = "skipped"
                print(f"[{i}/{len(drawings)}] {f.name} → {spec}（跳过）")
                continue
            w = workdir / f.stem
            # 输入已是几何产物（复用 batch/识图侧成果）→ 直接用；否则跑提取。
            # 判据：产物专属键（municipal_geometry/steel_profiles/connections；
            # 注意 members 两边都有不能作判据）或文件名符合 {stem}.{后缀}.json 约定
            is_geo = (f.stem.endswith((".structural", ".steel", ".municipal"))
                      or any(k in data for k in
                             ("municipal_geometry", "steel_profiles", "connections")))
            geo = detail if is_geo else run_geometry(detail, spec, w, cfr)
            row["_geo"] = str(geo)
            if spec == "结构":
                steel_json = geo if geo.name.endswith(".steel.json") else \
                    geo.parent / f"{geo.stem}.steel.json"
                if steel_json.exists():
                    row["outputs"]["steel"] = run_steel(steel_json, w, tujian)
                rb = run_rebar_profile(detail if f.suffix.lower() == ".json" else
                                       (w / f"{f.stem}.detail.json"), tujian)
                if rb:
                    row["outputs"]["rebar"] = rb
            else:
                row["outputs"]["pipe"] = run_pipe(geo, w, anz)
            rows.append(row)
            state[key] = "ok"
            o = row["outputs"]
            print(f"[{i}/{len(drawings)}] {f.name} → {spec}："
                  f"{' '.join(f'{k}={v is not None}' for k, v in o.items()) or '无算量产物'}")
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = str(exc)[:300]
            rows.append(row)
            state[key] = "failed"
            print(f"[{i}/{len(drawings)}] {f.name} 失败：{exc}", file=sys.stderr)

    # 可选：跨专业碰撞（用每图的几何产物）
    if clash_script:
        geo_sides = [(r, Path(r["_geo"])) for r in rows
                     if r["status"] == "ok" and r["spec"] in SPEC_GEOMETRY
                     and r.get("_geo") and Path(r["_geo"]).exists()]
        ci = 0
        for a in range(len(geo_sides)):
            for b in range(a + 1, len(geo_sides)):
                if geo_sides[a][0]["spec"] == geo_sides[b][0]["spec"]:
                    continue
                ci += 1
                n = run_clash_pair(geo_sides[a][1], geo_sides[b][1],
                                   workdir, clash_script, ci)
                if n is not None:  # 对内两侧都记该对总数（含对方碰撞）
                    geo_sides[a][0]["clash_total"] = geo_sides[a][0].get("clash_total", 0) + n
                    geo_sides[b][0]["clash_total"] = geo_sides[b][0].get("clash_total", 0) + n

    report = {"schema": "cad-pipeline/v1", "final_quantity": False,
              "boundary": "批量概算/估算口径；2D 候选提示非 BIM 碰撞检测；"
                          "跨图合计为各图带相加，需人工去重",
              "rows": [{k: v for k, v in r.items() if not k.startswith("_")}
                       for r in rows],
              "skipped": skipped, **aggregate_report(rows)}
    (outdir / "pipeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "一本账.md").write_text(render_md(report), encoding="utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    print(f"完成：{len(rows)} 张（失败 {sum(1 for r in rows if r['status'] == 'failed')}）"
          f"→ {outdir/'一本账.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
