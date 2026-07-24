"""Monthly report handlers."""

from __future__ import annotations

import jdatetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.db.database import Database
from bot.handlers.keyboards import format_monthly_report, main_keyboard, months_keyboard
from bot.services.receipt_parser import MONTH_NAME_TO_NUM


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


async def report_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    db = get_db(context)
    user_id = update.effective_user.id

    if len(args) >= 2 and args[0].isdigit() and args[1].isdigit():
        y, m = int(args[0]), int(args[1])
        if not 1 <= m <= 12:
            await update.effective_message.reply_text("ماه باید بین ۱ تا ۱۲ باشد.")
            return
        summary = await db.monthly_summary(user_id, y, m)
        await update.effective_message.reply_text(
            format_monthly_report(summary), reply_markup=main_keyboard()
        )
        return

    if len(args) == 1:
        # month name or number for current year
        today = jdatetime.date.today()
        token = args[0].strip()
        if token.isdigit():
            m = int(token)
        else:
            m = MONTH_NAME_TO_NUM.get(token)
        if not m or not 1 <= m <= 12:
            await update.effective_message.reply_text("ماه نامعتبر است.")
            return
        summary = await db.monthly_summary(user_id, today.year, m)
        await update.effective_message.reply_text(
            format_monthly_report(summary), reply_markup=main_keyboard()
        )
        return

    months = await db.list_months(user_id, limit=12)
    await update.effective_message.reply_text(
        "ماه گزارش را انتخاب کنید:",
        reply_markup=months_keyboard(months),
    )


async def report_month_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    db = get_db(context)
    user_id = update.effective_user.id

    if data == "month:current":
        today = jdatetime.date.today()
        y, m = today.year, today.month
    else:
        _, y_s, m_s = data.split(":")
        y, m = int(y_s), int(m_s)

    summary = await db.monthly_summary(user_id, y, m)
    await query.edit_message_text(format_monthly_report(summary))


async def report_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.args = []
    await report_entry(update, context)
