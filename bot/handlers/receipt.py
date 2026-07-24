"""Receipt photo/text flow: Gemini AI first, Tesseract fallback."""

from __future__ import annotations

import logging
from datetime import date

import jdatetime
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.db.database import Database
from bot.handlers.keyboards import (
    TYPE_LABEL,
    cancel_keyboard,
    category_keyboard,
    format_tx_line,
    main_keyboard,
    receipt_confirm_keyboard,
    type_confirm_keyboard,
)
from bot.services.categories import category_label, guess_category_from_text
from bot.services.gemini import (
    analyze_receipt_image,
    analyze_receipt_text,
    gemini_enabled,
    gemini_to_parsed,
)
from bot.services.ocr import extract_text_from_image
from bot.services.receipt_parser import (
    ParsedReceipt,
    format_jalali,
    format_money,
    parse_manual_amount,
    parse_receipt_text,
)

logger = logging.getLogger(__name__)

WAIT_RECEIPT, CONFIRM, EDIT_AMOUNT, PICK_CATEGORY = range(4)


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def _ensure_category(parsed: ParsedReceipt) -> ParsedReceipt:
    if parsed.category:
        return parsed
    text = f"{parsed.description}\n{parsed.raw_text}"
    guessed = guess_category_from_text(text, parsed.tx_type)
    if guessed:
        parsed.category = guessed
    return parsed


def _preview(parsed: ParsedReceipt) -> str:
    kind = TYPE_LABEL.get(parsed.tx_type or "", "نامشخص")
    amount = format_money(parsed.amount) if parsed.amount else "—"
    when = (
        format_jalali(
            jy=parsed.jalali_year,
            jm=parsed.jalali_month,
            jd=parsed.transaction_date.day,
        )
        if parsed.transaction_date and parsed.jalali_year and parsed.jalali_month
        else "—"
    )
    lines = [
        "📄 نتیجه خواندن رسید:",
        f"• نوع: {kind}",
        f"• مبلغ: {amount}",
        f"• دسته: {category_label(parsed.category)}",
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


def _parse_image_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> ParsedReceipt:
    if gemini_enabled():
        try:
            data = analyze_receipt_image(image_bytes, mime_type=mime_type)
            return _ensure_category(gemini_to_parsed(data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini image analysis failed: %s", exc)

    raw_text = extract_text_from_image(image_bytes)
    if not raw_text.strip():
        return ParsedReceipt(notes=["متنی از عکس خوانده نشد"], raw_text="")
    parsed = parse_receipt_text(raw_text)
    notes = list(parsed.notes or [])
    notes.insert(0, "خوانده‌شده با OCR (پشتیبان)")
    parsed.notes = notes
    return _ensure_category(parsed)


def _parse_text(raw_text: str) -> ParsedReceipt:
    if gemini_enabled():
        try:
            data = analyze_receipt_text(raw_text)
            return _ensure_category(gemini_to_parsed(data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini text analysis failed: %s", exc)

    parsed = parse_receipt_text(raw_text)
    notes = list(parsed.notes or [])
    notes.insert(0, "خوانده‌شده با پارس محلی (پشتیبان)")
    parsed.notes = notes
    return _ensure_category(parsed)


async def _after_parse(
    update: Update, context: ContextTypes.DEFAULT_TYPE, parsed: ParsedReceipt
) -> int:
    message = update.effective_message
    context.user_data["parsed"] = parsed

    if not parsed.amount and not (parsed.raw_text or "").strip():
        await message.reply_text(
            "متنی از رسید خوانده نشد. عکس واضح‌تر بفرستید یا متن را بنویسید.",
            reply_markup=cancel_keyboard(),
        )
        return WAIT_RECEIPT

    if not parsed.amount:
        await message.reply_text(
            _preview(parsed) + "\n\nمبلغ پیدا نشد. مبلغ را به تومان بفرستید:",
            reply_markup=cancel_keyboard(),
        )
        return EDIT_AMOUNT

    if not parsed.tx_type:
        await message.reply_text(
            _preview(parsed) + "\n\nنوع تراکنش را انتخاب کنید:",
            reply_markup=type_confirm_keyboard(),
        )
        return CONFIRM

    if not parsed.category:
        await message.reply_text(
            _preview(parsed) + "\n\nدسته را انتخاب کنید:",
            reply_markup=category_keyboard(parsed.tx_type),
        )
        return PICK_CATEGORY

    await message.reply_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
    return CONFIRM


async def receipt_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("parsed", None)
    engine = "Gemini AI" if gemini_enabled() else "OCR"
    await update.effective_message.reply_text(
        "📷 عکس رسید را بفرستید، یا متن رسید را کپی کنید و بفرستید.\n"
        f"ربات با {engine} مبلغ، نوع و تاریخ را استخراج می‌کند.",
        reply_markup=cancel_keyboard(),
    )
    return WAIT_RECEIPT


async def receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.effective_message
    if message.text and message.text.strip() in ("❌ انصراف", "/cancel"):
        from bot.handlers.manual import cancel

        return await cancel(update, context)

    if message.photo:
        await message.reply_text("⏳ در حال خواندن رسید با هوش مصنوعی...")
        photo = message.photo[-1]
        file = await photo.get_file()
        bio = await file.download_as_bytearray()
        parsed = _parse_image_bytes(bytes(bio), mime_type="image/jpeg")
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        await message.reply_text("⏳ در حال خواندن رسید با هوش مصنوعی...")
        file = await message.document.get_file()
        bio = await file.download_as_bytearray()
        mime = message.document.mime_type or "image/jpeg"
        parsed = _parse_image_bytes(bytes(bio), mime_type=mime)
    elif message.text:
        await message.reply_text("⏳ در حال تحلیل متن رسید...")
        parsed = _parse_text(message.text)
    else:
        await message.reply_text("عکس یا متن رسید بفرستید.")
        return WAIT_RECEIPT

    return await _after_parse(update, context, parsed)


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
        parsed = _ensure_category(parsed)
        context.user_data["parsed"] = parsed
        if not parsed.category:
            await query.edit_message_text(
                _preview(parsed) + "\n\nدسته را انتخاب کنید:",
                reply_markup=category_keyboard(parsed.tx_type),
            )
            return PICK_CATEGORY
        await query.edit_message_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
        return CONFIRM

    if data.startswith("cat:"):
        parsed.category = data.split(":", 1)[1]
        context.user_data["parsed"] = parsed
        await query.edit_message_text(_preview(parsed), reply_markup=receipt_confirm_keyboard())
        return CONFIRM

    if data == "rcat":
        if not parsed.tx_type:
            await query.edit_message_text(
                "اول نوع تراکنش را مشخص کنید:",
                reply_markup=type_confirm_keyboard(),
            )
            return CONFIRM
        await query.edit_message_text(
            "دسته را انتخاب کنید:",
            reply_markup=category_keyboard(parsed.tx_type),
        )
        return PICK_CATEGORY

    if data == "rswitch":
        parsed.tx_type = "withdraw" if parsed.tx_type == "deposit" else "deposit"
        if not parsed.tx_type:
            parsed.tx_type = "deposit"
        parsed.category = None
        context.user_data["parsed"] = parsed
        await query.edit_message_text(
            _preview(parsed) + "\n\nدسته را انتخاب کنید:",
            reply_markup=category_keyboard(parsed.tx_type),
        )
        return PICK_CATEGORY

    if data == "redit_amount":
        await query.edit_message_text("مبلغ جدید را به تومان بفرستید:")
        return EDIT_AMOUNT

    if data == "rok":
        if not parsed.amount or not parsed.tx_type:
            await query.edit_message_text(
                "مبلغ یا نوع کامل نیست. اصلاح کنید.",
                reply_markup=receipt_confirm_keyboard()
                if parsed.amount
                else type_confirm_keyboard(),
            )
            return CONFIRM
        if not parsed.category:
            await query.edit_message_text(
                "دسته را انتخاب کنید:",
                reply_markup=category_keyboard(parsed.tx_type),
            )
            return PICK_CATEGORY
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

    if not parsed.category:
        await update.effective_message.reply_text(
            _preview(parsed) + "\n\nدسته را انتخاب کنید:",
            reply_markup=category_keyboard(parsed.tx_type),
        )
        return PICK_CATEGORY

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
    category = parsed.category or (
        "other_expense" if parsed.tx_type == "withdraw" else "other_income"
    )
    return await db.add_transaction(
        user_id=user.id,
        account_id=account.id,
        tx_type=parsed.tx_type or "deposit",
        amount=parsed.amount or 0,
        description=parsed.description or "از رسید",
        category=category,
        source="receipt",
        receipt_text=parsed.raw_text[:4000],
        transaction_date=gdate.isoformat(),
        jalali_year=jy,
        jalali_month=jm,
    )
