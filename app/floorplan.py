"""Blueprint layout: clean up what the AI read from a floor plan, and match it to the restaurant's tables.

Pure functions (no HTTP, no AI) so they are easy to test. Coordinates in a layout are % of the image (0-100).
The AI only *proposes* a layout; the owner sees it and taps Apply before anything is saved.
"""
import re

ROOM_TYPES = ("kitchen", "dining", "cashier", "store", "restroom", "entrance", "outdoor", "bar", "office", "other")
COUNTER_KINDS = ("cashier", "kitchen", "bar", "serving", "other")
MAX_ROOMS, MAX_COUNTERS, MAX_TABLES, MAX_WALLS = 30, 40, 80, 160


def _num(v, lo=0.0, hi=1000.0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return max(lo, min(hi, x))


def _box(b) -> dict | None:
    """Gemini box_2d [ymin, xmin, ymax, xmax] on 0-1000 -> {x, y, w, h} in %. Rejects empty or tiny boxes."""
    if not isinstance(b, (list, tuple)) or len(b) != 4:
        return None
    ymin, xmin, ymax, xmax = (_num(v) for v in b)
    if None in (ymin, xmin, ymax, xmax):
        return None
    if ymax < ymin:
        ymin, ymax = ymax, ymin
    if xmax < xmin:
        xmin, xmax = xmax, xmin
    if xmax - xmin < 5 or ymax - ymin < 5:  # under 0.5 % of the image: noise
        return None
    return {"x": round(xmin / 10, 2), "y": round(ymin / 10, 2), "w": round((xmax - xmin) / 10, 2), "h": round((ymax - ymin) / 10, 2)}


def _label(v, n=30) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


ROOM_WORDS = (("kitchen", ("kitchen", "cook")), ("store", ("store", "cold", "pantry", "storage")),
              ("restroom", ("restroom", "toilet", "wash room", "washroom", "wc", "bath")), ("cashier", ("cashier", "billing", "counter area")),
              ("entrance", ("entrance", "entry", "lobby")), ("bar", ("bar",)), ("office", ("office",)),
              ("outdoor", ("outdoor", "open-air", "open air", "parking", "garden")), ("dining", ("dining", "hall", "seating")))
COUNTER_WORDS = (("cashier", ("cashier", "billing", "pos")), ("serving", ("pass", "serving")), ("bar", ("bar",)),
                 ("kitchen", ("range", "stove", "tawa", "burner", "sink", "dish", "fridge", "prep", "grinder", "oven", "island", "hood")))


def _kind(label: str, words, default: str) -> str:
    low = (label or "").lower()
    for kind, keys in words:
        if any(k in low for k in keys):
            return kind
    return default


def _inside(px, py, r) -> bool:
    return r["x"] <= px <= r["x"] + r["w"] and r["y"] <= py <= r["y"] + r["h"]


def normalize_layout(raw) -> dict:
    """Validate and clamp an AI reading of a blueprint ({tables, rooms, counters} lists of box_2d + label).
    Anything malformed is dropped, never guessed. Walls are traced from the image pixels in the browser."""
    raw = raw if isinstance(raw, dict) else {}
    rooms = []
    for r in (raw.get("rooms") or [])[:MAX_ROOMS]:
        b = _box(r.get("box_2d")) if isinstance(r, dict) else None
        if b:
            label = _label(r.get("label")) or "Room"
            t = r.get("type") if r.get("type") in ROOM_TYPES else _kind(label, ROOM_WORDS, "other")
            rooms.append(dict(b, type=t, label=label.title() if label.islower() else label))
    counters = []
    for c in (raw.get("counters") or [])[:MAX_COUNTERS]:
        b = _box(c.get("box_2d")) if isinstance(c, dict) else None
        if b:
            label = _label(c.get("label"))
            k = c.get("kind") if c.get("kind") in COUNTER_KINDS else _kind(label, COUNTER_WORDS, "other")
            counters.append(dict(b, kind=k, label=label))
    tables = []
    cands = raw.get("tables") or []
    if cands and all(isinstance(x, list) for x in cands):  # several detection runs: pool their candidates
        cands = [t for run in cands for t in run]
    for t in cands[:MAX_TABLES * 3]:
        b = _box(t.get("box_2d")) if isinstance(t, dict) else None
        if not b:
            continue
        cx, cy = round(b["x"] + b["w"] / 2, 2), round(b["y"] + b["h"] / 2, 2)
        # a "table" inside a counter (stove burners, sink bowls) or inside a kitchen/store/restroom is not a dining table
        # a "table" on kitchen equipment (stove burners, sink bowls) is not a dining table. Room boxes from the AI are
        # too rough to filter with; the browser checks rooms and counters against the drawing itself.
        if any(_inside(cx, cy, c) for c in counters if c["kind"] == "kitchen"):
            continue
        try:
            seats = int(t.get("seats")) if t.get("seats") is not None else None
        except (TypeError, ValueError):
            seats = None
        if seats is not None and not 1 <= seats <= 20:
            seats = None
        shape = t.get("shape") if t.get("shape") in ("round", "rect") else None  # decided in the browser, which knows the image shape
        tables.append({"label": _label(t.get("label"), 12), "x": cx, "y": cy, "w": b["w"], "h": b["h"], "seats": seats, "shape": shape})
    # candidates from several runs: merge near-identical ones (same label, centres within 2 %). Different spots with
    # the same label stay as candidates; the browser keeps the one that matches a table drawn on the plan.
    uniq = []
    for t in tables:
        if not any(u["label"].upper() == t["label"].upper() and abs(u["x"] - t["x"]) < 2 and abs(u["y"] - t["y"]) < 2 for u in uniq):
            uniq.append(t)
    seen_r, rooms_u = set(), []
    for r in rooms:  # the same room twice: keep the first
        key = (r["type"], r["label"].lower())
        if key not in seen_r:
            seen_r.add(key)
            rooms_u.append(r)
    return {"rooms": rooms_u, "counters": counters, "tables": uniq, "walls": []}


def clean_saved_layout(layout) -> dict:
    """A layout sent back by the browser for saving: keep only the known keys, re-clamp numbers."""
    layout = layout if isinstance(layout, dict) else {}
    pct = lambda v: _num(v, 0, 100)  # noqa: E731

    def rect_ok(r):
        return all(pct(r.get(k)) is not None for k in ("x", "y", "w", "h"))
    rooms = [{"x": pct(r["x"]), "y": pct(r["y"]), "w": pct(r["w"]), "h": pct(r["h"]),
              "type": r.get("type") if r.get("type") in ROOM_TYPES else "other", "label": _label(r.get("label"))}
             for r in (layout.get("rooms") or [])[:MAX_ROOMS] if isinstance(r, dict) and rect_ok(r)]
    counters = [{"x": pct(c["x"]), "y": pct(c["y"]), "w": pct(c["w"]), "h": pct(c["h"]),
                 "kind": c.get("kind") if c.get("kind") in COUNTER_KINDS else "other", "label": _label(c.get("label"))}
                for c in (layout.get("counters") or [])[:MAX_COUNTERS] if isinstance(c, dict) and rect_ok(c)]
    walls = []
    for w in (layout.get("walls") or [])[:MAX_WALLS]:
        if isinstance(w, (list, tuple)) and len(w) >= 4 and None not in [pct(v) for v in w[:4]]:
            thick = _num(w[4], 0.1, 5) if len(w) > 4 and _num(w[4], 0.1, 5) is not None else 0.6
            walls.append([round(pct(v), 2) for v in w[:4]] + [round(thick, 2)])
    doors = [{"x": pct(d.get("x")), "y": pct(d.get("y")), "label": _label(d.get("label"))}
             for d in (layout.get("doors") or [])[:20] if isinstance(d, dict) and pct(d.get("x")) is not None and pct(d.get("y")) is not None]
    tables = [{"label": _label(t.get("label"), 12), "x": pct(t.get("x")), "y": pct(t.get("y")), "seats": t.get("seats") if isinstance(t.get("seats"), int) else None,
               "shape": "rect" if t.get("shape") == "rect" else "round", "w": pct(t.get("w")) or 4, "h": pct(t.get("h")) or 4}  # noqa: E501
              for t in (layout.get("tables") or [])[:MAX_TABLES] if isinstance(t, dict) and pct(t.get("x")) is not None and pct(t.get("y")) is not None]
    return {"rooms": rooms, "counters": counters, "walls": walls, "doors": doors, "tables": tables}
