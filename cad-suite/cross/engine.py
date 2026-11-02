#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross/engine.py —— 跨专业校对公共引擎 P0（转发层）。

0.2.4 起本文件不再自带实现，符号全部转出 cad-clash-check/clash_engine.py。
原因：两侧曾各存一份实现，长期必然漂移——0.1.3 的 entity 通道已出现单侧
落地（只进了 clash 侧），同一对图纸两个入口结果不一致。现在实现只留一份
（唯一真相），本层只做转出，一致性由 cross/tests/test_cross_parity.py 钉住。

引擎自身的定位与设计（原说明，仍有效）
--------------------------------------
方案定位（§4.2，采纳 Codex 的公共引擎架构）：不按专业对写 N 套，
一次建好统一对象模型与比较骨架，全部专业对复用。

诚实边界（必须随结果告知）：这是 2D 图纸的**一致性倾向提示 / 校对辅助**，
不是 BIM 碰撞检测（无 3D 模型）；输出「疑似冲突清单 + 待人工复核的坐标证据」，
不是盖章结论。final_quantity=false。

统一 key = 项目 + 楼层 + 轴网位置 + 构件名。
两两比较三视图：
  占位（place）   一方有该 key、另一方没有 → warn（可能未建/未识别）
  属性（attr）    同 key 的共享属性不一致（如 混凝土标号/洞口宽）→ conflict
  关联（relate）  一方声明引用另一方的构件（如 门窗洞→结构洞口），引用落空 → warn

每条结果带 severity(pass/warn/conflict) + evidence（双方来源与坐标）+
residualReason（无法判定时的原因）。坐标缺失时只做 key 级比较并如实标注
no_evidence（降级：place/attr 仍可用，坐标级核对跳过）。

用法
    from engine import CrossEngine, Member
    result = CrossEngine().compare(members_a, members_b, relations=rels)
    result.to_json() / to_md()

依赖 cad-clash-check；找不到时报错并给出安装指引，不静默降级。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clash_bridge  # noqa: E402

_ENGINE = clash_bridge.engine_module()

Member = _ENGINE.Member
CompareResult = _ENGINE.CompareResult
CrossEngine = _ENGINE.CrossEngine
norm_grid = _ENGINE.norm_grid
GRID_NORM = _ENGINE.GRID_NORM
AX_NUM_RE = _ENGINE.AX_NUM_RE

__all__ = ["Member", "CompareResult", "CrossEngine", "norm_grid",
           "GRID_NORM", "AX_NUM_RE"]


def __getattr__(name: str):
    """其余符号（含内部函数）一并转出，避免转发层遗漏导致再次分叉。"""
    try:
        return getattr(_ENGINE, name)
    except AttributeError:
        raise AttributeError(f"cross/engine 无符号：{name}")


def engine_source() -> Path:
    """实现的真实文件位置（供测试与排障确认唯一真相）。"""
    return Path(_ENGINE.__file__).resolve()


if __name__ == "__main__":
    print(f"实现来源：{engine_source()}")
    print(f"转出符号：{', '.join(__all__)}")
