# Claude Code 配置同步

把这台机器的 Claude Code 配置（`~/.claude/` 下的可移植子集）打包到 repo,方便换设备时一键恢复。

## 包含什么

| 路径 | 来源 | 说明 |
|------|------|------|
| `settings.json` | `~/.claude/settings.json` | 主设置(默认权限模式、status line、effort level、已知 marketplace) |
| `statusline-command.sh` | `~/.claude/statusline-command.sh` | 自定义 status line 脚本 |
| `session-aliases.json` | `~/.claude/session-aliases.json` | session 别名 |
| `rules/` | `~/.claude/rules/` | 全局规则(common/python/typescript/golang/php) |
| `skills/` | `~/.claude/skills/` | 39 个用户级 skill |
| `plugins/installed_plugins.json` | `~/.claude/plugins/installed_plugins.json` | plugin 安装清单(用于重装) |
| `plugins/known_marketplaces.json` | `~/.claude/plugins/known_marketplaces.json` | 已知 marketplace 清单 |
| `projects/-home-p-JDB/memory/` | `~/.claude/projects/-home-p-JDB/memory/` | JDB 项目 auto-memory(7 条) |

## 不包含什么(刻意排除)

- `.credentials.json` — **凭证**,绝不入库,新机器单独 `claude login`
- `history.jsonl`、`bash-commands.log`、`cost-tracker.log` — 历史与日志(含敏感对话)
- `cache/`、`paste-cache/`、`shell-snapshots/`、`session-env/`、`sessions/`、`ide/`、`homunculus/`、`tasks/`、`telemetry/`、`usage-data/`、`metrics/`、`stats-cache.json`、`file-history/`、`backups/`、`plans/`、`session-data/` — 单机状态/缓存,新机器自己生成
- `plugins/cache/`、`plugins/marketplaces/`、`plugins/data/`、`plugins/install-counts-cache.json` — 插件实际内容由 marketplace 重新拉取
- `~/.claude.json`(40K,模式 600) — 包含全局 project 路径与最近文件,机器特定且敏感,不入库
- 其他 `projects/*/` 会话 transcript — 含敏感对话内容
- `settings.local.json` — 本机覆盖项(已被根 `.gitignore` 排除)

## 在新机器上恢复

前置条件:已装好 Claude Code CLI,完成 `claude login`(凭证不在此 repo 内)。

```bash
# 1. clone repo
git clone https://github.com/15934110986pmq-debug/JDB-A-26.git
cd JDB-A-26

# 2. 运行恢复脚本
bash claude-config/restore.sh

# 3. 重启 Claude Code,让插件 marketplace 重新拉取
#    Claude Code 启动时会按 plugins/installed_plugins.json 自动安装缺失插件
```

## 把当前机器的最新配置同步回 repo

```bash
bash claude-config/sync-from-home.sh
git add claude-config/
git commit -m "chore(claude-config): sync from $(hostname -s)"
git push
```

## 注意

- 此 repo 是 **public** GitHub repo。`settings.json` 里 `effortLevel`、`autoUpdatesChannel` 等属个人偏好,公开无害;但提交前请扫一遍新加入的 skill / rule 文件,**确认不含 token / API key / 私人信息**。
- `installed_plugins.json` 里的 `projectPath` 字段写死了本机绝对路径(`/home/p/...`),换机后需要根据新机器路径手动调整,或直接让 Claude Code 在新机器上重新装一遍插件。
