"""Sarvam AI client: speech-to-text, text-to-speech, chat, and document reading (menu photos / PDFs).

Docs: https://docs.sarvam.ai  (auth header: api-subscription-key). The key never leaves the server.
"""
import base64
import json
import re
import time

from . import config
from .net import NetError, request, request_multipart

BASE = "https://api.sarvam.ai"


class SarvamError(Exception):
    pass


def _headers() -> dict:
    if not config.SARVAM_API_KEY:
        raise SarvamError("Sarvam is not set up. Add SARVAM_API_KEY to .env.")
    return {"api-subscription-key": config.SARVAM_API_KEY}


def _check(status: int, data, what: str):
    if status >= 300:
        msg = ""
        if isinstance(data, dict):
            err = data.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            msg = msg or data.get("message") or ""
        if status in (401, 403):
            msg = "the API key was refused. Check SARVAM_API_KEY in .env. " + (msg or "")
        raise SarvamError(f"Sarvam {what} failed ({status}): {(msg or str(data))[:200]}")
    if not isinstance(data, dict):
        raise SarvamError(f"Sarvam {what} returned an unexpected answer.")
    return data


# ---------------------------------------------------------------- speech to text

def stt(audio: bytes, filename: str = "voice.wav", content_type: str = "audio/wav", language: str | None = None) -> dict:
    """-> {"transcript": str, "language_code": str|None}. Sarvam accepts wav/webm/ogg/mp3 etc. (max 30 s)."""
    fields = {"model": config.SARVAM_STT_MODEL, "mode": "transcribe", "language_code": language or "unknown"}
    try:
        status, data = request_multipart(f"{BASE}/speech-to-text", fields, {"file": (filename, content_type, audio)},
                                         _headers(), timeout=config.SARVAM_TIMEOUT)
    except NetError:
        raise SarvamError("Could not reach Sarvam (speech-to-text).")
    data = _check(status, data, "speech-to-text")
    return {"transcript": str(data.get("transcript") or "").strip(), "language_code": data.get("language_code")}


# ---------------------------------------------------------------- text to speech

TTS_LANGS = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}


def _chunks(text: str, limit: int = 450) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for piece in re.split(r"(?<=[.!?।,])\s+", text):
        while len(piece) > limit:  # one very long sentence
            parts.append(piece[:limit]); piece = piece[limit:]
        if len(cur) + len(piece) + 1 > limit:
            parts.append(cur.strip()); cur = ""
        cur += " " + piece
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _join_wavs(wavs: list[bytes]) -> bytes:
    """Concatenate PCM WAV chunks that share a format (Sarvam returns plain 16-bit PCM WAV)."""
    if len(wavs) == 1:
        return wavs[0]
    pcm = b"".join(w[44:] for w in wavs)
    head = bytearray(wavs[0][:44])
    head[4:8] = (36 + len(pcm)).to_bytes(4, "little")
    head[40:44] = len(pcm).to_bytes(4, "little")
    return bytes(head) + pcm


_tts_cache: dict[tuple, bytes] = {}


def tts(text: str, language_code: str = "kn-IN") -> bytes:
    """-> WAV bytes. Long text is split into <=450-character chunks."""
    lang = language_code if language_code in TTS_LANGS else "en-IN"
    key = (text, lang)
    if key in _tts_cache:
        return _tts_cache[key]
    wavs = []
    for chunk in _chunks(text):
        body = {"text": chunk, "language_code": lang, "model": config.SARVAM_TTS_MODEL,
                "speaker": config.SARVAM_TTS_SPEAKER, "speech_sample_rate": 22050, "output_audio_codec": "wav"}
        try:
            status, data = request("POST", f"{BASE}/text-to-speech", body, _headers(), timeout=config.SARVAM_TIMEOUT)
        except NetError:
            raise SarvamError("Could not reach Sarvam (text-to-speech).")
        data = _check(status, data, "text-to-speech")
        audios = data.get("audios") or []
        if not audios:
            raise SarvamError("Sarvam returned no audio.")
        wavs.append(base64.b64decode("".join(audios)))
    wav = _join_wavs(wavs)
    if len(_tts_cache) > 300:
        _tts_cache.clear()
    _tts_cache[key] = wav
    return wav


# ---------------------------------------------------------------- chat

def chat(messages: list[dict], json_mode: bool = False, max_tokens: int = 1500) -> str:
    body = {"model": config.SARVAM_LLM_MODEL, "messages": messages, "temperature": 0,
            "reasoning_effort": None, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        status, data = request("POST", f"{BASE}/v1/chat/completions", body, _headers(),
                               timeout=max(config.SARVAM_TIMEOUT, 30))
        if status == 400 and json_mode:  # some models reject response_format: retry without it
            body.pop("response_format", None)
            status, data = request("POST", f"{BASE}/v1/chat/completions", body, _headers(),
                                   timeout=max(config.SARVAM_TIMEOUT, 30))
    except NetError:
        raise SarvamError("Could not reach Sarvam (chat).")
    data = _check(status, data, "chat")
    try:
        content = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        raise SarvamError("Sarvam chat returned no answer.")
    return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()


def extract_json(text: str):
    """First valid JSON object (or array) in an LLM reply."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except ValueError:
                continue
    raise SarvamError("Couldn't read the AI's answer.")


# ---------------------------------------------------------------- document reading (Doc AI)

def digitise_document(file_bytes: bytes, filename: str, content_type: str, language: str = "en-IN",
                      timeout: float = 90) -> str:
    """Menu photo / PDF -> markdown text. Async job: parse -> poll status -> results?format=md."""
    try:
        status, job = request_multipart(f"{BASE}/doc-ai/v1/job/parse", {"language": language},
                                        {"file": (filename, content_type, file_bytes)}, _headers(), timeout=40)
    except NetError:
        raise SarvamError("Could not reach Sarvam (document reading).")
    job = _check(status, job, "document reading")
    job_id = job.get("job_id")
    if not job_id:
        raise SarvamError("Sarvam did not start the document job.")
    deadline = time.time() + timeout
    state = str(job.get("status") or "").lower()
    while state not in ("completed", "partially_completed", "failed", "rejected"):
        if time.time() > deadline:
            raise SarvamError("Reading the menu took too long. Try a smaller or clearer photo.")
        time.sleep(2)
        try:
            status, info = request("GET", f"{BASE}/doc-ai/v1/job/{job_id}/status", None, _headers(), timeout=15)
        except NetError:
            continue
        info = _check(status, info, "document status")
        state = str(info.get("status") or "").lower()
    if state in ("failed", "rejected"):
        raise SarvamError("Sarvam couldn't read that document.")
    try:
        status, res = request("GET", f"{BASE}/doc-ai/v1/job/{job_id}/results?format=md", None, _headers(), timeout=30)
    except NetError:
        raise SarvamError("Could not download the document text from Sarvam.")
    res = _check(status, res, "document results")
    pages = []
    for doc in res.get("documents") or []:
        for page in doc.get("pages") or []:
            if page.get("content"):
                pages.append(str(page["content"]))
    text = "\n\n".join(pages).strip()
    if not text:
        raise SarvamError("No text was found in that document.")
    return text
