# Changelog

## 0.3.1 · 2026-11-08 · 技能层瘦身与发布完整性

- **SKILL.md 瘦身**：11,760 B → 12,593 B（+7.1%）。触发词、硬规则、能力边界保留在前置段；低频细则外移到 `references/`、`docs/`、`packs/`，按需加载，算法与业务口径不变。
- **发布完整性**：被引用文件随包存在、Python/bash/JSON 语法通过、技能自检 PASS；未实现的检查如实记 SKIP。
- **脱敏**：本机路径、真实项目名与公司资料引用替换为通用示例；平台专用入口只改发布副本。


## 0.3.0 · 2026-11-08

实测反馈整改（真实 DWG 项目，详见 `钢结构算量技能实测反馈_2026-11-08.md`）：

- **总吨位双口径**：`total_t` 改为当前主口径。全部构件有显式长度且单截面映射时取逐根台账求和并标“推荐”；
  分摊口径另存 `total_t_allocated_estimate`（不再叫 `total_t`），`total_basis`/`member_level_note`
  说明当前口径与退回原因；报告顶部并列两值并标注推荐值。
- **分摊口径不再冒充推荐值**：只有逐根台账完整时，报告/CSV 才把 `total_t` 标为“推荐”；退回分摊时标为“分摊草稿，不是答案”。
- **修牌号余量重复相加**：`grade_tonnage` 的 `unknown_grade` 只计算一次。分摊口径用总吨位扣除已分牌号；
  逐根口径对未分牌号构件与无牌号节点板求和，全部构件有牌号时不再产生虚假余量带。
- **新增 `--validate` 契约体检**：不出吨位，报告缺字段、未匹配截面的构件编号、只进 `only_count`
  的截面、长度证据和前置依赖；结构错误退出码 2；`--report` 可落盘。
- **新增 `--check-deps` 前置探测**：报告 `cad-file-reader` / `lis-skill-bus` 是否在位；输出 JSON/MD
  写入 `prerequisites`，缺依赖时在报告顶部明确提示（只影响正式识图链路）。
- **新增手工契约支持**：`examples/minimal.steel.json` + `examples/README.md`，写明必填字段、
  截面↔构件配对规则、坐标单位（mm）、`$` 嵌套图层名处理。
- **坐标透传**：`member_merge[]` 增加 `x/y/z/rotation`、`coord_unit=mm`、`location_status`，
  下游吊装覆盖/堆场/分区分析不再回读 DXF。
- **新增长度敏感性场景**：`--length-scenario`（可重复）输出多档构件长度吨位，明确标注“场景值不是结果”。
- **新增吊装/运输建议附加**：`allowance_advice` 给 3%/5%/8% 建议系数与参照总重，不并入 `total_t`。
- **空证据说明**：`steel_geometry[]`/`connections[]`/`finishes[]` 为空时报告明写“输入无证据”，
  与“技能未实现”区分；`geometry_closure` 由识图层提供时透传为 `geometry_closure_check`。
- **manifest 显式声明强依赖**：`requires.skills` 列出 `cad-file-reader` 与 `lis-skill-bus` 最低版本。
- 合成数据单测 40 → 49 项，全部通过。

## 0.2.1 · 2026-11-04

- 固化正式识图链路：`cad-file-reader -> cad-contract/v1 -> lis-skill-bus -> gangjiegou-suanliang`。
  本技能不读取 DWG/DXF/PDF，不提供绕开底座或总线的第二套识图路径。
- 接线 lis-skill-bus：新增 `scripts/gangjiegou_statesync.py`、`scripts/gangjiegou_statesync.sh`、`scripts/gangjiegou_statesync.cmd`（薄壳共享 `cad_statesync_core`），
  开工前 `pull` 复用 `cad-contract/v1`，落盘后 `push` 回总线；缺 bus 时 formal statesync 以退出码 2 停止并提示安装。
- 目标 sections：`members`、`sections`、`steel_geometry`、`connections`、`materials`、`finishes`；
  核心 sections 为 `members`、`sections`，`--require-core` 可收紧命中口径。
- 总线新增薄壳 `integration/gangjiegou_pull_contract.sh` / `gangjiegou_publish_contract.sh`。
- README/SKILL.md 补「lis-skill-bus 强制契约链路」章节；补系列蓝图蓝标 `icon.png`。
- 已由正式链路生成并留存的官方 `*.steel.json` 仍可直接送入 `steel_tonnage.py` 做计算或回归。

## 0.2.0 · 2026-11-03

- 输出契约升级为 `cad-steel-tonnage/v0.2`，输入契约文档补充 `connections[]` 与 `finishes[]`。
- 同步说明牌号分档、构件归并、连接计数、节点板吨位、涂装面积与防火口径。
- 明确暂不支持除节点板以外连接件吨位、焊缝吨位、构件级精确净量、牌号调米重、曲线/多段几何展开、三维涂装面积和防火等级推断。
- 修正 README 中“连接/涂装暂不支持”的过时描述；识图入口仍只写 `cad-file-reader`。
- 合成回归 40 项全绿，新增 `cad-steel-tonnage/v0.2` 输出契约断言。

## 0.1.0 · 2026-11-03

- 建立独立钢结构算量技能，实现从 `cad-steel-geometry/v1` 契约 JSON 到 `cad-steel-tonnage/v0.1` 的吨位估算。
- 支持米重几何公式：4 段式 H 型、圆管、方/矩管、角钢、C/Z 檩条、给足尺寸的槽钢和钢板。
- 新增 GB/T 706 查表：热轧槽钢 `[5`~`[40`、工字钢 `I10`~`I63`，含 a/b/c 分档。
- 建立长度两档口径：显式构件长度优先，钢构件图层线段次之；无长度证据时只出截面谱。
- 输出 JSON、Markdown、CSV，总量为 `±15%` 估算带且 `final_quantity=false`。
- 校验 `cad-steel-geometry/v1` 输入契约，拒绝非契约 JSON、缺字段/非法数组和全空识图证据；重复构件编号写入复核清单。
- 消费 `materials[]` 做十类钢材牌号分档；无牌号证据归 `unknown_grade`，多牌号证据归 `mixed_grade` 并复核。
- 消费 `members[].code/name` 建立构件归并台账，合并实例数、截面集合与显式长度证据；编号冲突、跨系统冲突或无法映射项进入复核清单。
- v0.1 当时明确暂不支持螺栓/锚栓/节点板计数、涂装与防火表面积。
- 合成数据单测 31 项全绿；牌号/归并合成冒烟通过，输出 JSON/MD/CSV 同步。
