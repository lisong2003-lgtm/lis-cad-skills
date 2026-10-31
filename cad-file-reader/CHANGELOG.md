# Changelog

## 0.39.2 (prepare) · 2026-11-01 · P1 轴网可选字段

- **新增可选 `axis_networks[]`（`scripts/cad_axis_networks.py` / `.sh`）**：
  - 从已解析 `cad_scan` 详情 JSON 的 text_records 中提取 AXIS/轴号/轴标/轴网/定位 图层上的
    数字轴号与字母轴号，按 sheet 排序去重（首尾重复轴号合并），再在轴号坐标附近找同方向
    长线段作几何佐证。
  - 输出每条轴网的 sheet / floor / axis_id / label / pos / along / grid.positions / grid.spans /
    total_span、geometry_matched、confidence 与 status（usable/degraded/missing）。
  - **不重新全图识图**，复用已有粗读产物；缺轴网如实 missing/degraded，不伪装 pass。
- 契约兼容：`axis_networks` 为 cad-file-reader/v0 contract 的可选字段（向后兼容）；
  `cad_contract.validate_contract_payload` 新增可选校验。
- 回归：319 项单测全绿（原 306 + 新增 13）；36 截图框回放均未破坏既有 pass/degraded。



## 0.38.7 · 2026-10-30

- 新增 `scripts/cad_statesync_core.py`：zhuangshi/anzhuang/yuanlin 三份 ~424 行
  复制粘贴 statesync 的共享实现（§2.4 抽共享）。三技能改为薄壳传参调用，
  push/pull 行为与旧实现逐函数等价（双路实测比对通过）。附 9 项单测（237 项全绿）。

## 0.38.7

- **新增几何轴网提取（`cad_axis_net`）**：上一版证明了「靠文字抓轴号做不出可用轴网」
  （轴网图层上有 0 条文字）。这一版换口径：轴线本身一直在图上——它是一组等长、
  互相平行、等距重复的直线。新模块只认几何、不认文字，输出每条轴网的
  **方向 / 轴数 / 总跨 / 开间序列**，作为跨专业核对的指纹。
  三道判据：① 必须落在轴网图层；② 单段 ≥2m；③ 同长度组内按位置排序后成簇
  （视图之间的空档远大于轴距，自动断开，但不允许断开阈值超过 30m——否则
  同一根轴在多视图里的副本会被连成一条 255m 的假轴网）。
- **新增共线拼接**：天正导出的轴线常被切成多段（实测 `J-2#` 轴网层最长线段只有 3000mm，
  而该楼轴距 6~9m），不先接起来就会把「被切碎的轴」判成「图上没有轴」。
  仅在原始线段提不出该方向轴网时才启用拼接——完整轴线拼接后端点不齐，
  长度分组会漂，实测会把建筑图从 25 轴并成 20 轴、轴距从 3000 变成 3600。
- **修复根因：LibreDWG 转出的 DXF 几何全空**。`J-2#`/`J-3#4#6#7#` 两张结构图是 R2007
  格式，直读失败后转 DXF，但产出的 DXF 缺 `EOF` tag、实体 handle 重复、图层名为空，
  `ezdxf.readfile` 抛 `DXFStructureError`，连 `recover.readfile` 也救不了
  （`DXFTypeError: name has to be a string`）。后果是这两张图的几何段为空，
  跨专业对照直接判「无法比对」。实际上文件里的 LINE 数据是完整的——
  新增 `dxf_geometry_stream`：按 group code 顺序流式扫一遍，跳过 ezdxf 的结构校验。
  实测 J-2# 取回 5269 段、J-3#4#6#7# 取回 8002 段。
- **跨专业核对改用几何口径**（`drawing_relation.grid_check`）：几何轴网优先，
  文字轴号只在几何不可用时兜底，`grid_check` 新增 `source`（geometry/text）、
  `direction`、`span_delta`、`structure_span`、`architecture_span` 字段。
  判定改为以**结构侧覆盖**为主判据：结构柱网通常只是建筑轴网的子集
  （建筑多出外墙轴、门窗定位轴），用两侧最大值会让「结构只对上 3 个开间、
  建筑有 30 个」也算一致。
- **开间比对支持「段和」匹配**：结构图一个 3300 开间，建筑图可能画成 1650+1650
  两段（中间插了隔墙定位轴）。只比等值会把这种正常情况算成对不上。
- **诚实结论（真图实测，J 地块 61 张）**：10 组配对里轴网核对**通过 3 组**
  （屋面 35/35 轴完全一致、J-1 9/25 开间全覆盖、J-5 14/20 覆盖 92%），
  **部分重叠 1 组**（J-8：结构图只画局部，跨差 26.8%），**判不了 6 组**
  （5 组因结构图 `J-2#`/`J-3#4#6#7#` 无几何——本次已修但重扫需原图；
  1 组大样类图本身无轴网）。**仍不能证明「是同一片区域」**：同户型不同楼栋
  共用同一套轴网，间距会完全一致（实测 J-1 结构 × J-5 建筑判「一致」）。
  本模块能证明「不一致」，不能证明「是同一栋」。
- 单测：cad-file-reader 248 → **263 项**（新增几何提取、共线拼接、重复轴合并、
  短线段拒判、子集一致、跨差不一致、方向不齐、小样本不下结论）。

## 0.38.6

- **修复（根因）轴网提取不看图层，8 万个候选里 99.4% 是噪声**：`grid_candidates` 只按文字形态抓
  `[A-Z]{1,3}\d{0,3}`，于是 `TEL_TEXT`（电话）、`TEXT_喷淋`、`DIM-照明`、`图框` 里的
  `PVC`/`SBS`/`C20`/`Co`/`Ltd`/`一二三` 全被当成轴号。实测 J 地块 61 张图共 80786 条 grid 候选，
  **只有 448 条（0.6%）落在轴网图层上**。后果：所有「轴网重叠度」判断（聚类是否同一单体、
  跨专业配对是否同一片区域）都建立在噪声平均上，看着有精确小数，其实无意义。
  修法：加 `AXIS_LAYER`（`轴|AXIS|SOCK-DOTE|GRID|定位`）硬前提——轴网图层上的值全收；
  其它图层只留形态严格像轴号的（1~3 位数字 / 1~2 位大写字母 / `1/A` 组合），并标
  `axis_layer=false` 让下游知道证据弱。`grid_set` 只取 `axis_layer` 为真的值。
- **新增跨专业配对后的轴网核对**（`drawing_relation.grid_check`）：配对上不等于能对照。
  给出 `轴网一致 / 部分重叠 / 轴网不对应 / 样本不足 / 无法比对 / 数据不可信` 六档结论，
  覆盖率按**较小一侧**算（结构图常只画本区轴网，用并集会把这个正常情况算成重叠度低），
  并设 `MIN_GRID_SAMPLE=10` 的门槛——较小一侧只有 4 个轴号时对上 3 个就是 75%，
  分母太小会把「几乎没数据」算成「高度一致」，比不判更糟。
- **产品行为变更**：`relation.json` 的 `drawings` 不再剔除轴网，改为输出 `grid_count` + 前 200 个
  `grids`（下游要核对就得拿得到轴网）；`pairs` 新增 `grid_check`；`summary` 新增
  `pairs_grid_ok / pairs_grid_mismatch / pairs_grid_inconclusive`；新增 review 类型
  `pair_grid_mismatch`（配上了但轴号几乎不重叠）。
- **诚实结论（真图实测）**：J 地块 10 组配对，轴网核对**通过 0 组**——1 组不对应、
  4 组样本不足、5 组无法比对。过滤后单张图只剩 1~6 个轴号且仍有 `CEN`/`con` 这类噪声，
  说明轴号在图上多与轴线线段一起画、不在独立文字图层，**光靠正则抓文字做不出可用的轴网**。
  要真正可用，得按轴线 LINE 实体聚类再找线端邻近文字（几何算法），属于下一阶段工作。
  在此之前，跨专业对照只能到「配对」这一步，构件级比对需人工看图。
- 单测：cad-file-reader 239 → **248 项**（新增轴网形态、脏数据拒判、axis_layer 过滤、
  较小一侧分母、最小样本门槛）。

## 0.38.5

- **修复（市政）构件系统名被图层污染**：系统名原取自「构件规则」，而规则是拿`文字+图层`匹配的。
  实测sample-road室外管网图把「给水」「雨水」「中水」全画在 `DIM_污水` 图层上，四种管线统统标成 `sewage`——
  按系统统计管线数量时给水与污水混成一笔账，整张表失去使用价值。改为**文字优先、图层兜底**，
  新增 `system_basis`（`text`/`component_rule`）字段摊开依据。修后 949 条管线候选分布为
  sewage 496 / rainwater 322 / drainage 96 / water_supply 65 …
- **修复（市政）`SIGN` 命中 `DE-SIGN`**：短代号边界匹配只覆盖 1~3 个字母，`SIGN` 是 4 个字母走朴素子串，
  结果设计院英文名「TONGYUAN DESIGN GROUP」被当成交通标志。规则改为 `SIGNBOARD`（中文侧仍有
  「交通标志」「标志牌」兜底）。
- **验证（钢结构）真图能力**：会展中心大跨屋顶（真钢屋盖）解出 25291 文字/298 图层/6811 几何段，
  截面 26 条（h_section 15 / channel 8 / tube 3），含 `H2000x600x36x60`、`HN500x200x10x16` 等；
  材质 Q355/Q390/Q460 共 89 处；连接 445 条（支座 302 / 加劲肋 100 / 焊缝 25 / 螺栓 13 / 高强螺栓 2）。
  **仍不出重量**——有截面有材质但没有长度汇总，就不该有吨位，契约 `final_quantity=false` 不变。
- **新增** scripts/tests（本机开发目录） 9 项：市政系统归属 3、SIGN 误命中 2、钢截面与材质 4、
  契约红线 1。全量 230 → **239 项通过**。
- 已知边界（不修，写进报告）：`[2003` 这类「`[20` + 编号」粘连文字会被误判成槽钢截面；
  ALC 钢立柱布置图与钢柱预埋排版图本就没有型钢截面，识别出 0~1 条是正确行为。

## 0.38.4

- **新增 `drawing_relation` 图种判定**：按图名判 `目录/总说明/专篇/系统图/大样/配筋/布置/立面剖面`，
  并归为三档 `admin / detail / plan`。起因是实测 J 地块屋面层把 3 张「防火节能专篇」配进了结构配筋图——
  专篇是报审文件，图上没有可对照的构件位置，"配上了"反而误导下游。
- **修复配对范围过粗**：楼层判不出来时按**楼栋**分组（`J-1结构 ↔ J-1#楼`、`J-2# ↔ J-2、3#楼`…），
  不再把 4 栋楼的结构图与 4 栋楼的建筑图堆成一组；大样档整簇汇总，避免不带楼栋号的
  「9J楼梯」配不上「J车库楼梯00」。J 地块实测配对 2 组 → 8 组，且每组能对上号。
- **修复 `infer_buildings` 漏号**：`J-3#4#6#7#`（数字# 连写）与 `J4，6，7#`（逗号列表）
  两种写法都要认，只认 `J\d` 会漏掉后三栋。
- **补 review 类型**：`pair_excluded_admin_sheets`（图纸存在但被主动排除）、
  `missing_architecture` 改为逐范围报缺（指明哪栋楼/哪一层缺），不再并成一条说不清的数字。
- 单测新增 15 项（图种判定 5 / 楼栋号 5 / 按范围配对 5），`开发期单测` 共 41 项通过。

## 0.38.3

- **修复（发布兼容）** SkillHub 分发包（zip）不保留文件权限，装完脚本全是 644，直接执行会 permission denied。现在 `scripts/setup.sh` 与各入口脚本（`runtime_env.sh` / `ensure_runtime.sh`）首次运行时幂等补回 `scripts/*.sh`、`scripts/*.py` 的可执行位，用户无需手动 chmod。
- **修复（macOS 兼容）** `run_cad.sh` 在 macOS 自带 bash 3.2 且 `set -u` 下对空数组取 `${#arr[@]}` 会报 `unbound variable` 崩溃；改用标量 `argc` 计数，无参数时正常打印用法。
- **新增** `.gitignore`：忽略 `__pycache__`、`.state/`、日志与密钥文件，避免误提交运行态产物。

## 0.38.2

- **更新发布** 补 CHANGELOG 详细条目与 README.en 版本号；三端（Codex/WorkBuddy/发布仓库）同版本同内容再次校验通过。tujian-suanliang 的 manifest tests 仅保留真实存在的 `scripts/self_test.py`（完整 tests 见本机 shangwu-suanliang 商务版）。
- 算法、契约、权限、SKILL.md 正文与上一版无变化。

## 0.38.1

- **授权与保留** 新增「授权与保留」段落：作者 lis 声明本技能可商用/可再分发/可对外授权，商用前按双许可说明确认是否需联系作者申报。
- **脱敏（发布合规）** rules 中的公司内部来源字段由「公司知识库/…/规范图集」改为「公开规范与行业通用做法整理」，不再引用公司内部资料路径。
- **版本对齐** 本机 `$CODEX_SKILLS_DIR/skills`、`~/.workbuddy/skills` 与发布仓库同步同版本；算法、契约、兼容性与上一版一致，未改业务逻辑。

## 0.37.1

- **修复（发布兼容）** `cad_batch.py` 调用 `run_cad.sh` 改为 `bash` 启动，不再依赖 `.sh` 执行位（SkillHub/ClawHub 打包会丢失执行位）。
- **修复（跨 Agent）** `cad_scan.py` 的 `VENDOR` 由写死 `$HOME/.codex/skills/.../vendor` 改为「`CAD_SKILL_VENDOR` → 技能自身 vendor → 其他 Agent 技能目录」，WorkBuddy / Claude 安装后可直接用自带 vendor。
- **新增** `requirements.txt` 依赖声明，vendor 缺失或需升级时有据可依。


## 0.34.0 (2026-10-23)
- lis-skill-bus 联动由“可选试点”改为“推荐联动（不装自动降级）”：补齐跨平台安装入口（SkillHub slug: lis-skill-bus；GitHub: lisong2003-lgtm/lis-skill-bus；安装器 python install_py.py --apply），保留不装自动降级（写 $HOME/.codex/skills/.skillbus/state.json，五件套各自可用）。
- doctor.py 恢复只读 bus 检测（$HOME/.codex/mcp_servers/lis-skill-bus/、$HOME/.codex/skills/lis-skill-bus/、$HOME/.codex/skills/.skillbus/ 与 SKILLBUS_HOME/SKILLBUS_CLIENT），输出已安装/未装（推荐安装），不打印内部 dev 路径与安装器原文。
- 新增 scripts/setup_win.py（Windows 纯 Python 安装入口，py→python→python3 探测，转发 scripts/setup.py，支持 --dry-run，打印 winget/choco 后端指引）；README.md / README.en.md 安装段补 setup_windows.ps1 / setup_win.py 与 bus 推荐入口。
- 新增根 VERIFICATION-selftest.md（0.32.1 三平台 CI 265/0 + 0.31.7 真图 20/20 基线）。
- 不改变契约 schema、cad_contract.py、wrap_v1/cmd_push/cmd_pull 与命令算法。


## 0.33.0 (2026-10-22)
- lis-skill-bus 可选联动（试点）：cad_scan/cad_measure 真实产出经 scripts/cad_statesync.py push 进 bus（cad-contract/v1），五件套可直接复用、免重复解图；pull 支持 SKILLBUS_HOME / 正式安装 / 本机降级四级路径，`--require-core` 收紧核心 section 命中；新增 Windows scripts/cad_statesync.cmd（未实机跑通，仅静态校验通过）。核心解析/契约/置信口径不变。

## 0.32.2 (2026-10-21)
- 三平台对齐（cross-platform + i18n overseas）：README.en.md、`--lang en|zh` 主入口、i18n.py、CFI 三平台 workflow 全绿。
- 不改变业务算法/中文模板；平台专用调整只改发布副本。

# 更新记录
## 0.32.1 — 2026-10-21（跨平台 CI 全绿 + 其他 agent 可调用硬化）

- 跨平台修复（GitHub Actions 三 OS 实测通过）：
  - UTF-8 自举：全部 40 个含 `def main` 的脚本接入 `pyboot.ensure_utf8_io()`（含 pyboot 自身与 7 个内部 CLI），修 Windows cp1252 中文乱码/无输出。
  - CI workflow 增加 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`，并新增 `cad_scan examples/sample_room.dxf --format json` 步骤作为 Windows 中文 JSON 防线。
  - `doctor` 相关测试改 `sys.executable` 调 doctor.py（修远端 100644 无执行位 PermissionError）。
  - sqlite 连接显式 `close()`（修 Windows 文件锁导致测试清理失败）。
  - `开发期单测` 路径断言改 `as_posix()`，并对 PATHEXT 差异做 mock。
- 三平台 CI 结果（run 39542083329）：macOS / Windows / Ubuntu 全部 success，self_test unit 265 / failures 0 / errors 0；sample_room.dxf 三平台 `text_total=2 / layers=3`；Windows 中文 JSON 可读。
- 其他 agent 可调用：本技能为“本地 Python 脚本 + CLI 入口 + SKILL.md 指令”，任何能运行 Python 3 并执行命令行的 agent（Codex / DeepSeek 等）均可调用，不依赖单一平台。
- 发布：GitHub + SkillHub + ClawHub 三平台同步更新到 0.32.1，本机 canonical 保持原版。

## 0.32.0 — 2026-10-21（跨平台发布收尾：平台支持矩阵 + platforms 字段）

- 新增 `README.md` / `SKILL.md`「平台支持矩阵」：macOS / Windows 10/11 / Linux x86_64 功能表、安装步骤对比、常见问题（Windows 中文输出、psutil 降级、vendor 安装、CI 白名单差异）。
- `manifest.json` 新增 `"platforms": ["macos","windows","linux"]`，并把 26 个 `.cmd` Windows 入口加入 `scripts` 清单（共 193 项）；版本同步升 0.32.0。
- 三平台发布包各自生成（GitHub 完整包 / SkillHub 轻量合规包 / ClawHub 包），随 GitHub Release 附 macOS / Windows / Linux 的 doctor-report 与 self_test 报告。
- 本机技能正文保持 canonical，不因平台安装差异修改。

## 0.31.7 — 2026-10-20（真图回归缺陷修复：候选门槛 + DWG 空解码自动复扫）

- `run_real_dwg_regression.py`：无显式 expect 时，缺省候选门槛由“最后一个细分域
  ≥1”改为“整套识图包至少产出一个领域候选”，避免把本无该细分域的真实图纸误判为缺陷
  （电气/园林/结构 9 条真实 DWG 由“候选不足”恢复通过）。
- `cad_scan.py`：DWG 直读文字/图层为空时自动尝试 LibreDWG→DXF 复扫（无需显式
  `--dwg-dxf-fallback`），并把 `解码失败 / section map has no entries` 纳入触发词；
  reg-0169（R2007 section map 无条目）经复扫产出结构几何候选。
- 回归：真实 DWG 子集 20 条由 10 通过/10 失败 → 20/20 通过；全量自测 205/205 保持全绿，
  schema/cad_validate 契约校验继续通过，`final_quantity=false` 未改动。
- `manifest.json` 同步升版 0.31.7。
- 发布备注（2026-10-20）：GitHub Release v0.31.7 + SkillHub @user_43faedd6/cad-file-reader 0.31.7 + ClawHub lisong2003-lgtm/cad-file-reader 1.1.0 三平台同步发布；发布包经 cad_release_scrub + check_release 脱敏/合规扫描，problems=0，不含真图/公司路径（真图清单仅存项目根，不随发布）。

## 0.31.6 — 2026-10-20（CI / self_test 统一自测回归闭环）
 — 2026-10-20（CI / self_test 统一自测回归闭环）

- 新增 `scripts/self_test.py` + `scripts/self_test.sh` 统一入口：一条命令跑
  doctor → 全量 unittest → schema/cad_validate 契约校验 → 样例 DXF 回归 →
  坏文件快速失败不变量 → 可选真实 DWG 回归，输出“三合一” JSON + Markdown 报告。
- `schemas/*.schema.json` 纳入自测：内置零依赖轻量 JSON Schema 校验器（无需
  jsonschema 包），对 `examples/qto-sample` 样例做正/负向不变量校验，并继续用
  `scripts/cad_validate.sh` 校验全部 v0 契约样例。
- 新增长效自动化用例 scripts/tests（本机开发目录）（schema 正/负向、
  快速跳过 CLI、缺 manifest 时回归记 skipped）；全量自测 201 → 205 项全部通过，
  三合一闭环无 manifest 运行 6 步：5 通过 + 1 跳过。
- 用法已写进 `README.md` 与 `SKILL.md`；`manifest.json` 同步升版 0.31.6。

## 0.31.5 — 2026-10-20（可靠性加固：快速失败/批量跳档/PDF 复核截图）

- 新增 `scripts/cad_preflight.py` 轻量预检（只读前 4KB，<5 秒）：空文件、<1KB、魔数错误
  （非 AC#### / DXF-SECTION / %PDF-）直接快速失败；不支持 DWG 版本报“不支持版本”。
- `cad_scan / read_cad / convert_dwg` 入口接入预检；批量 `cad_batch` 用同一预检，
  加密 DWG/不支持版本/超时/内存看门狗终止在台账“缺口/失败原因”里明确区分，
  不中断整批。
- `cad_batch.run_cad_scan` 增加硬超时（超时 rc=124）并把退出码 -9/内存闸关键词翻译为
  “内存看门狗终止”；新增 `rc_reason()` 原因翻译。
- `cad_pdf_ocr` 自动输出可疑页复核截图到 `outdir/_review/<图名>-p<页码>.png` 与
  `_review/index.json`：OCR 失败页、扫描页 OCR 无文字、整页平均置信 <60%、低置信区块
  （<40%）触发；候选带 `review_image` 字段；`--no-review` 可关闭。
- 保持 `cad-file-reader/v0` 契约不变，`cad_validate.sh` 校验继续通过。
- 新增 6 项自测（快速失败/原因翻译/批量不中断）+ PDF 复核字段不破坏 v0 校验；
  全量测试 189 → 201 全部通过。
- 回归：`examples/sample_room.dxf`（DXF 正常）+ 空文件 + 坏魔数 + 不支持 AC9999 版本头
  全部按预期：样例正常出结果，坏文件 <1s 快速失败并留原因。


## 0.38.8（2026-10-30）
- cad_municipal_geometry 新增就近管径挂接 attach_diameters：独立管径标注（DN150/de315/DN350-400 整条文字）建池，按同图框就近挂到管道标注（pipe_size，basis=nearby_text 带距离）与管线线段（diameter）；--dia-tolerance 控距离上限（默认 10000 图面单位）。真图（范村室外管网总图）实测：1363 条标注挂上 1137（83%）、11837 段挂上 6798；未挂段保持「未标注」不做多数派编造。
- 新增 tests（本机开发目录） 8 项。

## 0.39.0 · 2026-10-30

- **圆实体提取（块实体第一层）**：cad_scan 新增 `circle` worker（ezdwg.raw.decode_circle_entities），
  `--with-geom` 时同步提取 CIRCLE 实体（井圈/阀门/消火栓/池边），详情 JSON 新增
  `geometry_entities`（行=[x,y,r,layer,file_index]）；缓存命中分支现解一遍（不入 sqlite 缓存，表结构稳定），
  ROI/图框局部查询同步过滤。管网总图实测 2703 圆 2.2s。
- **市政识图新增 `entity_geometry`**：圆实体 → `entities` 产物（kind=entity、etype=circle、
  bbox=外接框、类别走图层规则映射，未映射→unclassified_entity review 不编造语义）。
  三层诚实剔除，全部真图驱动（范村管网×海绵平面 B 对验收）：
  ① 标注图层（DIM/标注/图框）圆=索引符号，剔除计数；
  ② 「图例」文字 3.5 万邻域圆=图例符号样板（42 个曾产生 2000 伪碰撞候选），剔除计数；
  ③ r<10 微圆=线面装饰（路缘石圆角 r=4 又 2000 伪候选），剔除计数。
- 边界：匿名块（INSERT）名字解码乱码语义不可得，本轮不入实体池；ARC/ELLIPSE 未提取
  （弧外接框过估会产生伪候选，诚实不做）。summary 新增 entities/entities_legend_excluded。
- 测试 281→289 项（test_municipal_entities 8 项）。

## 0.39.1 · 2026-10-30

- **人工标注验收驱动三连修（entity_geometry 新增三层符号剔除）**：用户对 B 对 14 条样本
  逐条 CAD 定位标注，确认引擎保留下来的 9 个抽样实体全部是符号（设备表符号列/大样区
  符号/系统图图框符号）——判定一致率修复前 5/14。新增：
  ① **远线剔除**：圆实体距最近市政线段 > --entity-far-tol（默认 5000）→ 图框角落/系统图
  符号（海绵图 24 个，实测距管线 183 万图面单位）；
  ② **等距符号列剔除**：同列（x±125）≥3 圆、y 向间距≈整数倍中位间距（容差 15%）且
  间距≥2×最大半径 → 设备表/图例符号列（管网 21 个，EQUIP_消防 沿 y 等距 882）；
  ③ **异图框剔除**：实体图框 ≠ 主图框（市政线段最多的 sheet）且就近线段也不在主图框
  → 大样/设备表图框内容（管网 27 个，sheet4/6 vs 主图框 sheet3）。
- 复跑 B 对：管网实体 21+27 剔除、海绵 24 剔除 → 两侧实体保留 0，与人工标注 14/14 一致；
  碰撞口径不变（dup 226,247 / 线×线 6,466,272 / 标注 2,182 / 实体候选 0，人工背书）。
- 诚实边界：等距列规则对真沿路等距设备有误伤风险（带计数+review 可追溯）；主图框判定
  为启发式（线段最多 sheet）；review「无一个落在市政图层」提示改为仅在全无剔除时触发。
- 测试 289→295（test_municipal_entities 8→14 项）。

## 0.39.2 · 2026-10-30（园林真图验收驱动）

真图：sample-road安置区景观施工图全套 22 张（155MB），扫描 30s 全通，识图产出 2379 条图例候选。
逐条核对发现**两类合成测试想不到的误报**，全部修复并计数可追溯：

- **并列人名噪声**（`_noise_name_plant`）：图签「signer-A signer-B」被单字 token「李」判成乔木（6 条）。
  判据：植物名含空格（多段）且**没有任何一段**命中长度≥2 的植物词 → 非植物。
  反例保护：「云杉 实生」第一段命中「云杉」→ 保留（真图「杉木柱 末口」同理）。
- **说明句 / 图名 / 铺装材料 / 硬景设施噪声**（`_noise_note_nonplant`）：
  绿化设计说明整段句（"1.3、清除现场碎石及杂草杂物…"）、铺装材料名（"芝麻白荔枝面花岗岩"
  19 次、"黄锈石荔枝面花岗岩（收边）"14 次、"杉树皮卷用棕榈绳捆束"13 次）、图名
  （"中心商业区树池详图"）、硬景（"成品花钵"9 条、"树池"3 条、"中层次地被"）共 151 条。
  判据：长度>8（真植物名实测 ≤8 字）/ 含标点编号 / 图名尾词 / 材料词 / 设施词，各自带原因码。
  「丰花月季」含"花"但不含"花钵"→ 不误伤（用完整词而非单字）。

结果：2379 → 2222 条（剔除 157），保留 75 种全为真实植物名（大叶黄杨球 177、红叶石楠篱 148、
白蜡 138、雪松 120…）；**苗木表 52 种 × 图面图例名称可对齐 45/46 = 98%**（仅"紫叶矮樱"未对齐）。
summary 新增 plant_name_noise_excluded / plant_note_noise_excluded。

诚实边界（本批图纸特性，非代码缺陷）：
- 该批 DWG **图层名解码全空**（186 个图层句柄有、名称全空；二进制亦搜不到中文图层名）
  → 铺装按图层分类路径失效、铺装闭合域 0；
- **块引用名 37244/37481 解码为空** → 块级图例与株数计数路径为 0（株数正路暂不可用）；
- 剩余约 5 条描述词（杉木柱固定/种植池/底层地被）未再过滤，避免过度拟合单张图。
- 测试 295→306（test_landscape_plant_noise 11 项）。
