"""Check the keys in .env before the demo:   python check.py   (or double-click check.bat)

- Gemini: a short text call, then a Kannada voice (TTS) call
- Cashfree (sandbox only): creates one Rs 1 test payment link and prints it
"""
import secrets
import sys

try:  # Windows consoles default to an old code page; Kannada text would crash print()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import cashfree, config, gemini


def ok(msg):
    print(f"  [OK]   {msg}")


def bad(msg):
    print(f"  [FAIL] {msg}")


def main() -> int:
    failures = 0
    print("\n  Bolo Dukaan key check\n")

    if not config.gemini_ready():
        bad("GEMINI_API_KEY is empty in .env")
        failures += 1
    else:
        try:
            menu = [{"id": 1, "name": "Masala Dosa", "name_local": "ಮಸಾಲೆ ದೋಸೆ", "category": "Dosa", "price_paise": 9000},
                    {"id": 2, "name": "Filter Coffee", "name_local": "ಫಿಲ್ಟರ್ ಕಾಫಿ", "category": "Beverages", "price_paise": 4000}]
            r = gemini.understand_order(menu, text="ಎರಡು ಮಸಾಲೆ ದೋಸೆ and one filter coffee")
            items = {i.get("id"): i.get("qty") for i in r.get("items", [])}
            if items.get(1) == 2 and items.get(2) == 1:
                ok(f"Gemini ordering ({config.GEMINI_MODEL}): understood 2 dosa + 1 coffee. Reply: {r.get('reply')}")
            else:
                bad(f"Gemini answered but the order looks off: {r}")
                failures += 1
        except gemini.GeminiError as e:
            bad(f"Gemini ordering: {e}")
            failures += 1
        try:
            wav = gemini.speak("ಟೇಬಲ್ 5, ಹೊಸ ಆರ್ಡರ್")
            out = config.DATA_DIR / "tts_test.wav"
            out.write_bytes(wav)
            ok(f"Gemini voice ({config.GEMINI_TTS_MODEL}): saved {out} ({len(wav) // 1024} KB). Play it to hear the Kannada alert.")
        except gemini.GeminiError as e:
            bad(f"Gemini voice: {e}  (the dashboard falls back to the browser voice)")

    if not config.cashfree_ready():
        bad("CASHFREE_APP_ID / CASHFREE_SECRET_KEY are empty in .env (guests can still pay cash)")
        failures += 1
    elif config.CASHFREE_ENV != "sandbox":
        print("  [SKIP] Cashfree is in production mode; not creating a test link.")
    else:
        try:
            link = cashfree.create_link(f"bdcheck{secrets.token_hex(4)}", 100, "9999999999", "Bolo Dukaan key check",
                                        return_url="https://example.com", notify_url=None)
            ok(f"Cashfree sandbox: test link created -> {link.get('link_url')}")
        except cashfree.CashfreeError as e:
            bad(f"Cashfree: {e}")
            failures += 1

    print("\n  All good. Ready for the demo.\n" if not failures else f"\n  {failures} problem(s) above.\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
