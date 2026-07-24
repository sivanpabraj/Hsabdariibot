"""Receipt photo/text OCR flow with confirmation."""

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
    receipt_confirm_keyboard,
    type_confirm_keyboard,
)
from bot.services.ocr import extract_text_from_image
from bot.services.receipt_parser import (
    ParsedReceipt,
    format_jalali,
    format_money,
    parse_manual_amount,
    parse_receipt_text,
)

WAIT_RECEIPT, CONFIRM, EDIT_AMOUNT = range(3)


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def _preview(parsed: ParsedReceipt) -> str:
    kind = TYPE_LABEL.get(parsed.tx_type or "", "نامشخص")
    amount = format_money(parsed.amount) if parsed.amount else "—"
    when = (
        format_jalali(jy=parsed.jalali_year, jm=parsed.jalali_month, jd=parsed.transaction_date.day)
        if parsed.transaction_date and parsed.jalali_year and parsed.jalali_month
        else "—"
    )
    lines = [
        "📄 نتیجه خواندن رسید:",
        f"• نوع: {kind}",
        f"• مبلغ: {amount}",
        f"• تاریخ: {when}",
    ]
    if parsed.description:
        lines.append(f"• توضیح: {parsed.description}")
    if parsed.notes:
        lines.append("")
        lines.append("⚠️ " + " | ".join(parsed.notes))
    lines.append("")
    lines.append("اگر درست است ثبت کنید؛ وگرنه اصلاح کنید.")
    return "\n".join(lines)


async def receipt_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("parsed", None)
    await update.effective_message.reply_text(
        "📷 عکس رسید را بفرستید، یا متن رسید را کپی کنید و بفرستید.\n"
        "ربات مبلغ، نوع و تاریخ را استخراج می‌کند.",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_RECEIPT


async def receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    if message.text and message.text.strip() in ("❌ انصراف", "/cancel"):
        from bot.handlers.manual import cancel

        return await cancel(update, context)

    raw_text = ""
    if message.photo:
        await message.reply_text("⏳ در حال خواندن رسید...")
        photo = message.photo[-1]
        file = await photo.get_file()
        bio = await file.download_as_bytearray()
        try:
            raw_text = extract_text_from_image(bytes(bio))
        except Exception as exc:  # noqa: BLE001
            await message.reply_text(
                f"خطا در OCR: {exc}\nمتن رسید را دستی بفرستید.",
                reply_markup=cancel_keyboard(),
            )
            return WAIT_RECEIPT
        if not raw_text.strip():
            await message.reply_text(
                "متنی از عکس خوانده نشد. عکس واضح‌تر بفرستید یا متن رسید را بنویسید.",
                reply_markup=cancel_keyboard(),
            )
            return WAIT_RECEIPT
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        await message.reply_text("⏳ در حال خواندن رسید...")
        file = await message.document.get_file()
        bio = await file.download_as_bytearray()
        raw_text = extract_text_from_image(bytes(bio))
    elif message.text:
        raw_text = message.text
    else:
        await message.reply_text("عکس یا متن رسید بفرستید.")
        return WAIT_RECEIPT

    parsed = parse_receipt_text(raw_text)
    context.user_data["parsed"] = parsed

    if not parsed.amount:
        await message.reply_text(
            "مبلغ پیدا نشد. مبلغ را به تومان بفرستید:",
            reply_markup=cancel_keyboard(),
        )
        # Keep OCR text for later
        return EDIT_AMOUNT

    if not parsed.tx_type:
        await message.reply_text(
            _preview(parsed) + "\n\nنوع تراکنش را انتخاب کنید:",
            reply_markup=type_confirm_keyboard(),
        )
        return CONFIRM

    await message.reply_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
    return CONFIRM


async def receipt_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parsed: ParsedReceipt | None = context.user_data.get("parsed")
    if not parsed and data != "rcancel":
        await query.edit_message_text("نشست منقضی شده. دوباره /receipt را بزنید.")
        return ConversationHandler.END

    if data == "rcancel":
        context.user_data.clear()
        await query.edit_message_text("انصراف داده شد.")
        await query.message.reply_text("منوی اصلی:", reply_markup=main_keyboard())
        return ConversationHandler.END

    if data.startswith("rtype:"):
        parsed.tx_type = data.split(":")[1]
        context.user_data["parsed"] = parsed
        await query.edit_message_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
        return CONFIRM

    if data == "rswitch":
        parsed.tx_type = "withdraw" if parsed.tx_type == "deposit" else "deposit"
        if not parsed.tx_type:
            parsed.tx_type = "deposit"
        context.user_data["parsed"] = parsed
        await query.edit_message_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
        return CONFIRM

    if data == "redit_amount":
        await query.edit_message_text("مبلغ جدید را به تومان بفرستید:")
        return EDIT_AMOUNT

    if data == "rok":
        if not parsed.amount or not parsed.tx_type:
            await query.edit_message_text(
                "مبلغ یا نوع کامل نیست. اصلاح کنید.",
                reply_markup=receipt_confirm_keyboard() if parsed.amount else type_confirm_keyboard(),
            )
            return CONFIRM
        tx = await _persist(update, context, parsed)
        context.user_data.clear()
        await query.edit_message_text(f"✅ ثبت شد.\n\n{format_tx_line(tx)}")
        await query.message.reply_text("منوی اصلی:", reply_markup=main_keyboard())
        return ConversationHandler.END

    return CONFIRM


async def edit_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if text in ("❌ انصراف", "/cancel"):
        from bot.handlers.manual import cancel

        return await cancel(update, context)

    amount = parse_manual_amount(text)
    if not amount:
        await update.effective_message.reply_text("مبلغ نامعتبر است. دوباره بفرستید.")
        return EDIT_AMOUNT

    parsed: ParsedReceipt = context.user_data.get("parsed") or ParsedReceipt()
    parsed.amount = amount
    if not parsed.transaction_date:
        today = date.today()
        j = jdatetime.date.fromgregorian(date=today)
        parsed.transaction_date = today
        parsed.jalali_year = j.year
        parsed.jalali_month = j.month
    context.user_data["parsed"] = parsed

    if not parsed.tx_type:
        await update.effective_message.reply_text(
            _preview(parsed) + "\n\nنوع تراکنش را انتخاب کنید:",
            reply_markup=type_confirm_keyboard(),
        )
        return CONFIRM

    await update.effective_message.reply_text(
        _preview(parsed), reply_markup=receipt_confirm_keyboard()
    )
    return CONFIRM


async def _persist(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parsed: ParsedReceipt
):
    db = get_db(context)
    user = update.effective_user
    account = await db.ensure_default_account(user.id)
    gdate = parsed.transaction_date or date.today()
    jy = parsed.jalali_year
    jm = parsed.jalali_month
    if not jy or not jm:
        j = jdatetime.date.fromgregorian(date=gdate)
        jy, jm = j.year, j.month
    return await db.add_transaction(
        user_id=user.id,
        account_id=account.id,
        tx_type=parsed.tx_type or "deposit",
        amount=parsed.amount or 0,
        description=parsed.description or "از رسید",
        source="receipt",
        receipt_text=parsed.raw_text[:4000],
        transaction_date=gdate.isoformat(),
        jalali_year=jy,
        jalali_month=jm,
    )
