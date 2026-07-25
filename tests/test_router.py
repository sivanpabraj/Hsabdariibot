"""Tests for always-on router (no ConversationHandler)."""

from __future__ import annotations

from bot.router import _is_cancel, _menu_action
from bot.textnorm import normalize_text


def test_menu_actions_resolve():
    assert _menu_action(normalize_text("➕ واریز دستی")) == "deposit"
    assert _menu_action(normalize_text("➖ برداشت دستی")) == "withdraw"
    assert _menu_action(normalize_text("📷 ثبت با رسید\ufe0f")) == "receipt"
    assert _menu_action(normalize_text("📊 گزارش ماه")) == "report"
    assert _menu_action(normalize_text("📋 آخرین تراکنش\u200cها")) == "list"
    assert _menu_action(normalize_text("🏦 حساب\u200cها و بانک\u200cها")) == "accounts"
    assert _menu_action(normalize_text("🏷 دستهها")) == "categories"
    assert _menu_action(normalize_text("❓ راهنما")) == "help"
    assert _menu_action(normalize_text("سلام")) is None


def test_cancel_detection():
    assert _is_cancel("❌ انصراف")
    assert _is_cancel("❌ انصراف\ufe0f")
    assert _is_cancel("/cancel")
    assert not _is_cancel("واریز")


def test_build_app_wires_router(monkeypatch):
    import bot.__main__ as mainmod
    import bot.config as config

    monkeypatch.setattr(config, "BOT_TOKEN", "123456:AA-test-token-not-real-xxxx")
    monkeypatch.setattr(mainmod, "BOT_TOKEN", "123456:AA-test-token-not-real-xxxx")
    app = mainmod.build_app()
    # No ConversationHandler anywhere
    from telegram.ext import ConversationHandler

    for group_handlers in app.handlers.values():
        for h in group_handlers:
            assert not isinstance(h, ConversationHandler)
    # ping + start present
    cmds = set()
    for group_handlers in app.handlers.values():
        for h in group_handlers:
            if getattr(h, "commands", None):
                cmds |= set(h.commands)
    assert "ping" in cmds and "start" in cmds
