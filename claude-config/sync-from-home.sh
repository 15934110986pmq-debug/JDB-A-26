#!/usr/bin/env bash
# 把 ~/.claude/ 当前可移植子集同步进 claude-config/(在源机器上使用)
set -euo pipefail

CFG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${HOME}/.claude"

mkdir -p "${CFG_DIR}/rules" "${CFG_DIR}/skills" "${CFG_DIR}/plugins" "${CFG_DIR}/projects/-home-p-JDB"

cp -v "${SRC}/settings.json"          "${CFG_DIR}/settings.json"
cp -v "${SRC}/statusline-command.sh"  "${CFG_DIR}/statusline-command.sh"
cp -v "${SRC}/session-aliases.json"   "${CFG_DIR}/session-aliases.json"

rsync -a --delete "${SRC}/rules/"  "${CFG_DIR}/rules/"
rsync -a --delete "${SRC}/skills/" "${CFG_DIR}/skills/"
rsync -a --delete "${SRC}/projects/-home-p-JDB/memory" "${CFG_DIR}/projects/-home-p-JDB/"

cp -v "${SRC}/plugins/installed_plugins.json"  "${CFG_DIR}/plugins/installed_plugins.json"
cp -v "${SRC}/plugins/known_marketplaces.json" "${CFG_DIR}/plugins/known_marketplaces.json"

echo
echo "✓ 同步完成。下一步: git add claude-config/ && git commit && git push"
