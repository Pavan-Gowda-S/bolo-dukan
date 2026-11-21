"""Download the photos listed in app/data/photos.json into static/img/photos/ (500 px wide JPEGs).

    .venv\\Scripts\\python.exe scripts\\localize_photos.py

Hot-linked Wikimedia thumbnails can be slow or refused; local copies load fast and work without internet.
The licence, author and source page stay in photos.json and are shown on /credits.
Already-downloaded files are skipped, so you can run this again after fetch_photos.py finds more.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data" / "photos.json"
OUT = ROOT / "static" / "img" / "photos"
UA = "BoloDukaanPhotoFinder/1.0 (open-source restaurant demo)"


def file_name(key: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", key.lower()).strip("_") + ".jpg"


def small_url(thumb: str) -> str:
    """Ask Wikimedia for a standard 500 px thumbnail instead of the 640/960 px one."""
    return re.sub(r"/(\d+)px-([^/]+)$", r"/500px-\2", thumb.split("?")[0])


def fetch(url: str) -> bytes:
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if "429" in str(e) and attempt < 3:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    raise RuntimeError("gave up")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    photos = json.loads(DATA.read_text(encoding="utf-8"))
    ok = bad = 0
    for key, p in photos.items():
        name = file_name(key)
        dest = OUT / name
        if not dest.exists():
            data = None
            for url in dict.fromkeys([small_url(p["thumb"]), p["thumb"]]):
                try:
                    data = fetch(url)
                    break
                except Exception as e:
                    print("  failed", key, url[:80], e)
            if not data or len(data) < 2000 or data[:2] not in (b"\xff\xd8", b"\x89P"):
                bad += 1
                continue
            dest.write_bytes(data)
            time.sleep(0.8)
        p["local"] = f"/static/img/photos/{name}"
        ok += 1
    DATA.write_text(json.dumps(photos, ensure_ascii=False, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.glob("*.jpg")) / 1e6
    print(f"saved {ok} photos locally ({size:.1f} MB), {bad} failed (those stay hot-linked)")


if __name__ == "__main__":
    main()
