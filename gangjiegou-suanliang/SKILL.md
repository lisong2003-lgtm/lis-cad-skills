---
name: gangjiegou-suanliang
slug: gangjiegou-suanliang
displayName: 钢结构算量 · 吨位估算带
version: 0.3.1
platforms: [macos, windows, linux]
author: lis
license: CC-BY-NC-SA-4.0
description: "钢结构算量：消费 cad-file-reader 的 *.steel.json，按截面标注/米重公式/显式或图面长度出吨位估算带（json/md/csv），含牌号分档、构件归并、连接计数、节点板、涂装面积、复核清单。不做识图，不替代深化/翻样/下料/结算/报价。"
i18n:
  en: README.en.md
  zh: README.md
locale: zh-CN
---

# 钢结构算量

本技能只做一件独立的事：把 `cad-file-reader` 的 `cad-steel-geometry/v1` 产物转成可复核的钢结构吨位估算带。识图、图纸解析、证据提取都归 `cad-file-reader`；本技能不读取 DWG/DXF/DWT/PDF，也不复制识别实现。

正式识图链路固定为 `cad-file-reader -> cad-contract/v1 -> lis-skill-bus -> gangjiegou-suanliang`：

- `cad-file-reader` 是唯一图纸解析器，只解图一次并生成 `cad-contract/v1`。
- `lis-skill-bus` 是唯一定接线，不解析图纸，只传递和复用契约。
- 本技能不提供第二套识图路径。bus 缺失时正式识图链路停止并提示安装；已经由该链路生成并留存的官方契约仍可直接送入 `steel_tonnage.py` 做计算或回归。
- 算量结果必须带契约来源（图号/坐标证据）。
- 首次使用或换机后先运行 `python3 scripts/steel_tonnage.py --check-deps`：齐全退出 0，缺依赖退出 1 并明确列出；缺依赖只阻断“从 DWG 开始”的正式识图链路，不阻断已有契约或手工契约的计算。

## 输入契约

唯一接受的计算输入是 `cad_steel_geometry` 生成的 `*.steel.json`，顶层应为：

| 字段 | 用途 |
|---|---|
| `sections[]` | 截面候选；至少含 `section_type`、`text` 和证据。识别层保留 `status=candidate/review`、`confidence`、坐标与原文证据，本技能只读取可见标注。 |
| `members[]` | 构件候选；`code/name` 与证据中的 `L=...` 或 `长度...` 用于显式长度。`x/y/z/rotation`（mm）可选，用于下游吊装覆盖、堆场、分区等空间分析；缺失时台账记 `location_status=missing`。 |
| `materials[]` | 契约字段可选（bus 链路本身必需）的钢材牌号候选；用于 Q235/Q345/Q355/Q390/Q420/Q460/S235/S355/A36/16Mn 分档，不用于调整单位重量。 |
| `steel_geometry[]` | 钢构件图层几何段；`layer` 和 `geometry` 用于图面长度证据。 |
| `connections[]` | 契约字段可选的连接候选；用于高强螺栓、普通螺栓、锚栓、栓钉、节点板、加劲肋计数；有证据的节点板可进吨位。 |
| `finishes[]` | 契约字段可选的涂装候选；用于底漆、面漆、热浸镀锌、防火涂料面积分档；防火等级不做默认推断。 |
| `geometry_closure` | 契约字段可选的圆/线段闭合校核结果（由 `cad-file-reader` 识图层给出），原样透传到输出 `geometry_closure_check`；本技能不做识图，缺省记 `not_provided`。 |

本技能消费的截面类型为 `h_section`、`channel`、`angle`、`tube`、`rect_tube`、`purlin_section`、`plate`；未映射或解析失败的截面只进截面谱并标“仅计数”。识别层报出的 `review`、置信度和缺口不由本技能改成确定量。

## 调用链路

```bash
# 0) 正式识图链路要求先安装 lis-skill-bus；缺 bus 时本步骤以退出码 2 停止
bash skills/gangjiegou-suanliang/scripts/gangjiegou_statesync.sh pull --project 项目

# 1) cad-file-reader 负责唯一一次识图；钢结构包产出契约 JSON
bash skills/cad-file-reader/scripts/cad_scan.sh 钢结构图.dwg \
  --with-mtext --with-insert --with-geom --with-geom-layer \
  --detail-json 钢结构详情.json --format json -o 钢结构扫描

bash skills/cad-file-reader/scripts/cad_steel_geometry.sh \
  钢结构详情.json --out-dir 钢结构识图

# 2) cad-file-reader 把识别契约经 bus 发布，后续算量技能复用同一份契约
bash skills/cad-file-reader/scripts/cad_statesync.sh push \
  --entry-file 钢结构识图/钢结构详情.steel.json --project 项目 --specialty 钢结构

# 3) 出数前先体检契约（不出吨位，只查字段/配对/仅计数）
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --validate 钢结构识图/钢结构详情.steel.json

# 4) 本技能只消费 *.steel.json
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --steel 钢结构识图/钢结构详情.steel.json --out-prefix 钢结构吨位
```

前置依赖可单独探测；只影响正式识图链路，不影响已有契约的计算：

```bash
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py --check-deps
```

0) 未命中只表示当前没有可复用契约，随后仍按 1)→2)→3) 由 `cad-file-reader` 解图并经 bus 发布。没装 bus 时停止正式识图链路并安装 bus，不允许由本技能自行解图或用其它解析器兜底。

最小消费示例：

```bash
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --steel 已有产物.steel.json --out-prefix /tmp/steel-tonnage
```

## 口径

- 输出是估算带：总吨位按 `-15%~+15%` 表达，`final_quantity=false`。
- 米重使用 `rho=7.85`，即面积 `mm^2 x 0.00785 kg/m`：
  - 4 段式 H 型钢、圆管、方/矩管、角钢、C/Z 檩条、给足尺寸的槽钢和钢板走几何近似公式。
  - H 型近似不含圆角，约偏低 1~2%；冷弯 C/Z 檩条约偏低 2~5%。
  - GB/T 706 查表只用于号数型无几何公式的热轧槽钢 `[5`~`[40` 和工字钢 `I10`~`I63`，含 a/b/c 分档；无分档的号数默认按 a 档查表。
  - 2 段式 H 型缺腹板/翼缘厚度，只计数，不进吨位。
  - GB/T 706 表外号数、缺宽钢板、未知截面都只计数，不用默认值硬凑。
- 长度分两档：
  1. `explicit`：构件标注里的 `L=6000`、`长度4500` 等，单位按 mm 转 m；有显式长度时优先使用。
  2. `drawn`：没有显式长度时，合计钢构件图层线段长度；这是图面口径，不含节点板、加劲肋、下料余量，通常偏低。
  3. `none`：无长度证据时不出吨位，只出截面谱。
- 总吨位分两个口径，`total_t` 是当前主口径：逐根台账完整时为推荐值，否则为分摊草稿并明示不得当答案：
  1. `member_level`（推荐）：全部构件编号都有显式长度且为单截面映射时，`total_t` = 逐根台账 `tonnage_t` 求和。
  2. `allocated_estimate`（草稿）：逐根台账不完整时，才按 `米重 x 标注次数` 加权分摊总长度；该值始终另存到 `total_t_allocated_estimate`，并在报告顶部标注“草稿，不作推荐值”。
  `total_basis` 标明当前采用哪个口径，`member_level_note` 说明为何退回分摊。
- 构件归并只使用 `members[].code/name` 证据和识图层保留的类别/系统；同编号多实例合并实例数，类别或系统冲突、无编号、无截面映射进入归并复核。
- 牌号只按 `materials[]` 证据归档；证据无法关联到构件时归 `unknown_grade`，多牌号证据归 `mixed_grade` 并复核，不默认指定牌号。
- 连接候选按高强螺栓、普通螺栓、锚栓、栓钉、节点板、加劲肋六类归档；全部候选有显式数量证据时合计，只有部分证据或无证据时总量进入复核，不外推。节点板仅在厚宽长或板厚×面积证据下进入吨位。
- 涂装按底漆、面漆、热浸镀锌、防火涂料分类；仅显式面积证据输出 ±15% 面积带，缺面积/范围时 `unavailable`，不默认防火等级。

## 钢结构专属口径现状

| 口径 | 当前状态 |
|---|---|
| 钢材牌号分档 | 已支持证据分档。按 Q235、Q345、Q355、Q390、Q420、Q460、S235、S355、A36、16Mn 十类输出吨位带；无牌号证据归 `unknown_grade`，多牌号证据归 `mixed_grade` 并复核。牌号不改变米重。 |
| 构件归并编号 | 已支持编号归并台账。合并实例数、截面集合、显式长度证据；冲突、无编号或无截面映射进入复核。 |
| 螺栓/锚栓/节点板计数 | 已支持连接候选分类统计；有显式数量证据时合计数量，无数量证据时只记标注次数并复核。节点板仅在厚宽长或板厚×面积证据下进入吨位。 |
| 涂装与防火表面积 | 已按底漆、面漆、热浸镀锌、防火涂料分类；仅显式面积证据输出 ±15% 面积带，缺面积/范围时 `unavailable`，不默认防火等级。 |

## 输出

每次运行写三个文件：

- `*.json`：`cad-steel-tonnage/v0.2`，含 `final_quantity`、长度口径、牌号吨位带、构件归并台账、连接清单、涂装清单、复核清单、分截面吨位带、截面谱和仅计数截面。
- `*.md`：可读复核报告，置顶显示口径、长度依据、总吨位带和需复核项。
- `*.csv`：总吨位带、分截面吨位和截面谱的表格摘要。

JSON 关键字段包括 `length_basis`（`explicit/drawn/none`）、`length_used_m`、`rows`、`spec_rows`、`only_count`、`total_t`、`total_basis`、`total_t_member_level`、`total_t_allocated_estimate`、`member_merge`、`length_scenarios`、`allowance_advice`、`geometry_closure_check`、`prerequisites`、`input_evidence` 和 `summary`。长度为 `none` 或无可计截面时 `rows` 与 `total_t` 为空。

报告里对 `steel_geometry[]`、`connections[]`、`finishes[]` 为空的情况会明写“输入无证据”，与“技能未实现”区分。

## 手工契约与体检（受支持降级路径）

识图层不可用时，手工构造 `*.steel.json` 是受支持的降级路径，不是灰色地带：

- `examples/minimal.steel.json` 是最小可用样本，`examples/README.md` 写明必填字段、截面↔构件配对规则（文本/同 file+sheet/1500 单位邻近）、坐标单位和 `$` 嵌套图层名处理。
- `--validate` 只体检不出数：报告缺字段、匹配不到截面的构件编号、只进 `only_count` 的截面、长度证据和前置依赖；可计算时退出码 0，有结构错误时退出码 2。
- `--report out.json` 可把体检结果落盘。
- `--length-scenario 4.5 --length-scenario 6` 在长度证据不足时给多档敏感性场景，场景值明确标注“不是结果”。

## 使用边界

- 这是图面证据驱动的草稿估算，不替代深化设计、结构计算、翻样、下料、清单编制、结算、竣工计量或报价。
- 不做节点承载力、稳定性、防火等级、规范符合性或构件级精确净量判断。
- 不承诺识别任何图纸；没有 `cad-file-reader` 钢结构识图包产物时不出数，也不用 DWG 文件代替输入。
- 缺长度、缺厚度、缺宽度或表外规格时如实“仅计数”；识别层标记的 `review` 和缺口必须保留给人工复核。
- 暂不支持：除节点板以外的连接件吨位、焊缝吨位、构件级精确截面对应与净量、牌号对米重的影响、曲线或多段几何展开长度、三维模型涂装面积计算、防火等级推断。这些能力都按“暂不支持”或复核处理，不用默认值硬算。

## lis-skill-bus 强制契约链路

- 正式链路：`cad-file-reader -> cad-contract/v1 -> lis-skill-bus -> gangjiegou-suanliang`；本技能不读图纸，bus 缺失时不另开识图路径（formal statesync 以退出码 2 停止，提示装 `lis-skill-bus>=0.1.9`）。
- 开工前 `scripts/gangjiegou_statesync.sh pull --project 项目 [--building] [--floor] [--out]`，命中且含本专业 section 时 `hit=true usable=true` 直接复用；算量落盘后 `push --entry-file <输出.json> --project 项目` 入 bus。
- 候选级命中不跳过滤：`review_required`/P2/P3 只标 `review_flagged`，长度两档、米重公式、GB/T 706 查表、牌号分档仍按本技能口径复核；`--require-core` 要求核心 section 命中。
- 路径变更设 `SKILLBUS_HOME`；安装定位优先级、section 字段清单、Windows `.cmd` 差异见 `references/bus-contract.md`。

## 验证

```bash
cd skills/gangjiegou-suanliang/scripts/tests
python3 -m unittest test_steel_tonnage
```

v0.3.0 含 49 项合成数据单测，覆盖米重公式、GB/T 706 查表、长度两档、无长度降级、输入契约拒绝、重复编号提示、牌号分档、unknown_grade、构件归并复核、连接分类计数、节点板吨位、涂装面积降级、逐根/分摊双口径、坐标透传、节点板牌号余量、`--validate` 体检和长度敏感性场景。
