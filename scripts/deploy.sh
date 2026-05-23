#!/usr/bin/env bash
# 一键部署:本机离线门 → rsync VPS → docker compose rebuild/restart → tail logs。
# 用法: ./scripts/deploy.sh [service]
#   service 默认 bot,可选 viewer / metrics / all。
# 详细文档见 MAINTENANCE.md §5。
set -e
SERVICE="${1:-bot}"

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
if [ "$SERVICE" = "all" ]; then
  ssh -p 62769 root@104.233.146.220 'cd /srv/wren && docker compose up -d --build' | tail -20
else
  ssh -p 62769 root@104.233.146.220 "cd /srv/wren && docker compose up -d --build $SERVICE" | tail -10
fi

echo
echo "== 4) tail logs(最近 20 行) =="
sleep 4
ssh -p 62769 root@104.233.146.220 "cd /srv/wren && docker compose logs --tail=20 $SERVICE"

echo
echo "✓ deploy.sh 完成 · 见 dashboard http://localhost:8002(需 SSH 隧道)"
