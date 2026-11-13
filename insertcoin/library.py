"""The game library: RetroArch's playlists, favorites and history, plus browser playlists."""
import collections, json, os, re, time
from paths import APPDIR, CONFDIR, RA
from insertcoin.systems import FRIENDLY, ORDER
from insertcoin.cores import core_short
from insertcoin.names import REGION_RANK, rom_stem, split_archive, tags, title_key
from insertcoin.games import Game
from insertcoin.web import WebGame, load_web_playlists


def save_names():
    """Names of every battery save (RetroArch's and Insert Coin's), to prefer the copy of a game you've played."""
    names = set()
    for d in (f"{RA}/saves", f"{APPDIR}/saves"):
        for root, _, files in os.walk(d):
            names.update(os.path.splitext(f)[0].lower() for f in files)
    return names


def dedupe(games, saves):
    """One entry per game. RetroArch names every copy of the same game identically, so copies kept in several
    folders (a main folder, a "top 100", ...) show once. The copy shown is the one with a save, else the one
    in the shallowest folder (usually the main collection), so its save keeps working."""
    best = {}
    for g in games:
        score = (rom_stem(g.path).lower() not in saves, g.path.count("/"), len(g.path))
        if g.label not in best or score < best[g.label][0]: best[g.label] = (score, g)
    return [g for _, g in best.values()]

def version_score(g, saves):
    """Lower is better: the copy you've played, then the USA / World release, then Europe, then Japan;
    translations, hacks, alternates, betas and protos after the clean dumps."""
    tagtext = " ".join(tags(g.label)).lower()
    region = next((r for pat, r in REGION_RANK if re.search(pat, tagtext)), 3)
    odd = bool(re.search(r"\[(tr|t[+-]|h|b|p|a|o)|pt-br|\balt\b|beta|proto|hack|sample|demo|\(t\)", g.label.lower()))
    return (rom_stem(g.path).lower() not in saves, odd, region, g.path.count("/"), len(g.label))

def group_versions(games, saves):
    """One entry per game title; the best version leads and carries the rest in .versions (shown with X)."""
    groups = collections.OrderedDict()
    for g in games: groups.setdefault((g.system, title_key(g.title)), []).append(g)
    # a name without its subtitle ("Star Pilot 2") joins the one game it starts ("Star Pilot II - Return of the Comet")
    by_short = collections.defaultdict(list)
    for (sysid, key), vs in groups.items():
        if " - " in vs[0].title: by_short[(sysid, title_key(vs[0].title.split(" - ")[0]))].append((sysid, key))
    for k in list(groups):
        if k in by_short and len(by_short[k]) == 1 and by_short[k][0] != k and " - " not in groups[k][0].title:
            groups[by_short[k][0]] += groups.pop(k)
    out = []
    for vs in groups.values():
        vs.sort(key=lambda g: version_score(g, saves))
        lead = vs[0]; lead.versions = vs if len(vs) > 1 else None; out.append(lead)
    return out


class Library:
    def __init__(self, one_per_game=True):
        self.one_per_game = one_per_game                            # False: every ROM in the playlists, as RetroArch lists them
        self.defaults = {}
        self.hidden = 0                                             # duplicate copies not shown
        self.systems = []          # list of dicts: id, name, maker, color, games, special
        self.load()

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f: return json.load(f)
        except Exception: return None

    def load(self):
        self.systems = []
        pls = {}
        pdir = f"{RA}/playlists"
        for f in sorted(os.listdir(pdir) if os.path.isdir(pdir) else []):
            if f.endswith(".lpl"):
                d = self._read(f"{RA}/playlists/{f}")
                if d: pls[f[:-4]] = d
        for name, d in pls.items():
            dc = d.get("default_core_path") or ""
            self.defaults[name + ".lpl"] = dc if dc and os.path.exists(dc) else None
        saves = save_names(); self.hidden = 0
        for name, d in sorted(pls.items(), key=lambda kv: (ORDER.get(kv[0], 99), kv[0])):
            games = [Game(it, name + ".lpl", self.defaults[name + ".lpl"]) for it in d.get("items", []) if it.get("path")]
            if not games: continue                                  # tidy: hide empty systems
            if self.one_per_game:
                n = len(games); games = dedupe(games, saves); self.hidden += n - len(games)
                games = group_versions(games, saves)
            games.sort(key=lambda g: g.key)
            fn, maker, col = FRIENDLY.get(name, (name.split(" - ")[-1], name.split(" - ")[0], (90, 100, 130)))
            self.systems.append({"id": name, "name": fn, "maker": maker, "color": col, "games": games, "special": None})
        web = load_web_playlists()                                  # browser games: after the systems
        self.systems += web
        self.web_index = {g.path: g for s in web for g in s["games"]}
        self.favorites_raw = (self._read(f"{RA}/content_favorites.lpl") or {"version": "1.5", "items": []})
        self.refresh_specials()

    # Browser games can't go into RetroArch's favorites / history (it can't open them), so Insert Coin keeps its
    # own: favorites, when each was played, and a short log of every launch, to slot them into Recently Played.
    STATE = "played.json"

    def _state(self):
        d = self._read(f"{CONFDIR}/{self.STATE}") or {}
        for k in ("favorites", "recent", "launches"): d.setdefault(k, [])
        return d

    def _save_state(self, d):
        os.makedirs(CONFDIR, exist_ok=True)
        tmp = f"{CONFDIR}/{self.STATE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, indent=1)
        os.replace(tmp, f"{CONFDIR}/{self.STATE}")

    def note_launch(self, g, t=None):
        """Every game started from Insert Coin, newest last (kept to 300). Browser games also go into 'recent'."""
        d = self._state(); t = t or time.time(); web = isinstance(g, WebGame)
        d["launches"] = (d["launches"] + [{"path": g.path, "web": web, "t": round(t)}])[-300:]
        if web: d["recent"] = ([{"path": g.path, "t": round(t)}] + [r for r in d["recent"] if r.get("path") != g.path])[:60]
        self._save_state(d)

    def _web_recent(self, rec, d):
        """Merge browser games into RetroArch's Recently Played: each goes in front of the games launched before
        it, counting the games started from Insert Coin since then (RetroArch's history has no times)."""
        launches = d["launches"]; ranked = [((i, 0), g) for i, g in enumerate(rec)]
        for r in d["recent"]:
            g = self.web_index.get(r.get("path"))
            if not g: continue
            newer = {x["path"] for x in launches if not x.get("web") and x.get("t", 0) > r.get("t", 0)}
            ranked.append(((min(len(newer), len(rec)) - 0.5, -r.get("t", 0)), g))
        return [g for _, g in sorted(ranked, key=lambda x: x[0])]

    def _special_games(self, items):
        out = []
        for it in items:
            if not it.get("path") or not os.path.exists(split_archive(it["path"])[0]): continue
            db = it.get("db_name") or ""
            out.append(Game(it, db, self.defaults.get(db)))
        return out

    def refresh_specials(self):
        self.systems = [s for s in self.systems if not s["special"]]
        hist = self._read(f"{RA}/content_history.lpl") or {"items": []}
        self.favorites_raw = self._read(f"{RA}/content_favorites.lpl") or {"version": "1.5", "items": []}
        fav = self._special_games(self.favorites_raw.get("items", []))
        fav = dedupe(fav, set()) if self.one_per_game else fav
        st = self._state() if self.web_index else None
        if st: fav += [self.web_index[p] for p in st["favorites"] if p in self.web_index]
        fav = sorted(fav, key=lambda g: g.key)
        seen, rec = set(), []
        for g in self._special_games(hist.get("items", [])):
            k = (g.db, g.label) if self.one_per_game else g.path
            if k not in seen: seen.add(k); rec.append(g)
        if st: rec = self._web_recent(rec, st)
        specials = []
        if fav: specials.append({"id": "favorites", "name": "Favorites", "maker": "Your picks", "color": (230, 180, 40), "games": fav, "special": "fav"})
        if rec: specials.append({"id": "recent", "name": "Recently Played", "maker": "Pick up where you left off", "color": (60, 170, 200), "games": rec[:60], "special": "recent"})
        self.systems = specials + self.systems
        self.fav_paths = {it.get("path") for it in self.favorites_raw.get("items", [])}
        self.fav_keys = {(it.get("db_name") or "", it.get("label")) for it in self.favorites_raw.get("items", [])}
        self.web_favs = set(st["favorites"]) if st else set()

    def is_fav(self, g):
        """A favorite, whichever copy of the game was starred."""
        if isinstance(g, WebGame): return g.path in self.web_favs
        return g.path in self.fav_paths or ((g.db or ""), g.label) in self.fav_keys

    def toggle_favorite(self, g):
        if isinstance(g, WebGame):
            d = self._state(); added = g.path not in d["favorites"]
            d["favorites"] = [p for p in d["favorites"] if p != g.path] + ([g.path] if added else [])
            self._save_state(d); self.web_favs = set(d["favorites"])
            return added
        items = self.favorites_raw.setdefault("items", [])
        same = lambda it: it.get("path") == g.path or ((it.get("db_name") or ""), it.get("label")) == ((g.db or ""), g.label)
        if self.is_fav(g):
            items[:] = [it for it in items if not same(it)]; added = False
        else:
            items.append({"path": g.path, "label": g.label, "core_path": g.core or "DETECT",
                          "core_name": "DETECT" if not g.core else core_short(g.core),
                          "crc32": "00000000|crc", "db_name": g.db or ""}); added = True
        self.favorites_raw.setdefault("version", "1.5")
        p = f"{RA}/content_favorites.lpl"; tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.favorites_raw, f, indent=2)
        os.replace(tmp, p)
        self.fav_paths = {it.get("path") for it in items}
        self.fav_keys = {(it.get("db_name") or "", it.get("label")) for it in items}
        return added

    def add_history(self, g):
        """Put a game at the top of Recently Played (the built-in player's job; RetroArch does it itself)."""
        p = f"{RA}/content_history.lpl"
        d = self._read(p) or {"version": "1.5", "items": []}
        items = [it for it in d.get("items", []) if it.get("path") != g.path]
        items.insert(0, {"path": g.path, "label": g.label, "core_path": g.core,
                         "core_name": core_short(g.core), "crc32": "DETECT", "db_name": g.db or ""})
        d["items"] = items[:200]; d.setdefault("version", "1.5")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)
        os.replace(tmp, p)
