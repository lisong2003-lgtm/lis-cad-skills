#!/usr/bin/env bash
# 薄壳：运行时解析（Python / 底座 / vendor）见 scripts/runtime_env.sh。
_HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! source "$_HERE/runtime_env.sh"; then
  exit 2
fi
exec "${PYTHON_BIN}" "$_HERE/steel_tonnage.py" "$@"
