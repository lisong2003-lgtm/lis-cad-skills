---
name: cad-suite
slug: cad-suite
displayName: CAD Suite Review Pipeline
version: 0.3.2
platforms: [macos, windows, linux]
author: lis
license: CC-BY-NC-SA-4.0
description: Routes drawings, parsed contracts, downstream specialties, aggregation and cross-discipline review into one evidence-backed local pipeline. Preserves source hashes, coordinates, confidence tiers and degradation states, and never upgrades candidates into final quantities.
i18n:
  en: README.en.md
  zh: README.md
locale: en-US
locales: [en-US, zh-CN]
---

# CAD 融合流程（cad-suite）

## 融合原则

cad-suite 不是七个技能文档的堆叠，也不是第二套识图或算量算法。它把七个技能接成一条
**证据 → 决策 → 派发 → 台账**的链路，并统一五件跨技能必须一致的事：

1. **入口路由**：按输入是原始图纸、识图产物还是已解析缓存，决定复用、增量识别或重跑。
2. **契约统一**：识图候选、算量候选、碰撞候选都保留来源文件、sha256、坐标证据、置信档位。
3. **状态复用**：同一张图优先复用已有产物；必须重扫时只允许用户要求、图纸变化或没有可用产物。
4. **降级台账**：`ok`、`skipped`、`degraded`、`unavailable` 分开记录，绝不把没跑或读不出写成通过。
5. **口径红线**：所有输出 `final_quantity=false`，只作为概算、估算、复核候选和人工核对底稿。

模块负责领域实现；融合层负责调度和审计。这样源技能改算法、换库或加专业包时，cad-suite
不需要复制实现，只需要保证模块入口、JSON 契约和失败语义不变。

## 模块分工

| 模块 | 在融合链中的职责 | 固有边界 |
|---|---|---|
| `cad-file-reader` | 本地读 DWG/DXF/DWT/PDF，出文字、图层、块、图框、几何、专业识图包、轴网、构件候选与证据坐标 | 只出候选，不算量、不造价 |
| `tujian-suanliang` | 结构混凝土净候选/订货量候选、钢筋标注谱与吨位带、构件级图面-模型校对 | 计划/估算带；不替代翻样、下料、结算 |
| `zhuangshi-suanliang` | 消费房间、做法表、节点与长度/面积候选，映射做法、扣减洞口、出装饰概算与材料台账 | 做法缺项必须标注，不冒充精确清单 |
| `anzhuang-suanliang` | 安装管线分档、电线芯线展开、预留、桥架、喷淋、支吊架、市政管长等概算底稿 | 不出金额，不替代结算 |
| `yuanlin-suanliang` | 苗木图例统计、苗木表基线、闭合铺装面积与 P0-P3 置信分层 | 不替代设计复核、放线、竣工计量 |
| `lis-skill-bus` | 本地缓存、契约推送、项目/楼栋/楼层溯源；命中时同图不重复解析 | 完全本地；缺失时按状态降级，不静默丢溯源 |
| `cad-clash-check` | 构件三分类、轴格定位、2D 空间候选、属性冲突、洞口/穿墙语义、碰撞报告 | 2D 倾向提示，非 BIM 碰撞检测 |

`cross/engine.py` 与 `cross/adapt.py` 是到 `cad-clash-check` 的转发层，唯一实现在
`modules/cad-clash-check`。依赖缺失时报错并给安装指引，不回退到第二份实现。

## 两条入口

### 1. 项目级流程：`suite_run.py`

适合一套图纸要做完整性检查、关系推断、跨图聚合、土建算量和出表。

```bash
# 原始图纸直进
python3 scripts/suite_run.py --inputs 图纸1.dwg 图纸2.dwg --out-dir 输出目录

# 扫描挂载盘/目录
python3 scripts/suite_run.py --roots /Volumes/拓展 --pack structural --out-dir 输出目录

# 已有识图产物：只重跑下游，不重新解图
python3 scripts/suite_run.py --prebuilt 输出目录/scan/*_detail.json --out-dir 新输出目录
python3 scripts/suite_run.py --prebuilt 输出目录/structural/*.structural.json --out-dir 新输出目录

# 开启 bus 缓存与溯源
python3 scripts/suite_run.py --inputs 图纸.dwg --out-dir 输出目录 \
  --use-bus --project 项目 --building 5# --floor 三层
```

主线阶段：

```text
s0 发现图纸 → s1a 本地识图 → s1b 专业识图契约 → s1c 缓存/溯源
s2 图纸关系 → s3a 钢筋牌号 → s3 跨图聚合 → s4 跨专业配对与轴网核对
s5a 图框/板厚准备 → s5 专业算量 → s6 统一报告与复核清单
```

主入口当前优先覆盖结构、市政、钢结构和碰撞校对链路。装饰、安装 MEP 和园林已有模块能力，
但项目级批量终点仍需按对应技能的专用输入调用；SKILL.md 不把它们伪装成已全自动接入。

### 2. 批量生产入口：`cad_pipeline.py`

适合多专业、多文件批量过账。

```bash
python3 scripts/cad_pipeline.py 图纸目录 -o 汇总目录 --glob "*.dwg" --recursive --resume
python3 scripts/cad_pipeline.py 图纸目录 -o 汇总目录 --with-clash
python3 scripts/cad_pipeline.py a.detail.municipal.json b.detail.json -o 汇总目录
```

流程是：发现图纸 → cad_scan 识图 → 专业判定 → 对应几何提取 → 钢结构吨位/市政管长/钢筋标注谱
→ 可选跨专业碰撞 → `pipeline.json` 与《一本账.md》。单图失败只入台账，不中断整批。

## 融合后的新增能力

这些能力不是七个源技能单独完整具备的：

- **统一证据账**：把识图候选、算量结果、碰撞候选放入同一套 `source.sha256`、来源模块、
  坐标证据、置信档位和复核原因的语境中。
- **跨图视角**：从单张图理解升级到楼层序列、单体聚类、缺图清单、跨专业配对和轴网一致性。
- **自动派发**：根据专业判定把结构、市政、给排水、钢结构送入对应下游，并拒绝建筑图误走市政管长链。
- **同图复用**：输出目录已有产物或 bus 命中时优先复用；`--prebuilt` 按内容判类型并跳过已完成阶段。
- **跨技能碰撞接口**：`cross/` 统一适配识图产物，`--with-clash` 可在批量流水线中附加碰撞候选。
- **降级报告**：每个阶段给出 `ok/skipped/degraded/unavailable` 与原因，最终报告专列未执行项。
- **口径守门**：报告、JSON、Markdown 和交接单统一标注 `final_quantity=false`。

## 结果怎么读

| 文件 | 作用 |
|---|---|
| `SUITE-REPORT.md` | 先看阶段状态、降级项、置信说明和必须人工复核的点 |
| `relation.json/.md` | 单体、楼层序列、图种、专业、配对建议、缺图清单 |
| `rebar-legend.json/.md` | 本批图纸说明表反解出的「钢筋符号 → 牌号」映射；映射不跨项目串用 |
| `aggregate.json/.md/.csv` | 楼层、构件规格、钢筋直径、牌号分布等跨图表 |
| `compare-plan.json` | 跨专业配对与轴网核对结论；配对成功不等于构件级对照完成 |
| `qty-prepare.json` | 可算量图框、图框标题、板厚分布；默认板厚是近似，不是实测分档 |
| `qty-handoff.json` | 土建算量逐张结果；毛量与净量分开列 |
| `pipeline.json` / `一本账.md` | 批量图纸专业分布、结果、失败原因、碰撞候选和跨图合计警示 |
| `clash_*.json/.md` | 碰撞候选、属性冲突、预留通道、位置证据和施工计划模板 |

## 使用决策

1. **已有识图产物存在且图纸未变化**：直接复用，不做整图重扫。
2. **已有产物缺某类字段**：只做新增薄层或最小增量识别，仍走 cad-file-reader 统一契约。
3. **图纸 hash/时间戳变化**：允许重扫，并保留旧台账。
4. **找不到产物**：先查共享产物目录、`outputs`、`work`、恢复包和历史交接；确认无可用产物后再解析。
5. **需要结算、翻样、下料、对量、正式报价**：不使用本技能输出作为依据，交专项流程复核。
6. **需要装饰、安装 MEP、园林专用底稿**：按源技能输入要求准备房间表、做法表、回路表或图例，再派发；融合层如实记录为手动派发项。

## 红线

1. **图纸不出机**：解析、缓存、报告、台账都只落本机；不得上传、联网或进入发布包。
2. **`final_quantity=false`**：所有量是候选、估算带或概算底稿，不是结算量。
3. **不编造**：牌号、楼层、截面、轴号、图框、管线长度、碰撞位置取不到就如实降级，不猜。
4. **置信不升级**：融合层不把 `inferred_candidate` 或 `review_required` 提升为 `confirmed_evidence`。
5. **不复制算法**：模块内实现只通过 `modules/` 原样同步与子进程调用；`cross/` 转发 cad-clash-check。
6. **失败必须可见**：非零退出、空产物、读不出、缺依赖都写入台账和报告。
7. **公司资料不发布**：真图、项目路径、测试产物和公司文档不得进 GitHub、SkillHub、ClawHub 包。

## 部署与同步

```text
cad-suite/
├── SKILL.md
├── manifest.json
├── scripts/suite_run.py
├── scripts/cad_pipeline.py
├── cross/compare.py, adapt.py, engine.py
├── extract/normalize.py, confidence.py, merge_floor.py
├── modules/
│   ├── cad-file-reader/
│   ├── tujian-suanliang/
│   ├── zhuangshi-suanliang/
│   ├── anzhuang-suanliang/
│   ├── yuanlin-suanliang/
│   ├── lis-skill-bus/
│   └── cad-clash-check/
└── references/
    ├── capability-matrix.md
    ├── boundaries.md
    └── stage-contract.md
```

`modules/` 是可替换实现层，调度层不 import 业务模块，全部按模块 CLI 和 JSON 契约通信。
源技能更新后运行：

```bash
python3 scripts/resync_modules.py
python3 scripts/resync_modules.py --check
python3 scripts/check_install.py
```

`modules/cad-file-reader/vendor` 是符号链接，指向本机 CAD 依赖。同步时保留链接、不解引用；
没有 vendor 的机器识图阶段会失败，必须先按 cad-file-reader 依赖说明安装依赖。因此融合包
不是自包含分发包。

## 验证

```bash
cd <skills-root>/cad-suite
python3 -m pytest -q extract/tests cross/tests scripts/tests
python3 scripts/check_install.py
python3 scripts/resync_modules.py --check
```

测试覆盖契约归一、置信分层、楼层归并、cross 与 cad-clash-check 行为一致、suite 调度和批量流水线。
