"""Simple always-on message router (no ConversationHandler stuck states)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers import banking, manual, receipt, reports, start
from bot.handlers.keyboards import main_keyboard
from bot.textnorm import normalize_text

logger = logging.getLogger("bot.router")

# Flow names stored in context.user_data["flow"]
FLOW_MANUAL_AMOUNT = "manual_amount"
FLOW_MANUAL_CATEGORY = "manual_category"
FLOW_MANUAL_DESC = "manual_desc"
FLOW_MANUAL_ACCOUNT = "manual_account"
FLOW_NEW_ACCOUNT = "new_account"
FLOW_RECEIPT_WAIT = "receipt_wait"
FLOW_RECEIPT_CONFIRM = "receipt_confirm"
FLOW_RECEIPT_CATEGORY = "receipt_category"
FLOW_RECEIPT_EDIT_AMOUNT = "receipt_edit_amount"
FLOW_BA_TITLE = "ba_title"
FLOW_BA_TYPE = "ba_type"
FLOW_BA_BANK = "ba_bank"
FLOW_BA_CARD = "ba_card"
FLOW_BA_ACCOUNT_NO = "ba_account_no"
FLOW_BA_SHEBA = "ba_sheba"
FLOW_BA_OPENING = "ba_opening"
FLOW_BA_CONFIRM = "ba_confirm"

# Map legacy ConversationHandler ints → flow names (handlers still return ints)
_MANUAL_STATE = {
    manual.ASK_AMOUNT: FLOW_MANUAL_AMOUNT,
    manual.ASK_CATEGORY: FLOW_MANUAL_CATEGORY,
    manual.ASK_DESC: FLOW_MANUAL_DESC,
    manual.ASK_ACCOUNT: FLOW_MANUAL_ACCOUNT,
    manual.ASK_NEW_ACCOUNT: FLOW_NEW_ACCOUNT,
}
_RECEIPT_STATE = {
    receipt.WAIT_RECEIPT: FLOW_RECEIPT_WAIT,
    receipt.CONFIRM: FLOW_RECEIPT_CONFIRM,
    receipt.PICK_CATEGORY: FLOW_RECEIPT_CATEGORY,
    receipt.EDIT_AMOUNT: FLOW_RECEIPT_EDIT_AMOUNT,
}
_BA_STATE = {
    banking.BA_TITLE: FLOW_BA_TITLE,
    banking.BA_TYPE: FLOW_BA_TYPE,
    banking.BA_BANK: FLOW_BA_BANK,
    banking.BA_CARD: FLOW_BA_CARD,
    banking.BA_ACCOUNT_NO: FLOW_BA_ACCOUNT_NO,
    banking.BA_SHEBA: FLOW_BA_SHEBA,
    banking.BA_OPENING: FLOW_BA_OPENING,
    banking.BA_CONFIRM: FLOW_BA_CONFIRM,
}

_END = None  # unused; ConversationHandler.END used via import inside _apply_result


def _apply_result(context: ContextTypes.DEFAULT_TYPE, result, mapping: dict) -> None:
    """Update flow from a legacy handler return value."""
    from telegram.ext import ConversationHandler

    if result is None:
        return
    if result == ConversationHandler.END:
        context.user_data.pop("flow", None)
        return
    flow = mapping.get(result)
    if flow:
        context.user_data["flow"] = flow
    else:
        context.user_data.pop("flow", None)


def _clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("flow", None)


def _is_cancel(text: str) -> bool:
    t = text.strip()
    return t == "/cancel" or normalize_text(t) == normalize_text("❌ انصراف")


def _menu_action(norm: str) -> str | None:
    table = {
        normalize_text("➕ واریز دستی"): "deposit",
        normalize_text("➖ برداشت دستی"): "withdraw",
        normalize_text("📷 ثبت با رسید"): "receipt",
        normalize_text("📊 گزارش ماه"): "report",
        normalize_text("📋 آخرین تراکنش‌ها"): "list",
        normalize_text("📋 آخرین تراکنشها"): "list",
        normalize_text("🏷 دسته‌ها"): "categories",
        normalize_text("🏷 دستهها"): "categories",
        normalize_text("🏦 حساب‌ها و بانک‌ها"): "accounts",
        normalize_text("🏦 حسابها و بانکها"): "accounts",
        normalize_text("🏦 حساب‌ها"): "accounts",
        normalize_text("🏦 حسابها"): "accounts",
        normalize_text("❓ راهنما"): "help",
    }
    return table.get(norm)


async def _run_menu(action: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if action == "deposit":
        result = await manual.deposit_entry(update, context)
        _apply_result(context, result, _MANUAL_STATE)
    elif action == "withdraw":
        result = await manual.withdraw_entry(update, context)
        _apply_result(context, result, _MANUAL_STATE)
    elif action == "receipt":
        result = await receipt.receipt_entry(update, context)
        _apply_result(context, result, _RECEIPT_STATE)
    elif action == "report":
        await reports.report_button(update, context)
    elif action == "list":
        await manual.list_transactions(update, context)
    elif action == "categories":
        await manual.categories_list(update, context)
    elif action == "accounts":
        await banking.banking_menu(update, context)
    elif action == "help":
        await start.help_cmd(update, context)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("PING user=%s", update.effective_user.id if update.effective_user else None)
    await update.effective_message.reply_text(
        "pong ✅ ربات آنلاین است.\n/start را بزنید.",
        reply_markup=main_keyboard(),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await start.start(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await start.help_cmd(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await manual.cancel(update, context)
    _clear_flow(context)


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    result = await manual.deposit_entry(update, context)
    _apply_result(context, result, _MANUAL_STATE)


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    result = await manual.withdraw_entry(update, context)
    _apply_result(context, result, _MANUAL_STATE)


async def cmd_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    result = await receipt.receipt_entry(update, context)
    _apply_result(context, result, _RECEIPT_STATE)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await reports.report_entry(update, context)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await manual.list_transactions(update, context)


async def cmd_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await banking.banking_menu(update, context)


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await manual.categories_list(update, context)


async def cmd_newbankaccount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    result = await banking.new_bank_account_entry(update, context)
    _apply_result(context, result, _BA_STATE)


async def cmd_newaccount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    result = await manual.new_account_entry(update, context)
    _apply_result(context, result, _MANUAL_STATE)


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await manual.delete_command(update, context)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any photo is treated as a receipt."""
    flow = context.user_data.get("flow")
    if flow not in (None, FLOW_RECEIPT_WAIT):
        # Interrupt other flows — user sent a receipt photo
        context.user_data.clear()
    result = await receipt.receipt_photo(update, context)
    _apply_result(context, result, _RECEIPT_STATE)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every text message gets handled and answered."""
    message = update.effective_message
    text = message.text or ""
    norm = normalize_text(text)
    logger.info(
        "TEXT user=%s flow=%s text=%r",
        update.effective_user.id if update.effective_user else None,
        context.user_data.get("flow"),
        text[:80],
    )

    if _is_cancel(text):
        await manual.cancel(update, context)
        _clear_flow(context)
        return

    menu = _menu_action(norm)
    if menu:
        await _run_menu(menu, update, context)
        return

    flow = context.user_data.get("flow")

    try:
        if flow == FLOW_MANUAL_AMOUNT:
            result = await manual.manual_amount(update, context)
            _apply_result(context, result, _MANUAL_STATE)
            return
        if flow == FLOW_MANUAL_CATEGORY:
            result = await manual.prompt_pick_category(update, context)
            _apply_result(context, result, _MANUAL_STATE)
            return
        if flow == FLOW_MANUAL_DESC:
            result = await manual.manual_desc(update, context)
            _apply_result(context, result, _MANUAL_STATE)
            return
        if flow == FLOW_MANUAL_ACCOUNT:
            result = await manual.manual_account(update, context)
            _apply_result(context, result, _MANUAL_STATE)
            return
        if flow == FLOW_NEW_ACCOUNT:
            result = await manual.new_account_name(update, context)
            _apply_result(context, result, _MANUAL_STATE)
            return
        if flow == FLOW_RECEIPT_WAIT:
            result = await receipt.receipt_photo(update, context)
            _apply_result(context, result, _RECEIPT_STATE)
            return
        if flow in (FLOW_RECEIPT_CONFIRM, FLOW_RECEIPT_CATEGORY):
            result = await manual.prompt_pick_category(update, context)
            _apply_result(context, result, _RECEIPT_STATE)
            return
        if flow == FLOW_RECEIPT_EDIT_AMOUNT:
            result = await receipt.edit_amount_text(update, context)
            _apply_result(context, result, _RECEIPT_STATE)
            return
        if flow == FLOW_BA_TITLE:
            result = await banking.ba_title(update, context)
            _apply_result(context, result, _BA_STATE)
            return
        if flow == FLOW_BA_CARD:
            result = await banking.ba_card(update, context)
            _apply_result(context, result, _BA_STATE)
            return
        if flow == FLOW_BA_ACCOUNT_NO:
            result = await banking.ba_account_no(update, context)
            _apply_result(context, result, _BA_STATE)
            return
        if flow == FLOW_BA_SHEBA:
            result = await banking.ba_sheba(update, context)
            _apply_result(context, result, _BA_STATE)
            return
        if flow == FLOW_BA_OPENING:
            result = await banking.ba_opening(update, context)
            _apply_result(context, result, _BA_STATE)
            return
        if flow in (FLOW_BA_TYPE, FLOW_BA_BANK, FLOW_BA_CONFIRM):
            await message.reply_text(
                "لطفاً یکی از دکمه‌های روی پیام را لمس کنید، یا /start بزنید.",
                reply_markup=main_keyboard(),
            )
            return
    except Exception:
        logger.exception("flow handler failed flow=%s", flow)
        _clear_flow(context)
        await message.reply_text(
            "خطایی رخ داد. /start را بزنید.",
            reply_markup=main_keyboard(),
        )
        return

    await message.reply_text(
        "متوجه نشدم.\nاز دکمه‌های پایین استفاده کنید یا /start /ping بزنید.",
        reply_markup=main_keyboard(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all inline button presses."""
    query = update.callback_query
    data = (query.data or "") if query else ""
    flow = context.user_data.get("flow")
    logger.info("CALLBACK data=%r flow=%s", data, flow)

    try:
        if data.startswith("del:"):
            await manual.delete_callback(update, context)
            return

        if data.startswith("month:"):
            await reports.report_month_callback(update, context)
            return

        if data.startswith("batype:"):
            result = await banking.ba_type_callback(update, context)
            _apply_result(context, result, _BA_STATE)
            return

        if data.startswith("babank:"):
            result = await banking.ba_bank_callback(update, context)
            _apply_result(context, result, _BA_STATE)
            return

        if data == "baok":
            result = await banking.ba_confirm_callback(update, context)
            _apply_result(context, result, _BA_STATE)
            return

        if data == "bacancel":
            result = await banking.ba_cancel(update, context)
            _apply_result(context, result, _BA_STATE)
            return

        if (
            data.startswith("cat:")
            or data.startswith("rtype:")
            or data
            in ("rcancel", "rok", "redit_amount", "rswitch", "rcat")
        ):
            if flow == FLOW_MANUAL_CATEGORY:
                result = await manual.manual_category_callback(update, context)
                _apply_result(context, result, _MANUAL_STATE)
            else:
                result = await receipt.receipt_callbacks(update, context)
                _apply_result(context, result, _RECEIPT_STATE)
            return

    except Exception:
        logger.exception("callback failed data=%r", data)
        try:
            await query.answer()
            await context.bot.send_message(
                update.effective_chat.id,
                "خطای داخلی. /start را بزنید.",
                reply_markup=main_keyboard(),
            )
        except Exception:  # noqa: BLE001
            pass
        _clear_flow(context)
        return

    try:
        await query.answer()
        await query.edit_message_text("این دکمه دیگر معتبر نیست. /start را بزنید.")
    except Exception:  # noqa: BLE001
        pass
    _clear_flow(context)
