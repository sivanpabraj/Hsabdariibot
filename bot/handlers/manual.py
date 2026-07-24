"""Conversation handlers for manual deposit/withdraw and accounts."""

from __future__ import annotations

from datetime import date

import jdatetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.db.database import Database
from bot.handlers.keyboards import (
    TYPE_LABEL,
    cancel_keyboard,
    format_tx_line,
    main_keyboard,
)
from bot.services.receipt_parser import format_money, parse_manual_amount

ASK_AMOUNT, ASK_DESC, ASK_ACCOUNT = range(3)
ASK_NEW_ACCOUNT = 10


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


async def start_manual(update: Update, context: ContextTypes.DEFAULT_TYPE, tx_type: str) -> int:
    context.user_data["manual_type"] = tx_type
    context.user_data.pop("manual_amount", None)
    context.user_data.pop("manual_desc", None)
    label = TYPE_LABEL[tx_type]
    await update.effective_message.reply_text(
        f"مبلغ {label} را به تومان بفرستید.\n"
        "مثال: 250000 یا 250٬000 یا 1.5 میلیون\n"
        "برای ریال بنویسید: 2500000 ریال",
        reply_markup=cancel_keyboard(),
    )
    return ASK_AMOUNT


async def deposit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await quick_command(update, context, "deposit")
        return ConversationHandler.END
    return await start_manual(update, context, "deposit")


async def withdraw_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await quick_command(update, context, "withdraw")
        return ConversationHandler.END
    return await start_manual(update, context, "withdraw")


async def manual_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text in ("❌ انصراف", "/cancel"):
        return await cancel(update, context)

    amount = parse_manual_amount(text)
    if not amount:
        await update.effective_message.reply_text(
            "مبلغ نامعتبر است. دوباره به تومان بفرستید (مثلاً 150000)."
        )
        return ASK_AMOUNT

    context.user_data["manual_amount"] = amount
    await update.effective_message.reply_text(
        f"مبلغ: {format_money(amount)}\n"
        "توضیح را بفرستید یا /skip برای بدون توضیح.",
        reply_markup=cancel_keyboard(),
    )
    return ASK_DESC


async def manual_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text in ("❌ انصراف", "/cancel"):
        return await cancel(update, context)
    if text == "/skip":
        text = ""
    context.user_data["manual_desc"] = text

    db = get_db(context)
    accounts = await db.list_accounts(update.effective_user.id)
    if not accounts:
        account = await db.ensure_default_account(update.effective_user.id)
        accounts = [account]

    if len(accounts) == 1:
        return await _save_manual(update, context, accounts[0].id)

    names = "\n".join(f"• {a.name}" for a in accounts)
    await update.effective_message.reply_text(
        f"حساب را انتخاب کنید (نام را بنویسید):\n{names}",
        reply_markup=cancel_keyboard(),
    )
    return ASK_ACCOUNT


async def manual_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text in ("❌ انصراف", "/cancel"):
        return await cancel(update, context)

    db = get_db(context)
    account = await db.get_or_create_account_by_name(update.effective_user.id, text)
    return await _save_manual(update, context, account.id)


async def _save_manual(update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int) -> int:
    db = get_db(context)
    user_id = update.effective_user.id
    tx_type = context.user_data["manual_type"]
    amount = context.user_data["manual_amount"]
    desc = context.user_data.get("manual_desc", "")

    today = date.today()
    j = jdatetime.date.fromgregorian(date=today)
    tx = await db.add_transaction(
        user_id=user_id,
        account_id=account_id,
        tx_type=tx_type,
        amount=amount,
        description=desc,
        source="manual",
        transaction_date=today.isoformat(),
        jalali_year=j.year,
        jalali_month=j.month,
    )
    context.user_data.clear()
    await update.effective_message.reply_text(
        f"✅ {TYPE_LABEL[tx_type]} ثبت شد.\n\n{format_tx_line(tx)}",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "انصراف داده شد.", reply_markup=main_keyboard()
    )
    return ConversationHandler.END


async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE, tx_type: str) -> None:
    """Handle /deposit and /withdraw with inline args."""
    args = context.args or []
    if not args:
        await start_manual(update, context, tx_type)
        return

    amount = parse_manual_amount(args[0])
    if not amount:
        await update.effective_message.reply_text("مبلغ نامعتبر است.")
        return
    desc = " ".join(args[1:]).strip()
    db = get_db(context)
    account = await db.ensure_default_account(update.effective_user.id)
    today = date.today()
    j = jdatetime.date.fromgregorian(date=today)
    tx = await db.add_transaction(
        user_id=update.effective_user.id,
        account_id=account.id,
        tx_type=tx_type,
        amount=amount,
        description=desc,
        source="manual",
        transaction_date=today.isoformat(),
        jalali_year=j.year,
        jalali_month=j.month,
    )
    await update.effective_message.reply_text(
        f"✅ {TYPE_LABEL[tx_type]} ثبت شد.\n\n{format_tx_line(tx)}",
        reply_markup=main_keyboard(),
    )


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await quick_command(update, context, "deposit")


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await quick_command(update, context, "withdraw")


async def list_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    txs = await db.recent_transactions(update.effective_user.id, limit=15)
    if not txs:
        await update.effective_message.reply_text(
            "هنوز تراکنشی ثبت نشده.", reply_markup=main_keyboard()
        )
        return
    lines = ["📋 آخرین تراکنش‌ها:\n"]
    for tx in txs:
        lines.append(format_tx_line(tx))
        lines.append("")
    await update.effective_message.reply_text(
        "\n".join(lines).strip(), reply_markup=main_keyboard()
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text("مثال: /delete 12")
        return
    db = get_db(context)
    ok = await db.delete_transaction(int(args[0]), update.effective_user.id)
    if ok:
        await update.effective_message.reply_text("🗑 تراکنش حذف شد.")
    else:
        await update.effective_message.reply_text("تراکنش پیدا نشد.")


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    tx_id = int(query.data.split(":")[1])
    db = get_db(context)
    ok = await db.delete_transaction(tx_id, update.effective_user.id)
    await query.edit_message_text("🗑 حذف شد." if ok else "پیدا نشد.")


async def accounts_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    await db.ensure_default_account(update.effective_user.id)
    accounts = await db.list_accounts(update.effective_user.id)
    lines = ["🏦 حساب‌های شما:\n"]
    for a in accounts:
        lines.append(f"• {a.name} (#{a.id})")
    lines.append("\nبرای ساخت حساب جدید: /newaccount نام حساب")
    await update.effective_message.reply_text("\n".join(lines), reply_markup=main_keyboard())


async def new_account_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    args = context.args or []
    if args:
        name = " ".join(args).strip()
        db = get_db(context)
        account = await db.get_or_create_account_by_name(update.effective_user.id, name)
        await update.effective_message.reply_text(
            f"✅ حساب «{account.name}» آماده است.", reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "نام حساب جدید را بفرستید:", reply_markup=cancel_keyboard()
    )
    return ASK_NEW_ACCOUNT


async def new_account_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text in ("❌ انصراف", "/cancel"):
        return await cancel(update, context)
    db = get_db(context)
    account = await db.get_or_create_account_by_name(update.effective_user.id, text)
    await update.effective_message.reply_text(
        f"✅ حساب «{account.name}» آماده است.", reply_markup=main_keyboard()
    )
    return ConversationHandler.END
