"""Professional SQLite ledger: banks, accounts, transactions, balances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
import jdatetime

from bot.config import DATABASE_PATH, DEFAULT_ACCOUNT_NAME
from bot.db.models import Bank, BankAccount, LedgerEntry
from bot.services.iran_banking import BUILTIN_BANKS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or DATABASE_PATH)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._init_schema()
        await self._migrate_legacy()
        await self.seed_builtin_banks_global()

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
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS banks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,           -- 0 = system/builtin catalog
                name TEXT NOT NULL,
                code TEXT NOT NULL,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, code)
            );

            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bank_id INTEGER,
                title TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'card'
                    CHECK(account_type IN ('card','account','cash','wallet')),
                account_number TEXT NOT NULL DEFAULT '',
                card_number TEXT NOT NULL DEFAULT '',
                sheba TEXT NOT NULL DEFAULT '',
                opening_balance INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'IRR',
                notes TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE SET NULL,
                UNIQUE(user_id, title)
            );

            CREATE TABLE IF NOT EXISTS ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                entry_type TEXT NOT NULL
                    CHECK(entry_type IN ('deposit','withdraw','transfer_in','transfer_out','opening')),
                amount INTEGER NOT NULL CHECK(amount >= 0),
                category TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                counterparty TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                receipt_text TEXT NOT NULL DEFAULT '',
                reference_code TEXT NOT NULL DEFAULT '',
                entry_date TEXT NOT NULL,
                jalali_year INTEGER NOT NULL,
                jalali_month INTEGER NOT NULL,
                jalali_day INTEGER NOT NULL DEFAULT 1,
                related_entry_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES bank_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY(related_entry_id) REFERENCES ledger_entries(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_banks_user ON banks(user_id);
            CREATE INDEX IF NOT EXISTS idx_ba_user_active
                ON bank_accounts(user_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_ba_bank ON bank_accounts(bank_id);
            CREATE INDEX IF NOT EXISTS idx_ledger_user_month
                ON ledger_entries(user_id, jalali_year, jalali_month);
            CREATE INDEX IF NOT EXISTS idx_ledger_account_date
                ON ledger_entries(account_id, entry_date, id);
            CREATE INDEX IF NOT EXISTS idx_ledger_category
                ON ledger_entries(user_id, category);
            """
        )
        await self.db.commit()

    async def seed_builtin_banks_global(self) -> None:
        now = utc_now_iso()
        for code, name in BUILTIN_BANKS:
            await self.db.execute(
                """
                INSERT OR IGNORE INTO banks (user_id, name, code, is_builtin, created_at)
                VALUES (0, ?, ?, 1, ?)
                """,
                (name, code, now),
            )
        await self.db.commit()

    async def _table_exists(self, name: str) -> bool:
        rows = await self.db.execute_fetchall(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        )
        return bool(rows)

    async def _migrate_legacy(self) -> None:
        """Migrate old accounts/transactions tables into the new ledger."""
        if not await self._table_exists("accounts"):
            return
        # Already migrated?
        rows = await self.db.execute_fetchall(
            "SELECT value FROM schema_meta WHERE key='legacy_migrated_v2'"
        )
        if rows:
            return

        old_accounts = await self.db.execute_fetchall("SELECT * FROM accounts")
        id_map: dict[int, int] = {}
        now = utc_now_iso()
        for a in old_accounts:
            cur = await self.db.execute(
                """
                INSERT OR IGNORE INTO bank_accounts (
                    user_id, bank_id, title, account_type, account_number, card_number,
                    sheba, opening_balance, currency, notes, is_active, created_at, updated_at
                ) VALUES (?, NULL, ?, 'account', '', '', '', 0, 'IRR', 'migrated', 1, ?, ?)
                """,
                (a["user_id"], a["name"], a["created_at"] or now, now),
            )
            new_id = cur.lastrowid
            if not new_id:
                existing = await self.db.execute_fetchall(
                    "SELECT id FROM bank_accounts WHERE user_id=? AND title=?",
                    (a["user_id"], a["name"]),
                )
                new_id = int(existing[0]["id"])
            id_map[int(a["id"])] = int(new_id)

        if await self._table_exists("transactions"):
            old_txs = await self.db.execute_fetchall("SELECT * FROM transactions")
            for t in old_txs:
                old_acc = int(t["account_id"])
                new_acc = id_map.get(old_acc)
                if not new_acc:
                    continue
                day = 1
                try:
                    day = int(str(t["transaction_date"]).split("-")[2])
                except Exception:  # noqa: BLE001
                    day = 1
                category = ""
                try:
                    category = t["category"] or ""
                except Exception:  # noqa: BLE001
                    category = ""
                await self.db.execute(
                    """
                    INSERT INTO ledger_entries (
                        user_id, account_id, entry_type, amount, category, description,
                        counterparty, source, receipt_text, reference_code, entry_date,
                        jalali_year, jalali_month, jalali_day, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, '', ?, ?, ?, ?, ?)
                    """,
                    (
                        t["user_id"],
                        new_acc,
                        t["type"],
                        t["amount"],
                        category,
                        t["description"] or "",
                        t["source"] or "manual",
                        t["receipt_text"] or "",
                        t["transaction_date"],
                        t["jalali_year"],
                        t["jalali_month"],
                        day,
                        t["created_at"] or now,
                    ),
                )

        await self.db.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('legacy_migrated_v2', ?)",
            (now,),
        )
        await self.db.commit()

    # ── Banks ───────────────────────────────────────────────

    async def list_banks(self, user_id: int) -> list[Bank]:
        rows = await self.db.execute_fetchall(
            """
            SELECT * FROM banks
            WHERE user_id IN (0, ?)
            ORDER BY is_builtin DESC, name COLLATE NOCASE
            """,
            (user_id,),
        )
        return [Bank(**dict(r)) for r in rows]

    async def get_bank(self, bank_id: int) -> Bank:
        rows = await self.db.execute_fetchall("SELECT * FROM banks WHERE id=?", (bank_id,))
        if not rows:
            raise ValueError("بانک پیدا نشد")
        return Bank(**dict(rows[0]))

    async def get_bank_by_code(self, code: str, user_id: int = 0) -> Optional[Bank]:
        rows = await self.db.execute_fetchall(
            "SELECT * FROM banks WHERE code=? AND user_id IN (0, ?) ORDER BY user_id DESC LIMIT 1",
            (code, user_id),
        )
        return Bank(**dict(rows[0])) if rows else None

    async def create_custom_bank(self, user_id: int, name: str, code: str | None = None) -> Bank:
        name = name.strip()
        if not name:
            raise ValueError("نام بانک خالی است")
        code = (code or name).strip().lower().replace(" ", "_")
        cur = await self.db.execute(
            """
            INSERT INTO banks (user_id, name, code, is_builtin, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            (user_id, name, code, utc_now_iso()),
        )
        await self.db.commit()
        return await self.get_bank(cur.lastrowid)

    # ── Accounts ────────────────────────────────────────────

    async def ensure_default_account(self, user_id: int) -> BankAccount:
        rows = await self.db.execute_fetchall(
            """
            SELECT ba.*, COALESCE(b.name,'') AS bank_name, COALESCE(b.code,'') AS bank_code
            FROM bank_accounts ba
            LEFT JOIN banks b ON b.id = ba.bank_id
            WHERE ba.user_id=? AND ba.is_active=1
            ORDER BY ba.id LIMIT 1
            """,
            (user_id,),
        )
        if rows:
            return BankAccount(**dict(rows[0]))
        return await self.create_bank_account(
            user_id=user_id,
            title=DEFAULT_ACCOUNT_NAME,
            account_type="cash",
            opening_balance=0,
        )

    async def create_bank_account(
        self,
        *,
        user_id: int,
        title: str,
        account_type: str = "card",
        bank_id: int | None = None,
        account_number: str = "",
        card_number: str = "",
        sheba: str = "",
        opening_balance: int = 0,
        notes: str = "",
    ) -> BankAccount:
        title = title.strip() or DEFAULT_ACCOUNT_NAME
        if account_type not in ("card", "account", "cash", "wallet"):
            raise ValueError("نوع حساب نامعتبر است")
        now = utc_now_iso()
        cur = await self.db.execute(
            """
            INSERT INTO bank_accounts (
                user_id, bank_id, title, account_type, account_number, card_number,
                sheba, opening_balance, currency, notes, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'IRR', ?, 1, ?, ?)
            """,
            (
                user_id,
                bank_id,
                title,
                account_type,
                account_number,
                card_number,
                sheba,
                int(opening_balance),
                notes.strip(),
                now,
                now,
            ),
        )
        await self.db.commit()
        account = await self.get_bank_account(cur.lastrowid, user_id)
        # Opening balance is stored on the account row; optional ledger marker
        if opening_balance:
            today = datetime.now().date()
            j = jdatetime.date.fromgregorian(date=today)
            await self.add_entry(
                user_id=user_id,
                account_id=account.id,
                entry_type="opening",
                amount=abs(int(opening_balance)),
                category="opening",
                description="موجودی اولیه",
                source="system",
                entry_date=today.isoformat(),
                jalali_year=j.year,
                jalali_month=j.month,
                jalali_day=j.day,
            )
        return account

    async def update_bank_account(
        self,
        account_id: int,
        user_id: int,
        **fields: Any,
    ) -> BankAccount:
        allowed = {
            "bank_id",
            "title",
            "account_type",
            "account_number",
            "card_number",
            "sheba",
            "opening_balance",
            "notes",
            "is_active",
        }
        sets = []
        vals: list[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            sets.append(f"{k}=?")
            vals.append(v)
        if not sets:
            return await self.get_bank_account(account_id, user_id)
        sets.append("updated_at=?")
        vals.append(utc_now_iso())
        vals.extend([account_id, user_id])
        await self.db.execute(
            f"UPDATE bank_accounts SET {', '.join(sets)} WHERE id=? AND user_id=?",
            vals,
        )
        await self.db.commit()
        return await self.get_bank_account(account_id, user_id)

    async def get_bank_account(self, account_id: int, user_id: int) -> BankAccount:
        rows = await self.db.execute_fetchall(
            """
            SELECT ba.*, COALESCE(b.name,'') AS bank_name, COALESCE(b.code,'') AS bank_code
            FROM bank_accounts ba
            LEFT JOIN banks b ON b.id = ba.bank_id
            WHERE ba.id=? AND ba.user_id=?
            """,
            (account_id, user_id),
        )
        if not rows:
            raise ValueError("حساب پیدا نشد")
        return BankAccount(**dict(rows[0]))

    async def list_bank_accounts(self, user_id: int, active_only: bool = True) -> list[BankAccount]:
        q = """
            SELECT ba.*, COALESCE(b.name,'') AS bank_name, COALESCE(b.code,'') AS bank_code
            FROM bank_accounts ba
            LEFT JOIN banks b ON b.id = ba.bank_id
            WHERE ba.user_id=?
        """
        if active_only:
            q += " AND ba.is_active=1"
        q += " ORDER BY ba.id"
        rows = await self.db.execute_fetchall(q, (user_id,))
        return [BankAccount(**dict(r)) for r in rows]

    async def get_or_create_account_by_name(self, user_id: int, name: str) -> BankAccount:
        name = name.strip()
        rows = await self.db.execute_fetchall(
            """
            SELECT ba.*, COALESCE(b.name,'') AS bank_name, COALESCE(b.code,'') AS bank_code
            FROM bank_accounts ba
            LEFT JOIN banks b ON b.id = ba.bank_id
            WHERE ba.user_id=? AND ba.title=?
            """,
            (user_id, name),
        )
        if rows:
            return BankAccount(**dict(rows[0]))
        return await self.create_bank_account(user_id=user_id, title=name, account_type="account")

    # ── Ledger / balance ────────────────────────────────────

    async def account_balance(self, account_id: int, user_id: int) -> int:
        acc = await self.get_bank_account(account_id, user_id)
        rows = await self.db.execute_fetchall(
            """
            SELECT entry_type, COALESCE(SUM(amount),0) AS total
            FROM ledger_entries
            WHERE account_id=? AND user_id=? AND entry_type != 'opening'
            GROUP BY entry_type
            """,
            (account_id, user_id),
        )
        delta = 0
        for r in rows:
            t = r["entry_type"]
            total = int(r["total"] or 0)
            if t in ("deposit", "transfer_in"):
                delta += total
            elif t in ("withdraw", "transfer_out"):
                delta -= total
        return int(acc.opening_balance) + delta

    async def add_entry(
        self,
        *,
        user_id: int,
        account_id: int,
        entry_type: str,
        amount: int,
        category: str = "",
        description: str = "",
        counterparty: str = "",
        source: str = "manual",
        receipt_text: str = "",
        reference_code: str = "",
        entry_date: str,
        jalali_year: int,
        jalali_month: int,
        jalali_day: int = 1,
        related_entry_id: int | None = None,
    ) -> LedgerEntry:
        if entry_type not in ("deposit", "withdraw", "transfer_in", "transfer_out", "opening"):
            raise ValueError("نوع سند نامعتبر است")
        if amount < 0:
            raise ValueError("مبلغ منفی مجاز نیست")
        if entry_type != "opening" and amount <= 0:
            raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
        # ownership check
        await self.get_bank_account(account_id, user_id)
        cur = await self.db.execute(
            """
            INSERT INTO ledger_entries (
                user_id, account_id, entry_type, amount, category, description,
                counterparty, source, receipt_text, reference_code, entry_date,
                jalali_year, jalali_month, jalali_day, related_entry_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_id,
                entry_type,
                int(amount),
                category.strip(),
                description.strip(),
                counterparty.strip(),
                source,
                receipt_text,
                reference_code.strip(),
                entry_date,
                jalali_year,
                jalali_month,
                jalali_day,
                related_entry_id,
                utc_now_iso(),
            ),
        )
        await self.db.commit()
        return await self.get_entry(cur.lastrowid, user_id)

    # Compatibility aliases used by older handlers
    async def add_transaction(self, **kwargs: Any) -> LedgerEntry:
        mapping = {
            "tx_type": "entry_type",
            "transaction_date": "entry_date",
        }
        normalized = {}
        for k, v in kwargs.items():
            normalized[mapping.get(k, k)] = v
        if "jalali_day" not in normalized:
            try:
                normalized["jalali_day"] = int(str(normalized["entry_date"]).split("-")[2])
            except Exception:  # noqa: BLE001
                normalized["jalali_day"] = 1
        return await self.add_entry(**normalized)

    async def get_entry(self, entry_id: int, user_id: int) -> LedgerEntry:
        rows = await self.db.execute_fetchall(
            """
            SELECT e.*, ba.title AS account_title, COALESCE(b.name,'') AS bank_name
            FROM ledger_entries e
            JOIN bank_accounts ba ON ba.id = e.account_id
            LEFT JOIN banks b ON b.id = ba.bank_id
            WHERE e.id=? AND e.user_id=?
            """,
            (entry_id, user_id),
        )
        if not rows:
            raise ValueError("سند پیدا نشد")
        return LedgerEntry(**dict(rows[0]))

    async def get_transaction(self, tx_id: int, user_id: int) -> LedgerEntry:
        return await self.get_entry(tx_id, user_id)

    async def delete_transaction(self, tx_id: int, user_id: int) -> bool:
        cur = await self.db.execute(
            "DELETE FROM ledger_entries WHERE id=? AND user_id=? AND entry_type != 'opening'",
            (tx_id, user_id),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def recent_transactions(
        self, user_id: int, limit: int = 15, account_id: int | None = None
    ) -> list[LedgerEntry]:
        if account_id:
            rows = await self.db.execute_fetchall(
                """
                SELECT e.*, ba.title AS account_title, COALESCE(b.name,'') AS bank_name
                FROM ledger_entries e
                JOIN bank_accounts ba ON ba.id = e.account_id
                LEFT JOIN banks b ON b.id = ba.bank_id
                WHERE e.user_id=? AND e.account_id=? AND e.entry_type != 'opening'
                ORDER BY e.entry_date DESC, e.id DESC
                LIMIT ?
                """,
                (user_id, account_id, limit),
            )
        else:
            rows = await self.db.execute_fetchall(
                """
                SELECT e.*, ba.title AS account_title, COALESCE(b.name,'') AS bank_name
                FROM ledger_entries e
                JOIN bank_accounts ba ON ba.id = e.account_id
                LEFT JOIN banks b ON b.id = ba.bank_id
                WHERE e.user_id=? AND e.entry_type != 'opening'
                ORDER BY e.entry_date DESC, e.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        return [LedgerEntry(**dict(r)) for r in rows]

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
            account_filter = " AND account_id=?"
            params.append(account_id)

        rows = await self.db.execute_fetchall(
            f"""
            SELECT entry_type, SUM(amount) AS total, COUNT(*) AS cnt
            FROM ledger_entries
            WHERE user_id=? AND jalali_year=? AND jalali_month=?
              AND entry_type IN ('deposit','withdraw')
              {account_filter}
            GROUP BY entry_type
            """,
            params,
        )
        deposit = withdraw = deposit_count = withdraw_count = 0
        for r in rows:
            if r["entry_type"] == "deposit":
                deposit = int(r["total"] or 0)
                deposit_count = int(r["cnt"] or 0)
            else:
                withdraw = int(r["total"] or 0)
                withdraw_count = int(r["cnt"] or 0)

        by_account_rows = await self.db.execute_fetchall(
            f"""
            SELECT ba.id, ba.title AS name, e.entry_type AS type,
                   SUM(e.amount) AS total, COUNT(*) AS cnt
            FROM ledger_entries e
            JOIN bank_accounts ba ON ba.id = e.account_id
            WHERE e.user_id=? AND e.jalali_year=? AND e.jalali_month=?
              AND e.entry_type IN ('deposit','withdraw')
              {"AND e.account_id=?" if account_id else ""}
            GROUP BY ba.id, ba.title, e.entry_type
            ORDER BY ba.id
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
                CASE WHEN category IS NULL OR category='' THEN 'other' ELSE category END AS category,
                entry_type AS type,
                SUM(amount) AS total,
                COUNT(*) AS cnt
            FROM ledger_entries
            WHERE user_id=? AND jalali_year=? AND jalali_month=?
              AND entry_type IN ('deposit','withdraw')
              {account_filter}
            GROUP BY category, entry_type
            ORDER BY total DESC
            """,
            params,
        )
        categories = [
            {
                "category": r["category"],
                "type": r["type"],
                "total": int(r["total"] or 0),
                "count": int(r["cnt"] or 0),
            }
            for r in by_cat_rows
        ]

        # Current balances snapshot
        bals = []
        for acc in await self.list_bank_accounts(user_id):
            if account_id and acc.id != account_id:
                continue
            bals.append(
                {
                    "id": acc.id,
                    "name": acc.display_name,
                    "balance": await self.account_balance(acc.id, user_id),
                    "opening_balance": acc.opening_balance,
                    "card_number": acc.card_number,
                    "account_number": acc.account_number,
                    "bank_name": acc.bank_name,
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
            "balances": bals,
        }

    async def list_months(self, user_id: int, limit: int = 12) -> list[tuple[int, int]]:
        rows = await self.db.execute_fetchall(
            """
            SELECT DISTINCT jalali_year, jalali_month
            FROM ledger_entries
            WHERE user_id=? AND entry_type IN ('deposit','withdraw')
            ORDER BY jalali_year DESC, jalali_month DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [(int(r["jalali_year"]), int(r["jalali_month"])) for r in rows]

    # Legacy-compatible aliases
    async def list_accounts(self, user_id: int) -> list[BankAccount]:
        return await self.list_bank_accounts(user_id)

    async def create_account(self, user_id: int, name: str) -> BankAccount:
        return await self.create_bank_account(user_id=user_id, title=name, account_type="account")
