## 0.3.1 · 2026-11-03

- Added English-first metadata and README surface for the tri-platform package.
- Kept local parsing and quantity algorithms unchanged.


# CHANGELOG

## 0.3.0（2026-11-01）
- SKILL.md 从“六技能串联说明”重写为“七技能融合协议”：明确 cad-suite 只管路由、契约、
  证据归并、溯源、降级台账、口径守门；识图/算量/碰撞实现仍归七个源技能。
- `cad-clash-check` 纳入 `modules/` 原样同步与安装自检，`cross/` 继续作为其唯一实现的转发层。
- `resync_modules.py` 支持开发仓库与 `<skills-root>` 安装目录两种源定位，七模块 `--check` 可用。

## 0.2.6（2026-11-01）
- 融合包同步修复：`cad-file-reader` 缺失的轴网薄层脚本与测试已同步；`vendor` 改为指向本机
  源依赖的符号链接，避免实体依赖被解引用进融合包。
- `cad_pipeline.py` 优先定位包内 `modules/`，再回退本机安装副本；同一融合目录可在不依赖
  兄弟技能安装路径的情况下找到识图与算量入口。
- 修正“建筑”类图纸误走市政管长链的问题：建筑暂无批量算量终点，现在判定后如实跳过。

## 0.2.5（2026-11-01）
- ls skill-bus 融合接入：新增 `scripts/bus_bridge.py`（定位 bus 时 scripts/ 缺失也能命中），
  `suite_run.py --use-bus` 在 s1a 解图前按来源 sha256 查缓存（同图只解析一次）并在解图后推送契约，
  溯源字段（source.file/source.sha256/source_skill）随 bus 状态入库。
- 嵌套模块 `modules/lis-skill-bus` 已随 resync_modules 同步到 v0.1.6（skillbus 自测 14 个全绿）。
## 0.2.4（2026-10-31）
- **消除跨专业校对的双份实现**（重要）。cad-suite/cross 与 cad-clash-check 曾各存一份 engine/adapt，
  已发生漂移：cad-clash-check 0.1.3 落地的 entity 通道（圆实体）只进了 clash 侧，cad-suite 侧停在 0.1.2，
  同一对图纸两个入口给出的碰撞候选不一致。
- 新增 `cross/clash_bridge.py`：`cross/engine.py` 与 `cross/adapt.py` 改为**转发层**，
  符号与行为全部转出 cad-clash-check（clash_engine / clash_adapt）。实现只留一份。
- 转发后 cad-suite 侧同步获得 0.1.3 能力：构件三分类 entity/line/label、geometry 线段取两端 bbox、设计说明句剔除。
- 依赖缺失时**报错退出并给出安装指引**，不静默回退到自有副本（静默降级正是漂移根因）。
- 新增 `cross/tests/test_cross_parity.py` 10 项，钉住：实现源码逐字节同源、adapt 输出与 clash 侧完全一致、
  entity 通道已到达 suite 侧、cross 内不得再长出自有实现、缺依赖必须抛错。
- 端到端冒烟：合成产物经 cross/adapt → cross/compare，同项目下正确检出「管径 DN100 vs DN150」属性冲突。
- 测试：extract+cross **54 项**、scripts 53 项，全绿。

## 0.2.3（2026-10-30）
- 新增批量生产总入口 `scripts/cad_pipeline.py`：图纸目录（--glob/--recursive）或现成识图产物进 → 逐张识图（cad_scan 带几何，--budget 可调）→ 专业判定（关键词+产物结构回退）→ 对应几何提取与算量终点（钢结构吨位带 / 市政管长 / 钢筋口径B标注谱）→ 可选 --with-clash 跨专业碰撞 → 汇总一本账（pipeline.json + 一本账.md）。
- 断点续跑 --resume（SHA 键+旧账找回，旧账缺失自动重跑）；单图失败只记台账不中断；--max 试跑。
- 诚实边界：final_quantity=false；钢筋批量仅口径B标注谱（无料单不出吨位带）；跨图合计=各图带相加需人工去重。
- 新增 tests/test_cad_pipeline.py 9 项；scripts 层 53 项全绿。
- 真图冒烟：市政管长 438.0m + 钢结构吨位带 7083~9583t + 碰撞候选 35 处，两轮 resume 完整。
