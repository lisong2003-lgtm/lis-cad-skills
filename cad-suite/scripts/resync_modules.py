#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 7 个技能原样同步进 cad-suite/modules/。

为什么要有这个脚本
------------------
融合 skill 不能在内部复制业务算法，否则两边会慢慢分叉。modules/ 里的内容必须是
兄弟目录（~/Documents/GitHub/lis-cad-skills/<name>）的**原样副本**，同步只走这一个入口，
任何时候都能一条命令刷新，也随时能看出 modules 是否落后于源。

关于符号链接
------------
`cad-file-reader/vendor` 是符号链接（指向本机 40~70MB 的 CAD 依赖：numpy / ezdxf / ezdwg）。
「原样副本」意味着链接也要原样保留，绝不能被解引用成真实文件目录——否则 modules 会从
约 6MB 膨胀到 60MB，且把一份可随时重装的依赖钉死进融合包。历史 bug：
`shutil.copytree` 默认 symlinks=False 会解引用，而 `Path.rglob` 在 Python 3.13 默认不跟随
链接，两侧计数口径不一致，导致 --check 报「全部一致」但实际差了 1740 个文件。
所以这里统一约定：**任何符号链接都当作叶子条目，只比较链接目标，永不递归进去。**

用法：
    python3 scripts/resync_modules.py            # 同步（覆盖）
    python3 scripts/resync_modules.py --check    # 只检查差异，不写
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SUITE_DIR = Path(__file__).resolve().parents[1]
MODULES = SUITE_DIR / "modules"

MODULE_NAMES = [
    "cad-file-reader",
    "tujian-suanliang",
    "zhuangshi-suanliang",
    "anzhuang-suanliang",
    "yuanlin-suanliang",
    "lis-skill-bus",
    "cad-clash-check",
]

# 开发仓库里 cad-suite 与各源技能同层；安装目录里源技能在其父目录的 skills/ 下。
if (SUITE_DIR.parent / MODULE_NAMES[0]).is_dir():
    SOURCE_ROOT = SUITE_DIR.parent
elif (SUITE_DIR.parent / "skills" / MODULE_NAMES[0]).is_dir():
    SOURCE_ROOT = SUITE_DIR.parent / "skills"
else:
    SOURCE_ROOT = SUITE_DIR.parent

IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".idea", ".vscode", "node_modules"}
IGNORE_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
# 运行时生成的自检产物：两边跑的时间不同、内容天然不同，纳入比对会让 --check 永远报差异。
# 它们也不该进融合包——融合包要的是「能力」，不是某次自检的流水账。
IGNORE_NAMES = {
    "doctor-report.json", "doctor-report.md",
    "cad-self-test-report.json", "cad-self-test-report.md",
}

# 运行依赖目录不复制进融合包：源侧是本机实体依赖，包侧只保留指向它的链接。
# 这样模块运行时仍能找到依赖，但融合包不被 70MB 级依赖撑大，也不会被解引用钉死。
SPECIAL_LINK_DIRS = {"cad-file-reader": {"vendor"}}

# 指纹类型：("link", 链接目标) 或 ("file", 字节数)
MISSING = "missing"
DIFFERENT = "different"
EXTRA = "extra"


def _skip(rel: Path) -> bool:
    if any(part in IGNORE_DIRS for part in rel.parts):
        return True
    if rel.name in IGNORE_NAMES:
        return True
    return rel.suffix in IGNORE_SUFFIXES or rel.name == ".DS_Store"


def scan_root(root: Path) -> dict[str, tuple]:
    """收集 root 下所有条目的轻量指纹（相对路径 -> 指纹）。

    符号链接录成 ("link", target) 并停止下钻：既避免断链时 stat 报错，
    也保证两侧口径一致（不因为源侧 rglob 不跟随、副本侧已解引用而错位）。
    """
    out: dict[str, tuple] = {}
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        # os.walk 的 dirnames 里可能含指向目录的链接，剪掉它们并单独登记
        keep = []
        for d in dirnames:
            full = base / d
            if full.is_symlink():
                out[str(full.relative_to(root))] = ("link", os.readlink(full))
                continue
            keep.append(d)
        dirnames[:] = [d for d in keep if d not in IGNORE_DIRS]
        for f in filenames:
            full = base / f
            rel = full.relative_to(root)
            if _skip(rel):
                continue
            if full.is_symlink():
                out[str(rel)] = ("link", os.readlink(full))
            else:
                try:
                    out[str(rel)] = ("file", full.stat().st_size)
                except OSError:
                    out[str(rel)] = ("file", -1)
    return out


def compare_module(name: str, src_root: Path | None = None, dst_root: Path | None = None) -> dict[str, list[str]]:
    """双向比对：缺失 / 内容不同 / 副本多余。三个列表都为空才算一致。

    src_root / dst_root 可注入，纯为了单测能造临时目录。
    """
    src = (src_root or SOURCE_ROOT) / name
    dst = (dst_root or MODULES) / name
    src_map = scan_root(src)
    for rel in SPECIAL_LINK_DIRS.get(name, set()):
        special = src / rel
        if special.exists() and not special.is_symlink():
            # 源侧实体依赖在融合包里约定为链接；比较前把两侧口径统一。
            src_map = {
                key: value for key, value in src_map.items()
                if key != rel and not key.startswith(f"{rel}/")
            }
            src_map[rel] = ("link", str(special.resolve()))
    dst_map = scan_root(dst)
    result = {MISSING: [], DIFFERENT: [], EXTRA: []}
    for rel, fp in src_map.items():
        if rel not in dst_map:
            result[MISSING].append(rel)
        elif dst_map[rel] != fp:
            result[DIFFERENT].append(rel)
    for rel in dst_map:
        if rel not in src_map:
            result[EXTRA].append(rel)
    return result


def sync_module(name: str, src_root: Path | None = None, dst_root: Path | None = None) -> str:
    src = (src_root or SOURCE_ROOT) / name
    dst = (dst_root or MODULES) / name
    if not src.is_dir():
        return f"跳过 {name}：源目录不存在"
    # 不用 rmtree 清空再复制：单次批量删除有阈值限制（本机 50 个/轮），
    # cad-file-reader 有 190+ 个文件，会被安全策略直接拦下，同步静默失效
    # ——表现就是「跑过同步了，modules 里还是旧代码」。改成覆盖式复制，
    # 再按双向比对逐个删掉源侧已不存在的文件，删除量小且可控。
    # 目标里残留的同名符号链接会让 copytree 报 "File exists"（源侧也是链接时，
    # 它会去 symlink 到一个已经存在的路径）。先删链接本身——只删链接、不碰目标
    # 内容，数量极少，不会触发批量删除阈值。
    if dst.exists():
        for existing in dst.rglob("*"):
            if existing.is_symlink():
                existing.unlink()
    # symlinks=True：链接原样保留，不解引用（见模块 docstring 的历史 bug）
    shutil.copytree(
        src,
        dst,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*IGNORE_DIRS, *IGNORE_SUFFIXES),
    )
    for rel in SPECIAL_LINK_DIRS.get(name, set()):
        special_src = (src / rel).resolve()
        special_dst = dst / rel
        if not special_src.is_dir():
            continue
        if special_dst.is_symlink():
            special_dst.unlink()
        elif special_dst.exists():
            # 只处理同步副本里的依赖目录；源侧依赖不动。
            shutil.rmtree(special_dst)
        os.symlink(str(special_src), special_dst)
    pruned = 0
    for rel in compare_module(name, src_root, dst_root)[EXTRA]:
        try:
            (dst / rel).unlink()
            pruned += 1
        except OSError:
            continue
    entries = scan_root(dst)
    n_link = sum(1 for v in entries.values() if v[0] == "link")
    tail = f"（含 {n_link} 个符号链接，未解引用）" if n_link else ""
    if pruned:
        tail += f"（清理源侧已删除的 {pruned} 个文件）"
    return f"同步 {name}：{len(entries)} 个条目{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description="把 7 个技能原样同步进 cad-suite/modules/")
    ap.add_argument("--check", action="store_true", help="只检查差异，不写入")
    ap.add_argument("--verbose", action="store_true", help="列出每个差异文件")
    args = ap.parse_args()

    MODULES.mkdir(parents=True, exist_ok=True)
    # 本脚本的「源」是 cad-suite 的父目录。只有当父目录就是开发仓库（lis-cad-skills）时，
    # 兄弟目录才是权威源；在 <workbuddy-skills-root>、<skills-root> 这类安装目录里跑，
    # 兄弟目录只是安装副本（含运行时产物、可能落后于仓库），此时报的差异不可当真。
    if not (SOURCE_ROOT / ".git").exists():
        print(f"  ! 当前源目录 {SOURCE_ROOT} 不是开发仓库（无 .git），比对对象是安装副本。")
        print("    正式同步/校验请在 ~/Documents/GitHub/lis-cad-skills 下执行。")
    stale = 0
    for name in MODULE_NAMES:
        if not (SOURCE_ROOT / name).is_dir():
            print(f"  ✗ {name}: 源目录不存在（{SOURCE_ROOT / name}）")
            stale += 1
            continue
        if not args.check:
            print("  " + sync_module(name))
            continue
        dims = compare_module(name)
        n_missing, n_diff, n_extra = (len(dims[k]) for k in (MISSING, DIFFERENT, EXTRA))
        if not (n_missing or n_diff or n_extra):
            total = len(scan_root(SOURCE_ROOT / name))
            print(f"  ✓ {name}: {total}/{total} 一致")
            continue
        stale += 1
        total = len(scan_root(SOURCE_ROOT / name))
        parts = []
        if n_missing:
            parts.append(f"{n_missing} 个缺失")
        if n_diff:
            parts.append(f"{n_diff} 个内容不同")
        if n_extra:
            parts.append(f"{n_extra} 个副本多余")
        print(f"  ✗ {name}: {total - n_missing - n_diff}/{total} 一致（" + "，".join(parts) + "）")
        if args.verbose:
            for key, label in ((MISSING, "缺失"), (DIFFERENT, "不同"), (EXTRA, "多余")):
                for rel in sorted(dims[key])[:20]:
                    print(f"      - {label}: {rel}")
                if len(dims[key]) > 20:
                    print(f"      - {label}: …… 另有 {len(dims[key]) - 20} 个")
    if args.check:
        print("全部一致" if stale == 0 else f"有 {stale} 个模块需要同步（跑一次不带 --check 即可）")
    return 0 if stale == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
