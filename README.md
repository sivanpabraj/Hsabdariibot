# ربات حسابداری شخصی

ربات تلگرام برای **حسابداری شخصی**: ثبت درآمد (واریز) و هزینه (برداشت)، خواندن رسید بانکی با هوش مصنوعی، و گزارش ماهانه شمسی.

## امکانات

- ثبت دستی واریز و برداشت
- ثبت با عکس یا متن رسید (Gemini + پشتیبان OCR)
- چند حساب (مثلاً بانک، نقد، کارت)
- گزارش ماهانه به‌تفکیک حساب
- لیست و حذف تراکنش‌ها

## راه‌اندازی سریع

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

در `.env` این‌ها را پر کنید:

```env
BOT_TOKEN=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
DEFAULT_ACCOUNT_NAME=حساب شخصی
```

اجرا:

```bash
python run.py
```

اختیاری برای پشتیبان OCR:

```bash
sudo apt install tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng
```

## استفاده

| کار | روش |
|---|---|
| شروع | `/start` |
| واریز | «واریز دستی» یا `/deposit 250000 حقوق` |
| برداشت | «برداشت دستی» یا `/withdraw 50000 خرید` |
| رسید | «ثبت با رسید» یا ارسال مستقیم عکس |
| گزارش ماه | «گزارش ماه» یا `/report 1403 4` |
| تراکنش‌ها | `/list` |
| حساب جدید | `/newaccount بانک ملت` |
| حذف | `/delete 12` |

مبالغ به‌صورت پیش‌فرض **تومان** هستند. برای ریال بنویسید: `2500000 ریال`.

## ساختار

```
bot/           # کد ربات
data/          # دیتابیس SQLite (محلی)
run.py         # اجرای ربات
```

## تست

```bash
python -m unittest discover -s tests -v
```
