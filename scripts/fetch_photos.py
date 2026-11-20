"""Find real, freely licensed photos on Wikimedia Commons for recipes, grocery items and menu dishes.

    .venv\\Scripts\\python.exe scripts\\fetch_photos.py

Writes app/data/photos.json: {key: {thumb, page, author, license, title}}. Keys: "recipe:<id>", "ingredient:<id>".
Only CC0 / public domain / CC BY / CC BY-SA images are kept, and the author + licence are stored for credits.
Images are hot-linked from upload.wikimedia.org (Wikimedia allows this), so phones need internet to see them.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
API = "https://commons.wikimedia.org/w/api.php"
UA = "BoloDukaanPhotoFinder/1.0 (open-source restaurant demo)"
OK_LICENSE = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? [0-9.]+|cc by(-sa)?)", re.I)
BAD_WORDS = re.compile(r"(logo|map|diagram|chart|icon|stamp|flag|svg|drawing|illustration|seal|coat of arms)", re.I)

# better search words for some items (Commons titles)
QUERY = {
    "ingredient:atta": "whole wheat flour", "ingredient:maida": "all-purpose flour bowl", "ingredient:rava": "semolina",
    "ingredient:besan": "gram flour", "ingredient:poha": "flattened rice poha", "ingredient:toor_dal": "toor dal",
    "ingredient:moong_dal": "moong dal", "ingredient:urad_dal": "urad dal", "ingredient:chana_dal": "chana dal",
    "ingredient:masoor_dal": "masoor dal red lentils", "ingredient:green_moong": "mung beans", "ingredient:kabuli_chana": "chickpeas",
    "ingredient:curd": "dahi curd bowl", "ingredient:hing": "asafoetida", "ingredient:bhindi": "okra", "ingredient:brinjal": "brinjal eggplant",
    "ingredient:bottle_gourd": "bottle gourd", "ingredient:methi_leaves": "fenugreek leaves", "ingredient:curry_leaves": "curry leaves",
    "ingredient:coriander_leaves": "coriander leaves", "ingredient:sambar_powder": "sambar powder", "ingredient:rasam_powder": "rasam powder",
    "ingredient:garam_masala": "garam masala", "ingredient:chole_masala": "chana masala spice", "ingredient:pav_bhaji_masala": "pav bhaji masala",
    "ingredient:biryani_masala": "biryani masala", "ingredient:tandoori_masala": "tandoori masala", "ingredient:soya_chunks": "soya chunks",
    "ingredient:pav": "pav bread", "ingredient:gulab_jamun_mix": "gulab jamun", "ingredient:biscuits": "marie biscuits",
    "ingredient:coffee_powder": "filter coffee powder", "ingredient:tea_powder": "black tea leaves", "ingredient:roasted_chana": "roasted chickpeas",
    "ingredient:jaggery": "jaggery", "ingredient:tamarind": "tamarind", "ingredient:oil": "sunflower oil bottle", "ingredient:chicken": "raw chicken meat",
    "ingredient:mutton": "raw mutton meat", "ingredient:fish": "seer fish", "ingredient:prawns": "prawns", "ingredient:egg": "chicken eggs",
    "ingredient:milk": "glass of milk", "ingredient:ghee": "ghee", "ingredient:paneer": "paneer", "ingredient:noodles": "dry noodles",
    "ingredient:dry_red_chilli": "dried red chillies", "ingredient:chilli_powder": "chili powder", "ingredient:green_chilli": "green chillies",
    "ingredient:rice": "white rice grains", "ingredient:basmati_rice": "basmati rice", "ingredient:rice_flour": "rice flour",
    "ingredient:ragi_flour": "finger millet flour", "ingredient:oats": "rolled oats", "ingredient:vermicelli": "vermicelli",
    "recipe:south_indian_meals": "south indian meals banana leaf", "recipe:ragi_mudde": "ragi mudde", "recipe:majjige_huli": "majjige huli",
    "recipe:kootu": "kootu", "recipe:beans_palya": "beans poriyal", "recipe:cabbage_palya": "cabbage poriyal", "recipe:potato_palya": "potato curry south indian",
    "recipe:chow_chow_bath": "chow chow bath", "recipe:khara_bath": "khara bath", "recipe:kesari_bath": "kesari bath",
    "recipe:goli_baje": "goli baje", "recipe:mangalore_buns": "mangalore buns", "recipe:egg_rice_bowl": "egg pepper fry",
    "recipe:phulka_dal_combo": "roti dal", "recipe:paneer_rice_bowl": "paneer fried rice", "recipe:baked_veg_pasta": "mushroom toast",
    "recipe:kettle_poha": "poha", "recipe:rice_cooker_khichdi": "khichdi", "recipe:toast_egg_bhurji": "egg bhurji toast",
    "recipe:egg_curry_rice": "egg biryani", "recipe:air_fryer_chana": "roasted chickpeas", "recipe:peanut_poha_chivda": "poha chivda",
    "recipe:curd_oats_bowl": "oats yogurt bowl", "recipe:moong_soup": "lentil soup", "recipe:tofu_stir_fry": "tofu stir fry",
    "recipe:soya_pulao": "pulao", "recipe:chana_sundal": "sundal", "recipe:lime_soda": "lime soda", "recipe:plain_rice": "steamed rice bowl",
    "recipe:idli_vada": "idli vada", "recipe:dhokla": "dhokla", "recipe:aloo_tikki": "aloo tikki", "recipe:fish_tikka": "fish tikka",
}


def search(query: str):
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": "6", "gsrlimit": "8", "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
              "iiurlwidth": "640"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        title = p.get("title", "")
        if info.get("mime") not in ("image/jpeg", "image/png") or not OK_LICENSE.match(lic.strip()) or BAD_WORDS.search(title):
            continue
        if (info.get("thumbwidth") or 0) < 300:
            continue
        author = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()[:80] or "Unknown"
        return {"thumb": info.get("thumburl"), "page": info.get("descriptionurl"), "author": author, "license": lic, "title": title}
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    recipes = json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))
    ingredients = json.loads((DATA / "ingredients.json").read_text(encoding="utf-8"))
    out_path = DATA / "photos.json"
    photos = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    jobs = [(f"recipe:{r['id']}", re.sub(r"\(.*?\)", "", r["name"]).strip()) for r in recipes]
    jobs += [(f"ingredient:{i['id']}", re.sub(r"\(.*?\)", "", i["name"]).strip()) for i in ingredients]
    found = missing = 0
    for key, name in jobs:
        if key in photos:
            found += 1
            continue
        q = QUERY.get(key, name)
        try:
            hit = search(q) or (search(name) if q != name else None)
        except Exception as e:
            print("  error", key, e)
            hit = None
        if hit:
            photos[key] = hit
            found += 1
        else:
            missing += 1
            print("  no photo:", key, "(", q, ")")
        time.sleep(0.25)
    out_path.write_text(json.dumps(photos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"photos: {found} found, {missing} without a photo (they use an emoji). Saved {out_path}")


if __name__ == "__main__":
    main()
