"""Personal accounting categories (income + common household expenses)."""

from __future__ import annotations

# (key, label) — key is stored in DB
EXPENSE_CATEGORIES: list[tuple[str, str]] = [
    ("fuel", "بنزین و سوخت"),
    ("home", "مخارج منزل"),
    ("rent_home", "اجاره خانه"),
    ("rent_office", "اجاره دفتر"),
    ("water", "آب"),
    ("electricity", "برق"),
    ("gas", "گاز"),
    ("internet", "اینترنت و تلفن"),
    ("food", "خوراک و سوپرمارکت"),
    ("transport", "حمل‌ونقل"),
    ("health", "درمان و دارو"),
    ("education", "آموزش"),
    ("clothing", "پوشاک"),
    ("entertainment", "تفریح"),
    ("installment", "اقساط و وام"),
    ("other_expense", "سایر هزینه‌ها"),
]

INCOME_CATEGORIES: list[tuple[str, str]] = [
    ("salary", "حقوق"),
    ("freelance", "پروژه و فریلنس"),
    ("sales", "فروش"),
    ("gift", "هدیه"),
    ("other_income", "سایر درآمدها"),
]

CATEGORY_LABELS: dict[str, str] = {
    **dict(EXPENSE_CATEGORIES),
    **dict(INCOME_CATEGORIES),
}


def categories_for(tx_type: str) -> list[tuple[str, str]]:
    if tx_type == "deposit":
        return INCOME_CATEGORIES
    return EXPENSE_CATEGORIES


def category_label(key: str | None) -> str:
    if not key:
        return "بدون دسته"
    return CATEGORY_LABELS.get(key, key)


def guess_category_from_text(text: str, tx_type: str | None = None) -> str | None:
    """Best-effort category guess from description/receipt text."""
    t = (text or "").replace("ي", "ی").replace("ك", "ک")
    mapping = [
        (("بنزین", "سوخت", "گازوئیل", "CNG", "جایگاه"), "fuel"),
        (("اجاره دفتر", "اجاره مغازه", "اجاره محل کار"), "rent_office"),
        (("اجاره خانه", "اجاره منزل", "رهن", "اجاره مسکن"), "rent_home"),
        (("مخارج منزل", "خانه", "منزل", "تعمیر خانه"), "home"),
        (("آبفا", " قبض آب", "آب بها", "آبونمان آب"), "water"),
        (("برق", "توانیر", "قبص برق"), "electricity"),
        (("گاز", "شرکت گاز", "قبص گاز"), "gas"),
        (("اینترنت", "همراه اول", "ایرانسل", "رایتل", "مخابرات", "تلفن"), "internet"),
        (("سوپر", "نان", "خواربار", "رستوران", "غذا", "خوراک"), "food"),
        (("اسنپ", "تپسی", "تاکسی", "مترو", "اتوبوس", "حمل"), "transport"),
        (("دارو", "دکتر", "بیمارستان", "درمان", "آزمایش"), "health"),
        (("شهریه", "کلاس", "آموزش", "دانشگاه"), "education"),
        (("لباس", "پوشاک", "کفش"), "clothing"),
        (("سینما", "تفریح", "سفر", "گردش"), "entertainment"),
        (("قسط", "وام", "اقساط"), "installment"),
        (("حقوق", "حقوقی", "کارانه"), "salary"),
        (("پروژه", "فریلنس", "قرارداد"), "freelance"),
        (("فروش",), "sales"),
        (("هدیه", "عیدی"), "gift"),
    ]
    for keys, cat in mapping:
        if any(k in t for k in keys):
            if tx_type == "deposit" and cat in dict(EXPENSE_CATEGORIES):
                continue
            if tx_type == "withdraw" and cat in dict(INCOME_CATEGORIES):
                continue
            return cat
    return None
