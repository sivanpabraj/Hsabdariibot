"""Async SQLite storage for accounts and transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from bot.config import DATABASE_PATH, DEFAULT_ACCOUNT_NAME


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Account:
    id: int
    user_id: int
    name: str
    created_at: str


@dataclass
class Transaction:
    id: int
    user_id: int
    account_id: int
    type: str  # deposit | withdraw
    amount: int  # Rials (integer)
    description: str
    category: str
    source: str  # manual | receipt
    receipt_text: str
    transaction_date: str  # YYYY-MM-DD (Gregorian)
    jalali_year: int
    jalali_month: int
    created_at: str
    account_name: str = ""


class Database:
    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or DATABASE_PATH)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._init_schema()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if not self._db:
            raise RuntimeError("Database is not connected")
        return self._db

    async def _init_schema(self) -> None:
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('deposit', 'withdraw')),
                amount INTEGER NOT NULL CHECK(amount > 0),
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                receipt_text TEXT NOT NULL DEFAULT '',
                transaction_date TEXT NOT NULL,
                jalali_year INTEGER NOT NULL,
                jalali_month INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tx_user_month
                ON transactions(user_id, jalali_year, jalali_month);
            CREATE INDEX IF NOT EXISTS idx_tx_account
                ON transactions(account_id);
            """
        )
        # Migrate older DBs that lack category column
        cols = await self.db.execute_fetchall("PRAGMA table_info(transactions)")
        names = {r["name"] for r in cols}
        if "category" not in names:
            await self.db.execute(
                "ALTER TABLE transactions ADD COLUMN category TEXT NOT NULL DEFAULT ''"
            )
        await self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(user_id, category)"
        )
        await self.db.commit()

    async def ensure_default_account(self, user_id: int) -> Account:
        row = await self.db.execute_fetchall(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,),
        )
        if row:
            return Account(**dict(row[0]))
        return await self.create_account(user_id, DEFAULT_ACCOUNT_NAME)

    async def create_account(self, user_id: int, name: str) -> Account:
        name = name.strip() or DEFAULT_ACCOUNT_NAME
        cur = await self.db.execute(
            "INSERT INTO accounts (user_id, name, created_at) VALUES (?, ?, ?)",
            (user_id, name, utc_now_iso()),
        )
        await self.db.commit()
        return await self.get_account(cur.lastrowid)

    async def get_account(self, account_id: int) -> Account:
        rows = await self.db.execute_fetchall(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        if not rows:
            raise ValueError("حساب پیدا نشد")
        return Account(**dict(rows[0]))

    async def list_accounts(self, user_id: int) -> list[Account]:
        rows = await self.db.execute_fetchall(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id",
            (user_id,),
        )
        return [Account(**dict(r)) for r in rows]

    async def get_or_create_account_by_name(self, user_id: int, name: str) -> Account:
        name = name.strip()
        rows = await self.db.execute_fetchall(
            "SELECT * FROM accounts WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        if rows:
            return Account(**dict(rows[0]))
        return await self.create_account(user_id, name)

    async def add_transaction(
        self,
        *,
        user_id: int,
        account_id: int,
        tx_type: str,
        amount: int,
        description: str = "",
        category: str = "",
        source: str = "manual",
        receipt_text: str = "",
        transaction_date: str,
        jalali_year: int,
        jalali_month: int,
    ) -> Transaction:
        if tx_type not in ("deposit", "withdraw"):
            raise ValueError("نوع تراکنش نامعتبر است")
        if amount <= 0:
            raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
        cur = await self.db.execute(
            """
            INSERT INTO transactions (
                user_id, account_id, type, amount, description, category, source,
                receipt_text, transaction_date, jalali_year, jalali_month, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_id,
                tx_type,
                amount,
                description.strip(),
                category.strip(),
                source,
                receipt_text,
                transaction_date,
                jalali_year,
                jalali_month,
                utc_now_iso(),
            ),
        )
        await self.db.commit()
        return await self.get_transaction(cur.lastrowid, user_id)

    async def get_transaction(self, tx_id: int, user_id: int) -> Transaction:
        rows = await self.db.execute_fetchall(
            """
            SELECT t.*, a.name AS account_name
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.id = ? AND t.user_id = ?
            """,
            (tx_id, user_id),
        )
        if not rows:
            raise ValueError("تراکنش پیدا نشد")
        data = dict(rows[0])
        data.setdefault("category", "")
        return Transaction(**data)

    async def delete_transaction(self, tx_id: int, user_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (tx_id, user_id),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def recent_transactions(
        self, user_id: int, limit: int = 15, account_id: int | None = None
    ) -> list[Transaction]:
        if account_id:
            rows = await self.db.execute_fetchall(
                """
                SELECT t.*, a.name AS account_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.user_id = ? AND t.account_id = ?
                ORDER BY t.transaction_date DESC, t.id DESC
                LIMIT ?
                """,
                (user_id, account_id, limit),
            )
        else:
            rows = await self.db.execute_fetchall(
                """
                SELECT t.*, a.name AS account_name
                FROM transactions t
                JOIN accounts a ON a.id = t.account_id
                WHERE t.user_id = ?
                ORDER BY t.transaction_date DESC, t.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        result = []
        for r in rows:
            data = dict(r)
            data.setdefault("category", "")
            result.append(Transaction(**data))
        return result

    async def monthly_summary(
        self,
        user_id: int,
        jalali_year: int,
        jalali_month: int,
        account_id: int | None = None,
    ) -> dict[str, Any]:
        params: list[Any] = [user_id, jalali_year, jalali_month]
        account_filter = ""
        if account_id:
            account_filter = " AND account_id = ?"
            params.append(account_id)

        rows = await self.db.execute_fetchall(
            f"""
            SELECT type, SUM(amount) AS total, COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ? AND jalali_year = ? AND jalali_month = ?{account_filter}
            GROUP BY type
            """,
            params,
        )
        deposit = 0
        withdraw = 0
        deposit_count = 0
        withdraw_count = 0
        for r in rows:
            if r["type"] == "deposit":
                deposit = int(r["total"] or 0)
                deposit_count = int(r["cnt"] or 0)
            elif r["type"] == "withdraw":
                withdraw = int(r["total"] or 0)
                withdraw_count = int(r["cnt"] or 0)

        by_account_rows = await self.db.execute_fetchall(
            f"""
            SELECT a.id, a.name, t.type, SUM(t.amount) AS total, COUNT(*) AS cnt
            FROM transactions t
            JOIN accounts a ON a.id = t.account_id
            WHERE t.user_id = ? AND t.jalali_year = ? AND t.jalali_month = ?
            {"AND t.account_id = ?" if account_id else ""}
            GROUP BY a.id, a.name, t.type
            ORDER BY a.id
            """,
            params,
        )
        accounts: dict[int, dict[str, Any]] = {}
        for r in by_account_rows:
            aid = int(r["id"])
            if aid not in accounts:
                accounts[aid] = {
                    "id": aid,
                    "name": r["name"],
                    "deposit": 0,
                    "withdraw": 0,
                    "deposit_count": 0,
                    "withdraw_count": 0,
                }
            if r["type"] == "deposit":
                accounts[aid]["deposit"] = int(r["total"] or 0)
                accounts[aid]["deposit_count"] = int(r["cnt"] or 0)
            else:
                accounts[aid]["withdraw"] = int(r["total"] or 0)
                accounts[aid]["withdraw_count"] = int(r["cnt"] or 0)

        by_cat_rows = await self.db.execute_fetchall(
            f"""
            SELECT
                CASE WHEN category IS NULL OR category = '' THEN 'other' ELSE category END AS category,
                type,
                SUM(amount) AS total,
                COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ? AND jalali_year = ? AND jalali_month = ?{account_filter}
            GROUP BY category, type
            ORDER BY total DESC
            """,
            params,
        )
        categories: list[dict[str, Any]] = []
        for r in by_cat_rows:
            categories.append(
                {
                    "category": r["category"],
                    "type": r["type"],
                    "total": int(r["total"] or 0),
                    "count": int(r["cnt"] or 0),
                }
            )

        return {
            "year": jalali_year,
            "month": jalali_month,
            "deposit": deposit,
            "withdraw": withdraw,
            "deposit_count": deposit_count,
            "withdraw_count": withdraw_count,
            "balance": deposit - withdraw,
            "accounts": list(accounts.values()),
            "categories": categories,
        }

    async def list_months(self, user_id: int, limit: int = 12) -> list[tuple[int, int]]:
        rows = await self.db.execute_fetchall(
            """
            SELECT DISTINCT jalali_year, jalali_month
            FROM transactions
            WHERE user_id = ?
            ORDER BY jalali_year DESC, jalali_month DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [(int(r["jalali_year"]), int(r["jalali_month"])) for r in rows]
