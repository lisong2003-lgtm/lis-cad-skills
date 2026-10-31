#!/usr/bin/env bash
# 一键发布 6 个建筑算量技能到 5 个平台
#
# 前置认证（只需做一次，均为交互式，需本人操作）：
#   skillhub login --key skh_xxx   # SkillHub（也可 export SKILLHUB_TOKEN=skh_xxx）
#   clawhub login                  # ClawHub（浏览器 GitHub 授权）
#   gh auth login                  # GitHub（浏览器授权）
#
# 注意：Codex 上的 oc-skills 就是同一个 skillhub CLI，共用 ~/.skillhub/credentials.json。
#      所以 SkillHub 只需登录一次，本机终端与 Codex 通用，无需分别登录。
#
# 用法：
#   ./publish_all.sh              # 全部平台
#   ./publish_all.sh skillhub     # 只发 SkillHub
#   ./publish_all.sh clawhub      # 只发 ClawHub
#   ./publish_all.sh github       # 只发 GitHub
#   ./publish_all.sh local        # 只同步本机 WorkBuddy + Codex
#   ./publish_all.sh status       # 只检查各平台认证状态，不发布
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_BIN="$HOME/.workbuddy/binaries/node/versions/22.22.2-6/bin"
export PATH="$NODE_BIN:$HOME/.local/bin:$PATH"

SKILLS=(cad-file-reader lis-skill-bus zhuangshi-suanliang
        anzhuang-suanliang tujian-suanliang yuanlin-suanliang)

CHANGELOG="许可证与合规更新：明确 CC-BY-NC-SA-4.0 仅限非商业自用（企业商用需授权），\
补充作者商业保留条款；清理内部来源标注与项目名。"

TARGET="${1:-all}"
ok=0; fail=0
note() { printf "%-10s %s\n" "[$1]" "$2"; }

# ---------- 1. SkillHub（api.skillhub.cn）----------
do_skillhub() {
  command -v skillhub >/dev/null 2>&1 || { note skillhub "未找到 skillhub CLI，跳过"; return 1; }
  # 若提供 token 则先登录；否则直接用 CLI 已保存的登录态（~/.skillhub/credentials.json）
  if [[ -n "${SKILLHUB_TOKEN:-}" ]]; then
    skillhub login --key "$SKILLHUB_TOKEN" >/dev/null 2>&1 \
      && note skillhub "已登录（token）" || { note skillhub "登录失败，检查 SKILLHUB_TOKEN"; return 1; }
  else
    skillhub auth whoami >/dev/null 2>&1 \
      || { note skillhub "未登录：请先 skillhub login --key skh_xxx（一次登录，Codex 与本机通用）"; return 1; }
  fi
  for s in "${SKILLS[@]}"; do
    if skillhub publish "$REPO/$s" --changelog "$CHANGELOG" >/dev/null 2>&1; then
      note skillhub "✓ $s"; ok=$((ok+1))
    else
      note skillhub "✗ $s 发布失败"; fail=$((fail+1))
    fi
  done
}

# ---------- 2. ClawHub（clawhub.ai）----------
do_clawhub() {
  command -v clawhub >/dev/null 2>&1 || { note clawhub "未安装：npm i -g clawhub"; return 1; }
  clawhub whoami >/dev/null 2>&1 || { note clawhub "未登录：请先执行 clawhub login"; return 1; }
  for s in "${SKILLS[@]}"; do
    v=$(grep -m1 '^version:' "$REPO/$s/SKILL.md" | sed 's/version: //')
    if clawhub publish "$REPO/$s" --slug "$s" --version "$v" \
         --changelog "$CHANGELOG" >/dev/null 2>&1; then
      note clawhub "✓ $s v$v"; ok=$((ok+1))
    else
      note clawhub "✗ $s 失败（slug 可能已被占用，需换名或加 --owner）"; fail=$((fail+1))
    fi
  done
}

# ---------- 3. GitHub ----------
do_github() {
  command -v gh >/dev/null 2>&1 || { note github "未安装 gh：brew install gh"; return 1; }
  gh auth status >/dev/null 2>&1 || { note github "未登录：请先 gh auth login"; return 1; }
  cd "$REPO" || return 1
  git config user.name >/dev/null 2>&1 || git config user.name "lis"
  if ! git config user.email >/dev/null 2>&1; then
    [[ -n "${GIT_USER_EMAIL:-}" ]] && git config user.email "$GIT_USER_EMAIL" \
      || { note github "请先 git config user.email 或 export GIT_USER_EMAIL=你的邮箱"; return 1; }
  fi
  git add -A
  git commit -q -m "$CHANGELOG" 2>/dev/null || note github "无新改动可提交"
  if git remote get-url origin >/dev/null 2>&1; then
    git push -q && note github "✓ 已推送" && ok=$((ok+1)) \
      || { note github "✗ push 失败"; fail=$((fail+1)); }
  else
    gh repo create lis-cad-skills --public --source=. --push >/dev/null 2>&1 \
      && { note github "✓ 已创建并推送"; ok=$((ok+1)); } \
      || { note github "✗ 创建仓库失败"; fail=$((fail+1)); }
  fi
}

# ---------- 4/5. 本机 WorkBuddy + Codex ----------
do_local() {
  for s in "${SKILLS[@]}"; do
    rm -rf "$HOME/.workbuddy/skills/$s" && cp -R "$REPO/$s" "$HOME/.workbuddy/skills/$s"
    rm -rf "$HOME/.codex/skills/$s" && cp -R "$REPO/$s" "$HOME/.codex/skills/$s"
    note local "✓ $s -> workbuddy + codex"; ok=$((ok+1))
  done
}

# ---------- 0. 认证状态检查（不发布）----------
do_status() {
  printf "%-12s %s\n" "平台" "状态"
  printf "%-12s %s\n" "----" "----"

  if command -v skillhub >/dev/null 2>&1; then
    w=$(skillhub auth whoami 2>&1 | head -3 | tr '\n' ' ')
    if [[ "$w" == *"未登录"* || "$w" == *"Error"* ]]; then
      printf "%-12s %s\n" "SkillHub" "✗ 未登录 → skillhub login --key skh_xxx"
    else
      printf "%-12s %s\n" "SkillHub" "✓ 已登录  $w"
    fi
  else
    printf "%-12s %s\n" "SkillHub" "✗ CLI 未安装"
  fi

  if command -v clawhub >/dev/null 2>&1; then
    if clawhub whoami >/dev/null 2>&1; then
      printf "%-12s %s\n" "ClawHub" "✓ 已登录  $(clawhub whoami 2>&1 | head -1)"
    else
      printf "%-12s %s\n" "ClawHub" "✗ 未登录 → clawhub login"
    fi
  else
    printf "%-12s %s\n" "ClawHub" "✗ 未安装 → npm i -g clawhub"
  fi

  if command -v gh >/dev/null 2>&1; then
    if gh auth status >/dev/null 2>&1; then
      printf "%-12s %s\n" "GitHub" "✓ 已登录"
    else
      printf "%-12s %s\n" "GitHub" "✗ 未登录 → gh auth login"
    fi
  else
    printf "%-12s %s\n" "GitHub" "✗ gh 未安装 → brew install gh"
  fi

  printf "%-12s %s\n" "WorkBuddy" "✓ 免认证（本地目录复制）"
  printf "%-12s %s\n" "Codex" "✓ 免认证（本地目录复制）"
  return 0
}

case "$TARGET" in
  all)      do_local; do_skillhub; do_clawhub; do_github ;;
  skillhub) do_skillhub ;;
  clawhub)  do_clawhub ;;
  github)   do_github ;;
  local)    do_local ;;
  status)   do_status; exit 0 ;;
  *) echo "未知目标: $TARGET（可选 all/skillhub/clawhub/github/local/status）"; exit 1 ;;
esac

echo
echo "完成：成功 $ok 项，失败 $fail 项"
[[ $fail -eq 0 ]]
