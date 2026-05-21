"""组装并启动 Telegram bot(polling)。需 TELEGRAM_BOT_TOKEN。"""

from __future__ import annotations

from typing import Any

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from .. import config
from .handlers import cmd_delete, cmd_help, cmd_setlevel, cmd_start, on_message
from .scheduler import register_nightly


async def _on_error(_update: object, context: Any) -> None:
    """全局错误处理:网络抖动等异常只记日志、不崩、不刷未捕获栈(live 健壮性)。"""
    print(f"⚠️  handler error: {context.error!r}", flush=True)


def build_application(token: str | None = None) -> Any:
    token = token or config.telegram_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 未设置(.env 或环境变量)")
    # 放宽 HTTP 超时(默认 5s 在抖动链路上易 TimedOut)+ 注册错误处理(异常不吞回复、不崩)。
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(20.0)
        .read_timeout(20.0)
        .write_timeout(20.0)
        .pool_timeout(20.0)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("setlevel", cmd_setlevel))  # 调试:手动设等级看暖度
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(_on_error)
    register_nightly(app)  # Phase 6:每晚 ET 2:30 夜结算
    return app


def main() -> None:
    if not config.has_api_key():
        print("⚠️  无 WREN_API_KEY:Wren 将无话可说(模型走 fake)。先在 .env 配 key。")
    app = build_application()
    print("Wren bot 启动(polling)… Ctrl-C 退出。")
    app.run_polling()


if __name__ == "__main__":
    main()
