#!/usr/bin/env python3
"""Diagnose why the Telegram bot may not respond."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bot.config import BOT_TOKEN, GEMINI_API_KEY  # noqa: E402


def main() -> int:
    print("=== Hsabdariibot diagnose ===")
    env_path = ROOT / ".env"
    print(f".env exists: {env_path.is_file()}")
    if not BOT_TOKEN:
        print("BOT_TOKEN: MISSING")
        print("→ Copy .env.example to .env and paste token from @BotFather")
        print("→ Then run: python run.py")
        return 1

    print(f"BOT_TOKEN: set ({len(BOT_TOKEN)} chars)")
    print(f"GEMINI_API_KEY: {'set' if GEMINI_API_KEY else 'empty (OCR fallback only)'}")

    try:
        import httpx
    except ImportError:
        import urllib.request

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
            body = resp.read().decode()
        print("getMe:", body[:300])
        url2 = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
        with urllib.request.urlopen(url2, timeout=20) as resp:  # noqa: S310
            print("getWebhookInfo:", resp.read().decode()[:300])
        return 0

    with httpx.Client(timeout=20.0) as client:
        me = client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe").json()
        wh = client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo").json()
    print("getMe:", me)
    print("getWebhookInfo:", wh)
    if not me.get("ok"):
        print("→ Token invalid. Create a new one with @BotFather")
        return 2
    url = (wh.get("result") or {}).get("url") or ""
    if url:
        print(f"→ Webhook still set to {url!r}. run.py clears it on startup.")
    print("→ If getMe is ok, start exactly ONE process: python run.py")
    print("→ Then in Telegram send /ping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
