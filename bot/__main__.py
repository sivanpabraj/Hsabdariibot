"""Telegram personal accounting bot — simple always-respond router."""

from __future__ import annotations

import logging
import traceback

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN
from bot.db.database import Database
from bot import router

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")


async def post_init(app: Application) -> None:
    # Essential: if a webhook is set, polling receives nothing.
    await app.bot.delete_webhook(drop_pending_updates=True)
    db = Database()
    await db.connect()
    app.bot_data["db"] = db
    me = await app.bot.get_me()
    logger.info("Ready @%s id=%s — polling active", me.username, me.id)


async def post_shutdown(app: Application) -> None:
    db = app.bot_data.get("db")
    if db:
        await db.close()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    logger.error("ERROR: %s", err)
    logger.error(traceback.format_exc())
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                update.effective_chat.id,
                f"خطای داخلی: {type(err).__name__}\n/start یا /ping را بزنید.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send error message")


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN missing.\n"
            "Copy .env.example → .env and set BOT_TOKEN from @BotFather, then run again."
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Commands — always answered
    app.add_handler(CommandHandler("ping", router.cmd_ping))
    app.add_handler(CommandHandler("start", router.cmd_start))
    app.add_handler(CommandHandler("help", router.cmd_help))
    app.add_handler(CommandHandler("cancel", router.cmd_cancel))
    app.add_handler(CommandHandler("deposit", router.cmd_deposit))
    app.add_handler(CommandHandler("withdraw", router.cmd_withdraw))
    app.add_handler(CommandHandler("receipt", router.cmd_receipt))
    app.add_handler(CommandHandler("report", router.cmd_report))
    app.add_handler(CommandHandler("list", router.cmd_list))
    app.add_handler(CommandHandler("accounts", router.cmd_accounts))
    app.add_handler(CommandHandler("categories", router.cmd_categories))
    app.add_handler(CommandHandler("newbankaccount", router.cmd_newbankaccount))
    app.add_handler(CommandHandler("addaccount", router.cmd_newbankaccount))
    app.add_handler(CommandHandler("newaccount", router.cmd_newaccount))
    app.add_handler(CommandHandler("delete", router.cmd_delete))

    # Media + text + callbacks — single path each, always replies
    app.add_handler(MessageHandler(filters.PHOTO, router.on_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, router.on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router.on_text))
    app.add_handler(CallbackQueryHandler(router.on_callback))

    app.add_error_handler(on_error)
    return app


def main() -> None:
    app = build_app()
    logger.info("Starting long polling…")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
