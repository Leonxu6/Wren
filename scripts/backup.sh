#!/usr/bin/env bash
# 备份 data/(per-user 关系命脉)+ world/(today)—— 丢了 = 丢掉所有人挨来的关系。
# cron 每晚跑 + 异地副本。环境变量:WREN_APP_DIR / WREN_BACKUP_DIR / WREN_BACKUP_KEEP。
set -euo pipefail

APP_DIR="${WREN_APP_DIR:-/srv/wren}"
DEST="${WREN_BACKUP_DIR:-/srv/wren-backups}"
KEEP="${WREN_BACKUP_KEEP:-14}"

mkdir -p "$DEST"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$DEST/wren-$TS.tgz"

tar czf "$ARCHIVE" -C "$APP_DIR" data world
# 只留最近 KEEP 份
ls -1t "$DEST"/wren-*.tgz 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -f

echo "backup → $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
