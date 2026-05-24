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
echo "== 2) 打包 git HEAD → rsync VPS:/srv/wren/ =="
# Fail-safe allowlist:只上传 git HEAD 跟踪的文件(`git archive`)。
# .env / .git / 未跟踪的 recap 素材 / plan.md / WIP 自然进不去(#13)。
# 比 --exclude opt-out 安全:以后新增任何 WIP 目录不需要再补 exclude。
#
# 部署前要求 working tree 干净(modified tracked 文件不会被打进 archive,
# 不强卡的话很容易"我以为部署了改动但其实只部署了 HEAD")。
if ! git diff --quiet HEAD; then
  echo "  ✗ working tree 有未 commit 的 tracked 改动 —— git archive HEAD 不会带它们。" >&2
  echo "    先 commit(或 git stash)再 deploy,否则你看到的本地改动不会上 VPS。" >&2
  echo "    未跟踪文件不影响——本来就不该 deploy。" >&2
  exit 1
fi

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
git archive HEAD | tar -x -C "$STAGE"

rsync -az -e "ssh -p 62769" "$STAGE"/ root@104.233.146.220:/srv/wren/
echo "  ✓ rsync OK (tracked-only,$(find "$STAGE" -type f | wc -l | tr -d ' ') 个文件)"

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
