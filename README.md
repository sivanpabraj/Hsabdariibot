# ربات واریز و برداشت تلگرام

ربات فارسی برای ثبت **واریز** و **برداشت** حساب‌ها، با دو روش:

1. **ثبت دستی** — مبلغ و توضیح را خودتان وارد می‌کنید  
2. **ثبت با رسید** — عکس یا متن رسید بانکی را می‌فرستید؛ ربات با OCR می‌خواند و بعد از تأیید شما ثبت می‌کند  

در پایان هر ماه می‌توانید جمع واریز، برداشت و مانده را به تفکیک حساب ببینید.

## امکانات

- واریز / برداشت دستی (دکمه یا دستور)
- خواندن عکس رسید با Tesseract (فارسی + انگلیسی)
- پارس متن رسید (مبلغ، نوع، تاریخ شمسی)
- چند حساب جداگانه
- گزارش ماهانه شمسی
- لیست و حذف تراکنش‌ها
- محدودیت دسترسی با `ALLOWED_USER_IDS` (اختیاری)

## پیش‌نیاز

- Python 3.10+
- کلید Gemini از [Google AI Studio](https://aistudio.google.com/apikey) برای خواندن هوشمند رسید
- (اختیاری) Tesseract OCR فارسی به‌عنوان پشتیبان:

```bash
# Debian/Ubuntu
sudo apt install tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng
```

## راه‌اندازی

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# BOT_TOKEN و GEMINI_API_KEY را پر کنید
```

محتوای `.env`:

```env
BOT_TOKEN=123456:ABC...
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.5-flash
ALLOWED_USER_IDS=   # خالی = همه؛ یا آیدی عددی خودتان
DEFAULT_ACCOUNT_NAME=حساب اصلی
```

اجرا:

```bash
python run.py
# یا
python -m bot
```

## استفاده در تلگرام

| کار | روش |
|---|---|
| منو | `/start` |
| واریز دستی | دکمه «واریز دستی» یا `/deposit 250000 اجاره` |
| برداشت دستی | دکمه «برداشت دستی» یا `/withdraw 50000 خرید` |
| ثبت با رسید | دکمه «ثبت با رسید» یا مستقیم عکس رسید |
| گزارش ماه | «گزارش ماه» یا `/report` یا `/report 1403 4` |
| تراکنش‌ها | `/list` |
| حساب جدید | `/newaccount بانک ملت` |
| حذف | `/delete 12` |

مبلغ‌ها به‌صورت پیش‌فرض **تومان** هستند. اگر بنویسید `ریال`، همان ریال ذخیره می‌شود.

## ساختار پروژه

```
bot/
  config.py
  db/database.py
  services/ocr.py
  services/receipt_parser.py
  handlers/...
run.py
data/          # دیتابیس SQLite
```

## تست

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

## نکته درباره خواندن رسید

اولویت با **Gemini AI** است (عکس و متن). اگر Gemini در دسترس نباشد، از OCR محلی (Tesseract) استفاده می‌شود. قبل از ثبت نهایی می‌توانید مبلغ و نوع را اصلاح کنید.
