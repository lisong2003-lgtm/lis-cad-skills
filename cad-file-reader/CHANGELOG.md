# Changelog

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
- **版本对齐** 本机 `~/.codex/skills`、`~/.workbuddy/skills` 与发布仓库同步同版本；算法、契约、兼容性与上一版一致，未改业务逻辑。

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
  - `test_platform_paths.py` 路径断言改 `as_posix()`，并对 PATHEXT 差异做 mock。
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
- 新增长效自动化用例 `scripts/tests/test_self_test.py`（schema 正/负向、
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

