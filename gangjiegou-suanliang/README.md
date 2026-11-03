# 钢结构算量（gangjiegou-suanliang）

**[English](./README.en.md) | [中文](./README.md)**

给已有钢结构识图产物的使用者：不碰图纸解析，只把 `cad-file-reader` 钢结构包的 `*.steel.json` 变成 **截面谱 + 吨位估算带**。

## 能做什么

- 消费 `cad-steel-geometry/v1` 契约 JSON，输出 `cad-steel-tonnage/v0.2` 的 `json + md + csv`。
- 4 段式 H 型钢、圆管、方/矩管、角钢、C/Z 檩条、给足尺寸的槽钢和钢板按几何公式估米重。
- 号数型热轧槽钢 `[5`~`[40`、工字钢 `I10`~`I63`（含 a/b/c 分档）按 GB/T 706 理论重量查表。
- 按 `materials[]` 输出十类钢材牌号吨位带；无牌号证据归 `unknown_grade`，不默认指定牌号。
- 按 `members[].code/name` 归并构件实例、截面集合和显式长度证据；冲突与无法映射项进入复核清单。
- 按 `connections[]` 统计高强螺栓、普通螺栓、锚栓、栓钉、节点板、加劲肋；有厚宽长或板厚×面积证据的节点板进入吨位，其余不硬凑。
- 按 `finishes[]` 输出底漆、面漆、热浸镀锌、防火涂料面积带；缺面积或范围时 `unavailable`，防火等级不默认推断。
- 长度分两档：优先用构件标注里的显式长度；否则用钢构件图层线段合计；都没有时只出截面谱。
- 输出统一为 `±15%` 吨位带，`final_quantity=false`。

## 不能做什么

- **不做识图**：不读取 DWG/DXF/DWT/PDF；识图必须先走 `cad-file-reader` 的 `cad_steel_geometry`。
- **不替代专业成果**：不用于深化设计、翻样、下料、结算、报价或竣工计量。
- **暂不支持**：除节点板以外的连接件吨位、焊缝吨位、构件级精确截面对应与净量、牌号对米重的影响、曲线或多段几何展开长度、三维模型涂装面积计算、防火等级推断。

## 快速开始

```bash
# 识图链路由 cad-file-reader 完成；本技能只接 *.steel.json
python3 skills/gangjiegou-suanliang/scripts/steel_tonnage.py \
  --steel 钢结构识图/钢结构详情.steel.json \
  --out-prefix 钢结构吨位
```

需要先生成输入时，使用 `cad-file-reader` 钢结构包：

```bash
bash skills/cad-file-reader/scripts/cad_scan.sh 钢结构图.dwg \
  --with-mtext --with-insert --with-geom --with-geom-layer \
  --detail-json 钢结构详情.json --format json -o 钢结构扫描

bash skills/cad-file-reader/scripts/cad_steel_geometry.sh \
  钢结构详情.json --out-dir 钢结构识图
```

## 口径要点

| 项目 | 当前口径 |
|---|---|
| 量级 | `±15%` 估算带，草稿复核用 |
| H 型 | 4 段式走公式；2 段式 H 只计数 |
| 槽钢 | 给足尺寸走几何公式；号数型走 GB/T 706 查表 |
| 工字钢 | 号数型走 GB/T 706 查表，`I10`~`I63`，含 a/b/c |
| 长度 | `explicit` 优先，`drawn` 次之，`none` 不出吨位 |
| 牌号 | Q235/Q345/Q355/Q390/Q420/Q460/S235/S355/A36/16Mn 证据分档；`unknown_grade` 和 `mixed_grade` 不默认归入任一钢号 |
| 构件归并 | 同编号合并实例数；类别/系统冲突、无编号或无截面映射复核 |
| 连接 | 六类计数；显式数量优先，缺数量只记标注次数并复核 |
| 涂装 | 四类面积带；缺显式面积/范围 `unavailable`，防火等级不默认推断 |
| 分摊 | 缺构件级映射时按 `米重 x 标注次数` 加权分摊 |

缺厚度、缺宽度、表外规格或未知截面都进入“仅计数”，不用默认值硬凑。

## 依赖

- Python 3.10+
- 输入必须来自已安装的 `cad-file-reader` 钢结构识图包

## 验证

```bash
cd skills/gangjiegou-suanliang/scripts/tests
python3 -m unittest test_steel_tonnage
```

## 许可

采用 `CC-BY-NC-SA-4.0`；企业或经营性使用需按 `LICENSE.md` 另行取得作者授权。
