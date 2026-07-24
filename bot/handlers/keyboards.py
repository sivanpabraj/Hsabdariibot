"""Shared keyboards and formatting helpers for Telegram UI."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.db.models import LedgerEntry
from bot.services.categories import CATEGORY_LABELS, categories_for, category_label
from bot.services.receipt_parser import format_jalali, format_money, month_title

TYPE_LABEL = {"deposit": "واریز", "withdraw": "برداشت"}


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["➕ واریز دستی", "➖ برداشت دستی"],
            ["📷 ثبت با رسید", "📊 گزارش ماه"],
            ["📋 آخرین تراکنش‌ها", "🏦 حساب‌ها و بانک‌ها"],
            ["🏷 دسته‌ها", "❓ راهنما"],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ انصراف"]], resize_keyboard=True)


def category_keyboard(tx_type: str) -> InlineKeyboardMarkup:
    cats = categories_for(tx_type)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label in cats:
        row.append(InlineKeyboardButton(label, callback_data=f"cat:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data="rcancel")])
    return InlineKeyboardMarkup(rows)


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
                InlineKeyboardButton("🏷 تغییر دسته", callback_data="rcat"),
                InlineKeyboardButton("🔄 عوض کردن نوع", callback_data="rswitch"),
            ],
            [InlineKeyboardButton("❌ انصراف", callback_data="rcancel")],
        ]
    )


def months_keyboard(months: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    rows = []
    for y, m in months:
        rows.append(
            [InlineKeyboardButton(month_title(y, m), callback_data=f"month:{y}:{m}")]
        )
    rows.append([InlineKeyboardButton("📅 ماه جاری", callback_data="month:current")])
    return InlineKeyboardMarkup(rows)


def format_tx_line(tx: LedgerEntry) -> str:
    kind = TYPE_LABEL.get(tx.type, tx.type)
    emoji = "🟢" if tx.type == "deposit" else "🔴"
    date_str = format_jalali(
        jy=tx.jalali_year,
        jm=tx.jalali_month,
        jd=int(tx.transaction_date.split("-")[2]) if tx.transaction_date else None,
    )
    cat = category_label(getattr(tx, "category", "") or "")
    desc = f" — {tx.description}" if tx.description else ""
    src = "📷" if tx.source == "receipt" else "✍️"
    return (
        f"{emoji} #{tx.id} {kind} {format_money(tx.amount)}\n"
        f"   🏷 {cat} | {src} {tx.account_name} | {date_str}{desc}"
    )


def format_monthly_report(summary: dict) -> str:
    y, m = summary["year"], summary["month"]
    lines = [
        f"📊 گزارش {month_title(y, m)}",
        "",
        f"🟢 واریز: {format_money(summary['deposit'])} ({summary['deposit_count']} مورد)",
        f"🔴 برداشت: {format_money(summary['withdraw'])} ({summary['withdraw_count']} مورد)",
        f"⚖️ خالص ماه: {format_money(summary['balance'])}",
    ]

    if summary.get("balances"):
        lines.append("")
        lines.append("🏦 موجودی حساب‌ها:")
        for b in summary["balances"]:
            lines.append(f"• {b['name']}: {format_money(b['balance'])}")

    expense_cats = [c for c in summary.get("categories", []) if c["type"] == "withdraw"]
    income_cats = [c for c in summary.get("categories", []) if c["type"] == "deposit"]

    if expense_cats:
        lines.append("")
        lines.append("🧾 مخارج به تفکیک دسته:")
        for c in expense_cats:
            label = category_label(c["category"])
            if c["category"] in ("other", ""):
                label = "سایر / بدون دسته"
            lines.append(f"• {label}: {format_money(c['total'])} ({c['count']} مورد)")

    if income_cats:
        lines.append("")
        lines.append("💰 درآمد به تفکیک دسته:")
        for c in income_cats:
            label = category_label(c["category"])
            if c["category"] in ("other", ""):
                label = "سایر / بدون دسته"
            lines.append(f"• {label}: {format_money(c['total'])} ({c['count']} مورد)")

    if summary.get("accounts"):
        lines.append("")
        lines.append("📒 گردش ماه به تفکیک حساب:")
        for acc in summary["accounts"]:
            net = acc["deposit"] - acc["withdraw"]
            lines.append(
                f"• {acc['name']}: +{format_money(acc['deposit'])} / "
                f"-{format_money(acc['withdraw'])} | خالص {format_money(net)}"
            )
    return "\n".join(lines)


def categories_help_text() -> str:
    expense = "\n".join(f"• {label}" for _, label in categories_for("withdraw"))
    income = "\n".join(f"• {label}" for _, label in categories_for("deposit"))
    return (
        "🏷 دسته‌های حسابداری شخصی\n\n"
        "🔴 هزینه‌ها:\n"
        f"{expense}\n\n"
        "🟢 درآمدها:\n"
        f"{income}\n\n"
        "موقع ثبت واریز/برداشت یا رسید، دسته را انتخاب کنید.\n"
        "در گزارش ماه، جمع هر دسته جدا نشان داده می‌شود."
    )


def help_text() -> str:
    return (
        "📒 ربات حسابداری شخصی — سطح حرفه‌ای\n\n"
        "بانک، کارت، شماره حساب، شبا و موجودی اولیه را دقیق ثبت کنید.\n"
        "سپس درآمد/هزینه را با دسته بزنید و گزارش ماهانه بگیرید.\n\n"
        "دستورها:\n"
        "/newbankaccount — تعریف حساب/کارت جدید\n"
        "/accounts — لیست حساب‌ها و موجودی\n"
        "/deposit /withdraw — ثبت گردش\n"
        "/receipt — ثبت با رسید\n"
        "/report — گزارش ماه\n"
        "/categories — دسته‌ها\n"
        "/ping — تست آنلاین بودن\n\n"
        "مبلغ پیش‌فرض تومان است."
    )


# silence unused import warning if CATEGORY_LABELS only used indirectly
_ = CATEGORY_LABELS
