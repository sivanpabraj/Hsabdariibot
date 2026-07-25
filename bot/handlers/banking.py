"""High-quality banking account management (banks, cards, opening balance)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.db.database import Database
from bot.handlers.keyboards import cancel_keyboard, main_keyboard
from bot.services.iran_banking import (
    ACCOUNT_TYPES,
    format_sheba,
    guess_bank_from_card,
    mask_account,
    mask_card,
    validate_account_number,
    validate_card_number,
    validate_sheba,
)
from bot.services.receipt_parser import format_money, parse_manual_amount
from bot.textnorm import normalize_text


def _is_cancel_text(text: str | None) -> bool:
    t = (text or "").strip()
    return t == "/cancel" or normalize_text(t) == normalize_text("❌ انصراف")

(
    BA_TITLE,
    BA_TYPE,
    BA_BANK,
    BA_CARD,
    BA_ACCOUNT_NO,
    BA_SHEBA,
    BA_OPENING,
    BA_CONFIRM,
) = range(40, 48)


def get_db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def _type_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for key, label in ACCOUNT_TYPES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"batype:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data="bacancel")])
    return InlineKeyboardMarkup(rows)


def _banks_keyboard(banks) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for b in banks:
        row.append(InlineKeyboardButton(b.name, callback_data=f"babank:{b.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("بدون بانک / نقد", callback_data="babank:0")])
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data="bacancel")])
    return InlineKeyboardMarkup(rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ ثبت حساب", callback_data="baok")],
            [InlineKeyboardButton("❌ انصراف", callback_data="bacancel")],
        ]
    )


def _draft_preview(data: dict) -> str:
    lines = [
        "🏦 پیش‌نمایش حساب جدید",
        f"• عنوان: {data.get('title')}",
        f"• نوع: {ACCOUNT_TYPES.get(data.get('account_type',''), data.get('account_type'))}",
        f"• بانک: {data.get('bank_name') or '—'}",
        f"• کارت: {mask_card(data.get('card_number',''))}",
        f"• شماره حساب: {mask_account(data.get('account_number',''))}",
        f"• شبا: {format_sheba(data.get('sheba',''))}",
        f"• موجودی اولیه: {format_money(int(data.get('opening_balance') or 0))}",
    ]
    return "\n".join(lines)


async def banking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db(context)
    user_id = update.effective_user.id
    await db.ensure_default_account(user_id)
    accounts = await db.list_bank_accounts(user_id)
    lines = ["🏦 حساب‌ها و بانک‌ها\n"]
    total = 0
    for acc in accounts:
        bal = await db.account_balance(acc.id, user_id)
        total += bal
        lines.append(f"#{acc.id} {acc.display_name}")
        lines.append(f"   نوع: {ACCOUNT_TYPES.get(acc.account_type, acc.account_type)}")
        if acc.card_number:
            lines.append(f"   کارت: {mask_card(acc.card_number)}")
        if acc.account_number:
            lines.append(f"   حساب: {mask_account(acc.account_number)}")
        if acc.sheba:
            lines.append(f"   شبا: {format_sheba(acc.sheba)}")
        lines.append(f"   موجودی اولیه: {format_money(acc.opening_balance)}")
        lines.append(f"   موجودی فعلی: {format_money(bal)}")
        lines.append("")
    lines.append(f"💰 جمع موجودی‌ها: {format_money(total)}")
    lines.append("\nدستورها:")
    lines.append("/newbankaccount — تعریف حساب/کارت جدید")
    lines.append("/accounts — همین لیست")
    await update.effective_message.reply_text("\n".join(lines), reply_markup=main_keyboard())


async def new_bank_account_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ba"] = {}
    await update.effective_message.reply_text(
        "عنوان حساب را بفرستید.\nمثال: کارت ملت شخصی / حساب جاری شرکت / صندوق نقد",
        reply_markup=cancel_keyboard(),
    )
    return BA_TITLE


async def ba_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if _is_cancel_text(text):
        return await ba_cancel(update, context)
    if len(text) < 2:
        await update.effective_message.reply_text("عنوان خیلی کوتاه است.")
        return BA_TITLE
    context.user_data["ba"]["title"] = text
    await update.effective_message.reply_text(
        "نوع حساب را انتخاب کنید:", reply_markup=_type_keyboard()
    )
    return BA_TYPE


async def ba_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "bacancel":
        return await ba_cancel(update, context)
    key = query.data.split(":", 1)[1]
    context.user_data["ba"]["account_type"] = key
    if key in ("cash", "wallet"):
        context.user_data["ba"]["bank_id"] = None
        context.user_data["ba"]["bank_name"] = "—"
        await query.edit_message_text("موجودی اولیه را به تومان بفرستید (یا 0):")
        return BA_OPENING

    db = get_db(context)
    banks = await db.list_banks(update.effective_user.id)
    await query.edit_message_text("بانک را انتخاب کنید:", reply_markup=_banks_keyboard(banks))
    return BA_BANK


async def ba_bank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "bacancel":
        return await ba_cancel(update, context)
    bank_id = int(query.data.split(":")[1])
    db = get_db(context)
    if bank_id == 0:
        context.user_data["ba"]["bank_id"] = None
        context.user_data["ba"]["bank_name"] = "—"
    else:
        bank = await db.get_bank(bank_id)
        context.user_data["ba"]["bank_id"] = bank.id
        context.user_data["ba"]["bank_name"] = bank.name
    await query.edit_message_text(
        "شماره کارت ۱۶ رقمی را بفرستید.\nاگر ندارید /skip بزنید."
    )
    return BA_CARD


async def ba_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if _is_cancel_text(text):
        return await ba_cancel(update, context)
    if text == "/skip":
        context.user_data["ba"]["card_number"] = ""
    else:
        ok, digits, err = validate_card_number(text)
        if not ok:
            await update.effective_message.reply_text(err)
            return BA_CARD
        context.user_data["ba"]["card_number"] = digits
        # Auto-detect bank from BIN if not set
        if digits and not context.user_data["ba"].get("bank_id"):
            code = guess_bank_from_card(digits)
            if code:
                db = get_db(context)
                bank = await db.get_bank_by_code(code, update.effective_user.id)
                if bank:
                    context.user_data["ba"]["bank_id"] = bank.id
                    context.user_data["ba"]["bank_name"] = bank.name
    await update.effective_message.reply_text(
        "شماره حساب را بفرستید.\nاگر ندارید /skip بزنید."
    )
    return BA_ACCOUNT_NO


async def ba_account_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if _is_cancel_text(text):
        return await ba_cancel(update, context)
    if text == "/skip":
        context.user_data["ba"]["account_number"] = ""
    else:
        ok, digits, err = validate_account_number(text)
        if not ok:
            await update.effective_message.reply_text(err)
            return BA_ACCOUNT_NO
        context.user_data["ba"]["account_number"] = digits
    await update.effective_message.reply_text(
        "شماره شبا را بفرستید (IR...).\nاگر ندارید /skip بزنید."
    )
    return BA_SHEBA


async def ba_sheba(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if _is_cancel_text(text):
        return await ba_cancel(update, context)
    if text == "/skip":
        context.user_data["ba"]["sheba"] = ""
    else:
        ok, sheba, err = validate_sheba(text)
        if not ok:
            await update.effective_message.reply_text(err)
            return BA_SHEBA
        context.user_data["ba"]["sheba"] = sheba
    await update.effective_message.reply_text(
        "موجودی اولیه را به تومان بفرستید.\nمثال: 1500000 یا 0"
    )
    return BA_OPENING


async def ba_opening(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text or "").strip()
    if _is_cancel_text(text):
        return await ba_cancel(update, context)
    if text in ("0", "۰"):
        amount = 0
    else:
        amount = parse_manual_amount(text)
        if amount is None:
            await update.effective_message.reply_text("مبلغ نامعتبر است.")
            return BA_OPENING
    context.user_data["ba"]["opening_balance"] = amount
    preview = _draft_preview(context.user_data["ba"])
    await update.effective_message.reply_text(preview, reply_markup=_confirm_keyboard())
    return BA_CONFIRM


async def ba_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "bacancel":
        return await ba_cancel(update, context)
    data = context.user_data.get("ba") or {}
    db = get_db(context)
    account = await db.create_bank_account(
        user_id=update.effective_user.id,
        title=data["title"],
        account_type=data.get("account_type", "card"),
        bank_id=data.get("bank_id"),
        account_number=data.get("account_number", ""),
        card_number=data.get("card_number", ""),
        sheba=data.get("sheba", ""),
        opening_balance=int(data.get("opening_balance") or 0),
    )
    bal = await db.account_balance(account.id, update.effective_user.id)
    context.user_data.pop("ba", None)
    await query.edit_message_text(
        "✅ حساب با موفقیت ثبت شد.\n\n"
        f"{account.display_name}\n"
        f"کارت: {mask_card(account.card_number)}\n"
        f"حساب: {mask_account(account.account_number)}\n"
        f"شبا: {format_sheba(account.sheba)}\n"
        f"موجودی: {format_money(bal)}"
    )
    await query.message.reply_text("منوی اصلی:", reply_markup=main_keyboard())
    return ConversationHandler.END


async def ba_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("ba", None)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("انصراف داده شد.")
        except Exception:  # noqa: BLE001
            pass
        await update.callback_query.message.reply_text(
            "منوی اصلی:", reply_markup=main_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            "انصراف داده شد.", reply_markup=main_keyboard()
        )
    return ConversationHandler.END
