"""Shared keyboards and formatting helpers for Telegram UI."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.db.database import Transaction
from bot.services.receipt_parser import MONTH_NAMES, format_jalali, format_money, month_title

TYPE_LABEL = {"deposit": "واریز", "withdraw": "برداشت"}


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["➕ واریز دستی", "➖ برداشت دستی"],
            ["📷 ثبت با رسید", "📊 گزارش ماه"],
            ["📋 آخرین تراکنش‌ها", "🏦 حساب‌ها"],
            ["❓ راهنما"],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True)


def type_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ واریز", callback_data="rtype:deposit"),
                InlineKeyboardButton("✅ برداشت", callback_data="rtype:withdraw"),
            ],
            [InlineKeyboardButton("❌ انصراف", callback_data="rcancel")],
        ]
    )


def receipt_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ ثبت کن", callback_data="rok"),
                InlineKeyboardButton("✏️ اصلاح مبلغ", callback_data="redit_amount"),
            ],
            [
                InlineKeyboardButton("🔄 عوض کردن نوع", callback_data="rswitch"),
                InlineKeyboardButton("❌ انصراف", callback_data="rcancel"),
            ],
        ]
    )


def months_keyboard(months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    rows = []
    for y, m in months:
        rows.append(
            [
                InlineKeyboardButton(
                    month_title(y, m), callback_data=f"month:{y}:{m}"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton("📅 ماه جاری", callback_data="month:current")]
    )
    return InlineKeyboardMarkup(rows)


def delete_tx_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑 حذف", callback_data=f"del:{tx_id}")]]
    )


def format_tx_line(tx: Transaction) -> str:
    kind = TYPE_LABEL.get(tx.type, tx.type)
    emoji = "🟢" if tx.type == "deposit" else "🔴"
    date_str = format_jalali(
        jy=tx.jalali_year,
        jm=tx.jalali_month,
        jd=int(tx.transaction_date.split("-")[2]) if tx.transaction_date else None,
    )
    desc = f" — {tx.description}" if tx.description else ""
    src = "📷" if tx.source == "receipt" else "✍️"
    return (
        f"{emoji} #{tx.id} {kind} {format_money(tx.amount)}\n"
        f"   {src} {tx.account_name} | {date_str}{desc}"
    )


def format_monthly_report(summary: dict) -> str:
    y, m = summary["year"], summary["month"]
    lines = [
        f"📊 گزارش {month_title(y, m)}",
        "",
        f"🟢 واریز: {format_money(summary['deposit'])} ({summary['deposit_count']} مورد)",
        f"🔴 برداشت: {format_money(summary['withdraw'])} ({summary['withdraw_count']} مورد)",
        f"⚖️ مانده ماه: {format_money(summary['balance'])}",
    ]
    if summary.get("accounts"):
        lines.append("")
        lines.append("🏦 به تفکیک حساب:")
        for acc in summary["accounts"]:
            bal = acc["deposit"] - acc["withdraw"]
            lines.append(
                f"• {acc['name']}: واریز {format_money(acc['deposit'])} | "
                f"برداشت {format_money(acc['withdraw'])} | مانده {format_money(bal)}"
            )
    return "\n".join(lines)


def help_text() -> str:
    months = "، ".join(MONTH_NAMES[i] for i in range(1, 13))
    return (
        "🤖 ربات حساب واریز و برداشت\n\n"
        "چه کارهایی می‌توانید بکنید:\n"
        "• واریز/برداشت دستی با دکمه یا دستور\n"
        "• ارسال عکس رسید بانکی → خواندن خودکار و ثبت\n"
        "• ارسال متن رسید → پارس و ثبت\n"
        "• گزارش ماهانه برای هر حساب\n\n"
        "دستورها:\n"
        "/deposit مبلغ [توضیح] — واریز سریع\n"
        "/withdraw مبلغ [توضیح] — برداشت سریع\n"
        "/report — گزارش ماه جاری\n"
        "/report 1403 4 — گزارش ماه مشخص\n"
        "/list — آخرین تراکنش‌ها\n"
        "/accounts — لیست حساب‌ها\n"
        "/newaccount نام — ساخت حساب جدید\n"
        "/delete شماره — حذف تراکنش\n\n"
        "مبلغ‌ها به تومان وارد کنید (مثلاً 150000 یا 150٬000).\n"
        "اگر بنویسید ریال، همان ریال ذخیره می‌شود.\n\n"
        f"ماه‌های شمسی: {months}"
    )
