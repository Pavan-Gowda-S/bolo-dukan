"""Check the Sarvam key and every Sarvam call the app uses.

    .venv\\Scripts\\python.exe scripts\\check_sarvam.py                # chat + Kannada TTS + STT
    .venv\\Scripts\\python.exe scripts\\check_sarvam.py menu.jpg       # ...and read a menu photo/PDF
"""
import mimetypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app import config, sarvam  # noqa: E402


def step(name, fn):
    t = time.time()
    try:
        out = fn()
        print(f"  [OK]   {name} ({time.time() - t:.1f}s): {out}")
        return True
    except sarvam.SarvamError as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def main() -> int:
    print(f"\n  Sarvam check  (STT {config.SARVAM_STT_MODEL}, TTS {config.SARVAM_TTS_MODEL}/{config.SARVAM_TTS_SPEAKER}, "
          f"LLM {config.SARVAM_LLM_MODEL})\n")
    if not config.sarvam_ready():
        print("  [FAIL] SARVAM_API_KEY is empty in .env\n")
        return 1
    ok = True
    ok &= step("chat (JSON)", lambda: sarvam.extract_json(sarvam.chat(
        [{"role": "system", "content": 'Reply with ONE JSON object only: {"intent": string, "items": [{"name": string, "qty": integer}]}'},
         {"role": "user", "content": "eradu masala dose, ondu filter coffee"}], json_mode=True)))
    out = config.DATA_DIR / "kn_test.wav"

    def do_tts():
        wav = sarvam.tts("ಟೇಬಲ್ 5, ಹೊಸ ಆರ್ಡರ್.", "kn-IN")
        out.write_bytes(wav)
        return f"saved {out} ({len(wav) // 1024} KB)"
    tts_ok = step("Kannada text-to-speech", do_tts)
    ok &= tts_ok
    if tts_ok:
        ok &= step("speech-to-text (reading that audio back)",
                   lambda: sarvam.stt(out.read_bytes(), "kn_test.wav", "audio/wav", "kn-IN"))
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        ok &= step(f"document reading ({p.name})",
                   lambda: sarvam.digitise_document(p.read_bytes(), p.name, ctype)[:300].replace("\n", " | "))
    print("\n  All good.\n" if ok else "\n  Some checks failed (the app falls back to Gemini or taps).\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
