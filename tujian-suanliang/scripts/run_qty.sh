#!/usr/bin/env bash
# 统一入口：解释器三级回退 + 底座定位 + 内存闸
# 可选 bus 接线：传 --bus-pull --project 项目 [--building 楼栋] [--floor 楼层] 时，
# 先尝试从 lis-skill-bus 拉取 cad-file-reader 已发布的契约，命中则复用 detail，
# 未命中/无 bus 则照常本机解图，不报错。（--bus-pull 及其主键参数不会传给算量核心）
set -euo pipefail
_HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$_HERE/runtime_env.sh"
: "${CAD_MEM_LIMIT_MB:=4096}"; export CAD_MEM_LIMIT_MB
[[ -z "${CAD_SKILL_DIR:-}" ]] && { echo "找不到底座技能 cad-file-reader：设 CAD_SKILL_DIR 指向它" >&2; exit 2; }

# ---- 可选 bus 拉取与参数透出过滤 ----
A=("$@")
COUNT=$#
BUS=0; BUS_PROJECT=""; BUS_BUILDING=""; BUS_FLOOR=""; BUS_OUT=""
FWD=()
i=0
while [[ $i -lt $COUNT ]]; do
  a="${A[$i]}"
  case "$a" in
    --bus-pull)
      BUS=1; i=$((i+1));;
    --project)
      [[ $((i+1)) -lt $COUNT ]] && BUS_PROJECT="${A[$((i+1))]}"
      i=$((i+2));;
    --building)
      [[ $((i+1)) -lt $COUNT ]] && BUS_BUILDING="${A[$((i+1))]}"
      i=$((i+2));;
    --floor)
      [[ $((i+1)) -lt $COUNT ]] && BUS_FLOOR="${A[$((i+1))]}"
      i=$((i+2));;
    --out|-o)
      [[ $((i+1)) -lt $COUNT ]] && { BUS_OUT="${A[$((i+1))]}"; FWD+=("$a" "${A[$((i+1))]}"); }
      i=$((i+2));;
    *)
      FWD+=("$a"); i=$((i+1));;
  esac
done

if [[ "$BUS" -eq 1 ]]; then
  if [[ -z "${BUS_PROJECT:-}" || -z "${BUS_OUT:-}" ]]; then
    echo "[run_qty] --bus-pull 需要同时给出 --project 与 -o/--out（缺其一则跳过 bus 拉取，本机照常解图）" >&2
  else
    PULL=(--project "$BUS_PROJECT")
    [[ -n "${BUS_BUILDING:-}" ]] && PULL+=(--building "$BUS_BUILDING")
    [[ -n "${BUS_FLOOR:-}" ]] && PULL+=(--floor "$BUS_FLOOR")
    PULL+=(--out-dir "$BUS_OUT" --cad-skill-dir "$CAD_SKILL_DIR")
    mkdir -p "$BUS_OUT"
    "${PYTHON_BIN}" "${SKILL_DIR}/scripts/qty_statesync.py" "${PULL[@]}" || {
      echo "[run_qty] bus 拉取异常，已跳过并继续本机解图" >&2
    }
  fi
fi

if [[ "${FWD[0]:-}" == "advanced" || "${FWD[0]:-}" == "pipeline" ]]; then
  # pipeline 入口也接收过滤后的参数
  exec "${PYTHON_BIN}" "${SKILL_DIR}/scripts/cad_quantity_pipeline.py" "${FWD[@]:1}"
fi
exec "${PYTHON_BIN}" "${SKILL_DIR}/scripts/qty_core.py" "${FWD[@]}"
