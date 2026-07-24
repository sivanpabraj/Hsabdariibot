"""Domain models for personal banking ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Bank:
    id: int
    user_id: int
    name: str
    code: str
    is_builtin: int
    created_at: str


@dataclass(frozen=True)
class BankAccount:
    id: int
    user_id: int
    bank_id: Optional[int]
    title: str
    account_type: str  # card | account | cash | wallet
    account_number: str
    card_number: str  # digits only, may be empty
    sheba: str  # IR... or empty
    opening_balance: int  # Rials
    currency: str
    notes: str
    is_active: int
    created_at: str
    updated_at: str
    bank_name: str = ""
    bank_code: str = ""

    @property
    def name(self) -> str:
        return self.title

    @property
    def display_name(self) -> str:
        bank = self.bank_name or "بدون بانک"
        return f"{self.title} · {bank}"


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    user_id: int
    account_id: int
    entry_type: str  # deposit | withdraw | transfer_in | transfer_out | opening
    amount: int
    category: str
    description: str
    counterparty: str
    source: str
    receipt_text: str
    reference_code: str
    entry_date: str
    jalali_year: int
    jalali_month: int
    jalali_day: int
    created_at: str
    account_title: str = ""
    bank_name: str = ""
    related_entry_id: Optional[int] = None

    # Compatibility aliases for older handlers/UI
    @property
    def type(self) -> str:
        return self.entry_type

    @property
    def account_name(self) -> str:
        if self.bank_name:
            return f"{self.account_title} · {self.bank_name}"
        return self.account_title

    @property
    def transaction_date(self) -> str:
        return self.entry_date
