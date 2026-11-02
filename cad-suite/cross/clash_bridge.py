#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross/clash_bridge.py —— 跨专业校对的唯一真相桥接层。

为什么有这个模块
----------------
cad-suite/cross 与 cad-clash-check 曾各存一份实现（engine / adapt）。
cad-clash-check 0.1.3 落地的 entity 通道（圆实体提取）只进了 clash 侧，
cad-suite 侧仍停在 0.1.2 —— 同一对图纸，两个入口给出的碰撞候选不一样。

本模块把 cad-suite/cross 改成转发层：实现只留一份（cad-clash-check），
cad-suite 侧只做定位与加载。行为一致性由 cross/tests/test_cross_parity.py 钉住。

探测顺序
--------
① 环境变量 CAD_CLASH_CHECK_HOME（指向其 scripts 目录或其根目录）
② 包内 modules/cad-clash-check/scripts（发布时若嵌套进 cad-suite）
③ 与 cad-suite 同级的 cad-clash-check（<workbuddy-skills-root>、<skills-root> …）
④ 已知本地发布仓库 ~/Documents/GitHub/lis-cad-skills/cad-clash-check

找不到就抛错，不静默降级 —— 静默降级正是两份实现漂移的根因。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE_ROOT = _HERE.parent

ENGINE_SYMBOLS = ("CrossEngine", "Member", "CompareResult", "norm_grid",
                  "GRID_NORM", "AX_NUM_RE")
ADAPT_SYMBOLS = ("adapt", "_nearest_axis", "_bucket", "_floor_of", "_bbox_of",
                 "_is_annotation_text", "DEFAULT_AXIS_TOL", "DEFAULT_BUCKET")


def _candidate_dirs() -> list[Path]:
    """候选的 cad-clash-check scripts 目录，按优先级。"""
    cands: list[Path] = []

    env = os.environ.get("CAD_CLASH_CHECK_HOME", "").strip()
    if env:
        p = Path(env).expanduser()
        cands += [p / "scripts", p]

    # 包内嵌套（发布时若把 clash-check 一并打进 modules/）
    cands.append(_SUITE_ROOT / "modules" / "cad-clash-check" / "scripts")

    # 与 cad-suite 同级安装（各 skills 根目录）
    for skills_root in (_SUITE_ROOT.parent,
                        Path.home() / ".workbuddy" / "skills",
                        Path.home() / ".codex" / "skills",
                        Path.home() / "Documents" / "GitHub" / "lis-cad-skills"):
        cands.append(skills_root / "cad-clash-check" / "scripts")

    # 发布仓库直挂
    cands.append(Path.home() / "Documents" / "GitHub" / "lis-cad-skills"
                 / "cad-clash-check" / "scripts")
    return cands


def find_clash_scripts() -> Path | None:
    """返回可用的 cad-clash-check scripts 目录；找不到返回 None。"""
    for d in _candidate_dirs():
        try:
            if d.is_dir() and (d / "clash_engine.py").is_file() \
                    and (d / "clash_adapt.py").is_file():
                return d.resolve()
        except OSError:
            continue
    return None


def require_clash_scripts() -> Path:
    """返回 scripts 目录；找不到时抛出带指引的错误（不静默降级）。"""
    d = find_clash_scripts()
    if d is None:
        raise RuntimeError(
            "未找到 cad-clash-check（跨专业校对唯一实现）。\n"
            "cad-suite/cross 自 0.2.4 起只做转发，实现已收敛到 cad-clash-check，"
            "不再保留副本，以免两份实现漂移。\n"
            "请安装 cad-clash-check，或设置环境变量指向它：\n"
            "    export CAD_CLASH_CHECK_HOME=<workbuddy-skills-root>/cad-clash-check\n"
            f"已探测：{', '.join(str(c) for c in _candidate_dirs()[:6])} …"
        )
    return d


def _load(name: str):
    """从 clash-check 的 scripts 目录按文件路径加载模块。"""
    d = require_clash_scripts()
    path = d / f"{name}.py"
    mod_name = f"_clash_bridge_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def engine_module():
    return _load("clash_engine")


def adapt_module():
    return _load("clash_adapt")


def clash_home() -> Path:
    """cad-clash-check 根目录（供上层打印来源）。"""
    return require_clash_scripts().parent


def __getattr__(name: str):
    """按需把 clash 侧的符号转出（engine / adapt 共用命名空间）。"""
    if name in ENGINE_SYMBOLS:
        return getattr(engine_module(), name)
    if name in ADAPT_SYMBOLS:
        return getattr(adapt_module(), name)
    raise AttributeError(f"clash_bridge 无符号：{name}")


if __name__ == "__main__":
    try:
        home = clash_home()
    except RuntimeError as e:
        print(f"[错误] {e}", file=sys.stderr)
        raise SystemExit(2)
    print(f"cad-clash-check 位置：{home}")
    eng = engine_module()
    ad = adapt_module()
    print(f"engine 符号：{', '.join(s for s in ENGINE_SYMBOLS if hasattr(eng, s))}")
    print(f"adapt  符号：{', '.join(s for s in ADAPT_SYMBOLS if hasattr(ad, s))}")
