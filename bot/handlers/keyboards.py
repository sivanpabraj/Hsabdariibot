"""Shared keyboards and formatting helpers for Telegram UI."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.db.database import Transaction
from bot.services.receipt_parser import format_jalali, format_money, month_title

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
    return (
        "📒 ربات حسابداری شخصی\n\n"
        "با این ربات درآمد و هزینه‌های خودتان را ثبت و ماهانه جمع‌بندی کنید.\n\n"
        "امکانات:\n"
        "• واریز و برداشت دستی\n"
        "• خواندن عکس/متن رسید بانکی با هوش مصنوعی\n"
        "• چند حساب جدا\n"
        "• گزارش ماهانه شمسی\n\n"
        "دستورهای سریع:\n"
        "/deposit مبلغ [توضیح]\n"
        "/withdraw مبلغ [توضیح]\n"
        "/report\n"
        "/report 1404 4\n"
        "/list\n"
        "/accounts\n"
        "/newaccount نام\n"
        "/delete شماره\n\n"
        "مبلغ را به تومان وارد کنید.\n"
        "مثال: 150000 یا 1.5 میلیون\n"
        "برای ریال بنویسید: 1500000 ریال"
    )
