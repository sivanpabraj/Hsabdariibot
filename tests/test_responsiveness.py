"""Tests for Persian/Telegram text normalization."""

from __future__ import annotations

from bot.textnorm import normalize_text


def test_normalize_strips_zwnj_and_variation_selectors():
    raw = "🏦 حساب\u200cها و بانک\u200cها\ufe0f"
    assert normalize_text(raw) == normalize_text("🏦 حساب‌ها و بانک‌ها")
    assert "\u200c" not in normalize_text(raw)
    assert "\ufe0f" not in normalize_text(raw)


def test_normalize_arabic_yeh_kaf_to_persian():
    assert normalize_text("دسته‌ها") == normalize_text("دستهها")
    assert normalize_text("يك") == "یک"


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
