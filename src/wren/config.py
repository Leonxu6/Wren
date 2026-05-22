"""集中读取环境变量与默认配置 —— 所有 env 真相收口于此(§0② 轻量留 seam)。

p0-decisions 的"定数"也落在这里:候选清单、判官、阈值、reps。
⚠️ TODO(leon) 标记的是待你拍板、当前用提案默认的项。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根:src/wren/config.py → parents[2]。从这里加载本地 .env(gitignored;无 .env 时无副作用)。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# eval 阈值(EVAL_spec §4/§5;p0-decisions 默认提案)
PASS_THRESHOLD = 0.80  # 每类通过率门槛
CAT3_THRESHOLD = 0.90  # 反谄媚(pillar#2)硬验证门槛
BASELINE_WIN_THRESHOLD = 0.70  # 魔法 A/B:对甜妹 baseline 胜率门槛(special 成立)
PROACTIVE_CAT_THRESHOLD = 0.95  # 主动反谄媚零容忍(主动 ping 的过度热情/无来由是最刺眼 AI 味,Phase 5)

# 主动消息频率天花板(Phase 5「规则预筛」零-LLM)。平滑爬升:前期不找、后期 2-3/天(2026-05-21 与 Leon 定)。
# Lv0-1 不主动;Lv2 按周(刚开始);Lv3+ 按日(日~1 → 日~2 → 日~3)。
# ⚠️ 这是「关系等级允许的上限」,与付费门正交 —— free tier 在 core/proactive 里先短路成 0。
# 上限非配额:到点轻判在上限内【涌现】决定实际发几条(§0①),实际频率天然落在区间内。
PROACTIVE_WEEKLY_CAP = {0: 0, 1: 0, 2: 3}
PROACTIVE_DAILY_CAP = {3: 1, 4: 2, 5: 3, 6: 3}

CANON_DIR = PROJECT_ROOT / "canon"
WORLD_DIR = PROJECT_ROOT / "world"  # 全局 life skeleton(today.md 生成态 / life_arcs.md 手写种子)
CORPUS_PATH = PROJECT_ROOT / "eval" / "corpus" / "single_turn.yaml"
MULTITURN_CORPUS_PATH = PROJECT_ROOT / "eval" / "corpus" / "multi_turn.yaml"
ALIVENESS_CORPUS_PATH = PROJECT_ROOT / "eval" / "corpus" / "aliveness.yaml"


@dataclass(frozen=True)
class ModelSpec:
    """一个可调用模型的描述。api_key 懒读 env(不把密钥固化进对象)。"""

    name: str  # 内部标识(落 trace / 报告用,绝不含密钥)
    model: str  # 供应商 model id
    base_url: str
    api_key_env: str = "WREN_API_KEY"

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env)


# 候选模型清单(p0-decisions:DeepSeek 系必含)。
# 注:文档原写 DeepSeek-V3,但供应商已升级到 V4 代(V3 下线);依 §15「LLM 选型是开放提案」改用当前模型。
# ⚠️ TODO(leon): 是否再加一个非 DeepSeek 的更强 voice 模型作为第三候选。
DEFAULT_CANDIDATES: list[ModelSpec] = [
    ModelSpec(name="deepseek-v4-flash", model="deepseek-v4-flash", base_url=DEEPSEEK_BASE_URL),
    ModelSpec(name="deepseek-v4-pro", model="deepseek-v4-pro", base_url=DEEPSEEK_BASE_URL),
]


def candidates() -> list[ModelSpec]:
    """bake-off 候选清单。WREN_CANDIDATES(JSON 数组)可覆盖默认。"""
    raw = os.getenv("WREN_CANDIDATES")
    if raw:
        return [ModelSpec(**item) for item in json.loads(raw)]
    return list(DEFAULT_CANDIDATES)


def primary_model_spec() -> ModelSpec:
    """生产 Step1/Step2 的主模型(默认便宜候选 v4-flash)。"""
    return ModelSpec(
        name="primary",
        model=os.getenv("WREN_MODEL") or "deepseek-v4-flash",
        base_url=os.getenv("WREN_BASE_URL") or DEEPSEEK_BASE_URL,
    )


def judge_model_spec() -> ModelSpec:
    """判官:强推理模型(默认 v4-pro)。可独立 key/base_url(留 seam)。

    用 `or` 而非 getenv 默认值:.env 里的空串(如 WREN_JUDGE_BASE_URL=)要回退到默认,
    不能当作"已设为空"(否则 base_url="" → 连不上 → APIConnectionError)。
    """
    judge_key_env = "WREN_JUDGE_API_KEY" if os.getenv("WREN_JUDGE_API_KEY") else "WREN_API_KEY"
    return ModelSpec(
        name="judge",
        model=os.getenv("WREN_JUDGE_MODEL") or "deepseek-v4-pro",
        base_url=os.getenv("WREN_JUDGE_BASE_URL") or os.getenv("WREN_BASE_URL") or DEEPSEEK_BASE_URL,
        api_key_env=judge_key_env,
    )


def settlement_model_spec() -> ModelSpec:
    """夜结算的整体裁决(Phase 6):holistic 跨天判关系,默认强档 v4-pro(便宜模型弱项 §15#4)。
    每晚一次/用户,成本低;可独立 key/base_url(seam:改一行 env 即升 Opus)。同 judge 的空串回退处理。
    """
    key_env = "WREN_SETTLEMENT_API_KEY" if os.getenv("WREN_SETTLEMENT_API_KEY") else "WREN_API_KEY"
    return ModelSpec(
        name="settlement",
        model=os.getenv("WREN_SETTLEMENT_MODEL") or "deepseek-v4-pro",
        base_url=os.getenv("WREN_SETTLEMENT_BASE_URL")
        or os.getenv("WREN_BASE_URL")
        or DEEPSEEK_BASE_URL,
        api_key_env=key_env,
    )


def baseline_model_spec() -> ModelSpec:
    """魔法 A/B 的甜妹 baseline:跑在同一主模型上(控住模型变量,纯测 prompt 差异)。"""
    return primary_model_spec()


def eval_reps() -> int:
    return int(os.getenv("WREN_EVAL_REPS", "5"))


def multiturn_reps() -> int:
    """多轮:每 archetype 跑几次看通过率(2026-05-20 与 Leon 定 N=3,可配)。"""
    return int(os.getenv("WREN_MULTITURN_REPS", "3"))


def proactive_caps(level: int) -> tuple[int | None, int | None]:
    """主动频率上限 (weekly, daily);Lv0-3 看周、Lv4+ 看日,另一维 None。未知等级 → (None, None)=地板。"""
    return PROACTIVE_WEEKLY_CAP.get(level), PROACTIVE_DAILY_CAP.get(level)


def max_tokens() -> int:
    # V4 是推理模型(usage 含 reasoning_tokens),需留足空间给「思考 + 输出」。
    return int(os.getenv("WREN_MAX_TOKENS", "2048"))


def settlement_max_tokens() -> int:
    # 夜结算输出整段长 JSON(level+freeze+prose+core+unresolved)+ 强档推理模型(reasoning_tokens 占用大)。
    # 2048 会把 JSON 截在 prose/core 之间 → parse 失败 → 全字段静默回落旧值(夜结算变 no-op,关系永不更新)。
    # 故给足空间(每晚一次/用户,成本可忽略)。可经 env 调。
    return int(os.getenv("WREN_SETTLEMENT_MAX_TOKENS", "8000"))


def events_cap() -> int:
    """中期记忆注入 Step1 的事件条数上限(recency 排序 + salience 逐出)。
    seam:histories 长起来再换 token-cap / 夜间蒸馏 / 关键词召回(仍非 RAG)。"""
    return int(os.getenv("WREN_EVENTS_CAP", "40"))


def debounce_seconds() -> float:
    return float(os.getenv("WREN_DEBOUNCE_S", "4"))


def data_root() -> Path:
    # 防御:.env 里 `WREN_DATA_ROOT=   # 注释` 的行内注释可能被 dotenv 吞进值,
    # 空白 / 以 # 开头的值视作未设(否则会建出怪目录,如 `# 留空 → .`)。
    override = os.getenv("WREN_DATA_ROOT", "").strip()
    if not override or override.startswith("#"):
        return PROJECT_ROOT / "data" / "users"
    return Path(override)


def world_root() -> Path:
    """全局 world/ 目录(一个 Wren 一条命)。WREN_WORLD_ROOT 可覆盖 → eval 隔离 today/yesterday。"""
    override = os.getenv("WREN_WORLD_ROOT")
    return Path(override) if override else WORLD_DIR


def telegram_token() -> str | None:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def force_fake() -> bool:
    return os.getenv("WREN_FAKE_MODEL") == "1"


def has_api_key() -> bool:
    return bool(os.getenv("WREN_API_KEY"))
