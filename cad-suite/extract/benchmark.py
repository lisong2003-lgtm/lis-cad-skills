#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract/benchmark.py —— 单图解析速度基线。

方案定位（§五 阶段1 第4项）：单图解析耗时基线。对一张 DWG 计时跑各阶段 CLI：
  scan      cad_scan.py（文本/图层/构件索引）
  geometry  cad_geometry.py（构件几何展开，tujian）
  报告       两阶段合计与 MB/s 吞吐

输出 json/md 基线表，final_quantity=false。仅本机计时，图纸不上云。

用法
  python3 extract/benchmark.py --dwg /path/图.dwg --out-prefix 速度基线 [--repeat 2]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path

CAD_FR = Path.home() / ".workbuddy/skills/cad-file-reader/scripts"
TUJIAN = Path.home() / ".workbuddy/skills/tujian-suanliang/scripts"


def _run(cmd: list[str], timeout: int = 600) -> tuple[float, int]:
    env = dict(**__import__("os").environ)
    extra = f"{CAD_FR}:{CAD_FR.parent / 'vendor'}"
    env["PYTHONPATH"] = f"{extra}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else extra
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    dt = time.perf_counter() - t0
    if r.returncode not in (0,):
        raise SystemExit(f"❌ 阶段失败：{' '.join(cmd[:3])}\n{r.stderr[-500:]}")
    return dt, r.returncode


def benchmark(dwg: str, workdir: str, repeat: int = 1,
              floor_label: str | None = None) -> dict:
    dwg_path = Path(dwg)
    size_mb = dwg_path.stat().st_size / 1024 / 1024
    out_dir = Path(workdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: dict[str, dict] = {}

    for i in range(max(1, repeat)):
        tag = "" if i == 0 else f"_{i}"
        scan_out = out_dir / f"bench_scan{tag}"
        detail_out = out_dir / f"bench_detail{tag}.json"
        dt, _ = _run([sys.executable, str(CAD_FR / "cad_scan.py"), str(dwg_path),
                      "-o", str(scan_out), "--format", "json",
                      "--detail-json", str(detail_out)])
        stages.setdefault("scan", {"seconds": 0.0, "runs": 0})["seconds"] += dt
        stages["scan"]["runs"] += 1
    for s in stages.values():
        s["seconds"] = round(s["seconds"] / s["runs"], 2)

    scan_json = out_dir / "bench_scan.json"
    detail_json = out_dir / "bench_detail.json"
    if floor_label and scan_json.exists() and detail_json.exists():
        geom_out = out_dir / "bench_geom"
        try:
            dt, _ = _run([sys.executable, str(TUJIAN / "cad_geometry.py"),
                          str(dwg_path), "--scan", str(scan_json),
                          "--detail", str(detail_json),
                          f"--floor-label={floor_label}", "-o", str(geom_out)],
                         timeout=900)
            stages["geometry"] = {"seconds": round(dt, 2), "runs": 1}
        except SystemExit as e:
            stages["geometry"] = {"seconds": None, "runs": 0, "note": str(e)[-200:]}
    else:
        stages["geometry"] = {"seconds": None, "runs": 0,
                              "note": "未提供 --floor-label，跳过 geometry 阶段"}

    total = sum(s["seconds"] or 0 for s in stages.values())
    summary = {
        "图纸": str(dwg_path),
        "大小MB": round(size_mb, 2),
        "repeat": max(1, repeat),
        "总耗时s": round(total, 2),
        "吞吐MB/s": round(size_mb / total, 2) if total > 0 else None,
        "final_quantity": False,
    }
    return {"summary": summary, "stages": stages}


def render_md(out: dict, title: str) -> str:
    md = StringIO()
    s = out["summary"]
    md.write(f"# {title}（单图解析速度基线）\n\n")
    md.write(f"- 图纸 `{s['图纸']}`（{s['大小MB']} MB，repeat={s['repeat']}）\n")
    md.write(f"- 总耗时 **{s['总耗时s']} s**，吞吐 **{s['吞吐MB/s']} MB/s**\n\n")
    md.write("| 阶段 | 耗时s |\n|---|---|\n")
    for k, v in out["stages"].items():
        md.write(f"| {k} | {v['seconds'] if v['seconds'] is not None else '—'} |\n")
    return md.getvalue()


def build(dwg: str, workdir: str, out_prefix: str, repeat: int = 1,
          floor_label: str | None = None) -> Path:
    out = benchmark(dwg, workdir, repeat, floor_label=floor_label)
    out_base = Path(out_prefix)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    Path(str(out_base) + ".json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(str(out_base) + ".md").write_text(render_md(out, out_base.name), encoding="utf-8")
    s = out["summary"]
    print(f"[速度基线] {s['大小MB']} MB 共 {s['总耗时s']} s（{s['吞吐MB/s']} MB/s）")
    return out_base


def main() -> None:
    ap = argparse.ArgumentParser(description="Single-drawing parsing speed baseline")
    ap.add_argument("--dwg", required=True)
    ap.add_argument("--workdir", default="/tmp/cad_bench")
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--floor-label", default=None,
                    help="可选：提供后追加 geometry 阶段计时")
    a = ap.parse_args()
    build(a.dwg, a.workdir, a.out_prefix, a.repeat, floor_label=a.floor_label)


if __name__ == "__main__":
    main()
