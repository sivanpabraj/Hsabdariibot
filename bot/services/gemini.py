"""Gemini AI helpers for reading Iranian bank receipts."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from bot.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

RECEIPT_PROMPT = """
تو یک استخراج‌کننده داده از رسید بانکی ایرانی هستی.
از روی تصویر یا متن رسید، فقط یک JSON معتبر برگردان (بدون markdown و بدون توضیح اضافه).

قالب دقیق:
{
  "amount_rials": عدد صحیح مبلغ به ریال یا null,
  "amount_unit_seen": "rial" یا "toman" یا "unknown",
  "type": "deposit" یا "withdraw" یا null,
  "jalali_year": عدد یا null,
  "jalali_month": عدد 1 تا 12 یا null,
  "jalali_day": عدد یا null,
  "description": "خلاصه کوتاه فارسی حداکثر 80 کاراکتر",
  "raw_text": "متن خوانده‌شده از رسید",
  "confidence": عدد بین 0 و 1
}

قواعد:
- deposit = واریز / شارژ / دریافت / بستانکار
- withdraw = برداشت / پرداخت / خرید / انتقال از حساب / بدهکار
- اگر مبلغ به تومان بود، amount_rials را معادل ریال کن (×۱۰)
- اگر مبلغ به ریال بود همان را بگذار
- تاریخ را ترجیحاً شمسی استخراج کن
- اگر مطمئن نیستی null بگذار
""".strip()


def gemini_enabled() -> bool:
    return bool(GEMINI_API_KEY)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("پاسخ خالی از Gemini")

    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _client():
    from google import genai

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY تنظیم نشده است")
    return genai.Client(api_key=GEMINI_API_KEY)


def analyze_receipt_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """Send receipt image to Gemini and return structured fields."""
    from google.genai import types

    client = _client()
    parts = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        types.Part.from_text(text=RECEIPT_PROMPT),
    ]
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=types.Content(role="user", parts=parts),
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    text = getattr(response, "text", None) or ""
    if not text and getattr(response, "candidates", None):
        # Fallback: stitch parts
        chunks = []
        for cand in response.candidates:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                if getattr(part, "text", None):
                    chunks.append(part.text)
        text = "\n".join(chunks)
    data = _extract_json(text)
    data["_engine"] = "gemini"
    return data


def analyze_receipt_text(receipt_text: str) -> dict[str, Any]:
    """Parse pasted receipt text with Gemini."""
    from google.genai import types

    client = _client()
    prompt = RECEIPT_PROMPT + "\n\nمتن رسید:\n" + receipt_text
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    text = getattr(response, "text", None) or ""
    data = _extract_json(text)
    data["_engine"] = "gemini"
    if not data.get("raw_text"):
        data["raw_text"] = receipt_text
    return data


def gemini_to_parsed(data: dict[str, Any]):
    """Convert Gemini JSON into ParsedReceipt."""
    from datetime import date

    import jdatetime

    from bot.services.receipt_parser import ParsedReceipt

    notes: list[str] = ["خوانده‌شده با Gemini"]
    amount = data.get("amount_rials")
    try:
        amount = int(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
        notes.append("مبلغ Gemini نامعتبر بود")

    tx_type = data.get("type")
    if tx_type not in ("deposit", "withdraw"):
        tx_type = None

    jy = data.get("jalali_year")
    jm = data.get("jalali_month")
    jd = data.get("jalali_day")
    try:
        jy = int(jy) if jy is not None else None
        jm = int(jm) if jm is not None else None
        jd = int(jd) if jd is not None else None
    except (TypeError, ValueError):
        jy = jm = jd = None

    gdate: Optional[date] = None
    if jy and jm and jd:
        try:
            gdate = jdatetime.date(jy, jm, jd).togregorian()
        except ValueError:
            notes.append("تاریخ شمسی نامعتبر بود؛ تاریخ امروز استفاده می‌شود")
            jy = jm = jd = None

    if not gdate:
        today = date.today()
        j = jdatetime.date.fromgregorian(date=today)
        gdate = today
        jy, jm = j.year, j.month
        notes.append("تاریخ در رسید پیدا نشد؛ تاریخ امروز ثبت می‌شود.")

    conf = data.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.7
    except (TypeError, ValueError):
        confidence = 0.7

    description = str(data.get("description") or "").strip()[:120]
    raw_text = str(data.get("raw_text") or json.dumps(data, ensure_ascii=False))

    return ParsedReceipt(
        amount=amount if amount and amount > 0 else None,
        tx_type=tx_type,
        description=description,
        transaction_date=gdate,
        jalali_year=jy,
        jalali_month=jm,
        confidence=max(0.0, min(confidence, 1.0)),
        raw_text=raw_text,
        notes=notes,
    )
