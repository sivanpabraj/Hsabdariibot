"""Iranian banking helpers: validation, masking, formatting."""

from __future__ import annotations

import re
from typing import Optional

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Common Iranian banks (code, display name)
BUILTIN_BANKS: list[tuple[str, str]] = [
    ("melli", "بانک ملی"),
    ("mellat", "بانک ملت"),
    ("tejarat", "بانک تجارت"),
    ("sader", "بانک صادرات"),
    ("sepah", "بانک سپه"),
    ("parsian", "بانک پارسیان"),
    ("pasargad", "بانک پاسارگاد"),
    ("saman", "بانک سامان"),
    ("sina", "بانک سینا"),
    ("ayandeh", "بانک آینده"),
    ("shahr", "بانک شهر"),
    ("maskan", "بانک مسکن"),
    ("refah", "بانک رفاه"),
    ("keshavarzi", "بانک کشاورزی"),
    ("post", "پست بانک"),
    ("karafarin", "بانک کارآفرین"),
    ("eghtesad_novin", "اقتصاد نوین"),
    ("tourism", "گردشگری"),
    ("iran_zamin", "ایران‌زمین"),
    ("other", "سایر / متفرقه"),
]

ACCOUNT_TYPES = {
    "card": "کارت بانکی",
    "account": "حساب بانکی",
    "cash": "نقد / صندوق",
    "wallet": "کیف پول",
}


def only_digits(value: str) -> str:
    return re.sub(r"\D+", "", (value or "").translate(PERSIAN_DIGITS))


def normalize_sheba(value: str) -> str:
    raw = (value or "").translate(PERSIAN_DIGITS).upper().replace(" ", "").replace("-", "")
    if raw.startswith("IR"):
        body = only_digits(raw[2:])
        return f"IR{body}" if body else ""
    body = only_digits(raw)
    return f"IR{body}" if body else ""


def luhn_ok(number: str) -> bool:
    digits = only_digits(number)
    if len(digits) < 2:
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def validate_card_number(value: str) -> tuple[bool, str, str]:
    """Return (ok, digits, error_message)."""
    digits = only_digits(value)
    if not digits:
        return True, "", ""  # optional
    if len(digits) != 16:
        return False, digits, "شماره کارت باید ۱۶ رقم باشد."
    if not luhn_ok(digits):
        return False, digits, "شماره کارت نامعتبر است (چک‌رقم)."
    return True, digits, ""


def validate_account_number(value: str) -> tuple[bool, str, str]:
    digits = only_digits(value)
    if not digits:
        return True, "", ""
    if not (6 <= len(digits) <= 20):
        return False, digits, "شماره حساب باید بین ۶ تا ۲۰ رقم باشد."
    return True, digits, ""


def validate_sheba(value: str) -> tuple[bool, str, str]:
    sheba = normalize_sheba(value)
    if not sheba:
        return True, "", ""
    if not re.fullmatch(r"IR\d{24}", sheba):
        return False, sheba, "شبا باید به صورت IR + ۲۴ رقم باشد."
    # ISO 13616 checksum
    rearranged = sheba[4:] + "1827" + sheba[2:4]  # IR -> 1827
    # modular arithmetic for large number
    remainder = 0
    for ch in rearranged:
        remainder = (remainder * 10 + int(ch)) % 97
    if remainder != 1:
        return False, sheba, "شبا نامعتبر است (چک‌رقم)."
    return True, sheba, ""


def mask_card(card_digits: str) -> str:
    d = only_digits(card_digits)
    if len(d) != 16:
        return d or "—"
    return f"{d[:4]}‌{d[4:6]}**-****-{d[-4:]}"


def mask_account(account_digits: str) -> str:
    d = only_digits(account_digits)
    if len(d) <= 4:
        return d or "—"
    return f"{'*' * max(0, len(d) - 4)}{d[-4:]}"


def format_sheba(sheba: str) -> str:
    s = normalize_sheba(sheba)
    if len(s) != 26:
        return s or "—"
    body = s[2:]
    parts = [s[:2]] + [body[i : i + 4] for i in range(0, 24, 4)]
    return " ".join(parts)


def guess_bank_from_card(card_digits: str) -> Optional[str]:
    """Best-effort BIN -> bank code for common Iranian cards."""
    d = only_digits(card_digits)
    if len(d) < 6:
        return None
    bin6 = d[:6]
    mapping = {
        "603799": "melli",
        "589210": "sepah",
        "627648": "tosee_saderat",  # fallback other
        "627961": "sanat_madan",
        "603770": "keshavarzi",
        "628023": "maskan",
        "627760": "post",
        "502908": "tosee_taavon",
        "627412": "eghtesad_novin",
        "622106": "parsian",
        "627884": "parsian",
        "502229": "pasargad",
        "639347": "pasargad",
        "621986": "saman",
        "639346": "sina",
        "627488": "karafarin",
        "502806": "shahr",
        "504706": "shahr",
        "502938": "dey",
        "603769": "sader",
        "610433": "mellat",
        "991975": "mellat",
        "627353": "tejarat",
        "585983": "tejarat",
        "627381": "ansar",
        "505785": "iran_zamin",
        "636214": "ayandeh",
        "505416": "gardeshgari",
        "636795": "central",
        "639607": "sarmayeh",
        "639370": "mehreqtesad",
    }
    code = mapping.get(bin6)
    if not code:
        return None
    known = {c for c, _ in BUILTIN_BANKS}
    return code if code in known else "other"
