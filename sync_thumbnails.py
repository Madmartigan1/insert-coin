#!/usr/bin/env python3
"""Download missing RetroArch thumbnails (box art, snaps, titles) for every playlist.

Usage:  python3 sync_thumbnails.py --dry   # show what would be downloaded
        python3 sync_thumbnails.py         # download

Looks up each playlist entry's label on thumbnails.libretro.com: exact name first,
then a fuzzy match ignoring (tags)/[tags]/punctuation, preferring the same region.
Only fills in missing images; never overwrites existing ones. MAME* playlists use
the shared "MAME" thumbnail folder, like RetroArch does.
"""
import json, os, re, sys, glob, html, urllib.parse, urllib.request, concurrent.futures as cf
import time
from paths import RA, THUMB_SYNC_CACHE as S
BASE = "https://thumbnails.libretro.com"; TYPES = ["Named_Boxarts", "Named_Snaps", "Named_Titles"]
DRY = "--dry" in sys.argv
os.makedirs(f"{S}/idx", exist_ok=True)
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "retroarch-thumb-sync"})
    with urllib.request.urlopen(req, timeout=60) as r: return r.read()
def sanitize(s): return re.sub(r'[&*/:`<>?\\|"]', "_", s)
def key(s):
    s = s.lower().replace("_", " ")
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s)
    s = re.sub(r"\bthe\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)
UNIT = {"K": 1e3, "M": 1e6, "G": 1e9}
def index(system, t):
    cache = f"{S}/idx/{sanitize(system)}__{t}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400: return json.load(open(cache))
    try: page = get(f"{BASE}/{urllib.parse.quote(system)}/{t}/").decode("utf-8", "replace")
    except Exception as e: print("  no index", system, t, e); return {}
    out = {}
    for href, size in re.findall(r'<a href="([^"?/][^"]*\.png)">.*?</a></td><td[^>]*>[^<]*</td><td[^>]*>\s*([\d.]+[KMG]?)', page):
        name = html.unescape(urllib.parse.unquote(href))[:-4]
        out[name] = float(size[:-1]) * UNIT[size[-1]] if size[-1] in UNIT else float(size)
    json.dump(out, open(cache, "w")); return out
BAD = re.compile(r"\((?:[^)]*\b(?:Demo|Beta|Proto|Sample|Kiosk|Hack|Pirate)\b[^)]*)\)", re.I)
def rank(n, label=""):
    lab = re.search(r"\b(USA|World|Europe|Japan|Brazil|Korea|Asia)\b", label)
    order = ([lab.group(1)] if lab else []) + ["USA", "World", "Europe", "Japan"]
    for i, r in enumerate(order):
        if re.search(rf"\([^)]*\b{r}\b", n): return (bool(BAD.search(n)), i, len(n))
    return (bool(BAD.search(n)), 9, len(n))
jobs = []; stats = {}
for pl in sorted(glob.glob(f"{RA}/playlists/*.lpl")):
    items = json.load(open(pl))["items"]
    for it in items:
        db = (it.get("db_name") or os.path.basename(pl))[:-4]
        system = "MAME" if db.startswith("MAME") else db
        st = stats.setdefault(system, {"have": 0, "exact": 0, "fuzzy": 0, "none": 0, "bytes": 0})
        for t in TYPES:
            idx = index(system, t)
            if f"_k_{system}_{t}" not in globals():
                km = {}
                for n in idx: km.setdefault(key(n), []).append(n)
                globals()[f"_k_{system}_{t}"] = km
            km = globals()[f"_k_{system}_{t}"]
            local = f"{RA}/thumbnails/{system}/{t}/{sanitize(it['label'])}.png"
            if os.path.exists(local): st["have"] += 1; continue
            src = sanitize(it["label"])
            if src in idx: st["exact"] += 1
            elif km.get(key(it["label"])): src = sorted(km[key(it["label"])], key=lambda n: rank(n, it["label"]))[0]; st["fuzzy"] += 1
            else: st["none"] += 1; continue
            if any(j[1] == local for j in jobs): continue
            st["bytes"] += idx[src]; jobs.append((f"{BASE}/{urllib.parse.quote(system)}/{t}/{urllib.parse.quote(src)}.png", local))
for k, v in stats.items(): print(f"{k:50} have {v['have']:5}  exact {v['exact']:5}  fuzzy {v['fuzzy']:5}  not-on-server {v['none']:5}  ~{v['bytes']/1e6:.0f} MB")
print("TOTAL downloads:", len(jobs), f"~{sum(v['bytes'] for v in stats.values())/1e6:.0f} MB")
if DRY: sys.exit()
def dl(j):
    url, local = j
    try:
        data = get(url); os.makedirs(os.path.dirname(local), exist_ok=True)
        if not data.startswith(b"\x89PNG"): return "notpng"
        tmp = local + ".part"; open(tmp, "wb").write(data); os.replace(tmp, local); return "ok"
    except Exception as e: return "err"
res = {}
with cf.ThreadPoolExecutor(6) as ex:
    for i, r in enumerate(ex.map(dl, jobs)):
        res[r] = res.get(r, 0) + 1
        if i % 500 == 0: print(i, res, flush=True)
print("done", res)
