"""Telegram personal accounting bot — reliable handlers."""

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
from telegram.ext.filters import MessageFilter

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
from bot.textnorm import normalize_text

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")


async def post_init(app: Application) -> None:
    # Clear any leftover webhook so long-polling receives updates.
    await app.bot.delete_webhook(drop_pending_updates=True)
    db = Database()
    await db.connect()
    app.bot_data["db"] = db
    me = await app.bot.get_me()
    logger.info("Ready @%s (webhook cleared, polling)", me.username)


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
                f"خطای داخلی: {type(err).__name__}\n/start یا /ping را بزنید.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to send error message")


class TextIs(MessageFilter):
    """Match reply-keyboard labels after Persian/Telegram text normalization."""

    def __init__(self, *options: str):
        super().__init__()
        self.options = {normalize_text(o) for o in options}

    def filter(self, message) -> bool:
        return normalize_text(message.text) in self.options


BTN_DEPOSIT = TextIs("➕ واریز دستی")
BTN_WITHDRAW = TextIs("➖ برداشت دستی")
BTN_RECEIPT = TextIs("📷 ثبت با رسید")
BTN_REPORT = TextIs("📊 گزارش ماه")
BTN_LIST = TextIs("📋 آخرین تراکنش‌ها", "📋 آخرین تراکنشها")
BTN_CATS = TextIs("🏷 دسته‌ها", "🏷 دستهها")
BTN_ACCOUNTS = TextIs(
    "🏦 حساب‌ها و بانک‌ها",
    "🏦 حساب‌ها",
    "🏦 حسابها",
    "🏦 حسابها و بانکها",
    "🏦 حساب‌ها و بانکها",
)
BTN_HELP = TextIs("❓ راهنما")
BTN_CANCEL = TextIs("❌ انصراف")

# Any main-menu label — used inside conversation states so buttons are not
# swallowed by "please send amount/text" catch-all handlers.
BTN_MENU = (
    BTN_DEPOSIT
    | BTN_WITHDRAW
    | BTN_RECEIPT
    | BTN_REPORT
    | BTN_LIST
    | BTN_CATS
    | BTN_ACCOUNTS
    | BTN_HELP
)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("PING from %s", update.effective_user.id if update.effective_user else None)
    await update.effective_message.reply_text("pong ✅ ربات آنلاین است. /start را بزنید.")


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("UNKNOWN %r", update.effective_message.text if update.effective_message else None)
    await update.effective_message.reply_text(
        "متوجه نشدم.\nاز دکمه‌های پایین استفاده کنید یا /start /ping بزنید."
    )


def _fallbacks():
    """Always allow leaving a conversation via /start, cancel, or menu buttons."""
    return [
        CommandHandler("start", manual.cancel_to_start),
        CommandHandler("cancel", manual.cancel),
        MessageHandler(BTN_CANCEL, manual.cancel),
        MessageHandler(BTN_MENU, manual.cancel_to_start),
    ]


def _text_states(*extra_handlers):
    """State handlers: menu/cancel first, then conversation-specific handlers."""
    return [
        MessageHandler(BTN_CANCEL, manual.cancel),
        MessageHandler(BTN_MENU, manual.cancel_to_start),
        *extra_handlers,
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
            ASK_AMOUNT: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_amount),
            ),
            ASK_CATEGORY: [
                CallbackQueryHandler(manual.manual_category_callback, pattern=r"^(cat:|rcancel$)"),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            ASK_DESC: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_desc),
                CommandHandler("skip", manual.manual_desc),
            ),
            ASK_ACCOUNT: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_account),
            ),
        },
        fallbacks=fallbacks,
        allow_reentry=True,
        name="manual_conv",
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
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.receipt_photo),
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    receipt.receipt_callbacks,
                    pattern=r"^(rok|redit_amount|rswitch|rcancel|rcat|rtype:|cat:)",
                ),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            PICK_CATEGORY: [
                CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^(cat:|rcancel$)"),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category),
            ],
            EDIT_AMOUNT: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.edit_amount_text),
            ),
        },
        fallbacks=fallbacks
        + [CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^rcancel$")],
        allow_reentry=True,
        name="receipt_conv",
    )

    account_conv = ConversationHandler(
        entry_points=[CommandHandler("newaccount", manual.new_account_entry)],
        states={
            ASK_NEW_ACCOUNT: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.new_account_name),
            ),
        },
        fallbacks=fallbacks,
        allow_reentry=True,
        name="account_conv",
    )

    bank_account_conv = ConversationHandler(
        entry_points=[
            CommandHandler("newbankaccount", banking.new_bank_account_entry),
            CommandHandler("addaccount", banking.new_bank_account_entry),
        ],
        states={
            BA_TITLE: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_title),
            ),
            BA_TYPE: [
                CallbackQueryHandler(banking.ba_type_callback, pattern=r"^(batype:|bacancel$)"),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
            ],
            BA_BANK: [
                CallbackQueryHandler(banking.ba_bank_callback, pattern=r"^(babank:|bacancel$)"),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
            ],
            BA_CARD: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_card),
                CommandHandler("skip", banking.ba_card),
            ),
            BA_ACCOUNT_NO: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_account_no),
                CommandHandler("skip", banking.ba_account_no),
            ),
            BA_SHEBA: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_sheba),
                CommandHandler("skip", banking.ba_sheba),
            ),
            BA_OPENING: _text_states(
                MessageHandler(filters.TEXT & ~filters.COMMAND, banking.ba_opening),
            ),
            BA_CONFIRM: [
                CallbackQueryHandler(banking.ba_confirm_callback, pattern=r"^(baok|bacancel$)"),
                MessageHandler(BTN_CANCEL, manual.cancel),
                MessageHandler(BTN_MENU, manual.cancel_to_start),
            ],
        },
        fallbacks=fallbacks + [CallbackQueryHandler(banking.ba_cancel, pattern=r"^bacancel$")],
        allow_reentry=True,
        name="bank_account_conv",
    )

    # Highest priority: always answer /ping even if something else is stuck.
    app.add_handler(CommandHandler("ping", ping), group=-1)

    # Conversations FIRST so /start in fallbacks can end them.
    # (A top-level /start registered before conversations never clears CH state.)
    app.add_handler(manual_conv)
    app.add_handler(receipt_conv)
    app.add_handler(account_conv)
    app.add_handler(bank_account_conv)

    # Core commands / menu when NOT inside a conversation
    app.add_handler(CommandHandler("start", start.start))
    app.add_handler(CommandHandler("help", start.help_cmd))
    app.add_handler(MessageHandler(BTN_HELP, start.help_cmd))

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
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
