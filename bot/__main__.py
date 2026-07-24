"""Telegram finance bot entrypoint."""

from __future__ import annotations

import logging
import sys

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN
from bot.db.database import Database
from bot.handlers import manual, receipt, reports, start
from bot.handlers.manual import ASK_ACCOUNT, ASK_AMOUNT, ASK_DESC, ASK_NEW_ACCOUNT
from bot.handlers.receipt import CONFIRM, EDIT_AMOUNT, WAIT_RECEIPT

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

    manual_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^➕ واریز دستی$"), manual.deposit_entry),
            MessageHandler(filters.Regex(r"^➖ برداشت دستی$"), manual.withdraw_entry),
            CommandHandler("deposit", manual.deposit_entry),
            CommandHandler("withdraw", manual.withdraw_entry),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_amount)],
            ASK_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_desc),
                CommandHandler("skip", manual.manual_desc),
            ],
            ASK_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual.manual_account)],
        },
        fallbacks=[
            CommandHandler("cancel", manual.cancel),
            MessageHandler(filters.Regex(r"^❌ انصراف$"), manual.cancel),
        ],
        allow_reentry=True,
    )

    # Override: /deposit and /withdraw with args should use quick path.
    # ConversationHandler above catches bare commands; add separate quick handlers
    # that only fire when args exist via MessageHandler is hard — we handle in cmd_*
    # by replacing entry points with callbacks that check args.

    receipt_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^📷 ثبت با رسید$"), receipt.receipt_entry),
            CommandHandler("receipt", receipt.receipt_entry),
            # Also accept a photo sent directly as a receipt start
            MessageHandler(filters.PHOTO, receipt.receipt_photo),
        ],
        states={
            WAIT_RECEIPT: [
                MessageHandler(filters.PHOTO, receipt.receipt_photo),
                MessageHandler(filters.Document.IMAGE, receipt.receipt_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.receipt_photo),
            ],
            CONFIRM: [CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^(rok|redit_amount|rswitch|rcancel|rtype:)")],
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receipt.edit_amount_text)],
        },
        fallbacks=[
            CommandHandler("cancel", manual.cancel),
            MessageHandler(filters.Regex(r"^❌ انصراف$"), manual.cancel),
            CallbackQueryHandler(receipt.receipt_callbacks, pattern=r"^rcancel$"),
        ],
        allow_reentry=True,
    )

    account_conv = ConversationHandler(
        entry_points=[CommandHandler("newaccount", manual.new_account_entry)],
        states={
            ASK_NEW_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual.new_account_name)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", manual.cancel),
            MessageHandler(filters.Regex(r"^❌ انصراف$"), manual.cancel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start.start))
    app.add_handler(CommandHandler("help", start.help_cmd))
    app.add_handler(MessageHandler(filters.Regex(r"^❓ راهنما$"), start.help_cmd))

    app.add_handler(manual_conv)
    app.add_handler(receipt_conv)
    app.add_handler(account_conv)

    # Quick commands with optional args
    app.add_handler(CommandHandler("list", manual.list_transactions))
    app.add_handler(MessageHandler(filters.Regex(r"^📋 آخرین تراکنش‌ها$"), manual.list_transactions))
    app.add_handler(CommandHandler("accounts", manual.accounts_list))
    app.add_handler(MessageHandler(filters.Regex(r"^🏦 حساب‌ها$"), manual.accounts_list))
    app.add_handler(CommandHandler("delete", manual.delete_command))
    app.add_handler(CallbackQueryHandler(manual.delete_callback, pattern=r"^del:\d+$"))

    app.add_handler(CommandHandler("report", reports.report_entry))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 گزارش ماه$"), reports.report_button))
    app.add_handler(CallbackQueryHandler(reports.report_month_callback, pattern=r"^month:"))

    return app


def main() -> None:
    app = build_app()
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
