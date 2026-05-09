#!/usr/bin/env bash
# 把 claude-config/ 恢复到 ~/.claude/(新机器换机时使用)
# 不会覆盖 ~/.claude/.credentials.json — 凭证请单独 claude login
set -euo pipefail

CFG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${HOME}/.claude"

mkdir -p "${TARGET}/rules" "${TARGET}/skills" "${TARGET}/plugins" "${TARGET}/projects/-home-p-JDB"

cp -v "${CFG_DIR}/settings.json"           "${TARGET}/settings.json"
cp -v "${CFG_DIR}/statusline-command.sh"   "${TARGET}/statusline-command.sh"
cp -v "${CFG_DIR}/session-aliases.json"    "${TARGET}/session-aliases.json"
chmod +x "${TARGET}/statusline-command.sh"

rsync -a --delete "${CFG_DIR}/rules/"  "${TARGET}/rules/"
rsync -a --delete "${CFG_DIR}/skills/" "${TARGET}/skills/"
rsync -a --delete "${CFG_DIR}/projects/-home-p-JDB/memory" "${TARGET}/projects/-home-p-JDB/"

cp -v "${CFG_DIR}/plugins/installed_plugins.json"   "${TARGET}/plugins/installed_plugins.json"
cp -v "${CFG_DIR}/plugins/known_marketplaces.json"  "${TARGET}/plugins/known_marketplaces.json"

echo
echo "✓ 恢复完成。下一步:"
echo "  1) claude login  (如果尚未登录)"
echo "  2) 启动 Claude Code,marketplace 会自动重拉插件实体"
echo "  3) 如果项目路径变了,编辑 plugins/installed_plugins.json 里的 projectPath"
