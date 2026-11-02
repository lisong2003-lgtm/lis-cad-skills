# CHANGELOG

## 0.1.6

- 目录探测修复：`scripts/` 缺失也能探测（原默认 marker=scripts 的 deps.py 逻辑失败），
  无 scripts 的 lis-skill-bus 用根目录 `SKILL.md`/`manifest.json` 兜底。`list_skills`
  与新增 `detect-skill` 返回 `marker`/`has_scripts`/`scripts`。
- 新增 `find_contract`（CLI + MCP + client）：按 source sha256/文件名判同图，`同图只解析一次`
  有明确判据；push 时把 `source.file`/`source.sha256` 写入 `_provenance` 溯源。
- 自测扩到 14 个用例：同图判重、多算量共享、降级自身 state、无 scripts 目录探测全绿。
- 修 install_skillbus.sh 全角括号紧跟变量导致 bash 把 `（` 首字节并入标识符的问题（--dry-run/--uninstall 输出）。

## 0.1.5

- 前端文档补齐：识图契约红线（禁止各算量技能自行解图）固化到 SKILL.md，README 同步。
- 版本口径统一：SKILL.md / _meta.json / README 统一为 0.1.5。


- 发布兼容：SkillHub 打包不保留执行位，脚本调用统一走 `bash`；`LICENSE` 更名为 `LICENSE.md`（平台文件类型白名单）。

## 0.1.3

- 文档更正：土建技能名由 `shangwu-suanliang` 更正为实际发布的 `tujian-suanliang`（frontmatter 与正文两处）。
- 版本口径统一：SKILL.md / _meta.json 统一为 0.1.3，正文标题同步。
- 补齐 `LICENSE`（MIT，与 frontmatter 声明一致）与本 CHANGELOG。
- 补充说明：安装脚本支持 `CODEX_HOME` 覆盖落点，非 Codex 环境（如 WorkBuddy）可指定到本机对应目录。

## 0.1.2

- 内部版本：状态文件结构兼容性修补。

## 0.1.1

- 首次对外发布：MCP server 安装器 + 五个 CAD 技能共享项目状态与 `cad-contract/v1` 契约。
