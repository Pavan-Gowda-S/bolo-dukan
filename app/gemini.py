"""Gemini: voice/text ordering, menu photo reading, and spoken alerts (TTS)."""
import base64
import io
import json
import re
import struct

from . import config
from .net import NetError, request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    pass


def _generate(model: str, body: dict, timeout: float = 45) -> dict:
    if not config.gemini_ready():
        raise GeminiError("Gemini is not set up. Add GEMINI_API_KEY to .env.")
    url = f"{API_ROOT}/{model}:generateContent"
    headers = {"x-goog-api-key": config.GEMINI_API_KEY}
    try:
        status, data = request("POST", url, body, headers, timeout)
        if status == 400:
            # Some models reject optional settings (thinking budget, schema). Retry plainly.
            gen = dict(body.get("generationConfig") or {})
            changed = False
            for key in ("thinkingConfig", "responseSchema"):
                if key in gen:
                    gen.pop(key)
                    changed = True
            if changed:
                status, data = request("POST", url, {**body, "generationConfig": gen}, headers, timeout)
    except NetError:
        raise GeminiError("Could not reach Gemini. Check the internet and try again.")
    if status >= 300 or not isinstance(data, dict):
        msg = data.get("error", {}).get("message", "") if isinstance(data, dict) else str(data)[:300]
        if status in (401, 403):
            msg = "the API key was refused. Check GEMINI_API_KEY in .env. " + msg
        raise GeminiError(f"Gemini error ({status}): {msg}")
    return data


def _text_of(response: dict) -> str:
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise GeminiError("Gemini returned no answer. Try again.")
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _parse_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
        if start >= 0:
            end = max(text.rfind("}"), text.rfind("]"))
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise GeminiError("Gemini's answer could not be read. Try again.")


def _json_call(parts: list, schema: dict, temperature: float = 0.2):
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    return _parse_json(_text_of(_generate(config.GEMINI_MODEL, body)))


# ---------------------------------------------------------------- ordering

ORDER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "transcript": {"type": "STRING"},
        "intent": {"type": "STRING", "enum": ["order", "budget", "bill", "waiter", "unknown"]},
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"id": {"type": "INTEGER"}, "qty": {"type": "INTEGER"}},
                "required": ["id", "qty"],
            },
        },
        "budget_rupees": {"type": "NUMBER", "nullable": True},
        "people": {"type": "INTEGER", "nullable": True},
        "reply": {"type": "STRING"},
    },
    "required": ["transcript", "intent", "items", "reply"],
}


def understand_order(
    menu: list[dict],
    *,
    audio_wav: bytes | None = None,
    text: str | None = None,
    allow_budget: bool = True,
    allow_actions: bool = True,
) -> dict:
    menu_lines = "\n".join(
        f'{m["id"]} | {m["name"]}' + (f' / {m["name_local"]}' if m.get("name_local") else "")
        + f' | {m["category"]} | Rs {m["price_paise"] / 100:g}'
        for m in menu
    )
    intents = ["order"]
    if allow_budget:
        intents.append("budget")
    if allow_actions:
        intents += ["bill", "waiter"]
    prompt = f"""You are the friendly ordering assistant at an Indian restaurant table.
The guest may speak or type in Kannada, Hindi, English, or a mix (e.g. "2 masala dosa, 1 filter coffee",
"ಎರಡು ಮಸಾಲೆ ದೋಸೆ", "do chai aur ek samosa").

MENU (id | name / local name | category | price):
{menu_lines}

Decide the intent. Allowed intents: {", ".join(intents)}, unknown.
- order: the guest names dishes. Map each to the closest menu id (handle spelling, accents, local names,
  plurals). Default qty is 1. Only use ids from the menu. Skip dishes that are not on the menu and mention
  that in the reply.
- budget: the guest gives a money amount and/or number of people ("Rs 800, dinner for 4"). Build a sensible,
  balanced meal whose total is AT MOST budget_rupees (mains, a side or bread, drinks). Set budget_rupees
  and people.
- bill: the guest wants the bill / to pay.
- waiter: the guest wants a waiter / help / water / cutlery.
- unknown: anything else.
Write "transcript" as exactly what the guest said (in their script). Write "reply" as ONE short, warm sentence
in the same language the guest used, confirming what you understood. Return JSON only."""
    parts: list = [{"text": prompt}]
    if audio_wav:
        parts.append({"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(audio_wav).decode()}})
        parts.append({"text": "The guest's voice message is attached above."})
    if text:
        parts.append({"text": f'The guest typed: "{text}"'})
    result = _json_call(parts, ORDER_SCHEMA)
    if not isinstance(result, dict):
        raise GeminiError("Gemini's answer could not be read. Try again.")
    return result


# ---------------------------------------------------------------- menu photo

MENU_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING"},
            "name_local": {"type": "STRING"},
            "category": {"type": "STRING"},
            "price_rupees": {"type": "NUMBER"},
        },
        "required": ["name", "category", "price_rupees"],
    },
}


def read_menu_photo(image: bytes, mime_type: str) -> list[dict]:
    prompt = """This is a photo of a restaurant's paper menu (it may be in English, Kannada, Hindi or mixed).
Extract every dish with its price.
- name: the dish name in English (transliterate if it is written in another script).
- name_local: the name in the local script if the menu shows one, else "".
- category: the menu section (e.g. "Breakfast", "Dosa", "Beverages", "Meals"); invent a sensible one if none.
- price_rupees: the price as a number. If a dish has several sizes, make one entry per size, e.g. "Lassi (Large)".
Skip anything without a price. Return JSON only."""
    parts = [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image).decode()}},
    ]
    result = _json_call(parts, MENU_SCHEMA, temperature=0.1)
    if isinstance(result, dict):
        result = result.get("items") or result.get("menu") or []
    items = []
    for it in result if isinstance(result, list) else []:
        try:
            price = float(it.get("price_rupees") or 0)
        except (TypeError, ValueError):
            continue
        name = str(it.get("name") or "").strip()
        if not name or price <= 0:
            continue
        items.append(
            {
                "name": name[:80],
                "name_local": str(it.get("name_local") or "").strip()[:80],
                "category": (str(it.get("category") or "Menu").strip() or "Menu")[:40],
                "price_paise": int(round(price * 100)),
            }
        )
    return items


# ---------------------------------------------------------------- text to speech

def _pcm_to_wav(pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * width, channels * width, width * 8))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()


_tts_cache: dict[str, bytes] = {}


def speak(text: str) -> bytes:
    if text in _tts_cache:
        return _tts_cache[text]
    body = {
        # Send only the words to speak: the TTS model returns no audio (finishReason OTHER)
        # when an instruction is wrapped around non-English text.
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": config.GEMINI_TTS_VOICE}}},
        },
    }
    pcm = mime = None
    for _attempt in range(3):  # the preview TTS model often returns an empty answer at random; retry
        response = _generate(config.GEMINI_TTS_MODEL, body, timeout=30)
        try:
            part = response["candidates"][0]["content"]["parts"][0]
            inline = part.get("inlineData") or part.get("inline_data")
            pcm = base64.b64decode(inline["data"])
            mime = inline.get("mimeType") or inline.get("mime_type") or ""
            break
        except (KeyError, IndexError, TypeError):
            continue
    if not pcm:
        raise GeminiError("Gemini returned no audio.")
    rate_match = re.search(r"rate=(\d+)", mime)
    wav = pcm if pcm[:4] == b"RIFF" else _pcm_to_wav(pcm, int(rate_match.group(1)) if rate_match else 24000)
    if len(_tts_cache) > 200:
        _tts_cache.clear()
    _tts_cache[text] = wav
    return wav
