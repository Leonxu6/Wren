#!/usr/bin/env bash
# 从备份恢复 data/ + world/。
#
# 默认 staging 模式(D3.4 恢复演练):解到空 tmp 目录,人工核对可还原 —— 绝不碰 /srv/wren。
# --live 模式:恢复到 /srv/wren,需要显式 flag;先校验归档 → 自动备份当前目录到
#   /srv/wren/.pre-restore-<ts>/(失败可手动回滚)→ 解压 → smoke check。
# 不停服由 ops 自行 docker compose stop(脚本会检测并提醒);避免脚本越权 stop 跑着的 bot。
#
# 用法:
#   scripts/restore.sh <backup.tgz>                  # staging 演练(默认,安全)
#   scripts/restore.sh <backup.tgz> --staging /tmp/x # 显式 staging 路径
#   scripts/restore.sh <backup.tgz> --live           # 恢复 /srv/wren(危险,要求停服)
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <backup.tgz> [--live|--staging <dir>]}"
shift || true

MODE="staging"
STAGING_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --live) MODE="live"; shift ;;
    --staging)
      MODE="staging"
      STAGING_DIR="${2:?--staging 需要路径}"
      shift 2
      ;;
    *) echo "✗ 未知参数:$1" >&2; exit 2 ;;
  esac
done

# ---- 1) 校验归档结构 ----
# 只允许 data/ 或 world/ 顶层的相对路径;拒绝绝对路径 / .. 穿越 / 其他顶层(#27)
echo "== 1) 校验归档结构 =="
BAD_ENTRY=$(tar tzf "$ARCHIVE" | awk '
  /^\// || /\.\.\// { print "absolute-or-traversal: " $0; exit }
  !/^(data|world)\// && !/^(data|world)$/ { print "unexpected-toplevel: " $0; exit }
' || true)
if [ -n "$BAD_ENTRY" ]; then
  echo "✗ 归档结构不合法:$BAD_ENTRY" >&2
  echo "  归档只允许 data/... 或 world/... 相对路径(防穿越/越权)" >&2
  exit 1
fi
echo "  ✓ 归档只含 data/ + world/,无绝对路径 / .. 穿越"

# ---- 2) 选 target + live 前置 ----
if [ "$MODE" = "staging" ]; then
  if [ -z "$STAGING_DIR" ]; then
    TARGET=$(mktemp -d -t wren-restore-XXXXXX)
    echo "  staging 模式:解到 $TARGET(演练后人工核对;不影响 live)"
  else
    TARGET="$STAGING_DIR"
    mkdir -p "$TARGET"
  fi
else
  TARGET="/srv/wren"
  BACKUP_DIR=""
  echo "⚠️  --live 模式:恢复到 $TARGET"
  if pgrep -f 'docker compose|docker-compose' > /dev/null 2>&1; then
    echo "  ⚠️  检测到 docker compose 进程,**强烈建议先**:" >&2
    echo "       cd /srv/wren && docker compose stop" >&2
    echo "       否则 live 写入与恢复交错(#27)" >&2
  fi
  # 自动备份当前 data/+world/ 到 .pre-restore-<ts>(失败可手动恢复)
  if [ -d "$TARGET/data" ] || [ -d "$TARGET/world" ]; then
    BACKUP_DIR="$TARGET/.pre-restore-$(date +%Y%m%d-%H%M%S)"
    echo "  备份当前 data/+world/ → $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    [ -d "$TARGET/data" ] && mv "$TARGET/data" "$BACKUP_DIR/data" || true
    [ -d "$TARGET/world" ] && mv "$TARGET/world" "$BACKUP_DIR/world" || true
  fi
fi

# ---- 3) 解压 ----
echo "== 2) tar 解压 → $TARGET =="
mkdir -p "$TARGET"
tar xzf "$ARCHIVE" -C "$TARGET"

# ---- 4) Smoke ----
echo "== 3) smoke check =="
USER_COUNT=$(find "$TARGET/data/users" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
echo "  users:    $USER_COUNT"
[ -d "$TARGET/world" ] && echo "  world/:   exists" || echo "  world/:   ⚠️  不在"

echo
echo "✓ restored $ARCHIVE → $TARGET ($MODE 模式)"
if [ "$MODE" = "live" ]; then
  echo "  现在:cd $TARGET && docker compose up -d --build"
  if [ -n "$BACKUP_DIR" ]; then
    echo "  失败回滚:$BACKUP_DIR/data → $TARGET/data + 同理 world"
  fi
fi
