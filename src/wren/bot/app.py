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
from .handlers import cmd_delete, cmd_help, cmd_start, on_message


def build_application(token: str | None = None) -> Any:
    token = token or config.telegram_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN 未设置(.env 或环境变量)")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    return app


def main() -> None:
    if not config.has_api_key():
        print("⚠️  无 WREN_API_KEY:Wren 将无话可说(模型走 fake)。先在 .env 配 key。")
    app = build_application()
    print("Wren bot 启动(polling)… Ctrl-C 退出。")
    app.run_polling()


if __name__ == "__main__":
    main()
