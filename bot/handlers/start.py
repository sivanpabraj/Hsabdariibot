"""Start / help / access control."""

from __future__ import annotations

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
    if not await ensure_access(update, context):
        return
    db = get_db(context)
    await db.ensure_default_account(update.effective_user.id)
    name = update.effective_user.first_name or "دوست"
    await update.effective_message.reply_text(
        f"سلام {name} 👋\n"
        "ربات واریز و برداشت آماده‌ست.\n"
        "واریز/برداشت دستی ثبت کن یا عکس رسید بفرست تا خودش بخونه.",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_access(update, context):
        return
    await update.effective_message.reply_text(help_text(), reply_markup=main_keyboard())
