"""Tests for Persian/Telegram text normalization and button filters."""

from __future__ import annotations

from bot.textnorm import normalize_text


def test_normalize_strips_zwnj_and_variation_selectors():
    raw = "🏦 حساب\u200cها و بانک\u200cها\ufe0f"
    assert normalize_text(raw) == normalize_text("🏦 حساب‌ها و بانک‌ها")
    assert "\u200c" not in normalize_text(raw)
    assert "\ufe0f" not in normalize_text(raw)


def test_normalize_arabic_yeh_kaf_to_persian():
    # Arabic yeh/kaf should match Persian keyboard labels
    arabicish = "دستهها"  # already without ZWNJ
    assert normalize_text("دسته‌ها") == normalize_text("دستهها")
    assert normalize_text("يك") == "یک"  # ي→ی , ك→ک


def test_menu_labels_match_with_noise():
    from bot.__main__ import (
        BTN_ACCOUNTS,
        BTN_CATS,
        BTN_DEPOSIT,
        BTN_LIST,
        BTN_REPORT,
    )

    class Msg:
        def __init__(self, text):
            self.text = text

    assert BTN_DEPOSIT.filter(Msg("➕ واریز دستی"))
    assert BTN_DEPOSIT.filter(Msg("➕ واریز دستی\ufe0f"))
    assert BTN_REPORT.filter(Msg("📊 گزارش ماه"))
    assert BTN_LIST.filter(Msg("📋 آخرین تراکنش\u200cها"))
    assert BTN_LIST.filter(Msg("📋 آخرین تراکنشها"))
    assert BTN_CATS.filter(Msg("🏷 دسته\u200cها"))
    assert BTN_ACCOUNTS.filter(Msg("🏦 حساب\u200cها و بانک\u200cها"))
    assert BTN_ACCOUNTS.filter(Msg("🏦 حسابها و بانکها"))
    assert not BTN_DEPOSIT.filter(Msg("سلام"))
    assert not BTN_DEPOSIT.filter(Msg(None))


def test_build_app_requires_token(monkeypatch):
    import bot.__main__ as mainmod
    import bot.config as config

    monkeypatch.setattr(config, "BOT_TOKEN", "")
    monkeypatch.setattr(mainmod, "BOT_TOKEN", "")
    try:
        mainmod.build_app()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert "BOT_TOKEN" in str(exc)
