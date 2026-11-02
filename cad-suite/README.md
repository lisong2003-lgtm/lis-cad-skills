# cad-suite · CAD 融合流程

一个入口走完七技能融合链：发现图纸 → 本地识图与契约 → 图纸关系 → 跨图聚合 → 跨专业碰撞校对 → 算量派发 → 统一台账。

## 快速开始

```bash
# 1. 给具体图纸
python3 scripts/suite_run.py --inputs a.dwg b.dwg --out-dir out

# 2. 给扫描根（自动发现挂载盘/压缩包内的图纸）
python3 scripts/suite_run.py --roots /Volumes/扩展 --out-dir out

# 3. 换了源技能之后刷新 modules
python3 scripts/resync_modules.py            # 同步
python3 scripts/resync_modules.py --check    # 只看差异
```

## 产物

| 文件 | 内容 |
|---|---|
| `SUITE-REPORT.md` | 先看这个：阶段状态、降级项、钢筋型号表、构件规格表、契约三档 |
| `aggregate.md` / `.csv` / `.json` | 楼层×构件规格、钢筋型号、楼层×直径交叉表 |
| `relation.md` / `.json` | 单体聚类、楼层序列与缺口、专业、同层配对建议 |
| `compare-plan.json` | 跨专业对照计划；缺建筑图时如实列缺 |
| `qty-handoff.json` | 算量交接单（不是工程量） |
| `run-summary.json` | 机器可读的阶段状态 |

## 结构

```
cad-suite/
├── SKILL.md              技能说明（触发词、七阶段、边界）
├── scripts/suite_run.py  流程调度（不含业务算法）
├── scripts/resync_modules.py
├── modules/              7 个技能的原样副本
└── references/           能力矩阵 / 红线与已知缺陷 / 阶段契约
```

## 注意

- `modules/` 是原样副本（含 cad-file-reader 的 vendor，约 54MB）。发布包应改为 vendor 自举，
  不要分发二进制。
- 所有输出 `final_quantity=false`，**不是工程量**。
- 已知缺陷见 `references/boundaries.md`：部分 DWG 解析失败、部分文件图层名解不出（用 `#句柄` 标注）、
  牌号常为 unknown。**不要用版本号承诺"能读"。**
