#!/usr/bin/env bash
# shangwu-suanliang 安装/自检：显式依赖底座 cad-file-reader（未装自动安装，已装复用）。
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[shangwu-suanliang] 检测显式依赖底座 cad-file-reader……"
bash bash "$SKILL_DIR/scripts/ensure_base.sh"
echo "[shangwu-suanliang] 安装自检完成。"
