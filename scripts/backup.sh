#!/usr/bin/env bash
# 备份 data/(per-user 关系命脉)+ world/(today)—— 丢了 = 丢掉所有人挣来的关系。
# cron 每晚跑 + 异地副本(异地必须加密,见 #36)。
#
# 用法:
#   scripts/backup.sh                                    # 本机明文 .tgz(umask 077,root-only)
#   WREN_BACKUP_PASSPHRASE=xxx scripts/backup.sh --encrypt
#                                                        # openssl AES-256 加密,产物 .tgz.age
#   scripts/backup.sh --encrypt --encrypt-to age1xxx     # age 公钥加密(需要 age 工具)
#
# 环境:
#   WREN_APP_DIR             默认 /srv/wren
#   WREN_BACKUP_DIR          默认 /srv/wren-backups
#   WREN_BACKUP_KEEP         保留份数(默认 14)
#   WREN_BACKUP_PASSPHRASE   openssl 加密 passphrase(--encrypt 无 --encrypt-to 时用)
#
# 异地副本(#36):**只允许 .tgz.age 后缀**进入 offsite,绝不 cp .tgz 明文。
# data/users 里有原始聊天、inner voice、relationship prose、settlement raw output、
# raw chat_id 目录名 —— 一旦明文 tgz 离机,"内容不出机器" 的承诺就没了。
set -euo pipefail

APP_DIR="${WREN_APP_DIR:-/srv/wren}"
DEST="${WREN_BACKUP_DIR:-/srv/wren-backups}"
KEEP="${WREN_BACKUP_KEEP:-14}"

ENCRYPT=0
ENCRYPT_TO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --encrypt) ENCRYPT=1; shift ;;
    --encrypt-to) ENCRYPT=1; ENCRYPT_TO="${2:?--encrypt-to 需要 age recipient}"; shift 2 ;;
    *) echo "✗ 未知参数:$1" >&2; exit 2 ;;
  esac
done

# umask 077:即使明文 .tgz 也是 0600(防同机其他用户读到原始聊天/inner voice / chat_id)
umask 077
mkdir -p "$DEST"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_BASE="$DEST/wren-$TS.tgz"

if [ "$ENCRYPT" = "0" ]; then
  ARCHIVE="$ARCHIVE_BASE"
  tar czf "$ARCHIVE" -C "$APP_DIR" data world
else
  ARCHIVE="$ARCHIVE_BASE.age"
  if [ -n "$ENCRYPT_TO" ]; then
    if ! command -v age > /dev/null 2>&1; then
      echo "✗ --encrypt-to 需要 age 工具(brew install age / apt install age)" >&2
      exit 1
    fi
    tar cz -C "$APP_DIR" data world | age -r "$ENCRYPT_TO" -o "$ARCHIVE"
  elif [ -n "${WREN_BACKUP_PASSPHRASE:-}" ]; then
    # openssl AES-256-CBC + PBKDF2;passphrase 走 env 不进 process args(防 ps 偷看)
    tar cz -C "$APP_DIR" data world \
      | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:WREN_BACKUP_PASSPHRASE \
        -out "$ARCHIVE"
  else
    echo "✗ --encrypt 需要 --encrypt-to <age-recipient> 或 WREN_BACKUP_PASSPHRASE env" >&2
    exit 1
  fi
fi

# 只留最近 KEEP 份(明文 + 加密都算同一 KEEP 池)
# `|| true` 让 ls 在通配符无匹配时不污染 pipefail(只一种产物时常见)
{ ls -1t "$DEST"/wren-*.tgz "$DEST"/wren-*.tgz.age 2>/dev/null || true; } \
  | tail -n "+$((KEEP + 1))" | xargs -r rm -f

echo "backup → $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
