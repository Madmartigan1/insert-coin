#!/usr/bin/env python3
"""Download missing thumbnails (box art, snaps, titles) for every RetroArch playlist,
and for the games in Insert Coin's own library (library.json: e.g. games added by --scan --add).
New pictures go into Insert Coin's own art folder (~/.local/share/insert-coin/thumbnails/); a game
counts as having a picture when either that folder or RetroArch's has it.

Usage:  python3 sync_thumbnails.py --dry   # show what would be downloaded
        python3 sync_thumbnails.py         # download

Looks up each playlist entry's label on thumbnails.libretro.com: exact name first,
then a fuzzy match ignoring (tags)/[tags]/punctuation, preferring the same region.
Only fills in missing images; never overwrites existing ones. MAME* playlists use
the shared "MAME" thumbnail folder, like RetroArch does.

When thumbnails.libretro.com doesn't answer with its file lists (it returned empty pages and 404s on
2026-11-25), the same pictures come from the libretro-thumbnails repositories on GitHub
(https://github.com/libretro-thumbnails), which the server is built from: one request per system for the
file list (GitHub allows 60 an hour without an account), the pictures from raw.githubusercontent.com.
"""
import json, os, re, sys, glob, html, urllib.parse, urllib.request, concurrent.futures as cf
import time
from paths import LIBRARY, RA, RA_THUMBNAILS, THUMBNAILS, THUMB_SYNC_CACHE as S
BASE = "https://thumbnails.libretro.com"; TYPES = ["Named_Boxarts", "Named_Snaps", "Named_Titles"]
GH_API = "https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/master?recursive=1"
GH_RAW = "https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/{t}/{name}.png"
SOURCE = {}                                           # (system, type) -> "server" or "github": where its pictures come from
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
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400:
        got = json.load(open(cache))
        if set(got) == {"source", "files"}: SOURCE[(system, t)] = got["source"]; return got["files"]
        SOURCE[(system, t)] = "server"; return got                     # a list saved before 0.8.3: the server's
    out = {}
    try:
        page = get(f"{BASE}/{urllib.parse.quote(system)}/{t}/").decode("utf-8", "replace")
        for href, size in re.findall(r'<a href="([^"?/][^"]*\.png)">.*?</a></td><td[^>]*>[^<]*</td><td[^>]*>\s*([\d.]+[KMG]?)', page):
            name = html.unescape(urllib.parse.unquote(href))[:-4]
            out[name] = float(size[:-1]) * UNIT[size[-1]] if size[-1] in UNIT else float(size)
    except Exception as e: print("  no list from the art server:", system, t, e)
    source = "server"
    if not out:                                       # the server didn't answer: GitHub has the same pictures
        out, source = github_index(system, t), "github"
    SOURCE[(system, t)] = source
    if out: json.dump({"source": source, "files": out}, open(cache, "w"))
    return out
def github_index(system, t):
    """{picture name: bytes} for one system and type from the libretro-thumbnails repository on GitHub (the whole
    repository's file list is fetched once and cached)."""
    repo = system.replace(" ", "_")
    cache = f"{S}/idx/github__{sanitize(repo)}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400: tree = json.load(open(cache))
    else:
        try: tree = json.loads(get(GH_API.format(repo=urllib.parse.quote(repo))))["tree"]
        except Exception as e: print("  no list on GitHub either:", system, e); return {}
        tree = [[x["path"], x.get("size", 0)] for x in tree if x.get("type") == "blob" and x["path"].endswith(".png")]
        json.dump(tree, open(cache, "w"))
    return {p[len(t) + 1:-4]: size for p, size in tree if p.startswith(t + "/")}
def picture_url(system, t, name):
    if SOURCE.get((system, t)) == "github":
        return GH_RAW.format(repo=urllib.parse.quote(system.replace(" ", "_")), t=t, name=urllib.parse.quote(name))
    return f"{BASE}/{urllib.parse.quote(system)}/{t}/{urllib.parse.quote(name)}.png"
BAD = re.compile(r"\((?:[^)]*\b(?:Demo|Beta|Proto|Sample|Kiosk|Hack|Pirate)\b[^)]*)\)", re.I)
def rank(n, label=""):
    lab = re.search(r"\b(USA|World|Europe|Japan|Brazil|Korea|Asia)\b", label)
    order = ([lab.group(1)] if lab else []) + ["USA", "World", "Europe", "Japan"]
    for i, r in enumerate(order):
        if re.search(rf"\([^)]*\b{r}\b", n): return (bool(BAD.search(n)), i, len(n))
    return (bool(BAD.search(n)), 9, len(n))
def games():
    """(playlist, label) of every game: RetroArch's playlists, then Insert Coin's own library (each once)."""
    seen = set()
    def once(db, label):
        if label and (db, label) not in seen: seen.add((db, label)); return [(db, label)]
        return []
    out = []
    for pl in sorted(glob.glob(f"{RA}/playlists/*.lpl")):
        for it in json.load(open(pl))["items"]:
            out += once((it.get("db_name") or os.path.basename(pl))[:-4], it.get("label"))
    try:
        with open(LIBRARY, encoding="utf-8") as f: lib = json.load(f)
        for sy in lib.get("systems", []):
            for g in sy.get("games", []): out += once((g.get("db") or sy["name"] + ".lpl")[:-4], g.get("label"))
    except (OSError, ValueError): pass                        # no library of its own (yet)
    return out
jobs = []; stats = {}
for db, label in games():
    it = {"label": label}
    system = "MAME" if db.startswith("MAME") else db
    st = stats.setdefault(system, {"have": 0, "exact": 0, "fuzzy": 0, "none": 0, "bytes": 0})
    for t in TYPES:
        idx = index(system, t)
        if f"_k_{system}_{t}" not in globals():
            km = {}
            for n in idx: km.setdefault(key(n), []).append(n)
            globals()[f"_k_{system}_{t}"] = km
        km = globals()[f"_k_{system}_{t}"]
        rel = f"{system}/{t}/{sanitize(it['label'])}.png"
        local = f"{THUMBNAILS}/{rel}"                          # new pictures go to Insert Coin's own art folder
        if os.path.exists(local) or os.path.exists(f"{RA_THUMBNAILS}/{rel}"): st["have"] += 1; continue
        src = sanitize(it["label"])
        if src in idx: st["exact"] += 1
        elif km.get(key(it["label"])): src = sorted(km[key(it["label"])], key=lambda n: rank(n, it["label"]))[0]; st["fuzzy"] += 1
        else: st["none"] += 1; continue
        if any(j[1] == local for j in jobs): continue
        st["bytes"] += idx[src]; jobs.append((picture_url(system, t, src), local))
for k, v in stats.items(): print(f"{k:50} have {v['have']:5}  exact {v['exact']:5}  fuzzy {v['fuzzy']:5}  not-on-server {v['none']:5}  ~{v['bytes']/1e6:.0f} MB")
print("TOTAL downloads:", len(jobs), f"~{sum(v['bytes'] for v in stats.values())/1e6:.0f} MB")
if DRY: sys.exit()
def dl(j):
    url, local = j
    try:
        data = get(url); os.makedirs(os.path.dirname(local), exist_ok=True)
        if not data.startswith(b"\x89PNG") and len(data) < 400 and data.strip().endswith(b".png") and "githubusercontent" in url:
            target = data.decode("utf-8", "replace").strip()           # a link in the repository: the same picture
            data = get(urllib.parse.urljoin(url, urllib.parse.quote(target)))
        if not data.startswith(b"\x89PNG"): return "notpng"
        tmp = local + ".part"; open(tmp, "wb").write(data); os.replace(tmp, local); return "ok"
    except Exception as e: return "err"
res = {}
with cf.ThreadPoolExecutor(6) as ex:
    for i, r in enumerate(ex.map(dl, jobs)):
        res[r] = res.get(r, 0) + 1
        if i % 500 == 0: print(i, res, flush=True)
print("done", res)
