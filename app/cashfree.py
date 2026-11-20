"""Cashfree Payment Links: create a link, read a link, cancel a link, check webhook signatures.

API docs: https://www.cashfree.com/docs/api-reference/payments/latest/payment-links
"""
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from . import config
from .net import NetError, request

IST = timezone(timedelta(hours=5, minutes=30))


class CashfreeError(Exception):
    pass


def _headers() -> dict:
    return {
        "x-client-id": config.CASHFREE_APP_ID,
        "x-client-secret": config.CASHFREE_SECRET_KEY,
        "x-api-version": config.CASHFREE_API_VERSION,
    }


def _msg(data) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data)
    return str(data)[:300]


def create_link(link_id: str, amount_paise: int, phone: str, purpose: str, return_url: str,
                notify_url: str | None) -> dict:
    if not config.cashfree_ready():
        raise CashfreeError("Online payment is not set up. Add Cashfree keys to .env.")
    expiry = (datetime.now(IST) + timedelta(minutes=30)).replace(microsecond=0).isoformat()
    meta = {"return_url": return_url}
    if notify_url and notify_url.startswith("https://"):
        meta["notify_url"] = notify_url  # Cashfree only calls HTTPS webhooks
    body = {
        "link_id": link_id,
        "link_amount": round(amount_paise / 100, 2),
        "link_currency": "INR",
        "link_purpose": purpose[:500],
        "customer_details": {"customer_phone": phone},
        "link_notify": {"send_sms": False, "send_email": False},
        "link_auto_reminders": False,
        "link_partial_payments": False,
        "link_expiry_time": expiry,
        "link_meta": meta,
    }
    try:
        status, data = request("POST", f"{config.CASHFREE_BASE}/links", body, _headers())
    except NetError:
        raise CashfreeError("Could not reach Cashfree. Check the internet and tap Pay again.")
    if status >= 300 or not isinstance(data, dict) or not data.get("link_url"):
        raise CashfreeError(f"Cashfree could not create the payment link: {_msg(data)}")
    return data


def get_link(link_id: str) -> dict:
    if not config.cashfree_ready():
        raise CashfreeError("Online payment is not set up.")
    try:
        status, data = request("GET", f"{config.CASHFREE_BASE}/links/{link_id}", None, _headers(), timeout=15)
    except NetError:
        raise CashfreeError("Could not reach Cashfree.")
    if status >= 300 or not isinstance(data, dict):
        raise CashfreeError(f"Cashfree lookup failed: {_msg(data)}")
    return data


def cancel_link(link_id: str) -> None:
    """Best effort: stop an unpaid link from being used after a cash payment."""
    if not config.cashfree_ready():
        return
    try:
        request("POST", f"{config.CASHFREE_BASE}/links/{link_id}/cancel", {}, _headers(), timeout=10)
    except NetError:
        pass


def verify_signature(raw_body: bytes, timestamp: str | None, signature: str | None) -> bool:
    """signature = base64(HMAC_SHA256(secret_key, timestamp + raw_body))"""
    if not (timestamp and signature and config.CASHFREE_SECRET_KEY):
        return False
    message = timestamp.encode("utf-8") + raw_body
    digest = hmac.new(config.CASHFREE_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature.strip())


def find_link_id(payload: dict) -> str | None:
    """Webhook shapes differ between event types; look in the known places."""
    data = payload.get("data") or {}
    order_tags = (data.get("order") or {}).get("order_tags") or {}
    for candidate in (data.get("link_id"), order_tags.get("link_id"), (data.get("link") or {}).get("link_id")):
        if candidate:
            return str(candidate)
    return None


def is_paid(link: dict, amount_paise: int) -> bool:
    status = str(link.get("link_status", "")).upper()
    try:
        paid = round(float(link.get("link_amount_paid") or 0) * 100)
    except (TypeError, ValueError):
        paid = 0
    return status == "PAID" and paid >= amount_paise
