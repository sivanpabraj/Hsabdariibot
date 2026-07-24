"""Start / help / access control."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ALLOWED_USER_IDS
from bot.db.database import Database
from bot.handlers.keyboards import help_text, main_keyboard


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


async def ensure_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    if not user or user.id not in ALLOWED_USER_IDS:
        if update.effective_message:
            await update.effective_message.reply_text("دسترسی ندارید.")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger("bot.start")
    logger.info("start called by %s", update.effective_user.id if update.effective_user else None)
    if not await ensure_access(update, context):
        return
    db = get_db(context)
    await db.ensure_default_account(update.effective_user.id)
    name = update.effective_user.first_name or "دوست"
    await update.effective_message.reply_text(
        f"سلام {name}\n\n"
        "📒 ربات حسابداری شخصی\n"
        "درآمد و هزینه‌هات رو اینجا ثبت کن، "
        "با عکس رسید هم می‌تونی خودکار اضافه کنی، "
        "و آخر ماه گزارش بگیری.\n\n"
        "از دکمه‌های پایین شروع کن یا /help را بزن.",
        reply_markup=main_keyboard(),
    )
    logger.info("start reply sent")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_access(update, context):
        return
    await update.effective_message.reply_text(help_text(), reply_markup=main_keyboard())
