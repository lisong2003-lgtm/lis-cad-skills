---
name: gangjiegou-suanliang
slug: gangjiegou-suanliang
displayName: 钢结构算量 · 吨位估算带
version: 0.2.0
platforms: [macos, windows, linux]
author: lis
license: CC-BY-NC-SA-4.0
description: 消费 cad-file-reader 钢结构识图包产出的 *.steel.json，按截面标注、米重公式、显式/图面长度输出钢结构吨位估算带（json/md/csv），并支持牌号分档、构件归并、连接计数、节点板吨位、涂装面积与复核清单。只做吨位口径计算，不做 DWG/DXF/PDF 识图，不替代深化设计、翻样、下料、结算与报价。
i18n:
  en: README.en.md
  zh: README.md
locale: zh-CN
---

# 钢结构算量

本技能只做一件独立的事：把 `cad-file-reader` 的 `cad-steel-geometry/v1` 产物转成可复核的钢结构吨位估算带。识图、图纸解析、证据提取都归 `cad-file-reader`；本技能不读取 DWG/DXF/DWT/PDF，也不复制识别实现。

## 输入契约

唯一接受的计算输入是 `cad_steel_geometry` 生成的 `*.steel.json`，顶层应为：

| 字段 | 用途 |
|---|---|
| `sections[]` | 截面候选；至少含 `section_type`、`text` 和证据。识别层保留 `status=candidate/review`、`confidence`、坐标与原文证据，本技能只读取可见标注。 |
| `members[]` | 构件候选；`code/name` 与证据中的 `L=...` 或 `长度...` 用于显式长度。 |
| `materials[]` | 可选钢材牌号候选；用于 Q235/Q345/Q355/Q390/Q420/Q460/S235/S355/A36/16Mn 分档，不用于调整单位重量。 |
| `steel_geometry[]` | 钢构件图层几何段；`layer` 和 `geometry` 用于图面长度证据。 |
| `connections[]` | 可选连接候选；用于高强螺栓、普通螺栓、锚栓、栓钉、节点板、加劲肋计数；有证据的节点板可进吨位。 |
| `finishes[]` | 可选涂装候选；用于底漆、面漆、热浸镀锌、防火涂料面积分档；防火等级不做默认推断。 |

本技能消费的截面类型为 `h_section`、`channel`、`angle`、`tube`、`rect_tube`、`purlin_section`、`plate`；未映射或解析失败的截面只进截面谱并标“仅计数”。识别层报出的 `review`、置信度和缺口不由本技能改成确定量。

## 调用链路

```bash
# 1) cad-file-reader 负责识图；钢结构包产出契约 JSON
bash skills/cad-file-reader/scripts/cad_scan.sh 钢结构图.dwg \
  --with-mtext --with-insert --with-geom --with-geom-layer \
  --detail-json 钢结构详情.json --format json -o 钢结构扫描

bash skills/cad-file-reader/scripts/cad_steel_geometry.sh \
  钢结构详情.json --out-dir 钢结构识图

# 2) 本技能只消费 *.steel.json
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --steel 钢结构识图/钢结构详情.steel.json --out-prefix 钢结构吨位
```

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
- 缺少“每根构件 ↔ 截面”映射时，总长度按 `米重 x 标注次数` 加权分摊到可计米重截面；这是草稿分摊，不是构件级净量。
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

JSON 关键字段包括 `length_basis`（`explicit/drawn/none`）、`length_used_m`、`rows`、`spec_rows`、`only_count`、`total_t` 和 `summary`。长度为 `none` 或无可计截面时 `rows` 与 `total_t` 为空。

## 使用边界

- 这是图面证据驱动的草稿估算，不替代深化设计、结构计算、翻样、下料、清单编制、结算、竣工计量或报价。
- 不做节点承载力、稳定性、防火等级、规范符合性或构件级精确净量判断。
- 不承诺识别任何图纸；没有 `cad-file-reader` 钢结构识图包产物时不出数，也不用 DWG 文件代替输入。
- 缺长度、缺厚度、缺宽度或表外规格时如实“仅计数”；识别层标记的 `review` 和缺口必须保留给人工复核。
- 暂不支持：除节点板以外的连接件吨位、焊缝吨位、构件级精确截面对应与净量、牌号对米重的影响、曲线或多段几何展开长度、三维模型涂装面积计算、防火等级推断。这些能力都按“暂不支持”或复核处理，不用默认值硬算。

## 验证

```bash
cd skills/gangjiegou-suanliang/scripts/tests
python3 -m unittest test_steel_tonnage
```

v0.2.0 含 40 项合成数据单测，覆盖米重公式、GB/T 706 查表、长度两档、无长度降级、输入契约拒绝、重复编号提示、牌号分档、unknown_grade、构件归并复核、连接分类计数、节点板吨位和涂装面积降级。
