#!/usr/bin/env bash
# runtime_env.sh —— 统一运行时解析（供各技能 .sh 入口 source，不直接执行）
#
# 解决三件事：
#   1) 解释器：显式指定 > Codex 运行时 > PATH 上的 python3.13/3.12/3.11/3.10/3.9/3，
#      优先 3.10+；只有 3.9 时降级使用并在 stderr 提示一次
#   2) 底座：CAD_SKILL_DIR 显式指定 > 同级目录 > WorkBuddy/Claude/Codex 各 skills 目录
#   3) 依赖：把「本技能 scripts + 底座 scripts + 底座 vendor」拼进 PYTHONPATH，
#      让 ezdxf / ezdwg / openpyxl / typing_extensions 等无需全局 pip 安装即可导入
#
# 产出变量：SKILL_DIR、PYTHON_BIN、PYTHON_VERSION、CAD_SKILL_DIR、PYTHONPATH
# 覆盖方式：CAD_SKILL_PYTHON=<python>、CAD_SKILL_DIR=<cad-file-reader 目录>
# 返回码：0 = 可用；2 = 找不到 Python 3.9+（调用方必须检查，不能继续 exec 空路径）
# 注意：本文件被 source，不修改调用方的 set -e/-u/pipefail 选项。

_RT_SRC="${BASH_SOURCE[0]:-$0}"
_RT_SCRIPTS="$(cd -- "$(dirname -- "$_RT_SRC")" && pwd)"
SKILL_DIR="$(cd -- "$_RT_SCRIPTS/.." && pwd)"
# SkillHub 分发包（zip）会丢失可执行位：首次运行时幂等自愈，避免 permission denied
if [ -d "$SKILL_DIR/scripts" ]; then
  find "$SKILL_DIR/scripts" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.py' \) \
    ! -perm -u+x -exec chmod +x {} + 2>/dev/null || true
fi
export SKILL_DIR

# ---- 1) 解释器 ----
# 候选按优先级收集；glob 未命中时只留下字面量，由 -x 测试过滤，不会被当成有效路径。
_RT_CANDIDATES=()
_RT_SEEN=";"
for _rt_c in "${CAD_SKILL_PYTHON:-}" "${CODEX_PYTHON:-}"; do
  if [ -n "$_rt_c" ] && [ -x "$_rt_c" ] && [ "${_RT_SEEN#*;$_rt_c;}" = "$_RT_SEEN" ]; then
    _RT_CANDIDATES+=("$_rt_c"); _RT_SEEN="$_RT_SEEN$_rt_c;"
  fi
done
for _rt_c in "$HOME"/.cache/codex-runtimes/*/dependencies/python/bin/python3; do
  if [ -x "$_rt_c" ] && [ "${_RT_SEEN#*;$_rt_c;}" = "$_RT_SEEN" ]; then
    _RT_CANDIDATES+=("$_rt_c"); _RT_SEEN="$_RT_SEEN$_rt_c;"
  fi
done
for _rt_n in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  _rt_c="$(command -v "$_rt_n" 2>/dev/null || true)"
  if [ -n "$_rt_c" ] && [ -x "$_rt_c" ] && [ "${_RT_SEEN#*;$_rt_c;}" = "$_RT_SEEN" ]; then
    _RT_CANDIDATES+=("$_rt_c"); _RT_SEEN="$_RT_SEEN$_rt_c;"
  fi
done

PYTHON_BIN=""
PYTHON_VERSION=""
_RT_FALLBACK=""
_RT_FALLBACK_VER=""
_RT_FOUND_PY3=""
# 注意：macOS 自带 bash 3.2 在 set -u 下展开空数组会报 unbound variable，先判长度。
if [ "${#_RT_CANDIDATES[@]}" -gt 0 ]; then
  for _rt_c in "${_RT_CANDIDATES[@]}"; do
    _rt_v="$("$_rt_c" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || true)"
    [ -z "$_rt_v" ] && continue
    case "$_rt_v" in 2.*) continue ;; esac
    [ -z "$_RT_FOUND_PY3" ] && _RT_FOUND_PY3="$_rt_c ($_rt_v)"
    _rt_major="${_rt_v%%.*}"
    _rt_minor="${_rt_v#*.}"; _rt_minor="${_rt_minor%%.*}"
    if [ "$_rt_major" -gt 3 ] || { [ "$_rt_major" -eq 3 ] && [ "$_rt_minor" -ge 10 ]; }; then
      PYTHON_BIN="$_rt_c"; PYTHON_VERSION="$_rt_v"; break
    fi
    if [ -z "$_RT_FALLBACK" ] && [ "$_rt_major" -eq 3 ] && [ "$_rt_minor" -ge 9 ]; then
      _RT_FALLBACK="$_rt_c"; _RT_FALLBACK_VER="$_rt_v"
    fi
  done
fi
if [ -z "$PYTHON_BIN" ] && [ -n "$_RT_FALLBACK" ]; then
  PYTHON_BIN="$_RT_FALLBACK"; PYTHON_VERSION="$_RT_FALLBACK_VER"
  echo "⚠️  未找到 Python 3.10+，降级使用 $_RT_FALLBACK ($_RT_FALLBACK_VER)；主计算已通过 3.9 单测与最小示例，建议安装 3.10+。" >&2
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "❌ 未找到 Python 3.9+（本技能支持 3.10+，3.9 为降级兼容）。" >&2
  if [ -n "$_RT_FOUND_PY3" ]; then
    echo "   找到的解释器：$_RT_FOUND_PY3（版本过低）。" >&2
  else
    echo "   已尝试：CAD_SKILL_PYTHON、CODEX_PYTHON、~/.cache/codex-runtimes、PATH 上的 python3.13~3.9。" >&2
  fi
  echo "   修复：安装 Python 3.10+，或用 CAD_SKILL_PYTHON=/path/to/python3 指定后重试。" >&2
  unset _RT_CANDIDATES _RT_SEEN _RT_FOUND_PY3 _RT_FALLBACK _RT_FALLBACK_VER _rt_c _rt_n _rt_v _rt_major _rt_minor
  return 2
fi
export PYTHON_BIN PYTHON_VERSION

# ---- 2) 识图底座 ----
if [ -z "${CAD_SKILL_DIR:-}" ]; then
  for _rt_d in "$SKILL_DIR/../cad-file-reader" \
               "$HOME"/.workbuddy/skills/*/cad-file-reader \
               "$HOME"/.claude/skills/cad-file-reader \
               "$HOME"/.codex/skills/cad-file-reader; do
    if [ -d "${_rt_d}/scripts" ]; then
      CAD_SKILL_DIR="$(cd "$_rt_d" 2>/dev/null && pwd)"
      [ -d "${_rt_d}/vendor" ] && break
    fi
  done
fi
export CAD_SKILL_DIR="${CAD_SKILL_DIR:-}"

# ---- 3) 依赖搜索路径 ----
if [ -n "${CAD_SKILL_DIR}" ] && [ -d "${CAD_SKILL_DIR}/vendor" ]; then
  export PYTHONPATH="${SKILL_DIR}/scripts:${CAD_SKILL_DIR}/scripts:${CAD_SKILL_DIR}/vendor${PYTHONPATH:+:${PYTHONPATH}}"
elif [ -n "${CAD_SKILL_DIR}" ]; then
  export PYTHONPATH="${SKILL_DIR}/scripts:${CAD_SKILL_DIR}/scripts${PYTHONPATH:+:${PYTHONPATH}}"
else
  export PYTHONPATH="${SKILL_DIR}/scripts${PYTHONPATH:+:${PYTHONPATH}}"
fi

export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
unset _RT_CANDIDATES _RT_SEEN _RT_FOUND_PY3 _RT_FALLBACK _RT_FALLBACK_VER _rt_c _rt_n _rt_v _rt_major _rt_minor _rt_d
return 0
