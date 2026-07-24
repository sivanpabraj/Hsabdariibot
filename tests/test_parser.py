"""Unit tests for receipt parsing and money formatting."""

from __future__ import annotations

import unittest
from datetime import date

from bot.services.receipt_parser import (
    format_money,
    parse_manual_amount,
    parse_receipt_text,
)


class ParseManualAmountTests(unittest.TestCase):
    def test_toman_default(self):
        # 150000 تومان → 1_500_000 ریال
        self.assertEqual(parse_manual_amount("150000"), 1_500_000)
        self.assertEqual(parse_manual_amount("150٬000"), 1_500_000)
        self.assertEqual(parse_manual_amount("150000 تومان"), 1_500_000)

    def test_rial_explicit(self):
        self.assertEqual(parse_manual_amount("1500000 ریال"), 1_500_000)

    def test_million(self):
        self.assertEqual(parse_manual_amount("1.5 میلیون"), 15_000_000)

    def test_persian_digits(self):
        self.assertEqual(parse_manual_amount("۲۵۰۰۰۰"), 2_500_000)


class ParseReceiptTests(unittest.TestCase):
    def test_deposit_receipt(self):
        text = """
        رسید واریز وجه
        مبلغ: 2,500,000 ریال
        تاریخ: 1403/04/15
        شماره پیگیری: 123456
        """
        parsed = parse_receipt_text(text)
        self.assertEqual(parsed.amount, 2_500_000)
        self.assertEqual(parsed.tx_type, "deposit")
        self.assertEqual(parsed.jalali_year, 1403)
        self.assertEqual(parsed.jalali_month, 4)
        self.assertEqual(parsed.transaction_date, date(2024, 7, 5))

    def test_withdraw_receipt(self):
        text = """
        برداشت از حساب
        مبلغ 1,000,000 ریال
        1404/01/02
        """
        parsed = parse_receipt_text(text)
        self.assertEqual(parsed.amount, 1_000_000)
        self.assertEqual(parsed.tx_type, "withdraw")
        self.assertEqual(parsed.jalali_month, 1)

    def test_format_money(self):
        self.assertIn("تومان", format_money(1_500_000))
        self.assertIn("۱۵۰", format_money(1_500_000).translate(
            str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        ) or format_money(1_500_000))


class CategoryGuessTests(unittest.TestCase):
    def test_guess_fuel_and_utilities(self):
        from bot.services.categories import guess_category_from_text

        self.assertEqual(guess_category_from_text("بنزین جایگاه", "withdraw"), "fuel")
        self.assertEqual(guess_category_from_text("قبض برق", "withdraw"), "electricity")
        self.assertEqual(guess_category_from_text("اجاره خانه", "withdraw"), "rent_home")
        self.assertEqual(guess_category_from_text("اجاره دفتر", "withdraw"), "rent_office")
        self.assertEqual(guess_category_from_text("حقوق ماهانه", "deposit"), "salary")


class DatabaseSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_monthly_summary(self):
        import os
        import tempfile

        from bot.db.database import Database

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = Database(path)
            await db.connect()
            acc = await db.ensure_default_account(42)
            await db.add_transaction(
                user_id=42,
                account_id=acc.id,
                tx_type="deposit",
                amount=1_000_000,
                description="test",
                category="salary",
                transaction_date="2024-07-05",
                jalali_year=1403,
                jalali_month=4,
            )
            await db.add_transaction(
                user_id=42,
                account_id=acc.id,
                tx_type="withdraw",
                amount=400_000,
                description="بنزین",
                category="fuel",
                transaction_date="2024-07-06",
                jalali_year=1403,
                jalali_month=4,
            )
            summary = await db.monthly_summary(42, 1403, 4)
            self.assertEqual(summary["deposit"], 1_000_000)
            self.assertEqual(summary["withdraw"], 400_000)
            self.assertEqual(summary["balance"], 600_000)
            self.assertTrue(any(c["category"] == "fuel" for c in summary["categories"]))
            await db.close()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
