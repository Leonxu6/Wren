# Wren bot 镜像(W5)。单进程 long-poll + 内置 JobQueue(夜结算 2:30 ET + 主动消息 ~10min)。
# ⚠️ 单实例:long-poll + 内存锁/debounce 不可水平扩容(勿 scale > 1)。
FROM python:3.11-slim

RUN pip install --no-cache-dir uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# 先装依赖(层缓存);[job-queue] 在主依赖、duckdb(监测)在 dev 组 → 用完整 sync 让 wren-metrics 可用。
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen

# 运行期 ground truth 种子(版本化,非状态):persona canon + world 静态弧线种子。
COPY canon ./canon
COPY world/life_arcs.md ./world/life_arcs.md

# data/(per-user 关系命脉)与 world/today.md 是运行期状态 → 挂卷,不进镜像(见 compose / RUNBOOK)。
CMD ["uv", "run", "wren-bot"]
