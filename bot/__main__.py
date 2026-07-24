"""Telegram personal accounting bot — simplified reliable handlers."""

from __future__ import annotations

import logging
import traceback

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN
from bot.db.database import Database
from bot.handlers import banking, manual, receipt, reports, start
from bot.handlers.banking import (
    BA_ACCOUNT_NO,
    BA_BANK,
    BA_CARD,
    BA_CONFIRM,
    BA_OPENING,
    BA_SHEBA,
    BA_TITLE,
    BA_TYPE,
)
from bot.handlers.manual import ASK_ACCOUNT, ASK_AMOUNT, ASK_CATEGORY, ASK_DESC, ASK_NEW_ACCOUNT
from bot.handlers.receipt import CONFIRM, EDIT_AMOUNT, PICK_CATEGORY, WAIT_RECEIPT

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")


async def post_init(app: Application) -> None:
    db = Database()
    await db.connect()
    app.bot_data["db"] = db
    me = await app.bot.get_me()
    logger.info("Ready @%s", me.username)


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
                f"خطای داخلی: {type(err).__name__}\n/start را بزنید.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send error message")


def _norm(text: str | None) -> str:
    """Normalize Persian text for button matching (remove ZWNJ etc.)."""
    if not text:
        return ""
    return (
        text.replace("\u200c", "")
        .replace("\u200f", "")
        .replace("\u200e", "")
        .strip()
    )


from telegram.ext.filters import MessageFilter


class TextIs(MessageFilter):
    def __init__(self, *options: str):
        super().__init__()
        self.options = {_norm(o) for o in options}

    def filter(self, message) -> bool:
        return _norm(message.text) in self.options


BTN_DEPOSIT = TextIs("➕ واریز دستی")
BTN_WITHDRAW = TextIs("➖ برداشت دستی")
BTN_RECEIPT = TextIs("📷 ثبت با رسید")
BTN_REPORT = TextIs("📊 گزارش ماه")
BTN_LIST = TextIs("📋 آخرین تراکنش‌ها", "📋 آخرین تراکنشها")
BTN_CATS = TextIs("🏷 دسته‌ها", "🏷 دستهها")
BTN_ACCOUNTS = TextIs("🏦 حساب‌ها و بانک‌ها", "🏦 حساب‌ها", "🏦 حسابها", "🏦 حسابها و بانکها", "🏦 حساب‌ها و بانکها")
BTN_HELP = TextIs("❓ راهنما")
BTN_CANCEL = TextIs("❌ انصراف")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("PING from %s", update.effective_user.id if update.effective_user else None)
    await update.effective_message.reply_text("pong ✅ ربات آنلاین است. /start را بزنید.")


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("UNKNOWN %r", update.effective_message.text if update.effective_message else None)
    await update.effective_message.reply_text(
        "متوجه نشدم.\n/start یا /ping را بزنید."
    )


def _fallbacks():
    return [
        CommandHandler("start", manual.cancel_to_start),
        CommandHandler("cancel", manual.cancel),
        MessageHandler(BTN_CANCEL, manual.cancel),
        MessageHandler(
            BTN_DEPOSIT | BTN_WITHDRAW | BTN_RECEIPT | BTN_REPORT | BTN_LIST | BTN_CATS | BTN_ACCOUNTS | BTN_HELP,
            manual.cancel_to_start,
        ),
    ]


def build_app() -> Application:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing in .env")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    fallbacks = _fallbacks()

    manual_conv = ConversationHandler(
        entry_points=[
            MessageHandler(BTN_DEPOSIT, manual.deposit_entry),
            MessageHandler(BTN_WITHDRAW, manual.withdraw_entry),
            CommandHandler("deposit", manual.deposit_entry),
            CommandHandler("withdraw", manual.withdraw_entry),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_amount)],
            ASK_CATEGORY: [
                CallbackQueryHandler(manual.manual_category_callback, pattern=r"^(cat:|rcancel$)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            ASK_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_desc),
                CommandHandler("skip", manual.manual_desc),
            ],
            ASK_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_account)],
        },
        fallbacks=fallbacks,
        allow_reentry=True,
    )

    receipt_conv = ConversationHandler(
        entry_points=[
            MessageHandler(BTN_RECEIPT, receipt.receipt_entry),
            CommandHandler("receipt", receipt.receipt_entry),
            MessageHandler(filters.PHOTO, receipt.receipt_photo),
        ],
        states={
            WAIT_RECEIPT: [
                MessageHandler(filters.PHOTO, receipt.receipt_photo),
                MessageHandler(filters.Document.IMAGE, receipt.receipt_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.receipt_photo),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    receipt.receipt_callbacks,
                    pattern=r"^(rok|redit_amount|rswitch|rcancel|rcat|rtype:|cat:)",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            PICK_CATEGORY: [
                CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^(cat:|rcancel$)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.edit_amount_text)],
        },
        fallbacks=fallbacks
        + [CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^rcancel$")],
        allow_reentry=True,
    )

    account_conv = ConversationHandler(
        entry_points=[CommandHandler("newaccount", manual.new_account_entry)],
        states={
            ASK_NEW_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.new_account_name)
            ],
        },
        fallbacks=fallbacks,
        allow_reentry=True,
    )

    bank_account_conv = ConversationHandler(
        entry_points=[
            CommandHandler("newbankaccount", banking.new_bank_account_entry),
            CommandHandler("addaccount", banking.new_bank_account_entry),
        ],
        states={
            BA_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_title)],
            BA_TYPE: [
                CallbackQueryHandler(banking.ba_type_callback, pattern=r"^(batype:|bacancel$)")
            ],
            BA_BANK: [
                CallbackQueryHandler(banking.ba_bank_callback, pattern=r"^(babank:|bacancel$)")
            ],
            BA_CARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_card),
                CommandHandler("skip", banking.ba_card),
            ],
            BA_ACCOUNT_NO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_account_no),
                CommandHandler("skip", banking.ba_account_no),
            ],
            BA_SHEBA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_sheba),
                CommandHandler("skip", banking.ba_sheba),
            ],
            BA_OPENING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_opening)
            ],
            BA_CONFIRM: [
                CallbackQueryHandler(banking.ba_confirm_callback, pattern=r"^(baok|bacancel$)")
            ],
        },
        fallbacks=fallbacks + [CallbackQueryHandler(banking.ba_cancel, pattern=r"^bacancel$")],
        allow_reentry=True,
    )

    # Diagnostic
    app.add_handler(CommandHandler("ping", ping))

    # Core commands FIRST
    app.add_handler(CommandHandler("start", start.start))
    app.add_handler(CommandHandler("help", start.help_cmd))
    app.add_handler(MessageHandler(BTN_HELP, start.help_cmd))

    app.add_handler(manual_conv)
    app.add_handler(receipt_conv)
    app.add_handler(account_conv)
    app.add_handler(bank_account_conv)

    app.add_handler(CommandHandler("list", manual.list_transactions))
    app.add_handler(MessageHandler(BTN_LIST, manual.list_transactions))
    app.add_handler(CommandHandler("accounts", banking.banking_menu))
    app.add_handler(MessageHandler(BTN_ACCOUNTS, banking.banking_menu))
    app.add_handler(CommandHandler("categories", manual.categories_list))
    app.add_handler(MessageHandler(BTN_CATS, manual.categories_list))
    app.add_handler(CommandHandler("delete", manual.delete_command))
    app.add_handler(CallbackQueryHandler(manual.delete_callback, pattern=r"^del:\d+$"))

    app.add_handler(CommandHandler("report", reports.report_entry))
    app.add_handler(MessageHandler(BTN_REPORT, reports.report_button))
    app.add_handler(CallbackQueryHandler(reports.report_month_callback, pattern=r"^month:"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    app.add_error_handler(on_error)
    return app


def main() -> None:
    app = build_app()
    logger.info("Polling start")
    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
