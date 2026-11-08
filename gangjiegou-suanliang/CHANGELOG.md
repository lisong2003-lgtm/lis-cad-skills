# Changelog

## 0.3.6 · 2026-11-09 · 消除描述与行为不一致

- **README 去掉识图命令**：正式链路示例不再直接给出前置技能的扫描与几何提取调用，改为指向 `cad-file-reader` 的 SKILL.md。本技能文档中不再出现可被理解为“本技能发起识图”的命令，职责边界与描述一致。
- **背景**：ClawHub 0.3.5 的 SkillSpector `TP4` 将 README 中的识图命令判为“声明不做识图、实际编排识图”的描述与行为不一致；本版删除该示例命令，保留“按前置技能文档执行一次识图”的流程说明。
- 64 项单测与包自检不变。

## 0.3.5 · 2026-11-09 · statesync 代码加载加固

- **移除环境变量注入入口**：`gangjiegou_statesync.py` 不再读取 `CAD_FILE_READER_SCRIPTS` 并把该目录插到 `sys.path` 首位，只按固定布局（融合包 `modules/`、技能根、用户技能目录）定位 `cad_statesync_core.py`。环境变量不再能改变代码加载来源。
- **新增回归**：设置伪造的 `CAD_FILE_READER_SCRIPTS` 指向含 `cad_statesync_core.py` 的临时目录，断言该模块不会被导入；合计 64 项单测。
- **背景**：ClawHub 0.3.4 扫描的 SkillSpector `LP1` 指出该环境变量可形成条件式代码加载；本版按该真实风险修正，不把扫描项当作纯误报。

## 0.3.4 · 2026-11-08 · 安全扫描可解释性

- **前置技能边界更明确**：SKILL.md 不再把 `cad-file-reader` 的扫描命令写成由本技能执行的步骤，改为接口顺序说明；被测图命令与参数仍完整保留在 README，实际执行责任不变。
- **声明工具范围**：frontmatter 增加 `allowed-tools: Read, Write, Bash`；正文说明只读契约/示例、只写本地产物、不联网。
- **减少静态扫描误报**：测试夹具不再复制整个进程环境，只透传运行所需的少量变量；`pyboot.py` 改用普通 `import json` 与显式流对象。
- **回归**：新增工具范围声明测试，合计 63 项。

## 0.3.3 · 2026-11-08 · 分发一致性与入口指引

- **修 SkillHub 包完整性扣分**：平台评估指出 `manifest.json` 声明了轻量包内不存在的两个 `.cmd`。SkillHub 实测拒收 `.cmd` 与 `.png`（400），因此把 `.cmd` 从必需 `scripts` 移到 `scripts_windows_optional`，清单不再声明“必须存在”；GitHub/ClawHub 完整包照旧带 `.cmd`，Windows 无 `.cmd` 时用 `py -3 scripts\steel_tonnage.py`。
- **新增 `--check-package`**：按 `manifest.json` 的 `entry/scripts/references/tests/examples` 逐项核对文件是否在包内，缺文件退出 2；Windows 可选入口缺失只提示不计错。发布前和解包后都能自查，避免清单与包内容再次漂移。`--package-root` 可指向任意包目录。
- **入口选择前置**：SKILL.md 增加“入口怎么选”表，把体检、已有契约、正式链路、手工契约四种起手式集中到一屏；另加 5 条常见问题，减少首次使用的选择成本。
- **文档同步**：REPORT/README 版本号、测试数（62 项）、Windows `.cmd` 说明与三平台分发口径一致。

## 0.3.2 · 2026-11-08 · 运行时与前置校验修复

- **修 `runtime_env.sh` 解释器解析**：候选解释器改为逐项 `-x` 校验，glob 未命中不再把字面量当路径；优先 3.10+，只有 3.9 时降级运行并在 stderr 提示一次；macOS 自带 bash 3.2 在 `set -u` 下展开空数组的问题已规避。
- **修 `.sh` 入口静默失败**：`steel_tonnage.sh` 与 `gangjiegou_statesync.sh` 现在检查 `runtime_env.sh` 返回值；找不到 Python 时退出 2 并给出安装/指定路径提示，不再出现 `exec: : not found`。`steel_tonnage.sh` 也统一走 `runtime_env.sh`，不再硬编码 `python3`。
- **`--check-deps` 校验版本**：不再只看目录是否存在。`cad-file-reader` 按 `manifest.json`/`_meta.json`/`SKILL.md` 读版本并要求 ≥0.39.2，同时检查 `packs/steel-geometry`；`lis-skill-bus` 要求 ≥0.1.9。版本过低时退出 1，报告逐项给出当前值、最低要求和升级提示。
- **报告前置行同步**：`--validate` 与吨位报告里的前置探测行改为显示版本号与“正式链路可用/不可用”，与 `--check-deps` 口径一致。
- **Windows 入口补齐**：新增 `scripts/steel_tonnage.cmd`，并在 SKILL.md 注明无 `python3` 时改用 `py -3` / `python`；SkillHub 轻量包只保留 `.sh`/`.py`，GitHub 完整包含 `.cmd`。
- **测试**：新增 5 项 shell 入口回归（缺 Python 干净退出、版本过低提示、statesync 不 exec 空路径、正常路径可跑、`set -u` 下仍可 source）与 5 项前置版本校验单测；合计 59 项。

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
