---
name: zhuangshi-suanliang
slug: zhuangshi-suanliang
displayName: 装饰算量 · 概算与物资计划
version: 0.9.28
platforms: [macos, windows, linux]
author: lis
license: CC-BY-NC-SA-4.0
description: 根据房间类型、建筑说明、建筑图、结构图、房间装修表、做法表和节点详图，快速出装饰概算和物资计划；可导入 cad-file-reader 的长度/面积测量候选作为待核对输入，做法映射、洞口扣减、损耗、材料台账和清单量仍由本技能计算。
i18n:
  en: README.en.md
  zh: README.md
locale: zh-CN
locales: [zh-CN, en-US]
---

# 装饰算量 v0.9.24

## 0.7.0 优化概况

- 对接 `cad-file-reader >= 0.25.0` 的长度、面积、体积测量候选；只把长度/面积转成待核对输入，体积候选不直接导入。
- CAD 导入行保留证据坐标，做法编号留空、`需核对=是`，不把识图候选冒充正式装饰量。
- 概算量、物资计划量、做法映射、洞口扣减、侧壁、损耗和六表台账仍由本技能计算。

**它解决的一件事**：施工员/技术员快速得到装饰概算合价和物资计划量，同时保留计算式、依据、缺项和校验提示，防止“跑通但算错”。

## 适用

- 快速概算：按办公室、会议室、卫生间、走廊、楼梯间、屋面、外墙等房间类型展开。
- 明细算量：按楼层、区域、房间、部位、做法编号和节点逐行输入。
- 物资计划：输出主材/辅材分类、净量、损耗量、需求量和供货方式参考。
- 防水：计算上翻、附加层、卷材搭接，并按内置规范参考校验。

## 前置
## 强依赖底座说明（cad-file-reader 强依赖，不做弱化）

本技能采用**识图与算量分离**的固定架构，`cad-file-reader` 是**强依赖底座**，不是可选增强：

- **为什么必须强依赖**：DWG/DXF/DWT/PDF 的解析、图层/文字/块/图框/几何提取、识图候选和测量候选全部集中在底座完成，一次解图、全项目复用，保证证据坐标与契约一致。本技能只做本专业口径的量算、扣减、损耗、分账和台账，不重复解析图纸。
- **分工**：底座输出 `final_quantity=false` 的识图/测量候选；本技能输出本专业概算底稿/物资计划草稿（`final_quantity=true` 仅本专业口径）。
- **版本约束**：底座最低版本以各技能 `SKILL.md`「前置/依赖」写的 `>=x.y.z` 为准；缺底座或版本不够时明确报错，不静默用错误数据。
- **安装**：先装底座（`cad-file-reader` 的 `scripts/setup.sh`），再装本技能；运行时底座可在 `SKILL_NO_BASE=1` 下退化为只读已有扫描/候选/表格输入，但精度受限并必须在结果标注。
- **联动**：装有 lis-skill-bus 时，底座与各算量技能通过 `cad-contract/v1` 共享契约，同一张图只解一次；不装 bus 时各技能自动降级为各自 `state/`，功能不丢失。


- 读 CAD 用已安装的 `cad-file-reader >= 0.25.0`；读 Word/Excel/PDF 用 `markitdown`。
- 不自行解析大 DWG，只调用读图能力；第一次输入图纸先建索引，后续同图复用。
- 项目做法表、节点详图、项目专属规则、企业定额、现行规范优先于内置默认值。
- 项目专属做法必须绑定节点编号和节点详图，并在项目规则中匹配节点规则；缺节点时进待确认项，不用默认材料层凑数。

## 使用流程

1. **圈定范围**：确认楼层、区域、房间、部位和房间类型，不把全楼混算。
2. **读取依据**：交叉读取房间装修做法表、建筑总说明、建筑图、结构图、门窗表、节能/防水/防火说明和节点详图。  
   优先级：节点详图/大样图 > 项目专属节点规则 > 房间装修做法表 > 建筑总说明 > 建筑图/结构图 > 默认参考值。
3. **快速输入**：若只需初稿，填 `templates/快速概算输入表.csv`；脚本按房间模板展开为多条做法。
4. **明细输入**：正式核对时填 `templates/装饰算量输入表.csv`，逐行绑定尺寸和做法。
5. **计算**：概算取基面量；材料需求量乘损耗、搭接、附加层和单耗；块料向上取整。
6. **复核**：检查待确认项、重复行、防水参数、清单口径和单价来源。
7. **输出**：用六表 Excel 台账做商务和现场核对。

## 脚本用法

```bash
# 快速概算
python3 \
  scripts/decor_qty.py \
  --input templates/快速概算输入表.csv \
  --out-dir ./概算结果 \
  --project-rules templates/项目专属规则示例.json \
  --project "项目名"

# 明细算量
python3 \
  scripts/decor_qty.py \
  --input ./输入.csv \
  --out-dir ./明细结果 \
  --project-rules templates/项目专属规则示例.json \
  --project "项目名" --level "二层"
```

可用规则参数：

- `--room-templates rules/标准房间模板.json`
- `--quantity-rules rules/清单工程量规则.json`
- `--price-rules rules/概算综合单价.json`
- `--material-rules rules/物资分类规则.json`

## 输出

- `装饰概算物资计划台账.xlsx`：固定包含 `概算`、`物资计划`、`明细`、`汇总`、`缺项`、`依据`。
- `概算明细.csv`：清单编码、清单工程量、参考单价、概算合价、计算式和状态。
- `概算汇总.csv`：按清单项汇总工程量和合价。
- `物资计划.csv`：净量、损耗率、损耗量、需求量、完成状态需求量、分类和供货方式。
- `明细.csv`、`材料汇总.csv`：基面量、订货量、计算式和依据。
- `缺项核对.csv`、`依据.csv`、`装饰概算物资计划报告.md`。

## 输入校验

- 明细必填列：楼层、区域、房间、部位类型、做法编号、做法名称、做法类型、依据、间数。
- 快速输入按 `房间类型` 展开成明细；未知房间类型不静默跳过，进入待确认项。
- 数字列必须填数字，不带文字单位；不允许负数；间数必须大于0。
- 完全重复行标记为“重复”，不重复计入计算。
- 防水行要求附加层宽度、搭接宽度、涂膜厚度字段；卫生间/厨房还要求上翻高度。
- 项目专属做法必须填写节点编号、节点详图并匹配项目节点规则。

## 口径

- **概算量**：清单/商务口径，取基面量，不含损耗、搭接、附加层。
- **材料订货量**：基面量 × 单耗 ×（1 + 损耗率）；卷材另乘搭接系数；附加层单独计算。
- **块料**：按单片面积向上取整。
- **门窗洞口**：必须扣；洞口侧壁按项目口径单列。
- **单价**：内置综合单价只是示例参考；正式概算以合同清单、地方信息价、企业定额和市场询价为准。
- 输出不用于结算、对量、竣工计量或正式报价。

## 防水与规范复核

内置值是算量参考下限和校验提示，不替代条文原文；现行规范、设计文件、节点详图和项目规则优先。

- 卷材搭接参考下限：80mm。
- 涂膜厚度参考下限：1.5mm。
- 室内附加层宽度参考：0.25m；屋面/地下参考：0.5m。
- 室内有水房间上翻参考：0.25m；淋浴区按设计/规范另核，常见参考1.8m。
- 屋面防水道数参考：不少于2道，按防水等级和设计复核。
- 防水卷材用搭接系数计算：`幅宽 /（幅宽 - 搭接宽度）`。
- 防水附加层可填直接面积，或按长度×宽度计算。

参考标准包括：

- GB 50500-2013《建设工程工程量清单计价规范》
- GB 50854-2013《房屋建筑与装饰工程工程量计算规范》
- GB/T 50353-2013《建筑工程建筑面积计算规范》
- GB 50210-2018《建筑装饰装修工程质量验收标准》
- GB 50209-2010《建筑地面工程施工质量验收规范》
- GB 55030-2022《建筑与市政工程防水通用规范》
- GB 50207-2012《屋面工程质量验收规范》
- GB 50208-2011《地下防水工程质量验收规范》
- GB 50345-2012《屋面工程技术规范》
- JGJ 298-2013《住宅室内防水工程技术规范》
- JGJ 144-2019《外墙外保温工程技术标准》
- GB 50411-2019《建筑节能工程施工质量验收标准》
- GB 50325-2020《民用建筑工程室内环境污染控制标准》
- GB 50222-2017《建筑内部装修设计防火规范》
- GB 50327-2001《住宅装饰装修工程施工规范》

## CAD 测量候选交接

先用 `cad-file-reader` 生成带比例、单位、计算式和证据的测量候选：

```bash
# 在识图底座 cad-file-reader 技能目录执行：
scripts/cad_measure.sh 描述几何/图纸详情.descriptive.json --out-dir 测量候选
```

再把候选转成装饰算量输入表草稿：

```bash
scripts/cad_measure_to_input.py --measurements 测量候选/cad-measurement-candidates.json   --out CAD导入_待核对.csv --floor 二层
```

导入行会保留房间/部位候选、面积或长度候选和证据，但**做法编号留空、需核对固定为“是”**；做法映射、洞口扣减、侧壁、损耗、材料台账和正式清单量仍由本技能计算。

## 边界

1. 装饰造型、线条、异形吊顶、复杂幕墙、楼梯细部不自动展开，先列待确认项。
2. 材料消耗默认值只是参考，不能替代项目做法表、节点详图或企业定额。
3. 图纸文字粘连、天正实体、表格跨页时可能漏读，必须用待确认项复核。
4. CAD 测量候选只作识图证据，`final_quantity=false`；做法映射、洞口扣减、侧壁、损耗和材料台账必须在本技能内完成，真图回归仍是后续增强项。
5. 不自动把公司数据上传云端，不联网解析图纸。


## 显式依赖与降级（0.9+）

- 底座 `cad-file-reader >= 0.28.1` 是本技能的**显式依赖**：运行首次会自动检测，缺失时自动下载安装底座并补齐 vendor（联网，下载包做 SHA-256 完整性与版本校验，校验失败拒绝安装）；已装则直接复用，不重复下载。
- 独立/离线场景可设 `SKILL_NO_BASE=1`：不再自动安装底座，仅使用已有扫描 JSON、测量候选或表格输入（精度受限并在结果中标注）。
- 可设 `CAD_AUTO_SETUP=0` 关闭底座内部的 vendor 自动下载；手动安装用 `scripts/setup.sh` 或 `scripts/ensure_base.sh`。

## lis-skill-bus 可选联动（试点，不强制）

- 状态过滤：项目名/楼栋/楼层一致时，本技能可与 `cad-file-reader` 及其它算量 skill 通过 lis-skill-bus 交换 `cad-contract/v1`；命中即复用，不再重复解图。
- 拉取（开工前，推荐）：`scripts/zhuangshi_statesync.sh pull --project 项目 [--building 楼栋] [--floor 楼层] [--out 落盘.json]`
  —— 命中且契约含本专业 section 字段（`rooms`、`room_schedules`、`practices`、`room_boundaries`、`measurements`、`views`）时返回 `hit=true usable=true`，可直接复用；未命中/缺字段/无 bus 一律返回 `hit=false`/`usable=false`，走本技能正常解析。
- 发布（算量落盘后，可选）：`scripts/zhuangshi_statesync.sh push --entry-file <本技能输出.json> --project 项目 [--building 楼栋] [--floor 楼层] [--specialty 装饰]`，自动包装成 `cad-contract/v1` 后入 bus。
- 对应接线脚本：`lis-skill-bus/integration/zhuangshi_pull_contract.sh` / `zhuangshi_publish_contract.sh`（薄壳，等价调用本技能 statesync）。
- 命中口径：`usable=true` 为本机状态里的「候选级命中」（`candidate_only=true`）；命中 section 内若有 `review_required`/P2/P3 项，statesync 只标 `review_flagged`，P0–P3 与复核项过滤仍在本技能算量核心按既有口径完成，不因 bus 命中而跳过滤。
- 命中开关（默认宽松）：默认仍为「至少一个 section 字段命中即 `usable=true`」的候选级命中；加 `--require-core` 后收紧为必选核心 section 至少一个命中且非空（装饰=`rooms` 房间 / `room_schedules` 做法表），缺核心时 `usable=false` 并把缺项写入 `review_flagged`。是否把默认改为收紧属业务口径，待用户/业务确认。
- bus 路径变更：仅需设置 `SKILLBUS_HOME` 指向新 bus 目录，本技能任何文件无需改动。
- 兼容/降级：客户端按如下优先级定位 `skillbus_client.py`，正式路径存在时不回退 dev 副本：
① `SKILLBUS_HOME`（bus 目录）或 `SKILLBUS_CLIENT`（直接指向 client 文件）显式指定
② `$HOME/.codex/mcp_servers/lis-skill-bus/skillbus_client.py`（正式安装落点）
③ `$HOME/.codex/skills/lis-skill-bus/skillbus_client.py` / `$HOME/.codex/skills/.skillbus/skillbus_client.py`
④ 常见本机开发副本（`tan/work` 等，最后才回退）。
命中 dev/临时副本时 stderr 会输出告警行「bus 命中来源：<路径>（临时副本/dev，非正式安装）」，正式路径输出「（正式安装）」；找不到 bus 时不报错，直接写 `$HOME/.codex/skills/.skillbus/state.json`（与 bus 同构，后续装 bus 可无缝读取）。 无 MCP/无 bus 不影响任何算量能力；本技能算法、口径、扣减、损耗、分账与台账逻辑不变。

- Windows 接线：GitHub 完整包 scripts/zhuangshi_statesync.cmd push/pull（GitHub/ClawHub 包含 .cmd，SkillHub 轻量包剔除 .cmd、Windows 改用同目录 .py 入口；macOS/Linux 用 `bash scripts/zhuangshi_statesync.sh` 等价调用）；等价 lis-skill-bus/integration/zhuangshi_publish_contract.sh / zhuangshi_pull_contract.sh。Windows 未实机跑通，仅静态校验通过（CRLF 行尾；无 /Users、/bin/sh、python3 硬编码；py 启动器 + %PYTHON%/%CODEX_PYTHON% 回退；默认路径用 %USERPROFILE%\.codex）。

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
