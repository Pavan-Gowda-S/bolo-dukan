"""Relay.app AI agent hook (FEATURE_RELAY + RELAY_WEBHOOK_URL).

Bolo Dukaan sends small JSON events to the Webhook trigger of a Relay.app workflow. The AI steps live in Relay
(for example: "write me a 3-line summary of today's sales and WhatsApp it", "log every paid bill to Google Sheets",
"if a table calls the waiter twice, alert the manager"). Events go out in a background thread, so the restaurant
never waits for Relay. No customer phone numbers or payment secrets are ever sent.

Event shape:
    {"event": "bill_paid" | "waiter_call" | "daily_report" | "test",
     "restaurant": "Dosa Corner", "sent_at": "2026-11-21T08:30:00+00:00", "source": "bolo-dukaan", "data": {...}}
"""
import threading

from . import config
from .db import now_iso
from .net import NetError, request


def enabled() -> bool:
    return bool(config.FEATURE_RELAY and config.RELAY_WEBHOOK_URL.startswith("https://"))


def payload(event: str, restaurant: str, data: dict) -> dict:
    return {"event": event, "restaurant": restaurant, "sent_at": now_iso(), "source": "bolo-dukaan", "data": data}


def send(event: str, restaurant: str, data: dict, wait: bool = False) -> bool:
    """Fire and forget (wait=False), or send now and report success (wait=True, used by the owner's buttons)."""
    if not enabled():
        return False
    body = payload(event, restaurant, data)

    def go() -> bool:
        try:
            status, _ = request("POST", config.RELAY_WEBHOOK_URL, body, {}, 8)
            return 200 <= status < 300
        except NetError:
            return False
    if wait:
        return go()
    threading.Thread(target=go, daemon=True).start()
    return True
