#!/usr/bin/env bash
# 从备份恢复 data/ + world/。恢复演练(D3.4):解到空目录验证可还原,再比对。
# 用法:scripts/restore.sh <backup.tgz> [target_dir]
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <backup.tgz> [target_dir]}"
TARGET="${2:-/srv/wren}"

mkdir -p "$TARGET"
tar xzf "$ARCHIVE" -C "$TARGET"

echo "restored $ARCHIVE → $TARGET"
echo "users: $(find "$TARGET/data/users" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
