#!/usr/bin/env bash
# 一键部署:本机离线门 → rsync VPS → docker compose rebuild/restart → tail logs。
# 用法: ./scripts/deploy.sh [service]
#   service 默认 bot,可选 viewer / metrics / all。
# 详细文档见 MAINTENANCE.md §5。
# set -e 单独不够:`false | tail -10` 在 pipefail 关时整体 exit 0,会把
# "远端 rebuild 失败" 报告成成功(#23)。-u 抓未定义变量,-o pipefail 抓 pipeline 中段失败。
set -euo pipefail
SERVICE="${1:-bot}"

# 校验 SERVICE 只允许 4 个值,避免把意外字符串拼进 docker compose 命令(#23)
case "$SERVICE" in
  bot|metrics|viewer|all) ;;
  *) echo "✗ SERVICE 必须是 bot|metrics|viewer|all,实际:$SERVICE" >&2; exit 2 ;;
esac

cd "$(dirname "$0")/.."   # 走到仓库根

echo "== 1) 本机离线门(pytest + ruff + mypy) =="
WREN_FAKE_MODEL=1 uv run pytest -q
uv run ruff check . > /dev/null
uv run mypy src > /dev/null
echo "  ✓ 三连绿"

echo
echo "== 2) rsync → VPS:/srv/wren/ =="
rsync -az \
  --exclude data/ --exclude world/today.md --exclude world/yesterday.md \
  --exclude '*.duckdb*' --exclude '__pycache__/' --exclude '.venv/' \
  --exclude '.pytest_cache/' --exclude '.ruff_cache/' --exclude '.mypy_cache/' \
  --exclude '.coverage' --exclude '.env.bak.*' --exclude '*.vps' --exclude '.claude/' \
  -e "ssh -p 62769" \
  ./ root@104.233.146.220:/srv/wren/
echo "  ✓ rsync OK"

echo
echo "== 3) rebuild + restart $SERVICE =="
# 显式捕获 ssh 输出 + exit code,失败时 tail 出错 + 非零 exit;
# 不再裸 `| tail` 让 tail 的 0 覆盖 ssh 的非零(#23)。pipefail 是兜底。
REBUILD_LOG=$(mktemp); trap 'rm -f "$REBUILD_LOG"' EXIT
if [ "$SERVICE" = "all" ]; then
  REBUILD_CMD='cd /srv/wren && docker compose up -d --build'
else
  REBUILD_CMD="cd /srv/wren && docker compose up -d --build $SERVICE"
fi
if ! ssh -p 62769 root@104.233.146.220 "$REBUILD_CMD" > "$REBUILD_LOG" 2>&1; then
  echo "✗ 远端 rebuild 失败,最后 20 行:" >&2
  tail -20 "$REBUILD_LOG" >&2
  exit 1
fi
tail -20 "$REBUILD_LOG"

echo
echo "== 4) tail logs(最近 20 行) =="
sleep 4
ssh -p 62769 root@104.233.146.220 "cd /srv/wren && docker compose logs --tail=20 $SERVICE"

echo
echo "✓ deploy.sh 完成 · 见 dashboard http://localhost:8002(需 SSH 隧道)"
