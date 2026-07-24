"""Parse Iranian bank receipt text into structured transaction data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import jdatetime

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MONTH_NAMES = {
    1: "فروردین",
    2: "اردیبهشت",
    3: "خرداد",
    4: "تیر",
    5: "مرداد",
    6: "شهریور",
    7: "مهر",
    8: "آبان",
    9: "آذر",
    10: "دی",
    11: "بهمن",
    12: "اسفند",
}

MONTH_NAME_TO_NUM = {v: k for k, v in MONTH_NAMES.items()}
MONTH_NAME_TO_NUM.update(
    {
        "فروردين": 1,
        "ارديبهشت": 2,
        "آبان": 8,
        "آذر": 9,
    }
)


@dataclass
class ParsedReceipt:
    amount: Optional[int] = None  # Rials
    tx_type: Optional[str] = None  # deposit | withdraw
    description: str = ""
    category: Optional[str] = None
    transaction_date: Optional[date] = None
    jalali_year: Optional[int] = None
    jalali_month: Optional[int] = None
    confidence: float = 0.0
    raw_text: str = ""
    notes: list[str] | None = None


def normalize_text(text: str) -> str:
    text = text.translate(PERSIAN_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = text.replace("٬", ",").replace("٫", ".").replace("،", ",")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_amount_token(token: str) -> Optional[int]:
    """Parse a money token into integer Rials."""
    token = token.translate(PERSIAN_DIGITS)
    token = token.replace(",", "").replace("٬", "").replace(" ", "").strip()
    token = token.replace("ریال", "").replace("تومان", "").strip()
    if not token or not re.fullmatch(r"\d+", token):
        return None
    value = int(token)
    if value <= 0:
        return None
    return value


def _find_amounts(text: str) -> list[int]:
    # Patterns like 1,250,000 or 1250000
    candidates: list[int] = []
    patterns = [
        r"(?:مبلغ|amount|sum|وجه|واریزی|برداشتی)\s*[:：]?\s*([\d٬,]+)",
        r"([\d٬,]{4,})\s*(?:ریال|تومان|irr|rial)",
        r"(?<!\d)(\d{1,3}(?:[٬,]\d{3})+)(?!\d)",
        r"(?<!\d)(\d{5,12})(?!\d)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            amount = parse_amount_token(m.group(1))
            if amount and amount >= 1000:
                candidates.append(amount)

    # Deduplicate preserving order
    seen: set[int] = set()
    unique: list[int] = []
    for a in candidates:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


def _detect_type(text: str) -> Optional[str]:
    t = text.lower()
    deposit_keys = [
        "واریز",
        "واریزی",
        "deposit",
        "شارژ",
        "دریافت",
        "incoming",
        "credit",
        "بستانکار",
    ]
    withdraw_keys = [
        "برداشت",
        "برداشتی",
        "withdraw",
        "پرداخت",
        "خرید",
        "انتقال وجه",
        "debit",
        "بدهکار",
        "outgoing",
    ]
    # Prefer more specific matches first
    if any(k in text for k in ["برداشت از حساب", "برداشت وجه", "برداشت نقدی"]):
        return "withdraw"
    if any(k in text for k in ["واریز به حساب", "واریز وجه", "واریز نقدی"]):
        return "deposit"

    dep = sum(1 for k in deposit_keys if k in text or k in t)
    wdr = sum(1 for k in withdraw_keys if k in text or k in t)
    if dep > wdr and dep > 0:
        return "deposit"
    if wdr > dep and wdr > 0:
        return "withdraw"
    if dep == wdr and dep > 0:
        # Ambiguous — leave unset for user confirmation
        return None
    return None


def _parse_jalali_date(text: str) -> Optional[jdatetime.date]:
    # 1403/04/15 or 1403-04-15 or 1403.04.15
    m = re.search(r"(14\d{2})[\/\-.](\d{1,2})[\/\-.](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return jdatetime.date(y, mo, d)
        except ValueError:
            pass

    # 15 تیر 1403 / 15 تیرماه 1403
    m = re.search(
        r"(\d{1,2})\s*(فروردین|فروردين|اردیبهشت|ارديبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)"
        r"(?:ماه)?\s*(14\d{2})",
        text,
    )
    if m:
        d = int(m.group(1))
        mo = MONTH_NAME_TO_NUM.get(m.group(2))
        y = int(m.group(3))
        if mo:
            try:
                return jdatetime.date(y, mo, d)
            except ValueError:
                pass
    return None


def _parse_gregorian_date(text: str) -> Optional[date]:
    m = re.search(r"(20\d{2})[\/\-.](\d{1,2})[\/\-.](\d{1,2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_receipt_text(raw: str) -> ParsedReceipt:
    text = normalize_text(raw)
    notes: list[str] = []
    amounts = _find_amounts(text)
    amount = amounts[0] if amounts else None
    if len(amounts) > 1:
        notes.append(f"چند مبلغ پیدا شد؛ بزرگ‌ترین انتخاب شد مگر اینکه اصلاح کنید.")
        # Prefer the largest plausible amount (often the main transfer)
        amount = max(amounts)

    tx_type = _detect_type(text)

    jdate = _parse_jalali_date(text)
    gdate = None
    if jdate:
        gdate = jdate.togregorian()
    else:
        gdate = _parse_gregorian_date(text)
        if gdate:
            jdate = jdatetime.date.fromgregorian(date=gdate)

    if not gdate:
        # Default to today
        today = date.today()
        jdate = jdatetime.date.fromgregorian(date=today)
        gdate = today
        notes.append("تاریخ در رسید پیدا نشد؛ تاریخ امروز ثبت می‌شود.")

    # Build short description from first non-empty lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    desc_bits = []
    for ln in lines[:6]:
        if re.search(r"مبلغ|ریال|تومان|تاریخ|پیگیری|مرجع", ln):
            continue
        if len(ln) < 3:
            continue
        desc_bits.append(ln[:60])
        if len(desc_bits) >= 2:
            break
    description = " | ".join(desc_bits)[:120]

    confidence = 0.2
    if amount:
        confidence += 0.4
    if tx_type:
        confidence += 0.25
    if jdate and "تاریخ در رسید پیدا نشد" not in " ".join(notes):
        confidence += 0.15

    return ParsedReceipt(
        amount=amount,
        tx_type=tx_type,
        description=description,
        transaction_date=gdate,
        jalali_year=jdate.year if jdate else None,
        jalali_month=jdate.month if jdate else None,
        confidence=min(confidence, 1.0),
        raw_text=text,
        notes=notes,
    )


def parse_manual_amount(text: str) -> Optional[int]:
    """Parse user-typed amount. Accepts تومان (default) or ریال if marked.

    Returns amount in Rials.
    """
    t = normalize_text(text).strip()
    if not t:
        return None

    is_rial = bool(re.search(r"ریال", t))
    is_toman = bool(re.search(r"تومان", t))
    # Strip labels
    t = re.sub(r"(ریال|تومان)", "", t).strip()
    t = t.replace(",", "").replace("٬", "").replace(" ", "")
    # Support "1.5m" / "2 میلیون"
    million = False
    if re.search(r"میلیون|mln|m$", t, re.I):
        million = True
        t = re.sub(r"میلیون|mln|m$", "", t, flags=re.I).strip()

    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None

    value = float(t)
    if million:
        value *= 1_000_000

    # Default unit: تومان → convert to Rials (*10)
    if is_rial and not is_toman:
        rials = int(value)
    else:
        rials = int(value * 10)

    return rials if rials > 0 else None


def format_money(rials: int) -> str:
    tomans = rials // 10
    return f"{tomans:,} تومان".replace(",", "٬")


def format_jalali(d: date | datetime | None = None, jy: int | None = None, jm: int | None = None, jd: int | None = None) -> str:
    if jy and jm:
        day = jd or 1
        name = MONTH_NAMES.get(jm, str(jm))
        if jd:
            return f"{jd} {name} {jy}"
        return f"{name} {jy}"
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.day} {MONTH_NAMES[j.month]} {j.year}"


def month_title(year: int, month: int) -> str:
    return f"{MONTH_NAMES.get(month, month)} {year}"
