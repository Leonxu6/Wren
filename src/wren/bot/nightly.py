"""wren-nightly:手动跑一次夜结算(本地调试 + Opus 手判散文重写质量)。

  uv run wren-nightly                 # 对所有活跃用户各跑一次
  uv run wren-nightly --chat-id 123   # 只跑某用户

真模型默认走 settlement 档(v4-pro);fake/无 key 时只验机制(内容无意义)。
"""

from __future__ import annotations

import argparse

from .. import config
from ..core.settlement import settle_nightly
from ..core.storage import UserStore
from ..model.base import ChatModel
from ..model.registry import get_model
from .scheduler import active_chat_ids


def _run_one(chat_id: str, model: ChatModel) -> None:
    store = UserStore(chat_id)
    if not store.exists():
        print(f"[{chat_id}] 不存在,跳过")
        return
    outcome = settle_nightly(store, model)
    if not outcome.ran:
        print(f"[{chat_id}] 无今日印象,跳过结算")
        return
    b, a = outcome.before, outcome.after
    print(f"\n===== [{chat_id}] 结算({len(outcome.impressions)} 条今日印象)=====")
    print(f"  level : {b.level} → {a.level}")
    print(f"  freeze: {b.freeze} → {a.freeze}")
    print(f"  --- prose before ---\n{b.prose}")
    print(f"  --- prose after ---\n{a.prose}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wren 夜结算(手动跑一次)")
    parser.add_argument("--chat-id", default=None, help="只结算某用户;省略=所有活跃用户")
    args = parser.parse_args()

    if config.force_fake() or not config.has_api_key():
        print("⚠️  无 WREN_API_KEY 或 WREN_FAKE_MODEL=1:结算走 fake,内容无意义(只验机制)。\n")

    model = get_model("settlement")
    chat_ids = [args.chat_id] if args.chat_id else active_chat_ids()
    if not chat_ids:
        print("没有活跃用户(data/users/ 为空)。")
        return
    for cid in chat_ids:
        _run_one(cid, model)


if __name__ == "__main__":
    main()
