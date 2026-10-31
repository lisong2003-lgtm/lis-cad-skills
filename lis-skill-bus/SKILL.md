---
name: lis-skill-bus
slug: lis-skill-bus
displayName: 本地 Skill 联动总线
description: 本地 Skill 联动总线（MCP server 安装器，非业务算法技能）。把 5 个 CAD 技能（cad-file-reader、土建 tujian-suanliang、安装 anzhuang-suanliang、装饰 zhuangshi-suanliang、园林 yuanlin-suanliang）的项目状态与识图契约接在一起：同一张图只解析一次，各算量技能共享复用。完全本地、不联网；不装也能用（各技能自动降级到自身 state）。前置依赖 cad-file-reader + 至少一个算量技能。一行命令安装到 $HOME/.codex/mcp_servers/lis-skill-bus 并可选注册 MCP。
version: 0.1.6
license: MIT
---

# lis-skill-bus v0.1.6（本地 MCP server 安装器）

## 识图契约红线（硬规则，禁止绕行）
- 算量技能**不得单独识别 DWG/DXF/PDF**：识图必须由 `cad-file-reader` 完成一次，产出统一契约后各算量技能共享复用（同一张图只解析一次）。
- **禁止算量技能自行 `import ezdwg/read_cad`、自带或重新下载 cad-file-reader 来解图**；底座缺失时如实标 `unavailable`，不得降级成“自己解图”。
- 用户要算量 = 必须先走 `cad-file-reader → 契约 → 算量`；计算入口默认拒绝直接 DWG，开发/回归调试才能用显式 `CAD_ALLOW_DIRECT=1` 逃生。
- `lis-skill-bus` 是连接 cad-file-reader 契约与各算量技能的唯一定接线；算量结果必须带契约来源（图号/坐标证据）。


## 这是什么
`lis-skill-bus` 不是业务技能，不解析图纸、不算量。它是一个本地安装壳/总线：

- 安装到 `$HOME/.codex/mcp_servers/lis-skill-bus`，可选注册 MCP（`mcp__lis_skill_bus__*`）；
- 供 5 个 CAD 技能共享项目状态与识图契约（状态默认存 `$HOME/.codex/skills/.skillbus/state.json`）；
- 纯 Python stdlib、不联网、跨平台（macOS / Linux / Windows）。

## 前置依赖

- **为什么强依赖**：识图与算量分离是固定架构，`cad-file-reader` 负责唯一一次解图与证据契约，算量技能只做本专业口径；bus 只是连接两者的契约桥，本身不解析图纸。缺底座时 bus 无契约可读，故为强依赖；各算量技能另有 `SKILL_NO_BASE=1` 降级逃生（精度受限并在结果标注）。
- 至少一个 CAD 识图/算量技能：**cad-file-reader + 至少一个**（土建 `tujian-suanliang`、安装 `anzhuang-suanliang`、装饰 `zhuangshi-suanliang`、园林 `yuanlin-suanliang`）；
- Python 3（本机已有 Codex 运行环境即足够）。

## 安装（一行命令）
```bash
bash install_skillbus.sh --apply
```
可选：不注册 MCP 只复制文件（`SKIP_MCP_REG=1 bash install_skillbus.sh --apply`）；
Windows（GitHub 完整包）：`install_skillbus.cmd --apply`；SkillHub 版若被剔除 `.cmd`，用 `python install_py.py --apply`（功能等价）。

卸载只摘除 MCP 注册，保留已装文件：
```bash
bash install_skillbus.sh --uninstall
```

## 装上的好处
- **同一张图只解析一次**：cad-file-reader 解析完写契约，土建/安装/装饰/园林开工时直接复用，不重复读图；
- **5 技能共享**：共享项目 key / 楼层 / 契约，断点接续；
- **完全本地**：不联网、不上云，公司数据只落本机；
- **一行安装**：`bash install_skillbus.sh --apply`；
- **不装也能用**：找不到 bus 时各技能自动降级到自身 `state/` 目录，功能不丢失，后续装好即可无缝读取。

## 用法
- MCP 客户端注册样例见 `mcp-config.example.json`（Claude Desktop / Cursor / 其他 stdio 客户端）；
- CLI 直接可用：`python3 skillbus.py list-skills`、`python3 skillbus_client.py pull --project <项目>`；
- 试点链路演示：`bash example_pilot/pilot_demo.sh`（会写本机状态，建议先设 `SKILLBUS_STATE_DIR` 到临时目录）。

## 红线
- 状态与契约仅本机；不透传公司数据、不上云、不进 Git 远端；
- 本技能只做安装引导，不改动 5 个技能的算法与 canonical；
- 升级/删除前先备份。
