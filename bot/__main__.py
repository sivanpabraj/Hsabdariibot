"""Telegram finance bot entrypoint."""

from __future__ import annotations

import logging
import sys
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
from bot.handlers import manual, receipt, reports, start
from bot.handlers.manual import ASK_ACCOUNT, ASK_AMOUNT, ASK_CATEGORY, ASK_DESC, ASK_NEW_ACCOUNT
from bot.handlers.receipt import CONFIRM, EDIT_AMOUNT, PICK_CATEGORY, WAIT_RECEIPT

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(app: Application) -> None:
    db = Database()
    await db.connect()
    app.bot_data["db"] = db
    logger.info("Database ready")


async def post_shutdown(app: Application) -> None:
    db: Database | None = app.bot_data.get("db")
    if db:
        await db.close()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling update: %s", context.error)
    logger.error(traceback.format_exc())
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "خطایی رخ داد. /start را بزنید و دوباره تلاش کنید."
            )
        except Exception:  # noqa: BLE001
            pass


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "دستور را متوجه نشدم.\n"
        "از دکمه‌های پایین استفاده کنید یا /start بزنید."
    )


def _conv_fallbacks():
    return [
        CommandHandler("start", manual.cancel_to_start),
        CommandHandler("cancel", manual.cancel),
        MessageHandler(filters.Regex(r"^❌ انصراف$"), manual.cancel),
        MessageHandler(
            filters.Regex(
                r"^(➕ واریز دستی|➖ برداشت دستی|📷 ثبت با رسید|📊 گزارش ماه|"
                r"📋 آخرین تراکنش‌ها|🏷 دسته‌ها|🏦 حساب‌ها|❓ راهنما)$"
            ),
            manual.cancel_to_start,
        ),
    ]


def build_app() -> Application:
    if not BOT_TOKEN:
        print("خطا: BOT_TOKEN را در فایل .env تنظیم کنید.", file=sys.stderr)
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    fallbacks = _conv_fallbacks()

    manual_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^➕ واریز دستی$"), manual.deposit_entry),
            MessageHandler(filters.Regex(r"^➖ برداشت دستی$"), manual.withdraw_entry),
            CommandHandler("deposit", manual.deposit_entry),
            CommandHandler("withdraw", manual.withdraw_entry),
        ],
        states={
            ASK_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_amount)
            ],
            ASK_CATEGORY: [
                CallbackQueryHandler(
                    manual.manual_category_callback, pattern=r"^(cat:|rcancel$)"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category
                ),
            ],
            ASK_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_desc),
                CommandHandler("skip", manual.manual_desc),
            ],
            ASK_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_account)
            ],
        },
        fallbacks=fallbacks,
        allow_reentry=True,
    )

    receipt_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📷 ثبت با رسید$"), receipt.receipt_entry),
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
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category
                ),
            ],
            PICK_CATEGORY: [
                CallbackQueryHandler(
                    receipt.receipt_callbacks, pattern=r"^(cat:|rcancel$)"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, manual.prompt_pick_category
                ),
            ],
            EDIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.edit_amount_text)
            ],
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

    app.add_handler(CommandHandler("start", start.start))
    app.add_handler(CommandHandler("help", start.help_cmd))
    app.add_handler(MessageHandler(filters.Regex(r"^❓ راهنما$"), start.help_cmd))

    app.add_handler(manual_conv)
    app.add_handler(receipt_conv)
    app.add_handler(account_conv)

    app.add_handler(CommandHandler("list", manual.list_transactions))
    app.add_handler(
        MessageHandler(filters.Regex(r"^📋 آخرین تراکنش‌ها$"), manual.list_transactions)
    )
    app.add_handler(CommandHandler("accounts", manual.accounts_list))
    app.add_handler(MessageHandler(filters.Regex(r"^🏦 حساب‌ها$"), manual.accounts_list))
    app.add_handler(CommandHandler("categories", manual.categories_list))
    app.add_handler(MessageHandler(filters.Regex(r"^🏷 دسته‌ها$"), manual.categories_list))
    app.add_handler(CommandHandler("delete", manual.delete_command))
    app.add_handler(CallbackQueryHandler(manual.delete_callback, pattern=r"^del:\d+$"))

    app.add_handler(CommandHandler("report", reports.report_entry))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 گزارش ماه$"), reports.report_button))
    app.add_handler(CallbackQueryHandler(reports.report_month_callback, pattern=r"^month:"))

    # Always reply somehow
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))
    app.add_error_handler(on_error)

    return app


def main() -> None:
    """Run a classic long-polling bot against api.telegram.org (no local Bot API server)."""
    app = build_app()
    logger.info("Bot starting with simple polling (no webhook / no local Telegram server)...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
