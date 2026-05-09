#!/bin/bash
# Claude Code status line — derived from ~/.bashrc PS1
# Format: user@host:cwd [Model] ctx:N% $X.XX +A/-B

input=$(cat)

cwd=$(echo "$input"      | jq -r '.workspace.current_dir // .cwd // empty')
model=$(echo "$input"    | jq -r '.model.display_name // empty')
used=$(echo "$input"     | jq -r '.context_window.used_percentage // empty')
exceed=$(echo "$input"   | jq -r '.exceeds_200k_tokens // false')
cost=$(echo "$input"     | jq -r '.cost.total_cost_usd // empty')
added=$(echo "$input"    | jq -r '.cost.total_lines_added // empty')
removed=$(echo "$input"  | jq -r '.cost.total_lines_removed // empty')
api_ms=$(echo "$input"   | jq -r '.cost.total_api_duration_ms // empty')

user=$(whoami)
host=$(hostname -s)

# user@host:cwd
printf "\033[01;32m%s@%s\033[00m:\033[01;34m%s\033[00m" "$user" "$host" "$cwd"

# [Model]
if [ -n "$model" ]; then
  printf " \033[00;33m[%s]\033[00m" "$model"
fi

# ctx:N% — red if exceeds 200k, cyan otherwise
if [ -n "$used" ]; then
  if [ "$exceed" = "true" ]; then
    printf " \033[01;31mctx:%.0f%%!\033[00m" "$used"
  else
    printf " \033[00;36mctx:%.0f%%\033[00m" "$used"
  fi
fi

# $X.XX cost
if [ -n "$cost" ] && [ "$cost" != "0" ]; then
  printf " \033[00;35m\$%.2f\033[00m" "$cost"
fi

# +A/-B lines
if [ -n "$added" ] && [ -n "$removed" ]; then
  if [ "$added" != "0" ] || [ "$removed" != "0" ]; then
    printf " \033[00;32m+%s\033[00m/\033[00;31m-%s\033[00m" "$added" "$removed"
  fi
fi

# api time (s) — only if non-trivial
if [ -n "$api_ms" ] && [ "$api_ms" != "0" ]; then
  api_s=$(awk -v ms="$api_ms" 'BEGIN{printf "%.0f", ms/1000}')
  if [ "$api_s" -gt 1 ]; then
    printf " \033[02;37m%ss\033[00m" "$api_s"
  fi
fi

printf "\n"
