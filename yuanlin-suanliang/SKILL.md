---
name: yuanlin-suanliang
slug: yuanlin-suanliang
displayName: 园林算量 · 苗木统计与铺装面积
version: 0.4.30
platforms: [macos, windows, linux]
locale: zh-CN
locales: [zh-CN, en-US]
localeScope: 面向中国建筑工程与园林景观图纸；规则、植物词库与输出证据默认使用简体中文，并对常见英文图例做别名兼容；地域性词表按中文/本地场景设计，其他语言可通过 --plant-library 传入项目词库扩展。
author: lis
license: CC-BY-NC-SA-4.0
description: 基于 cad-file-reader 园林识图候选，按中英文图例分类统计苗木、解析苗木表设计基线、按闭合区域计算铺装面积，可选展开 DXF 块内铺装，输出带使用边界、置信分层（P0–P3）和证据坐标的园林概算底稿与物资计划草稿；不替代设计复核、放线、点树、竣工计量、对量、结算与正式报价。
i18n:
  en: README.en.md
  zh: README.md
---

# 园林算量 v0.4.27

## 语言与区域范围

本技能面向**中国建筑工程与园林景观图纸**：规则、植物词库与输出证据默认使用简体中文，并对常见英文图例做别名兼容；地域性词表（如西北温带荒漠区植物等）明确按中文/本地场景设计。如需其他语言/区域，可通过 `--plant-library` 传入项目词库扩展，不改算法与口径。

**它解决的一件事**：把 `cad-file-reader` 的园林识图候选复算成可复核的苗木统计与铺装面积概算底稿，并明确区分“苗木表设计给定数量”“有坐标的块级实例计数”“无坐标块实例计数”“块引用总数候选”“图例文字标记次数”“铺装强算候选”等口径。

## 适用

- 苗木统计：按乔木、灌木、地被、其他分类；支持中英文常见植物图例词，并区分苗木表基线、平面图块级计数、底座无坐标块实例计数、块引用总数 P2 候选、图例文字 P2 候选。
- 植物名称参考库：内置区域/素材植物库（`rules/plant_library_*.json` 全部默认加载，含常用园林植物 349 名、西北温带荒漠区 131 条、图块素材 311 名与分区苗木选型 1022 名（去别名后新增约 700 名）），可用 `--plant-library` 叠加项目库；**只做分类**，不读规格/密度/单价，不推断规格或报价。
- 铺装面积：优先按铺装图层识别闭合区域，鞋带公式算面积，含洞/内岛按嵌套深度奇偶扣减；可选展开 DXF 图块内闭合铺装环，支持 HATCH/ARC/Bulge 圆弧边界。
- 概算底稿与物资计划草稿：苗木数量、铺装面积、缺项、依据分层落盘。
- 真图边界验证：图层名/块名缺失的转换版 DWG，不硬出铺装面积；强算结果只标 P3 候选。

## 前置（显式依赖）
## 强依赖底座说明（cad-file-reader 强依赖，不做弱化）

本技能采用**识图与算量分离**的固定架构，`cad-file-reader` 是**强依赖底座**，不是可选增强：

- **为什么必须强依赖**：DWG/DXF/DWT/PDF 的解析、图层/文字/块/图框/几何提取、识图候选和测量候选全部集中在底座完成，一次解图、全项目复用，保证证据坐标与契约一致。本技能只做本专业口径的量算、扣减、损耗、分账和台账，不重复解析图纸。
- **分工**：底座输出 `final_quantity=false` 的识图/测量候选；本技能输出本专业概算底稿/物资计划草稿（`final_quantity=true` 仅本专业口径）。
- **版本约束**：底座最低版本以各技能 `SKILL.md`「前置/依赖」写的 `>=x.y.z` 为准；缺底座或版本不够时明确报错，不静默用错误数据。
- **安装**：先装底座（`cad-file-reader` 的 `scripts/setup.sh`），再装本技能；运行时底座可在 `SKILL_NO_BASE=1` 下退化为只读已有扫描/候选/表格输入，但精度受限并必须在结果标注。
- **联动**：装有 lis-skill-bus 时，底座与各算量技能通过 `cad-contract/v1` 共享契约，同一张图只解一次；不装 bus 时各技能自动降级为各自 `state/`，功能不丢失。


- 底座 `cad-file-reader >= 0.28.1` 的 `landscape-geometry` 包是**显式依赖**；不自行解析大 DWG。
- 苗木统计输入：底座 `cad_landscape_geometry` 输出 JSON（`plant_block_legends` / `plant_legends` / `plant_schedule_links` / `systems`）与 `cad_scan` 文字/块引用详情。
- 苗木表解析：从图纸文字中识别“苗木表/苗木配置表”的表头、名称、数量、单位列；数量单位必须来自数量表头括号或单位列，缺失时不默认为株并降 P1。
- 铺装面积输入：`cad_scan --with-geom --with-geom-layer --detail-json` 详情 JSON；应有可用的铺装图层名。
- DXF 块内铺装回退：可选 `--dxf-block-paving`，使用底座 `vendor/ezdxf` 展开 INSERT 变换；只提取命中铺装 token 的闭合 `LWPOLYLINE/POLYLINE/HATCH/ARC`，展开 LWPOLYLINE bulge 圆弧，结果强制 P3。
- DXF 块引用坐标回退：可选 `--dxf-block-refs`，读取模型空间顶层 INSERT 坐标，同名块按坐标去重；只有坐标命中的块引用才升级 P0，无坐标仍保持 P2。
- 扫描件/图片型 PDF 只出苗木文字候选，不给铺装面积。

## 使用流程

1. **识图**：用底座生成园林识图与几何详情。
2. **复算**：运行本技能脚本，得到苗木统计、铺装面积、缺项与台账。
3. **复核**：优先核对 `需核对=是`、P2/P3、含洞/内岛、强算候选行；数量/规格不确定时不猜默认。
4. **交付**：Excel 台账 + CSV + Markdown 报告，用于概算与物资计划核对，不用于结算。

## 脚本用法

```bash
# 1) 底座：园林识图（苗木图例/块分类/铺装闭合域候选）
scripts/cad_scan.sh 景观图.dwg --with-mtext --with-attrib --with-insert --with-blocks --with-block-geom \
  --with-geom --with-geom-layer --detail-json 景观详情.json --format json -o 景观扫描
scripts/cad_landscape_geometry.sh 景观详情.json --out-dir 园林识图

# 2) 本技能：苗木统计 + 铺装面积
bash scripts/yuanlin_qty.sh \
  --landscape 园林识图/景观详情.landscape.json \
  --scan 景观详情.json \
  --out-dir ./园林概算 \
  --project "项目名"

# 3) 可选：DXF 图块内铺装回退（仍强制 P3）
bash scripts/yuanlin_qty.sh \
  --landscape 园林识图/景观详情.landscape.json \
  --scan 景观详情.json \
  --dxf-block-paving 景观图.dxf \
  --out-dir ./园林概算-块铺装候选 \
  --project "项目名"

# 4) 可选：DXF 顶层块引用坐标去重（P2→P0；同名坐标重复不计）
bash scripts/yuanlin_qty.sh \
  --landscape 园林识图/景观详情.landscape.json \
  --scan 景观详情.json \
  --dxf-block-refs 景观图.dxf \
  --out-dir ./园林概算-块坐标 \
  --project "项目名"

# 5) 可选：叠加项目植物名称参考库（只取中文名→大类）
bash scripts/yuanlin_qty.sh \
  --landscape 园林识图/景观详情.landscape.json \
  --scan 景观详情.json \
  --plant-library 项目苗木清单.xlsx \
  --out-dir ./园林概算-项目词库 \
  --project "项目名"
```

可用参数：

- `--rules templates/项目专属规则示例.json`：项目专属图层 token、植物词库、去重半径。
- `--scale 100` / `--drawing-mm-per-unit 1`：覆盖自动比例/单位检测；显式指定后不回改单位。
- `--dedupe-tolerance 0.5`：同名块同坐标去重半径（图纸单位）。
- `--paving-all-geometry`：图层缺失时对全部几何做闭环候选；结果强制 P3、`final_quantity=false`，不计入主线。
- `--dxf-block-paving 图.dxf`：可选回退，展开块内铺装闭合环；结果强制 P3、不计入主线。
- `--dxf-block-refs 图.dxf`：可选回退，读取顶层 INSERT 坐标，同名块按坐标去重；无坐标块引用仍保持 P2，不猜株数。
- `--plant-library 参考库.{json,csv,xlsx}`：可选叠加项目植物名称参考库；**只读中文名与分类章节**，规格/密度/苗价/综合单价等列一律不读、不写进输出；可重复指定。
- `--no-default-plant-library`：不加载全部内置区域库（`rules/plant_library_*.json`，默认全部加载）；只影响分类，不影响数量口径。
- 块引用 P2：底座 `meta.block_refs` 中只有总数、没有坐标的植物块引用，只作复核线索，`final_quantity=false`。

## 输出

- `Yuanlin概算物资计划台账.xlsx`：固定含 `使用边界`、`苗木统计`、`铺装面积`、`缺项核对`、`汇总`、`依据`。
- `园林苗木统计.csv`：分类、来源、植物名/图例名、数量、单位、计量方式、平面图文字标记数、置信分层、证据坐标、需核对、分类依据、参考库命中、计入主线。
- `园林铺装面积.csv`：图层、区域、角色、面积、嵌套深度、计算式、证据坐标、需核对、计入主线。
- `缺项核对.csv`、`汇总.csv`、`依据.csv`、`园林概算报告.md`。

## 苗木口径（v0.4.13）

项目规则可加 `exclude_layers`、`include_layers_regex` 与 `exclude_frame_bbox` 缩小铺装候选；规则只会排除候选，不会改变置信分层。

| 来源 | 计量方式 | 置信 | 是否计入主线 | 说明 |
| --- | --- | --- | --- | --- |
| 苗木表（单位证据完整） | 设计给定（非逐株点数） | P0 | 是，作为设计基线 | 从图纸“苗木表/苗木配置表”名称+数量+单位证据解析；不能冒充平面图逐株点数 |
| 苗木表（单位缺失） | 设计给定（非逐株点数） | P1 | 是，但 `final_quantity=false` | 单位列为“待核对”，不默认为株；不计入株/棵/丛汇总 |
| 苗木表（数量=0，面积式/密度式） | 仅复核线索 | P3 | 否 | 无标题表靠“名称类表头+数量/单位表头”同排组合自识别；支持「中文名称」表头；不按株数推算 |
| 平面图图例（有坐标） | 块级实例去重计数 | P0 | 是（无冲突时） | 同名块按坐标去重；与苗木表冲突时降 P3 并退出主线，逐名对照写入缺项核对 |
| 底座块实例（无坐标） | `instance_count` | P1 | 是，标明未逐点去重 | 底座已给出实例数，但本技能无法复点坐标 |
| DXF 顶层块引用坐标回退 | 同名块坐标去重 | P0 | 是（无冲突时） | 只有显式提供 `--dxf-block-refs` 且读到 INSERT 坐标时启用；坐标重复按去重半径排除 |
| 平面图块引用总数 | `meta.block_refs` 计数 | P2 | 否 | 只有引用总数、无坐标且未去重，只作人工核对线索 |
| 识图图例/种植文字 | 文字出现次数（非株数） | P2 | 否 | 来自 `plant_legends` 或 `systems` 种植文字；用于人工复核和交叉检查 |
| 块名/文字推断失败 | 未计算 | P3 | 否 | 输出降级原因，不猜数量 |

## 植物名称参考库（v0.4.13）

- 内置库 `rules/plant_library_常用园林植物.json`：349 个中文名 → 乔木/灌木/地被/其他，来源为《常用园林植物品种规格及价格清单》的**名称与分类章节**（不含规格、密度、价格）。
- 内置区域/素材库：`rules/plant_library_*.json` 全部默认加载（按文件名稳定排序，先加载者优先）；当前含 `plant_library_常用园林植物.json`（349 名）、`plant_library_西北温带荒漠区.json`（112 名 / 131 条别名）、`plant_library_园林景观CAD图块素材.json`（311 名）与 `plant_library_分区苗木选型.json`（8 个气候区 1022 名 / 去别名后新增约 700 名）。
- 图块素材库只取《园林景观CAD图块》单个树图块的 DWG 文件名，并按乔木/灌木/地被/其他归大类；不读取块内几何作规格推断，不改变数量口径。
- 项目库：`--plant-library 文件.{json,csv,xlsx}`，xlsx 只按“中文名称”列 + 章节行识别；`.json` 支持 `names`/`categories`/`plants` 三种结构；`.csv` 支持 中文名称+分类/类别 或 名称+章节。
- 章节→大类顺序（顺序敏感）：地被（小灌木及地被 / 水生 / 草坪 / 地被 / 草花）→ 灌木（球类灌木 / 大灌木 / 灌木）→ 乔木（常绿乔木 / 落叶乔木 / 乔木）→ 其他（藤本 / 竹类）；避免“小灌木及地被”被误判成灌木。
- 保守口径：参考库**只补原词库缺口**；内建/项目词库已覆盖的名称保持原分类，因此不改变既有主线结果。
- 命中记录：`园林苗木统计.csv` 的 `参考库命中` 列（格式 `大类:名称`）与 `分类依据`；汇总输出 `植物名称参考库条目数`、`参考库命中分类条数`。
- 硬边界：参考库**不含也不读规格、标号、单价**；不据此自动推断规格或报价，不进入任何金额计算。

## 铺装面积口径

- `面积(m²) = 鞋带面积(图纸单位²) × (图纸单位对应毫米数 × 比例)² ÷ 1e6`。
- 外轮廓相加，洞/内岛按嵌套深度奇偶扣减。
- 有铺装图层且能成环：P0/P1 候选，无复核项时可计入主线。
- 含洞、闭环候选超过 50、疑似重复环/文字几何混入：标 `需核对`，退出主线。
- 图层名缺失：默认只出 REVIEW，不给面积；加 `--paving-all-geometry` 才出强算双口径——候选环面积合计与奇偶扣减净值，二者均强制 P3、不计入主线。
- DXF 块内铺装：只在 `--dxf-block-paving` 时输出，展开 INSERT 变换与 HATCH/ARC/Bulge 边界后按环面积合计，强制 P3、不计入主线。
- 过滤“同一节点重复经过”的伪环；但不能替代真实洞、内岛与外轮廓关系确认。

## 置信分层

| 层 | 含义 | 处理 |
| --- | --- | --- |
| P0 | 直接证据 0.86–0.95：块名/坐标直中、苗木表文字直读、干净闭环 | 计入主线；苗木表只作设计基线 |
| P1 | 几何模式/无坐标计数 0.6–0.85 | 计入主线并标注 |
| P2 | 名称/文字推断 0.5–0.6 | 只进候选，不进主线 |
| P3 | 需人工核对：苗木表冲突、无法成环、缺图层、块内铺装、强算候选 | 标 `需核对=是`，排除主线 |

## 证据坐标

汇总表记录比例与图纸单位判定来源（用户覆盖/DXF INSUNITS/图纸文字/规则配置/默认）；每条统计/面积行保留 `文件 | 图层 | 块名/图例名 | 坐标(sample_coords/bbox/center) | 计算式 | 需核对原因`，便于按图复核。P2 图例文字也保留出现位置样例；无坐标块计数标 `无坐标；块计数=N`。

## 边界

1. 苗木数量受块引用/图例命名质量影响：无坐标、块名乱码时只能给苗木表设计基线或 P2/P3 候选，必须人工点数复核。
2. 苗木表数量单位缺失时显示“待核对”，不默认为株；需补看表头或单位列后再计入物资口径。
3. 苗木表数量是设计给定基线，不是平面图逐株点数；二者口径不可混用。
4. 铺装面积依赖可靠图层和闭合环；含洞、细缝、重复环、缺图层时进 `需核对`，不替代设计复核与现场核对。
5. 转换版/净化版 DWG 若图层名为空、块名乱码，铺装面积不可用；强算候选只能作排查线索。
6. 比例/单位自动检测失败时面积不可信，必须用 `--scale` / `--drawing-mm-per-unit` 指定。
7. 扫描件/图片型 PDF 不给铺装面积；苗木文字候选也需人工核对。
8. 不自动把公司数据上传云端，不联网解析图纸。
9. 输出只作概算底稿与物资计划草稿，不作为结算、对量、竣工计量或正式报价依据。

## 真图回归结论（2026-10-14）

- 公司转换版：经十一路安置区景观施工图 `_t3` 边界。
  - `02种植总图+苗木表_t3.dwg`：苗木表 54 条、株数基线 1792；图例/种植文字 P2 15 类/115 次；因图层空、块名空，平面逐株计数不可用。
  - `04铺装详图一_t3.dwg`：默认不硬出面积；强算 403 条 P3 候选、合计 235976.5657 m²，不计主线。v0.2.0 的 561 条/85374.0195 m² 差异来自伪环过滤与“候选环面积合计”口径修正，不是同一口径直接比较。
  - `01总图部分_t3.dwg`、`绿化样本图.dwg`、`绿化设计说明.dwg`：主线 0，降级正确。
- 公开 DXF：
  - riveryard：13 类植物；P0/P1 主线 7 株；P2 块引用 6 类/12 次；DXF 块内铺装 P3 候选 2.52 m²，主线 0。
  - clifftop：40 类植物；P0/P1 主线 34 株；P2 块引用 15 类/46 次；P2 文字 6 类/6 次；铺装未命中，主线 0。
  - drone、greenplan_demo、green-atlas-site、green-atlas-closed-loop、Synovia：主线 0，负向控制通过。
  - 公开样例只作本机回归，不随技能分发；clifftop 许可为 CC-BY-NC-SA 4.0，riveryard 未声明许可证。公司图纸不上云。

## 依赖与降级

- 底座 `cad-file-reader >= 0.28.1` 为显式依赖；缺失时提示先安装底座，不静默用旧数据。
- 只有 landscape 输出、无几何详情：苗木统计可用，铺装面积降级为 review。
- 只有几何详情、无 landscape 输出：铺装面积可用，苗木分类退回块名/文字推断并标注。
- `ezdxf` 仅用于可选 DXF 块内铺装回退；底座 `vendor/ezdxf` 已提供，未安装时该回退不可用，不影响主线。
- 无 `openpyxl`：仍输出 CSV/Markdown，台账 xlsx 跳过。

## lis-skill-bus 可选联动（试点，不强制）

- 状态过滤：项目名/楼栋/楼层一致时，本技能可与 `cad-file-reader` 及其它算量 skill 通过 lis-skill-bus 交换 `cad-contract/v1`；命中即复用，不再重复解图。
- 拉取（开工前，推荐）：`scripts/yuanlin_statesync.sh pull --project 项目 [--building 楼栋] [--floor 楼层] [--out 落盘.json]`
  —— 命中且契约含本专业 section 字段（`plant_legends`、`plant_block_legends`、`plant_schedule_links`、`paving_closed_areas`、`green_area_candidates`、`hardscape`）时返回 `hit=true usable=true`，可直接复用；未命中/缺字段/无 bus 一律返回 `hit=false`/`usable=false`，走本技能正常解析。
- 发布（算量落盘后，可选）：`scripts/yuanlin_statesync.sh push --entry-file <本技能输出.json> --project 项目 [--building 楼栋] [--floor 楼层] [--specialty 园林]`，自动包装成 `cad-contract/v1` 后入 bus。
- 对应接线脚本：`lis-skill-bus/integration/yuanlin_pull_contract.sh` / `yuanlin_publish_contract.sh`（薄壳，等价调用本技能 statesync）。
- 命中口径：`usable=true` 为本机状态里的「候选级命中」（`candidate_only=true`）；命中 section 内若有 `review_required`/P2/P3 项，statesync 只标 `review_flagged`，P0–P3 与复核项过滤仍在本技能算量核心按既有口径完成，不因 bus 命中而跳过滤。
- 命中开关（默认宽松）：默认仍为「至少一个 section 字段命中即 `usable=true`」的候选级命中；加 `--require-core` 后收紧为必选核心 section 至少一个命中且非空（园林=`plant_schedule_links` 苗木表 / `paving_closed_areas` 铺装），缺核心时 `usable=false` 并把缺项写入 `review_flagged`。是否把默认改为收紧属业务口径，待用户/业务确认。
- bus 路径变更：仅需设置 `SKILLBUS_HOME` 指向新 bus 目录，本技能任何文件无需改动。
- 兼容/降级：客户端按如下优先级定位 `skillbus_client.py`，正式路径存在时不回退 dev 副本：
① `SKILLBUS_HOME`（bus 目录）或 `SKILLBUS_CLIENT`（直接指向 client 文件）显式指定
② `$HOME/.codex/mcp_servers/lis-skill-bus/skillbus_client.py`（正式安装落点）
③ `$HOME/.codex/skills/lis-skill-bus/skillbus_client.py` / `$HOME/.codex/skills/.skillbus/skillbus_client.py`
④ 常见本机开发副本（`tan/work` 等，最后才回退）。
命中 dev/临时副本时 stderr 会输出告警行「bus 命中来源：<路径>（临时副本/dev，非正式安装）」，正式路径输出「（正式安装）」；找不到 bus 时不报错，直接写 `$HOME/.codex/skills/.skillbus/state.json`（与 bus 同构，后续装 bus 可无缝读取）。 无 MCP/无 bus 不影响任何算量能力；本技能算法、口径、扣减、损耗、分账与台账逻辑不变。

- Windows 接线：GitHub 完整包 scripts/yuanlin_statesync.cmd push/pull（GitHub/ClawHub 包含 .cmd，SkillHub 轻量包剔除 .cmd、Windows 改用同目录 .py 入口；macOS/Linux 用 `bash scripts/yuanlin_statesync.sh` 等价调用）；等价 lis-skill-bus/integration/yuanlin_publish_contract.sh / yuanlin_pull_contract.sh。Windows 未实机跑通，仅静态校验通过（CRLF 行尾；无 /Users、/bin/sh、python3 硬编码；py 启动器 + %PYTHON%/%CODEX_PYTHON% 回退；默认路径用 %USERPROFILE%\.codex）。

## QTO 五专业联动（P1，可选）

可与 `cad-file-reader` 及其它算量 skill 联动（可选）：识别放 `<项目目录>/识别/<slug>/`，量算层输出写 `<项目目录>/算量/<slug>/`，用底座 `<底座>/scripts/qto_p1_link.py` 登记。此联动只在目录上登记输入/输出与缺口，不替代本技能既有算法、口径与复核。

## 环境与运行时（自动解析，无需手工配置）

- 所有 `scripts/*.sh` 入口都 `source scripts/runtime_env.sh`，由它统一解析三件事：
  1. **解释器**：`CAD_SKILL_PYTHON` / `CODEX_PYTHON` → Codex 运行时 → PATH 上的 `python3.12/3.11` → `python3`（要求 ≥3.10）；
  2. **识图底座**：`CAD_SKILL_DIR` → 同级 `../cad-file-reader` → `~/.workbuddy/skills/*/cad-file-reader` → `~/.claude` → `$HOME/.codex`；
  3. **依赖路径**：把「本技能 scripts + 底座 scripts + 底座 vendor」拼进 `PYTHONPATH`，`ezdxf / ezdwg / openpyxl` 等**无需全局 pip 安装**。
- 推荐用对应的 `bash scripts/<入口>.sh`；直接 `python3 <入口>.py` 只在全局已装齐依赖时可用。
- 依赖缺失时按 `requirements.txt` 安装：`python3 -m pip install -r requirements.txt`。

## 授权与保留

本技能以 **CC-BY-NC-SA-4.0** 授权给公众：可自由使用与改造，但**仅限非商业用途**（个人学习、研究与非营利使用）；改造后若公开发布，须以相同条款授权。

企业、机构或将本技能用于经营性项目（如承接工程造价、算量咨询业务）的商业使用，需另行取得作者书面授权。

作者（lis）作为著作权人，不受上述许可限制，明确保留以下权利：

1. 将本作品用于任何商业目的；
2. 改造、再发布、封装为收费商品或服务；
3. 向第三方授予商业使用授权。

完整许可文本见 `LICENSE.md`。
