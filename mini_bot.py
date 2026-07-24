#!/usr/bin/env python3
"""Minimal bot to verify Telegram round-trip works."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bot.config import BOT_TOKEN
from bot.handlers.keyboards import main_keyboard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mini")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("START from %s", update.effective_user.id)
    await update.message.reply_text(
        "✅ ربات کار می‌کند!\nاز منو استفاده کنید یا /ping بزنید.",
        reply_markup=main_keyboard(),
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.info("PING from %s", update.effective_user.id)
    await update.message.reply_text("pong ✅")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    log.info("ECHO %r from %s", text, update.effective_user.id)
    await update.message.reply_text(f"دریافت شد: {text}")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("no token")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    log.info("mini bot polling")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
