"""One door to the AI providers: Sarvam first, Gemini as backup. Every function raises AIError on failure,
so routes can show a friendly message and let people carry on with taps and forms."""
from . import config, gemini, sarvam


class AIError(Exception):
    pass


def _run(sarvam_fn, gemini_fn):
    errors = []
    if config.sarvam_ready():
        try:
            return sarvam_fn()
        except sarvam.SarvamError as e:
            errors.append(str(e))
    if config.gemini_ready() and gemini_fn is not None:
        try:
            return gemini_fn()
        except gemini.GeminiError as e:
            errors.append(str(e))
    if not errors:
        raise AIError("AI isn't set up. Add SARVAM_API_KEY (or GEMINI_API_KEY) to .env.")
    print("  AI error:", " | ".join(errors))
    raise AIError(errors[-1])


def stt(audio: bytes, filename: str, content_type: str, language: str | None = None) -> dict:
    return _run(lambda: sarvam.stt(audio, filename, content_type, language),
                lambda: {"transcript": gemini.transcribe(audio, content_type if content_type.startswith("audio/") else "audio/wav"),
                         "language_code": language})


def chat(messages: list[dict], json_mode: bool = False) -> str:
    return _run(lambda: sarvam.chat(messages, json_mode), lambda: gemini.chat_text(messages, json_mode))


def chat_json(messages: list[dict]):
    text = chat(messages, json_mode=True)
    try:
        return sarvam.extract_json(text)
    except sarvam.SarvamError as e:
        raise AIError(str(e))


def tts(text: str, language_code: str) -> bytes:
    gem = (lambda: gemini.speak(text)) if config.FEATURE_GEMINI_TTS else None
    return _run(lambda: sarvam.tts(text, language_code), gem)


def read_document(data: bytes, filename: str, content_type: str, language: str) -> str:
    return _run(lambda: sarvam.digitise_document(data, filename, content_type, language),
                lambda: gemini.read_document_text(data, content_type))
