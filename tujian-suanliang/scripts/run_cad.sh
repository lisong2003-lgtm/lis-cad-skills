#!/usr/bin/env bash
# 土建算量内部脚本入口：优先本技能脚本，底座仅提供识图模块与 vendor。
set -euo pipefail
_HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$_HERE/runtime_env.sh"
BASE_VAL="$("$SKILL_DIR/scripts/ensure_base.sh")" || exit $?
if [ -z "$BASE_VAL" ]; then
  echo "[土建算量] 降级模式：未能获取识图底座 cad-file-reader；请提供已有扫描/测量 JSON 或设置 CAD_SKILL_DIR。" >&2
  exit 2
fi
CAD_SKILL_DIR="$BASE_VAL"
export CAD_SKILL_DIR
: "${CAD_MEM_LIMIT_MB:=4096}"; export CAD_MEM_LIMIT_MB
export PYTHONPATH="${SKILL_DIR}/scripts:${CAD_SKILL_DIR}/scripts:${CAD_SKILL_DIR}/vendor${PYTHONPATH:+:${PYTHONPATH}}"
SCRIPT_NAME="${1:?用法: run_cad.sh <脚本名> [参数...]}"; shift
# 脚本查找顺序：本技能 scripts/ → 识图底座 scripts/（底座脚本也允许用同名入口调用）
TARGET="${SKILL_DIR}/scripts/${SCRIPT_NAME}.py"
if [ ! -f "$TARGET" ] && [ -n "${CAD_SKILL_DIR:-}" ] && [ -f "${CAD_SKILL_DIR}/scripts/${SCRIPT_NAME}.py" ]; then
  TARGET="${CAD_SKILL_DIR}/scripts/${SCRIPT_NAME}.py"
fi
if [ ! -f "$TARGET" ]; then
  echo "[土建算量] 找不到脚本 ${SCRIPT_NAME}：本技能与识图底座的 scripts/ 下均无此文件。" >&2
  exit 2
fi
exec "${PYTHON_BIN}" "$TARGET" "$@"
