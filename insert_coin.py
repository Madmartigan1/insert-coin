#!/usr/bin/env python3
"""Insert Coin - a controller-driven, console-style front end for RetroArch.

It reads RetroArch's own playlists, thumbnails, favorites and history, and
launches games through RetroArch with each game's assigned core. Nothing is
duplicated: whatever works in RetroArch works here.

Controls (Xbox-style pad; keyboard in brackets)
  D-pad / left stick  move            [arrows]
  A                   open / play     [Enter]
  B                   back            [Backspace / Esc]
  Y                   toggle favorite [F]
  LB / RB             previous / next letter   [PageUp / PageDown]
  Menu sounds can be switched off in the B menu (saved in ~/.config/insert-coin/settings.json).
  In a game: Select+Start opens the game menu (Resume / Quit game, or RetroArch's Quick Menu).

Options: --windowed   run in a window (for testing)
         --shot DIR   render sample screens to PNG files and exit (no display needed)
"""
__version__ = "0.4.0.dev0"

import json, os, re, sys, time, random, threading, subprocess, collections, logging, faulthandler, platform

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from pygame._sdl2 import controller as sdlc

HOME = os.path.expanduser("~")
RA = f"{HOME}/.config/retroarch"
APPDIR = f"{HOME}/.local/share/insert-coin"
CACHE = f"{HOME}/.cache/insert-coin"
LOGDIR = f"{os.environ.get('XDG_STATE_HOME') or HOME + '/.local/state'}/insert-coin"
log = logging.getLogger("insert-coin")


def start_log():
    """insert-coin.log: start-up, every game launch and how it ended, errors and crashes (kept to ~1 MB)."""
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        path = f"{LOGDIR}/insert-coin.log"
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000: os.replace(path, path + ".1")
        h = logging.FileHandler(path, encoding="utf-8")
    except Exception: return                                        # no log is no reason not to run
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(h); log.setLevel(logging.INFO)
    faulthandler.enable(h.stream)                                   # hard crashes (segfaults) too
W, H = 1920, 1080

# ---------------------------------------------------------------- systems
# playlist name -> (friendly name, maker, accent colour)
SYSTEMS = [
    ("FBNeo - Arcade Games", "Arcade", "Neo Geo, Capcom & more", (226, 64, 64)),
    ("MAME 2003-Plus", "MAME", "Classic arcade", (232, 140, 40)),
    ("Nintendo - Nintendo Entertainment System", "NES", "Nintendo", (200, 40, 50)),
    ("Nintendo - Super Nintendo Entertainment System", "Super Nintendo", "Nintendo", (110, 90, 200)),
    ("Nintendo - Nintendo 64", "Nintendo 64", "Nintendo", (40, 150, 70)),
    ("Nintendo - Game Boy", "Game Boy", "Nintendo", (140, 160, 60)),
    ("Nintendo - Game Boy Color", "Game Boy Color", "Nintendo", (150, 70, 190)),
    ("Nintendo - Game Boy Advance", "Game Boy Advance", "Nintendo", (70, 80, 200)),
    ("Sega - Mega Drive - Genesis", "Mega Drive", "Sega", (30, 110, 210)),
    ("Sega - 32X", "Sega 32X", "Sega", (200, 60, 60)),
    ("NEC - PC Engine - TurboGrafx 16", "PC Engine", "NEC", (240, 120, 40)),
    ("Sony - PlayStation", "PlayStation", "Sony", (110, 120, 140)),
    ("SNK - Neo Geo Pocket", "Neo Geo Pocket", "SNK", (90, 90, 110)),
    ("SNK - Neo Geo Pocket Color", "Neo Geo Pocket Color", "SNK", (40, 160, 170)),
    ("Atari - 2600", "Atari 2600", "Atari", (170, 110, 60)),
]
FRIENDLY = {k: (n, m, c) for k, n, m, c in SYSTEMS}
ORDER = {k: i for i, (k, *_ ) in enumerate(SYSTEMS)}

LAUNCH_CFG = """# Written by Insert Coin: controller shortcuts while a game runs
# Select + Start opens RetroArch's menu (Quick Menu > Resume / Close Content), like the built-in player's pause
# menu; Close Content then returns to Insert Coin (only for games started from the command line, i.e. by us).
input_quit_gamepad_combo = "0"
input_menu_toggle_gamepad_combo = "4"
quit_on_close_content = "2"
quit_press_twice = "false"
video_fullscreen = "true"
"""
# Added for `--windowed` (testing): a window, and nothing of this saved into retroarch.cfg
LAUNCH_CFG_WINDOWED = """video_fullscreen = "false"
config_save_on_exit = "false"
"""


# ---------------------------------------------------------------- controller styles (for on-screen button hints)
# USB SNES replicas that SDL knows but maps by position, Xbox-style (vendor, product)
SNES_REPLICA_IDS = {("0583", "2060")}                              # iBuffalo Classic USB Gamepad


def controller_style(name, guid=""):
    """'playstation', 'nintendo', 'snes' (a third-party SNES replica) or 'xbox', from the USB vendor and product
    in SDL's GUID, falling back to the name."""
    n = (name or "").lower()
    vendor = guid[10:12] + guid[8:10] if len(guid) >= 12 else ""     # bytes 4-5 of the GUID, little-endian
    product = guid[18:20] + guid[16:18] if len(guid) >= 20 else ""   # bytes 8-9
    if vendor == "054c" or any(k in n for k in ("ps3", "ps4", "ps5", "playstation", "dualshock", "dualsense", "sony")):
        return "playstation"
    if vendor == "057e":                                           # Nintendo's own pads: SDL follows their labels
        return "nintendo"
    if (vendor, product) in SNES_REPLICA_IDS or any(k in n for k in ("snes", "super nintendo", "super famicom")):
        return "snes"
    if any(k in n for k in ("nintendo", "switch", "joy-con", "joycon")):
        return "nintendo"
    return "xbox"


# action -> how its button looks, per style. kinds: letter (round button), shape (PlayStation symbol), pill, key
GLYPHS = {
    "xbox": {"a": ("letter", "A", (90, 190, 90)), "b": ("letter", "B", (220, 80, 70)),
             "y": ("letter", "Y", (230, 190, 50)), "x": ("letter", "X", (70, 130, 230)), "lbrb": ("pill", "LB RB", (120, 130, 150))},
    "playstation": {"a": ("shape", "cross", (120, 160, 245)), "b": ("shape", "circle", (235, 90, 95)),
                    "y": ("shape", "triangle", (70, 200, 160)), "x": ("shape", "square", (230, 130, 200)), "lbrb": ("pill", "L1 R1", (120, 130, 150))},
    "nintendo": {"a": ("letter", "A", (110, 116, 132)), "b": ("letter", "B", (110, 116, 132)),
                 "y": ("letter", "Y", (110, 116, 132)), "x": ("letter", "X", (110, 116, 132)), "lbrb": ("pill", "L R", (120, 130, 150))},
    "keyboard": {"a": ("key", "Enter", None), "b": ("key", "Esc", None),
                 "y": ("key", "F", None), "x": ("key", "V", None), "lbrb": ("key", "PgUp PgDn", None)},
}
GLYPHS["snes"] = dict(GLYPHS["nintendo"])                        # replicas: same printed letters as Nintendo
GLYPHS["generic"] = {"a": ("letter", "A", (110, 116, 132)), "b": ("letter", "B", (110, 116, 132)),   # set-up pads
                     "y": ("letter", "Y", (110, 116, 132)), "x": ("letter", "X", (110, 116, 132)), "lbrb": ("pill", "LB RB", (120, 130, 150))}
QUIT_COMBO = {"xbox": "Back + Start", "playstation": "Share + Options", "nintendo": "Minus + Plus", "keyboard": "Esc",
              "generic": "Select + Start", "snes": "Select + Start"}

# controller set-up for pads SDL doesn't recognise: (action, button shown, what it does, optional)
SETUP_STEPS = [("up", "up", "Up", False), ("down", "down", "Down", False), ("left", "left", "Left", False),
               ("right", "right", "Right", False), ("a", "A", "Select / play", False), ("b", "B", "Back", False),
               ("y", "Y", "Favorite", True), ("x", "X", "Other versions", True),
               ("lb", "LB", "Previous letter", True), ("rb", "RB", "Next letter", True)]
CONFDIR = os.environ.get("INSERT_COIN_CONFIG") or os.path.expanduser("~/.config/insert-coin")


def quit_combo(style, name="", guid=""):
    """The buttons that quit a game, as printed on this controller (PS3: Select/Start, PS5: Create/Options)."""
    product = guid[18:20] + guid[16:18] if len(guid) >= 20 else ""   # bytes 8-9 of the GUID, little-endian
    n = (name or "").lower()
    if style == "playstation" and (product == "0268" or "ps3" in n or "playstation(r)3" in n):
        return "Select + Start"
    if style == "playstation" and (product in ("0ce6", "0df2") or "dualsense" in n or "ps5" in n):
        return "Create + Options"
    return QUIT_COMBO[style]


def split_archive(path):
    """RetroArch's 'archive.zip#file.nes' -> ('archive.zip', 'file.nes'). Only a '#' straight after .zip / .7z
    counts: folder names may contain '#' themselves (e.g. '# Translations #')."""
    m = re.search(r"(?i)\.(zip|7z)#", path)
    return (path[:m.end() - 1], path[m.end():]) if m else (path, "")


def sanitize(s):
    return re.sub(r'[&*/:`<>?\\|"]', "_", s)


def clean_title(label):
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", label).strip()
    m = re.match(r"^(.*), (The|A|An)( - .*)?$", t)          # "Legend of Zelda, The - X" -> "The Legend of Zelda - X"
    if m: t = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    return t or label


def tags(label):
    return [x.strip() for x in re.findall(r"[\(\[]([^)\]]*)[\)\]]", label)]


def sort_key(label):
    t = clean_title(label).lower()
    t = re.sub(r"^(the|a|an) ", "", t)
    return re.sub(r"[^a-z0-9 ]", "", t) or t


def letter_of(label):
    c = sort_key(label)[:1].upper()
    return c if c.isalpha() else "#"


def thumb_system(db_name):
    db = (db_name or "")[:-4] if (db_name or "").endswith(".lpl") else (db_name or "")
    return "MAME" if db.startswith("MAME") else db


# ---------------------------------------------------------------- data
class Game:
    __slots__ = ("label", "path", "core", "db", "title", "letter", "key", "system", "versions")

    def __init__(self, it, playlist_db, default_core):
        self.label = it.get("label") or os.path.splitext(os.path.basename(split_archive(it["path"])[0]))[0]
        self.path = it["path"]
        c = it.get("core_path") or ""
        self.core = c if c not in ("", "DETECT") and os.path.exists(c) else default_core
        self.db = it.get("db_name") or playlist_db
        self.title = clean_title(self.label)
        self.letter = letter_of(self.label)
        self.key = sort_key(self.label)
        self.system = (self.db or "")[:-4] if (self.db or "").endswith(".lpl") else self.db
        self.versions = None                                        # other regions / translations / dumps of this game

    def thumb(self, kind):
        return f"{RA}/thumbnails/{thumb_system(self.db)}/{kind}/{sanitize(self.label)}.png"


def rom_stem(path):
    """The game's own file name without extension: 'a.zip#Game (USA).nes' -> 'Game (USA)'. Saves are named after it."""
    return os.path.splitext(os.path.basename(split_archive(path)[1] or path))[0]


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


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}

def title_key(title):
    """'The Pixel Knights' / 'Pixel Knights, The', 'Star Pilot II' / 'Star Pilot 2', 'Turbo-Tanks' / 'Turbo Tanks'."""
    t = re.sub(r"^the\s+", "", title.lower())
    words = re.findall(r"[a-z0-9]+", t)
    return " ".join(ROMAN.get(w, w) for w in words)

REGION_RANK = [(r"\b(usa|us|u|ue|ju|jp-us|world)\b", 0), (r"\b(europe|eu|e)\b", 1), (r"\b(japan|j|jp)\b", 2)]

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
        self.favorites_raw = (self._read(f"{RA}/content_favorites.lpl") or {"version": "1.5", "items": []})
        self.refresh_specials()

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
        fav = sorted(dedupe(fav, set()) if self.one_per_game else fav, key=lambda g: g.key)
        seen, rec = set(), []
        for g in self._special_games(hist.get("items", [])):
            k = (g.db, g.label) if self.one_per_game else g.path
            if k not in seen: seen.add(k); rec.append(g)
        specials = []
        if fav: specials.append({"id": "favorites", "name": "Favorites", "maker": "Your picks", "color": (230, 180, 40), "games": fav, "special": "fav"})
        if rec: specials.append({"id": "recent", "name": "Recently Played", "maker": "Pick up where you left off", "color": (60, 170, 200), "games": rec[:60], "special": "recent"})
        self.systems = specials + self.systems
        self.fav_paths = {it.get("path") for it in self.favorites_raw.get("items", [])}
        self.fav_keys = {(it.get("db_name") or "", it.get("label")) for it in self.favorites_raw.get("items", [])}

    def is_fav(self, g):
        """A favorite, whichever copy of the game was starred."""
        return g.path in self.fav_paths or ((g.db or ""), g.label) in self.fav_keys

    def toggle_favorite(self, g):
        items = self.favorites_raw.setdefault("items", [])
        same = lambda it: it.get("path") == g.path or ((it.get("db_name") or ""), it.get("label")) == ((g.db or ""), g.label)
        if self.is_fav(g):
            items[:] = [it for it in items if not same(it)]; added = False
        else:
            items.append({"path": g.path, "label": g.label, "core_path": g.core or "DETECT",
                          "core_name": "DETECT" if not g.core else os.path.basename(g.core).replace("_libretro.so", ""),
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
                         "core_name": os.path.basename(g.core).replace("_libretro.so", ""), "crc32": "DETECT", "db_name": g.db or ""})
        d["items"] = items[:200]; d.setdefault("version", "1.5")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)
        os.replace(tmp, p)


# ---------------------------------------------------------------- metadata (year / publisher) from RetroArch's databases
def _rdb_load(path):
    b = open(path, "rb").read(); out = []

    def rd(i):
        t = b[i]; i += 1
        if t <= 0x7f: return t, i
        if 0x80 <= t <= 0x8f: return rmap(i, t & 15)
        if 0xa0 <= t <= 0xbf: n = t & 31; return b[i:i + n].decode("utf-8", "replace"), i + n
        if t == 0xc0: return None, i
        if t in (0xc2, 0xc3): return t == 0xc3, i
        if t in (0xc4, 0xc5, 0xc6):
            w = {0xc4: 1, 0xc5: 2, 0xc6: 4}[t]; n = int.from_bytes(b[i:i + w], "big"); i += w; return None, i + n
        if t in (0xcc, 0xcd, 0xce, 0xcf):
            w = {0xcc: 1, 0xcd: 2, 0xce: 4, 0xcf: 8}[t]; return int.from_bytes(b[i:i + w], "big"), i + w
        if t in (0xd9, 0xda, 0xdb):
            w = {0xd9: 1, 0xda: 2, 0xdb: 4}[t]; n = int.from_bytes(b[i:i + w], "big"); i += w
            return b[i:i + n].decode("utf-8", "replace"), i + n
        if t in (0xde, 0xdf):
            w = 2 if t == 0xde else 4; return rmap(i + w, int.from_bytes(b[i:i + w], "big"))
        raise ValueError(t)

    def rmap(i, n):
        d = {}
        for _ in range(n):
            k, i = rd(i); v, i = rd(i); d[k] = v
        return d, i
    i = 16
    while i < len(b) and b[i] != 0xc0:
        r, i = rd(i)
        if isinstance(r, dict): out.append(r)
    return out


class Meta:
    def __init__(self, dbs):
        self.data = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._load, args=(list(dbs),), daemon=True).start()

    def _load(self, dbs):
        os.makedirs(f"{CACHE}/meta", exist_ok=True)
        for db in dbs:
            src = f"{RA}/database/rdb/{db}.rdb"; cp = f"{CACHE}/meta/{sanitize(db)}.json"
            if not os.path.exists(src): continue
            try:
                if os.path.exists(cp) and os.path.getmtime(cp) >= os.path.getmtime(src):
                    m = json.load(open(cp))
                else:
                    m = {}
                    for e in _rdb_load(src):
                        yr = e.get("releaseyear"); pub = e.get("publisher") or e.get("developer")
                        if not (yr or pub): continue
                        v = [yr or "", pub or ""]
                        if e.get("name"): m.setdefault("n:" + e["name"], v)
                        if e.get("rom_name"): m.setdefault("r:" + os.path.splitext(e["rom_name"])[0], v)
                    json.dump(m, open(cp, "w"))
                with self.lock: self.data[db] = m
            except Exception:
                pass

    def get(self, g):
        db = g.system or ""
        with self.lock: m = self.data.get(db)
        if not m: return None
        rom = os.path.splitext(os.path.basename(split_archive(g.path)[0]))[0]
        return m.get("n:" + g.label) or m.get("r:" + rom)


# ---------------------------------------------------------------- images: loaded & scaled off the main thread
class Images:
    def __init__(self, sync=False):
        self.cache = collections.OrderedDict(); self.raw = {}
        self.want = []; self.cv = threading.Condition(); self.done = collections.deque()
        self.pending = set(); self.sync = sync; self.limit = 400
        if not sync:
            for _ in range(3): threading.Thread(target=self._worker, daemon=True).start()

    def _make(self, key):
        path, w, h, mode = key
        if not os.path.exists(path): return None
        try:
            img = pygame.image.load(path)
        except Exception:
            return None
        if img.get_bitsize() not in (24, 32):                     # palette PNGs can't be smooth-scaled
            full = pygame.Surface(img.get_size(), pygame.SRCALPHA, 32); full.blit(img, (0, 0)); img = full
        iw, ih = img.get_size()
        if mode == "fit":
            s = min(w / iw, h / ih); size = (max(1, int(iw * s)), max(1, int(ih * s)))
            return pygame.transform.smoothscale(img, size)
        if mode == "blur":                                         # cover the screen, cheap blur
            s = max(w / iw, h / ih); cw, ch = int(iw * s), int(ih * s)
            small = pygame.transform.smoothscale(img, (max(1, cw // 12), max(1, ch // 12)))
            big = pygame.transform.smoothscale(small, (cw, ch))
            return big.subsurface(((cw - w) // 2, (ch - h) // 2, w, h)).copy()
        return img

    def _worker(self):
        while True:
            with self.cv:
                while not self.want: self.cv.wait()
                key = self.want.pop()                              # newest request first
            surf = self._make(key)
            self.done.append((key, surf))

    def get(self, path, w, h, mode="fit"):
        key = (path, int(w), int(h), mode)
        if key in self.cache:
            self.cache.move_to_end(key); return self.cache[key]
        if self.sync:
            s = self._make(key); self._store(key, s); return s
        if key not in self.pending:
            self.pending.add(key)
            with self.cv:
                self.want.append(key)
                if len(self.want) > 60: dropped = self.want.pop(0); self.pending.discard(dropped)
                self.cv.notify()
        return False                                               # False = loading, None = no image

    def _store(self, key, s):
        if s is not None and pygame.display.get_init():
            try: s = s.convert_alpha()
            except Exception: pass
        self.cache[key] = s; self.cache.move_to_end(key)
        while len(self.cache) > self.limit: self.cache.popitem(last=False)

    def pump(self):
        n = 0
        while self.done and n < 12:
            key, s = self.done.popleft(); self.pending.discard(key); self._store(key, s); n += 1
        return n


# ---------------------------------------------------------------- drawing helpers
class Fonts:
    def __init__(self):
        name = pygame.font.match_font("ubuntu,notosans,dejavusans")
        bold = pygame.font.match_font("ubuntu,notosans,dejavusans", bold=True) or name
        self.f = {}
        self.name, self.bold = name, bold

    def __call__(self, size, bold=False):
        k = (size, bold)
        if k not in self.f: self.f[k] = pygame.font.Font(self.bold if bold else self.name, size)
        return self.f[k]


# ---------------------------------------------------------------- sound effects
class Sounds:
    """Menu sounds, synthesised at start-up, so there are no audio files. Silent if there is no audio device."""
    # name -> notes: (start Hz, end Hz, seconds, wave, volume[, decay]); a tuple of notes plays them together
    SPEC = {
        "move":    [(1250, 1250, .022, "tri", .30)],
        "system":  [(880, 880, .030, "tri", .32)],
        "select":  [(660, 660, .045, "sq", .15), (990, 990, .08, "sq", .15)],
        "back":    [(620, 620, .045, "sq", .13), (415, 415, .08, "sq", .13)],
        "menu":    [(440, 880, .09, "tri", .30)],
        "jump":    [(500, 1500, .07, "tri", .26)],
        # the credit counter ticking up, then a bell: Insert Coin's own coin-up sound
        "coin":    [n for k in range(6) for n in ((1000 + 140 * k, 0, .028, "sq", .13), (0, 0, .014, "rest", 0))]
                   + [(0, 0, .02, "rest", 0), ((2093, 2093, .45, "tri", .30, 2.2), (2093, 2093, .45, "sq", .06, 3))],
        "fav_on":  [(784, 784, .04, "tri", .32), (988, 988, .04, "tri", .32), (1319, 1319, .13, "tri", .32)],
        "fav_off": [(988, 988, .05, "tri", .30), (659, 659, .11, "tri", .30)],
        "error":   [(150, 120, .18, "sq", .13)],
    }

    def __init__(self, enabled=True, start=True):
        self.enabled = enabled; self.snd = {}; self.last_tick = 0.0
        if start: self.open()

    def open(self):
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init(44100, -16, 2, 512)
            rate, fmt, ch = pygame.mixer.get_init()
            if fmt != -16: return                                   # only 16-bit output is synthesised
            pygame.mixer.set_reserved(1); self.tick_chan = pygame.mixer.Channel(0)
            self.snd = {k: pygame.mixer.Sound(buffer=self._synth(v, rate, ch)) for k, v in self.SPEC.items()}
        except Exception: self.snd = {}

    @staticmethod
    def _synth(notes, rate, ch):
        import array
        def note(f0, f1, dur, wave, vol, decay=1.5):
            n = int(rate * dur); attack = rate * .003; phase = 0.0; f1 = f1 or f0; out = []
            for i in range(n):
                t = i / n; phase = (phase + (f0 + (f1 - f0) * t) / rate) % 1.0
                v = 0.0 if wave == "rest" else (1.0 if phase < .5 else -1.0) if wave == "sq" else 4 * abs(phase - .5) - 1
                out.append(v * vol * min(1.0, i / attack) * (1 - t) ** decay)   # quick attack, smooth decay: no clicks
            return out
        out = array.array("h")
        for nt in notes:
            seg = [sum(v) for v in zip(*(note(*p) for p in nt))] if isinstance(nt[0], tuple) else note(*nt)
            for v in seg: out.extend([int(max(-1.0, min(1.0, v)) * 32767)] * ch)
        return out.tobytes()

    def play(self, name):
        if not self.enabled or name not in self.snd: return
        if name in ("move", "system"):                              # scrolling: one tick at a time, never a pile-up
            now = time.time()
            if now - self.last_tick < .04: return
            self.last_tick = now; self.tick_chan.play(self.snd[name])
        else: self.snd[name].play()

    def finish(self, limit=1.0):
        """Let a playing sound end (before the audio device is handed to RetroArch)."""
        end = time.time() + limit
        while self.snd and pygame.mixer.get_busy() and time.time() < end: pygame.time.wait(10)

    def close(self):
        self.snd = {}
        try: pygame.mixer.quit()
        except Exception: pass


DEFAULT_SETTINGS = {"sound": True, "engine": False, "one_per_game": True}

# Cores the built-in player (engine.py) runs; every other core still goes through RetroArch
ENGINE_CORES = {"mesen_libretro.so", "fbneo_libretro.so", "mame2003_plus_libretro.so"}
HERE = os.path.dirname(os.path.abspath(__file__))

def load_settings():
    try:
        with open(f"{CONFDIR}/settings.json") as f: return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception: return dict(DEFAULT_SETTINGS)

def save_settings(s):
    os.makedirs(CONFDIR, exist_ok=True)
    tmp = f"{CONFDIR}/settings.json.tmp"
    with open(tmp, "w") as f: json.dump(s, f, indent=2)
    os.replace(tmp, f"{CONFDIR}/settings.json")


def text(surf, font, s, pos, color=(255, 255, 255), anchor="topleft", shadow=True, maxw=None):
    if maxw:
        while font.size(s)[0] > maxw and len(s) > 4: s = s[:-2].rstrip() + "…" if not s.endswith("…") else s[:-2].rstrip() + "…"
    img = font.render(s, True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(s, True, (0, 0, 0)); sh.set_alpha(150); surf.blit(sh, r.move(2, 3))
    surf.blit(img, r)
    return r


def wrap(font, s, width, lines=3):
    words, out, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= width: cur = t
        else:
            if cur: out.append(cur)
            cur = w
    if cur: out.append(cur)
    return out[:lines]


def rrect(surf, color, rect, radius=18, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def star(surf, center, r, color=(255, 210, 60)):
    import math
    cx, cy = center
    pts = [(cx + (r if k % 2 == 0 else r * 0.45) * math.sin(k * math.pi / 5), cy - (r if k % 2 == 0 else r * 0.45) * math.cos(k * math.pi / 5)) for k in range(10)]
    pygame.draw.polygon(surf, (0, 0, 0), [(x + 2, y + 3) for x, y in pts])
    pygame.draw.polygon(surf, color, pts)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


# ---------------------------------------------------------------- the app
class App:
    def __init__(self, windowed=False, shot=None):
        self.windowed, self.shot = windowed, shot
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init(); sdlc.init()
        self.settings = load_settings()
        self.sfx = Sounds(enabled=self.settings["sound"], start=not shot)
        self.open_display()
        self.fonts = Fonts()
        self.lib = Library(one_per_game=self.settings["one_per_game"])
        self.meta = Meta({s["id"] for s in self.lib.systems if not s["special"]})
        self.img = Images(sync=bool(shot))
        self.pads = {}; self.pad_style = {}                         # device index -> Controller; instance id -> style
        self.pad_quit = {}; self.cur_pad = None                    # instance id -> quit-combo words; last pad used
        self.raw = {}; self.raw_map = {}                           # unrecognised joysticks: instance id -> Joystick / mapping
        self.saved_maps = self.load_maps(); self.setup = None
        self.style = "keyboard"                                    # button hints follow the last device used
        self.open_pads()
        if self.pad_style: self.cur_pad, self.style = next(iter(self.pad_style.items()))
        log.info("Insert Coin %s started (Python %s, pygame-ce %s, SDL %s, %s)", __version__, platform.python_version(),
                 pygame.version.ver, ".".join(map(str, pygame.get_sdl_version())), platform.platform())
        log.info("%d systems, %d games (%d duplicate copies hidden); sound %s (%s)", sum(not s["special"] for s in self.lib.systems),
                 sum(len(s["games"]) for s in self.lib.systems if not s["special"]), self.lib.hidden,
                 "on" if self.sfx.enabled else "off", "audio ready" if self.sfx.snd else "no audio device")
        for c in self.pads.values(): log.info("Controller: %s (%s)", c.name, self.pad_style.get(c.as_joystick().get_instance_id()))
        for j in self.raw.values(): log.info("Controller without SDL mapping: %s (%s)", j.get_name(), "set up" if j.get_instance_id() in self.raw_map else "not set up")
        self.screen_mode = "systems"                              # systems | games | quit
        self.si = next((i for i, s in enumerate(self.lib.systems) if not s["special"]), 0)
        self.gi = {}                                              # system id -> selected game index
        self.spos = float(self.si); self.gpos = 0.0
        self.toast = None; self.jump = None
        self.prev_bg = None; self.bg_change = 0
        self.hold = {}; self.quit_sel = 1; self.vlist = []; self.vsel = 0
        self.clock = pygame.time.Clock()

    # -- display / input
    def open_display(self):
        flags = 0 if self.shot else pygame.SCALED | (0 if self.windowed else pygame.FULLSCREEN)
        self.screen = pygame.display.set_mode((W, H), flags, vsync=0 if self.shot else 1)
        pygame.display.set_caption("Insert Coin")
        pygame.mouse.set_visible(bool(self.windowed))

    def open_pads(self):
        for i in range(sdlc.get_count()):
            if sdlc.is_controller(i) and i not in self.pads:
                try:
                    c = sdlc.Controller(i); self.pads[i] = c
                    j = c.as_joystick()
                    st = controller_style(c.name, j.get_guid()); self.pad_style[j.get_instance_id()] = st
                    self.pad_quit[j.get_instance_id()] = quit_combo(st, c.name, j.get_guid())
                except Exception: pass
            elif not sdlc.is_controller(i):                         # a joystick SDL has no mapping for
                try:
                    j = pygame.joystick.Joystick(i); iid = j.get_instance_id()
                    if iid in self.raw: continue
                    self.raw[iid] = j
                    m = self.saved_maps.get(j.get_guid())
                    if m: self.use_map(iid, m["map"])
                except Exception: pass

    def rescan_pads(self):
        """After a game: controllers may have been unplugged or swapped while it ran, and those events were missed,
        so rebuild the list from what is connected now. Hints follow the pad last used if it is still there."""
        pygame.event.pump()
        last = self.cur_pad
        self.pads = {}; self.pad_style = {}; self.pad_quit = {}; self.raw = {}; self.raw_map = {}
        self.open_pads()
        now = list(self.pad_style)
        if last in now: return
        if now:
            self.cur_pad, self.style = now[-1], self.pad_style[now[-1]]
            name = next((c.name for c in self.pads.values() if c.as_joystick().get_instance_id() == now[-1]), "Controller")
            log.info("Controller after the game: %s (%s)", name, self.style)
        else:
            self.cur_pad, self.style = None, "keyboard"
        if self.raw and not now:
            self.say("Controller connected - press a button on it to set it up", 3.0)

    def pad_plugged(self):
        """A controller was connected: the button hints switch to it straight away (not only after a button press)."""
        before = set(self.pad_style) | set(self.raw)
        self.open_pads()
        new = [iid for iid in list(self.pad_style) + list(self.raw) if iid not in before]
        if not new: return                                         # SDL also reports pads that were already there
        iid = new[-1]
        name = next((c.name for c in self.pads.values() if c.as_joystick().get_instance_id() == iid), None) or \
               (self.raw[iid].get_name() if iid in self.raw else "Controller")
        if iid in self.pad_style:
            self.cur_pad, self.style = iid, self.pad_style[iid]
            self.say(f"Controller connected: {name}")
        else:
            self.say(f"Controller connected: {name} - press a button on it to set it up", 3.0)
        log.info("Controller connected: %s (%s)", name, self.pad_style.get(iid, "needs set-up"))

    # -- controller set-up for unrecognised pads
    def load_maps(self):
        try:
            with open(f"{CONFDIR}/controllers.json") as f: return json.load(f)
        except Exception: return {}

    def save_maps(self):
        os.makedirs(CONFDIR, exist_ok=True)
        tmp = f"{CONFDIR}/controllers.json.tmp"
        with open(tmp, "w") as f: json.dump(self.saved_maps, f, indent=2)
        os.replace(tmp, f"{CONFDIR}/controllers.json")

    def use_map(self, iid, mapping):
        self.raw_map[iid] = mapping; self.pad_style[iid] = "generic"; self.pad_quit[iid] = QUIT_COMBO["generic"]

    def start_setup(self, iid, name="", guid="", baseline=None):
        j = self.raw.get(iid)
        if baseline is None:                                       # resting axis positions (triggers rest at -1)
            baseline = {k: j.get_axis(k) for k in range(j.get_numaxes())} if j else {}
        self.setup = {"iid": iid, "name": name or (j.get_name() if j else "Controller"), "guid": guid or (j.get_guid() if j else ""),
                      "step": 0, "map": {}, "base": baseline, "wait": None, "msg": "", "prev": self.screen_mode}
        self.screen_mode = "setup"; self.hold.clear(); self.sfx.play("menu")

    def setup_input(self, e):
        s = self.setup
        cand = None
        if e.type == pygame.JOYBUTTONDOWN: cand = ["button", e.button]
        elif e.type == pygame.JOYBUTTONUP and s["wait"] == ["button", e.button]: s["wait"] = None
        elif e.type == pygame.JOYHATMOTION:
            x, y = e.value
            if (x, y) == (0, 0):
                if s["wait"] and s["wait"][0] == "hat" and s["wait"][1] == e.hat: s["wait"] = None
            else: cand = ["hat", e.hat, 0, y] if y else ["hat", e.hat, x, 0]
        elif e.type == pygame.JOYAXISMOTION:
            base = s["base"].get(e.axis, 0.0)
            if s["wait"] and s["wait"][0] == "axis" and s["wait"][1] == e.axis and abs(e.value - base) < 0.3: s["wait"] = None
            elif abs(e.value - base) > 0.6 and abs(e.value) > 0.5: cand = ["axis", e.axis, 1 if e.value > 0 else -1]
        if cand is None or s["wait"]: return                       # nothing new, or the last input isn't released yet
        act, shown, what, optional = SETUP_STEPS[s["step"]]
        s["wait"] = cand
        if optional and cand == s["map"].get("b"):                 # B skips an optional step
            s["msg"] = ""; self.next_setup_step(); return
        used = next((a for a, v in s["map"].items() if v == cand), None)
        if used:
            label = next(w for a2, _, w, _ in SETUP_STEPS if a2 == used)
            s["msg"] = f"That one is already {label} - try another"; self.sfx.play("error"); return
        s["map"][act] = cand; s["msg"] = ""; self.next_setup_step()

    def next_setup_step(self):
        s = self.setup; s["step"] += 1
        if s["step"] < len(SETUP_STEPS): self.sfx.play("move"); return
        self.sfx.play("select")
        self.saved_maps[s["guid"] or s["name"]] = {"name": s["name"], "map": s["map"]}
        try: self.save_maps()
        except Exception as e: self.say(f"Could not save the controller set-up: {e}")
        self.use_map(s["iid"], s["map"]); self.cur_pad, self.style = s["iid"], "generic"
        self.screen_mode = s["prev"] if s["prev"] != "quit" else "systems"; self.setup = None
        self.hold.clear(); self.say("Controller ready")

    def cancel_setup(self):
        self.screen_mode = self.setup["prev"] if self.setup["prev"] != "quit" else "systems"; self.setup = None
        self.say("Controller set-up cancelled"); self.sfx.play("back")

    def raw_input(self, e):
        """Turn a set-up pad's raw joystick events into menu actions."""
        m = self.raw_map[e.instance_id]
        for act, b in m.items():
            if e.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP) and b == ["button", e.button]:
                self.set_hold(act, e.type == pygame.JOYBUTTONDOWN)
            elif e.type == pygame.JOYHATMOTION and b[0] == "hat" and b[1] == e.hat:
                self.set_hold(act, (b[2] != 0 and e.value[0] == b[2]) or (b[3] != 0 and e.value[1] == b[3]))
            elif e.type == pygame.JOYAXISMOTION and b[0] == "axis" and b[1] == e.axis:
                self.set_hold(act, e.value * b[2] > 0.5)

    # -- current state helpers
    @property
    def sys(self): return self.lib.systems[self.si]

    def games(self): return self.sys["games"]

    def cur_gi(self): return min(self.gi.get(self.sys["id"], 0), max(0, len(self.games()) - 1))

    def cur_game(self):
        g = self.games(); return g[self.cur_gi()] if g else None

    def say(self, msg, secs=2.0): self.toast = (msg, time.time() + secs)

    def err(self, msg): self.say(msg); self.sfx.play("error"); log.warning(msg)

    # -- actions
    def move(self, d):
        """Move the selection; returns True if it moved (a list end makes no sound)."""
        if self.screen_mode == "systems":
            old = self.si; self.si = (self.si + d) % len(self.lib.systems); return self.si != old
        elif self.screen_mode == "games":
            n = len(self.games())
            if n:
                old = self.cur_gi(); self.gi[self.sys["id"]] = max(0, min(n - 1, old + d)); return self.cur_gi() != old
        elif self.screen_mode == "quit":
            self.quit_sel = (self.quit_sel + (1 if d > 0 else -1)) % len(self.POWER_MENU); return True
        elif self.screen_mode == "versions":
            n = len(self.vlist); old = self.vsel; self.vsel = max(0, min(n - 1, self.vsel + (1 if d > 0 else -1))); return self.vsel != old
        return False

    def open_versions(self):
        g = self.cur_game() if self.screen_mode == "games" else None
        if not g or not g.versions: return
        self.vlist = g.versions; self.vsel = 0; self.screen_mode = "versions"; self.sfx.play("menu")

    def jump_letter(self, d):
        if self.screen_mode != "games": return
        gs = self.games(); i = self.cur_gi()
        if not gs: return
        cur = gs[i].letter
        if d > 0:
            j = next((k for k in range(i + 1, len(gs)) if gs[k].letter != cur), len(gs) - 1)
        else:
            start = next((k for k in range(i, -1, -1) if gs[k].letter != cur), None)
            if start is None: j = 0
            else:
                L = gs[start].letter; j = start
                while j > 0 and gs[j - 1].letter == L: j -= 1
        if j != i: self.sfx.play("jump")
        self.gi[self.sys["id"]] = j; self.jump = (gs[j].letter, time.time() + 0.9)

    def accept(self):
        if self.screen_mode == "systems":
            self.screen_mode = "games"; self.gpos = float(self.cur_gi()); self.sfx.play("select")
        elif self.screen_mode == "games":
            g = self.cur_game()
            if g: self.launch(g)
        elif self.screen_mode == "versions":
            self.screen_mode = "games"; self.launch(self.vlist[self.vsel])
        elif self.screen_mode == "quit":
            choice = self.POWER_MENU[self.quit_sel]
            if choice == "Resume": self.screen_mode = "systems"; self.sfx.play("back")
            elif choice == "Exit Insert Coin": self.running = False; log.info("Exit chosen from the menu")
            elif choice.startswith("Sound"): self.toggle_sound()
            elif choice.startswith("Player"): self.toggle_engine()
            elif choice.startswith("Games"): self.toggle_grouping()
            else: self.sfx.play("select"); self.setup_from_menu()

    def toggle_grouping(self):
        """One entry per game (copies hidden, versions under X) or every ROM, exactly as the playlists list them."""
        self.settings["one_per_game"] = not self.settings["one_per_game"]
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        sid = self.sys["id"] if self.lib.systems else None
        self.lib = Library(one_per_game=self.settings["one_per_game"]); self.gi = {}
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.spos = float(self.si)
        self.sfx.play("select")
        total = sum(len(s["games"]) for s in self.lib.systems if not s["special"])
        self.say(f"One entry per game: {total:,} games (other versions under X)" if self.settings["one_per_game"]
                 else f"Showing every ROM: {total:,} entries", 3.0)

    def toggle_engine(self):
        self.settings["engine"] = not self.settings.get("engine")
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        self.sfx.play("select")
        self.say("Built-in player: NES, FBNeo and MAME 2003-Plus games run without RetroArch" if self.settings["engine"]
                 else "All games run in RetroArch", 3.0)

    def toggle_sound(self):
        self.settings["sound"] = self.sfx.enabled = not self.sfx.enabled
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        self.sfx.play("select")                                     # only heard when it was switched on

    def setup_from_menu(self):
        """Set up (or redo) the unrecognised controller used last, or say why it isn't needed."""
        iid = self.cur_pad if self.cur_pad in self.raw else next(iter(self.raw), None)
        if iid is None:
            self.screen_mode = "systems"
            self.say("Your controller is recognised automatically - no set-up needed" if self.pads
                     else "Connect a controller first, then choose Set up controller")
            return
        self.start_setup(iid)

    def back(self):
        if self.screen_mode == "games": self.screen_mode = "systems"; self.sfx.play("back")
        elif self.screen_mode == "versions": self.screen_mode = "games"; self.sfx.play("back")
        elif self.screen_mode == "systems": self.screen_mode = "quit"; self.quit_sel = 0; self.sfx.play("menu")
        else: self.screen_mode = "systems"; self.sfx.play("back")

    def favorite(self):
        g = self.cur_game() if self.screen_mode == "games" else None
        if not g: return
        if subprocess.run(["pgrep", "-x", "retroarch"], capture_output=True).returncode == 0:
            self.err("Close RetroArch first to change favorites"); return
        added = self.lib.toggle_favorite(g)
        self.sfx.play("fav_on" if added else "fav_off")
        self.say(("Added to Favorites: " if added else "Removed from Favorites: ") + g.title)
        sid = self.sys["id"]; self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0)
        if self.sys["id"] != sid: self.screen_mode = "systems"

    def launch(self, g):
        if not g.core:
            self.err("No core is set for this game yet - assign one in RetroArch"); return
        if not os.path.exists(split_archive(g.path)[0]):
            self.err("ROM file not found"); return
        engine = self.settings.get("engine") and os.path.basename(g.core) in ENGINE_CORES
        who = "Built-in player" if engine else "RetroArch"
        self.sfx.play("coin"); self.draw(); self.splash(g, engine)
        self.sfx.finish(); self.sfx.close()                          # hand the audio device to the game
        os.makedirs(APPDIR, exist_ok=True); os.makedirs(LOGDIR, exist_ok=True)
        with open(f"{APPDIR}/launch.cfg", "w") as f:
            f.write(LAUNCH_CFG.replace('video_fullscreen = "true"\n', "") + LAUNCH_CFG_WINDOWED if self.windowed else LAUNCH_CFG)
        pygame.display.quit()
        kind = "engine" if engine else "retroarch"
        t0 = time.time(); ralog = f"{LOGDIR}/{kind}-last.log"; rc = None
        log.info("Launch (%s): %s | %s | %s", who, g.label, os.path.basename(g.core), g.path)
        try:
            if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/{kind}-previous.log")
            if engine:
                with open(ralog, "w") as out:
                    rc = subprocess.run([sys.executable, f"{HERE}/engine.py", g.core, g.path] + (["--windowed"] if self.windowed else []),
                                        stdout=out, stderr=subprocess.STDOUT).returncode
            else:
                rc = subprocess.run(["retroarch", "--verbose", f"--log-file={ralog}", "-L", g.core, g.path,
                                     f"--appendconfig={APPDIR}/launch.cfg"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        except Exception as e:
            self.err(f"Could not start {who}: {e}")
        took = time.time() - t0
        how = ("ended normally" if rc == 0 else f"was killed by signal {-rc} (crash)" if rc is not None and rc < 0
               else f"exited with code {rc}" if rc is not None else "did not start")
        (log.info if rc == 0 else log.warning)("%s %s after %d min %02d s (log: %s)", who, how, took // 60, took % 60, ralog)
        if rc:                                                       # keep the clues next to the event
            try:
                errs = [ln.rstrip() for ln in open(ralog, errors="replace") if "[ERROR]" in ln or "[WARN]" in ln]
                for ln in errs[-15:]: log.warning("  %s: %s", kind, ln)
            except Exception: pass
        if engine and rc == 0 and took >= 3:
            try: self.lib.add_history(g)
            except Exception as e: log.warning("Could not update Recently Played: %s", e)
        pygame.display.init(); self.open_display(); self.rescan_pads(); self.sfx.open()
        self.img.cache.clear(); self.prev_bg = None
        pygame.event.clear(); self.hold.clear()
        sid, gid = self.sys["id"], self.cur_gi()
        self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.gi[sid] = gid
        if took < 3: self.err("The game closed straight away - it may need a different core")

    # -- input handling with key repeat
    REPEAT_FIRST, REPEAT = 0.32, 0.075

    def press(self, act):
        if not self.lib.systems:                                    # empty setup: only "exit" does anything
            if act == "b": self.running = False; log.info("Exit (no games found)")
            return
        if act in ("left", "right", "up", "down"):
            d = -1 if act in ("left", "up") else 1
            if self.screen_mode == "games" and act in ("up", "down"): d *= 10
            if self.screen_mode == "versions" and act in ("left", "right"): return
            if self.move(d): self.sfx.play("system" if self.screen_mode == "systems" else "move")
        elif act == "a": self.accept()
        elif act == "b": self.back()
        elif act == "y": self.favorite()
        elif act == "x": self.open_versions()
        elif act == "lb": self.jump_letter(-1)
        elif act == "rb": self.jump_letter(1)

    def set_hold(self, act, down):
        if down:
            if act not in self.hold: self.press(act); self.hold[act] = time.time() + self.REPEAT_FIRST
        else:
            self.hold.pop(act, None)

    def handle(self, e):
        K = {pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down",
             pygame.K_RETURN: "a", pygame.K_KP_ENTER: "a", pygame.K_BACKSPACE: "b", pygame.K_ESCAPE: "b",
             pygame.K_f: "y", pygame.K_v: "x", pygame.K_PAGEUP: "lb", pygame.K_PAGEDOWN: "rb"}
        B = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
             pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
             pygame.CONTROLLER_BUTTON_A: "a", pygame.CONTROLLER_BUTTON_B: "b", pygame.CONTROLLER_BUTTON_Y: "y",
             pygame.CONTROLLER_BUTTON_X: "x",
             pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "lb", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb",
             pygame.CONTROLLER_BUTTON_START: "a", pygame.CONTROLLER_BUTTON_BACK: "b"}
        JOY = (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYHATMOTION, pygame.JOYAXISMOTION)
        jid = getattr(e, "instance_id", None)
        if e.type == pygame.JOYDEVICEADDED: self.pad_plugged()
        elif e.type == pygame.JOYDEVICEREMOVED and jid in self.raw:
            if self.setup and self.setup["iid"] == jid: self.cancel_setup()
            for d in (self.raw, self.raw_map, self.pad_style, self.pad_quit): d.pop(jid, None)
            if self.cur_pad == jid: self.cur_pad, self.style = next(iter(self.pad_style.items()), (None, "keyboard"))
        if self.screen_mode == "setup":                            # the set-up screen owns the input
            if e.type == pygame.QUIT: self.running = False; log.info("Asked to close (window closed, log-out or a stop signal)")
            elif e.type in JOY and jid == self.setup["iid"]: self.setup_input(e)
            elif (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE) or \
                 (e.type == pygame.CONTROLLERBUTTONDOWN and e.button == pygame.CONTROLLER_BUTTON_B): self.cancel_setup()
            return
        if e.type in JOY and jid in self.raw:                      # unrecognised pads: set up, or use their mapping
            if jid in self.raw_map:
                if e.type == pygame.JOYBUTTONDOWN or (e.type == pygame.JOYHATMOTION and e.value != (0, 0)) \
                   or (e.type == pygame.JOYAXISMOTION and abs(e.value) > 0.5):
                    self.cur_pad, self.style = jid, "generic"
                self.raw_input(e)
            elif e.type == pygame.JOYBUTTONDOWN: self.start_setup(jid)
            return
        if e.type == pygame.KEYDOWN: self.style = "keyboard"
        elif e.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERAXISMOTION) and hasattr(e, "instance_id"):
            if e.type == pygame.CONTROLLERBUTTONDOWN or abs(e.value) > 16000:
                if e.instance_id in self.pad_style: self.cur_pad, self.style = e.instance_id, self.pad_style[e.instance_id]
        if e.type == pygame.QUIT: self.running = False; log.info("Asked to close (window closed, log-out or a stop signal)")
        elif e.type == pygame.KEYDOWN and e.key in K: self.set_hold(K[e.key], True)
        elif e.type == pygame.KEYUP and e.key in K: self.set_hold(K[e.key], False)
        elif e.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
            if self.pad_style.get(getattr(e, "instance_id", None)) == "snes":
                # SDL maps replicas by position: its "A" is the bottom button, printed B. Follow the printed
                # labels like a real Nintendo pad: right (printed A) plays, bottom (B) goes back, left (Y) favorites.
                Bs = dict(B)
                Bs.update({pygame.CONTROLLER_BUTTON_A: "b", pygame.CONTROLLER_BUTTON_B: "a", pygame.CONTROLLER_BUTTON_X: "y",
                           pygame.CONTROLLER_BUTTON_Y: "x"})
            else: Bs = B
            if e.button in Bs: self.set_hold(Bs[e.button], e.type == pygame.CONTROLLERBUTTONDOWN)
        elif e.type == pygame.CONTROLLERAXISMOTION and e.axis in (pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY):
            neg, pos = ("left", "right") if e.axis == pygame.CONTROLLER_AXIS_LEFTX else ("up", "down")
            v = e.value / 32767
            self.set_hold(neg, v < -0.55); self.set_hold(pos, v > 0.55)
        elif e.type == pygame.CONTROLLERDEVICEADDED: self.pad_plugged()
        elif e.type == pygame.CONTROLLERDEVICEREMOVED:
            self.pads = {}; self.pad_style = {}; self.pad_quit = {}; self.open_pads()
            if self.style != "keyboard": self.cur_pad, self.style = next(iter(self.pad_style.items()), (None, "keyboard"))

    def tick_repeat(self):
        now = time.time()
        for act, t in list(self.hold.items()):
            if act in ("left", "right", "up", "down") and now >= t:
                self.press(act); self.hold[act] = now + self.REPEAT

    # -- drawing
    def card(self, g, w, h, color):
        """Box art fitted into (w, h), or a placeholder card with the title."""
        s = self.img.get(g.thumb("Named_Boxarts"), w, h)
        if s: return s
        surf = pygame.Surface((int(w * 0.74), int(h)), pygame.SRCALPHA)
        rrect(surf, shade(color, 0.55), surf.get_rect(), 16)
        rrect(surf, shade(color, 0.9), surf.get_rect(), 16, 4)
        f = self.fonts(max(14, int(h / 12)), True)
        lines = wrap(f, g.title, surf.get_width() - 24, 4)
        y = surf.get_height() / 2 - len(lines) * f.get_linesize() / 2
        for ln in lines:
            text(surf, f, ln, (surf.get_width() / 2, y), anchor="midtop"); y += f.get_linesize()
        return surf

    def draw_background(self, color, g=None):
        top, bot = shade(color, 0.32), (8, 8, 14)
        for y in range(0, H, 8):
            t = y / H; c = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
            pygame.draw.rect(self.screen, c, (0, y, W, 8))
        if g is not None:
            bg = self.img.get(g.thumb("Named_Snaps"), W, H, "blur")
            if bg:
                if self.prev_bg is not bg:
                    self.prev_bg_old, self.prev_bg, self.bg_change = self.prev_bg, bg, time.time()
                a = min(1.0, (time.time() - self.bg_change) / 0.25)
                old = getattr(self, "prev_bg_old", None)
                if old and a < 1:
                    old.set_alpha(int(255 * (1 - a))); self.screen.blit(old, (0, 0))
                bg.set_alpha(int(255 * a)); self.screen.blit(bg, (0, 0))
                dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((5, 5, 12, 165)); self.screen.blit(dim, (0, 0))

    def draw_header(self, title, sub):
        text(self.screen, self.fonts(46, True), title, (70, 48))
        text(self.screen, self.fonts(26), sub, (72, 108), (200, 205, 220))
        text(self.screen, self.fonts(34, True), time.strftime("%H:%M"), (W - 70, 52), anchor="topright")

    def draw_button(self, action, x, cy, draw=True):
        """Draw the button for `action` in the current controller style; return the x after it."""
        kind, label, color = GLYPHS[self.style].get(action, GLYPHS["xbox"][action])
        s = self.screen
        if kind == "letter":
            if draw:
                pygame.draw.circle(s, color, (x + 21, cy), 21)
                text(s, self.fonts(24, True), label, (x + 21, cy), anchor="center", shadow=False)
            return x + 52
        if kind == "shape":                                        # PlayStation: coloured symbol on a dark button
            if draw:
                cx = x + 21
                pygame.draw.circle(s, (34, 37, 50), (cx, cy), 21); pygame.draw.circle(s, (90, 96, 115), (cx, cy), 21, 2)
                if label == "cross":
                    pygame.draw.line(s, color, (cx - 8, cy - 8), (cx + 8, cy + 8), 4); pygame.draw.line(s, color, (cx - 8, cy + 8), (cx + 8, cy - 8), 4)
                elif label == "circle":
                    pygame.draw.circle(s, color, (cx, cy), 9, 4)
                elif label == "triangle":
                    pygame.draw.polygon(s, color, [(cx, cy - 10), (cx + 10, cy + 8), (cx - 10, cy + 8)], 4)
                elif label == "square":
                    pygame.draw.rect(s, color, (cx - 8, cy - 8, 16, 16), 4)
            return x + 52
        f = self.fonts(22, True)                                   # pills (shoulder buttons) and keyboard keys
        for part in label.split():
            w = max(54, f.size(part)[0] + 26)
            if draw:
                r = pygame.Rect(x, cy - 19, w, 38)
                if kind == "key":
                    rrect(s, (225, 228, 238), r, 8); rrect(s, (150, 155, 170), r, 8, 2)
                    text(s, f, part, r.center, (25, 28, 38), anchor="center", shadow=False)
                else:
                    rrect(s, color, r, 10); text(s, f, part, r.center, anchor="center", shadow=False)
            x += w + 8
        return x + 2

    def draw_hints(self, hints):
        y, f = H - 54, self.fonts(26)
        width = 0
        for action, label in hints:                                # measure first, so the row is centred
            width = self.draw_button(action, width, y, draw=False) + f.size(label)[0] + 40
        x = W / 2 - (width - 40) / 2
        for action, label in hints:
            x = self.draw_button(action, x, y)
            r = text(self.screen, f, label, (x, y), (225, 228, 238), anchor="midleft"); x = r.right + 40

    def draw_systems(self, hints=True):
        s = self.sys
        self.draw_background(s["color"])
        self.draw_header("Insert Coin", f"{sum(len(x['games']) for x in self.lib.systems if not x['special']):,} games · {len([x for x in self.lib.systems if not x['special']])} systems")
        self.spos += (self.si - self.spos) * 0.22
        n = len(self.lib.systems); cy = 500
        order = sorted(range(-3, 4), key=lambda k: -abs(k))
        base = round(self.spos)
        for k in order:
            i = base + k
            if not 0 <= i < n: continue
            sy = self.lib.systems[i]; d = i - self.spos; ad = abs(d)
            sc = max(0.45, 1 - 0.22 * ad); w, h = 560 * sc, 400 * sc
            x = W / 2 + d * 470 - w / 2 * (1 if d >= 0 else 1)
            rect = pygame.Rect(0, 0, w, h); rect.center = (W / 2 + d * 470 * (1 - 0.06 * ad), cy)
            tile = pygame.Surface((w, h), pygame.SRCALPHA)
            rrect(tile, shade(sy["color"], 0.5), tile.get_rect(), 26)
            g3 = sy["games"][:: max(1, len(sy["games"]) // 3)][:3] if sy["special"] else random.Random(sy["id"]).sample(sy["games"], min(3, len(sy["games"])))
            for j, g in enumerate(g3):                                     # a little fan of box art
                im = self.img.get(g.thumb("Named_Boxarts"), 190 * sc, 230 * sc)
                if im:
                    r = im.get_rect(); r.midbottom = (w * (0.3 + 0.2 * j), h * 0.70)
                    tile.blit(im, r)
            grad = pygame.Surface((w, h * 0.45), pygame.SRCALPHA)
            for yy in range(int(h * 0.45)):
                pygame.draw.line(grad, (*shade(sy["color"], 0.25), int(235 * yy / (h * 0.45))), (0, yy), (w, yy))
            tile.blit(grad, (0, h * 0.55))
            text(tile, self.fonts(int(46 * sc), True), sy["name"], (26 * sc, h - 98 * sc), maxw=w - 40)
            text(tile, self.fonts(int(24 * sc)), f"{sy['maker']}  ·  {len(sy['games']):,} games", (28 * sc, h - 42 * sc), (215, 220, 230), maxw=w - 40)
            mask = pygame.Surface((w, h), pygame.SRCALPHA); rrect(mask, (255, 255, 255, 255), mask.get_rect(), 26)
            tile.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            if ad > 0.5: tile.set_alpha(int(255 * max(0.35, 1 - 0.3 * ad)))
            self.screen.blit(tile, rect)
            if ad < 0.5: rrect(self.screen, (255, 255, 255), rect.inflate(10, 10), 30, 5)
        dots_w = n * 22; x0 = W / 2 - dots_w / 2
        for i in range(n):
            pygame.draw.circle(self.screen, (255, 255, 255) if i == self.si else (110, 115, 130), (x0 + i * 22 + 11, 790), 6 if i == self.si else 4)
        text(self.screen, self.fonts(30), s["maker"] if s["special"] else f"{len(s['games']):,} games", (W / 2, 850), (210, 215, 228), anchor="midtop")
        if hints: self.draw_hints([("a", "Open"), ("b", "Power")])

    def draw_games(self, hints=True):
        s = self.sys; gs = self.games(); i = self.cur_gi(); g = gs[i] if gs else None
        self.draw_background(s["color"], g)
        self.draw_header(s["name"], f"{len(gs):,} games  ·  {i + 1:,} / {len(gs):,}")
        self.gpos += (i - self.gpos) * 0.25
        if abs(i - self.gpos) > 40: self.gpos = i - 40 * (1 if i > self.gpos else -1)
        cx, cy, H0 = 700, 470, 470
        base = round(self.gpos)
        self.screen.set_clip(pygame.Rect(0, 150, 1320, 700))           # keep the carousel clear of the side panel
        for k in sorted(range(-4, 4), key=lambda k: -abs(k)):
            j = base + k
            if not 0 <= j < len(gs): continue
            d = j - self.gpos; ad = abs(d)
            h = H0 * max(0.42, 1 - 0.2 * ad) if ad > 0.5 else H0
            hb = int(h // 16 * 16)
            im = self.card(gs[j], hb * 0.95, hb, s["color"])
            x = cx + (d * 330 if ad <= 1 else (330 + (ad - 1) * 215) * (1 if d > 0 else -1))
            r = im.get_rect(); r.center = (x, cy)
            if ad > 0.5:
                im = im.copy(); im.set_alpha(int(255 * max(0.25, 1 - 0.28 * ad)))
            else:
                sh = pygame.Surface((r.w + 30, r.h + 30), pygame.SRCALPHA); rrect(sh, (0, 0, 0, 120), sh.get_rect(), 24)
                self.screen.blit(sh, r.move(-6, 4).inflate(18, 18))
            self.screen.blit(im, r)
            if ad <= 0.5:
                rrect(self.screen, (255, 255, 255), r.inflate(12, 12), 14, 5)
                if self.lib.is_fav(gs[j]):
                    star(self.screen, (r.right - 30, r.top + 32), 26)
        self.screen.set_clip(None)
        # title-screen side panel
        px, py, pw, ph = 1360, 230, 500, 375
        rrect(self.screen, (0, 0, 0, 0), (px - 8, py - 8, pw + 16, ph + 16), 18)
        frame = pygame.Surface((pw + 16, ph + 16), pygame.SRCALPHA); rrect(frame, (10, 10, 18, 200), frame.get_rect(), 18)
        self.screen.blit(frame, (px - 8, py - 8))
        if g:
            ts = self.img.get(g.thumb("Named_Titles"), pw, ph)
            if ts:
                r = ts.get_rect(center=(px + pw / 2, py + ph / 2)); self.screen.blit(ts, r)
            elif ts is None:
                text(self.screen, self.fonts(26), "No title screen", (px + pw / 2, py + ph / 2), (150, 155, 170), anchor="center")
        text(self.screen, self.fonts(22, True), "TITLE SCREEN", (px, py + ph + 18), (170, 175, 190))
        # title + info
        if g:
            text(self.screen, self.fonts(58, True), g.title, (cx, 770), anchor="midtop", maxw=1250)
            info = []
            m = self.meta.get(g)
            if m:
                if m[0]: info.append(str(m[0]))
                if m[1]: info.append(m[1])
            sysname = FRIENDLY.get(g.system, (g.system,))[0] if s["special"] else None
            if sysname: info.append(sysname)
            t = [x for x in tags(g.label) if len(x) < 30][:2]
            info += t
            if info: text(self.screen, self.fonts(28), "  ·  ".join(info), (cx, 846), (205, 210, 225), anchor="midtop", maxw=1250)
            if not g.core:
                text(self.screen, self.fonts(24), "No core assigned", (cx, 892), (240, 150, 120), anchor="midtop")
            elif g.versions:                                        # "3 versions · (X) to choose", with this pad's own X button
                f1, f2 = self.fonts(26, True), self.fonts(26)
                a, b = f"{len(g.versions)} versions  ·  ", "  to choose"
                bw = self.draw_button("x", 0, 0, draw=False)
                x0 = cx - (f1.size(a)[0] + bw + f2.size(b)[0]) / 2
                text(self.screen, f1, a, (x0, 908), (150, 200, 255), anchor="midleft")
                x1 = self.draw_button("x", x0 + f1.size(a)[0], 908)
                text(self.screen, f2, b, (x1 - 10, 908), (190, 205, 230), anchor="midleft")
        else:
            text(self.screen, self.fonts(40), "No games here", (W / 2, H / 2), anchor="center")
        if self.jump and time.time() < self.jump[1]:
            box = pygame.Surface((220, 220), pygame.SRCALPHA); rrect(box, (0, 0, 0, 190), box.get_rect(), 30)
            self.screen.blit(box, (cx - 110, cy - 110))
            text(self.screen, self.fonts(150, True), self.jump[0], (cx, cy), anchor="center")
        if not hints: return
        hs = [("a", "Play"), ("b", "Back"), ("y", "Favorite")]
        if g and g.versions: hs.append(("x", "Versions"))
        self.draw_hints(hs + [("lbrb", "Jump A–Z")])

    def draw_versions(self):
        self.draw_games(hints=False)
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 175)); self.screen.blit(dim, (0, 0))
        vs = self.vlist; show = 7; top = max(0, min(self.vsel - show // 2, len(vs) - show))
        box = pygame.Rect(0, 0, 1180, 190 + 84 * min(show, len(vs))); box.center = (W / 2, H / 2 - 20)
        rrect(self.screen, (28, 30, 42), box, 28); rrect(self.screen, (90, 95, 115), box, 28, 3)
        text(self.screen, self.fonts(40, True), vs[0].title, (W / 2, box.top + 34), anchor="midtop", maxw=1080)
        text(self.screen, self.fonts(26), f"{len(vs)} versions", (W / 2, box.top + 88), (170, 175, 190), anchor="midtop")
        for row, k in enumerate(range(top, min(len(vs), top + show))):
            r = pygame.Rect(0, 0, 1080, 70); r.midtop = (W / 2, box.top + 140 + row * 84)
            on = k == self.vsel
            rrect(self.screen, (230, 232, 240) if on else (55, 58, 75), r, 18)
            folder = os.path.basename(os.path.dirname(split_archive(vs[k].path)[0]))
            text(self.screen, self.fonts(28, True), vs[k].label, (r.left + 28, r.centery), (20, 22, 30) if on else (230, 232, 240),
                 anchor="midleft", shadow=False, maxw=760)
            text(self.screen, self.fonts(22), folder, (r.right - 24, r.centery), (90, 95, 110) if on else (150, 155, 170),
                 anchor="midright", shadow=False, maxw=260)
        self.draw_hints([("a", "Play"), ("b", "Back")])

    @property
    def POWER_MENU(self):
        return ("Resume", f"Sound: {'On' if self.sfx.enabled else 'Off'}",
                f"Player: {'Built-in (beta)' if self.settings.get('engine') else 'RetroArch'}",
                f"Games: {'One per game' if self.settings['one_per_game'] else 'Show all'}", "Set up controller", "Exit Insert Coin")

    def draw_quit(self):
        self.draw_systems(hints=False)
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 170)); self.screen.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 640, 200 + 96 * len(self.POWER_MENU)); box.center = (W / 2, H / 2)
        rrect(self.screen, (28, 30, 42), box, 28); rrect(self.screen, (90, 95, 115), box, 28, 3)
        text(self.screen, self.fonts(44, True), "Insert Coin", (W / 2, box.top + 48), anchor="midtop")
        for k, lbl in enumerate(self.POWER_MENU):
            r = pygame.Rect(0, 0, 480, 76); r.center = (W / 2, box.top + 180 + k * 96)
            on = self.quit_sel == k
            rrect(self.screen, (230, 232, 240) if on else (55, 58, 75), r, 20)
            text(self.screen, self.fonts(32, True), lbl, r.center, (20, 22, 30) if on else (230, 232, 240), anchor="center", shadow=False)
        self.draw_hints([("a", "Choose"), ("b", "Close")])

    def draw_setup(self):
        s = self.setup; act, shown, what, optional = SETUP_STEPS[s["step"]]
        self.draw_background((60, 70, 100))
        self.draw_header("Set up your controller", s["name"])
        text(self.screen, self.fonts(30), f"Step {s['step'] + 1} of {len(SETUP_STEPS)}", (W / 2, 250), (190, 195, 210), anchor="midtop")
        text(self.screen, self.fonts(40), "Press the button you want for", (W / 2, 330), anchor="midtop")
        cy = 500                                                    # the button being asked for, big
        if shown in ("up", "down", "left", "right"):
            pygame.draw.circle(self.screen, (110, 116, 132), (W / 2, cy), 70)
            pts = {"up": [(0, -34), (30, 18), (-30, 18)], "down": [(0, 34), (30, -18), (-30, -18)],
                   "left": [(-34, 0), (18, -30), (18, 30)], "right": [(34, 0), (-18, -30), (-18, 30)]}[shown]
            pygame.draw.polygon(self.screen, (255, 255, 255), [(W / 2 + x, cy + y) for x, y in pts])
        else:
            f = self.fonts(80, True); tw = max(140, f.size(shown)[0] + 70)
            if len(shown) == 1: pygame.draw.circle(self.screen, (110, 116, 132), (W / 2, cy), 70)
            else: rrect(self.screen, (120, 130, 150), pygame.Rect(W / 2 - tw / 2, cy - 60, tw, 120), 28)
            text(self.screen, f, shown, (W / 2, cy), anchor="center", shadow=False)
        text(self.screen, self.fonts(44, True), what, (W / 2, 610), anchor="midtop")
        if s["msg"]:
            text(self.screen, self.fonts(30), s["msg"], (W / 2, 690), (255, 170, 120), anchor="midtop")
        elif optional:
            text(self.screen, self.fonts(30), "Optional - press your B button to skip", (W / 2, 690), (190, 195, 210), anchor="midtop")
        for k in range(len(SETUP_STEPS)):                          # progress dots
            x = W / 2 + (k - (len(SETUP_STEPS) - 1) / 2) * 34
            pygame.draw.circle(self.screen, (255, 255, 255) if k <= s["step"] else (90, 95, 115), (x, 790), 9 if k == s["step"] else 7)
        text(self.screen, self.fonts(26), "Buttons, the d-pad and sticks all work.   Esc on the keyboard cancels.",
             (W / 2, H - 70), (170, 175, 190), anchor="midtop")

    def splash(self, g, engine=False):
        self.screen.fill((0, 0, 0))
        im = self.img.get(g.thumb("Named_Boxarts"), 420, 520)
        if im: self.screen.blit(im, im.get_rect(center=(W / 2, H / 2 - 60)))
        text(self.screen, self.fonts(44, True), g.title, (W / 2, H / 2 + 250), anchor="midtop", maxw=1500)
        text(self.screen, self.fonts(26), f"Starting…   ({self.pad_quit.get(self.cur_pad, QUIT_COMBO[self.style]) if self.style != 'keyboard' else 'Esc'} opens the game menu)", (W / 2, H / 2 + 320), (180, 185, 200), anchor="midtop")
        pygame.display.flip()

    def draw_empty(self):
        self.draw_background((60, 70, 100))
        self.draw_header("Insert Coin", "No games found")
        lines = ["Insert Coin shows the games in your RetroArch playlists,",
                 "but none were found in ~/.config/retroarch/playlists.",
                 "", "Open RetroArch, use Import Content to scan your games,",
                 "then start Insert Coin again."]
        for n, ln in enumerate(lines):
            text(self.screen, self.fonts(34), ln, (W / 2, 360 + n * 56), (220, 224, 235), anchor="midtop")
        self.draw_hints([("b", "Exit")])

    def draw(self):
        self.img.pump()
        if self.screen_mode == "setup":
            return self.draw_setup()
        if not self.lib.systems:
            return self.draw_empty()
        {"systems": self.draw_systems, "games": self.draw_games, "quit": self.draw_quit,
         "versions": self.draw_versions}[self.screen_mode]()
        if self.toast and time.time() < self.toast[1]:
            f = self.fonts(30); w = f.size(self.toast[0])[0] + 60
            r = pygame.Rect(0, 0, w, 64); r.midtop = (W / 2, H - 150 if self.screen_mode == "quit" else 150)   # clear of the menu
            box = pygame.Surface(r.size, pygame.SRCALPHA); rrect(box, (0, 0, 0, 200), box.get_rect(), 32); self.screen.blit(box, r)
            text(self.screen, f, self.toast[0], r.center, anchor="center", shadow=False)

    # -- main loop
    def run(self):
        if self.shot: return self.screenshots()
        self.running = True
        while self.running:
            for e in pygame.event.get(): self.handle(e)
            self.tick_repeat(); self.draw(); pygame.display.flip(); self.clock.tick(60)
        pygame.quit()

    def screenshots(self):
        os.makedirs(self.shot, exist_ok=True)
        def snap(name):
            for _ in range(40): self.draw()                         # let animations settle
            pygame.image.save(self.screen, f"{self.shot}/{name}.png")
        if not self.lib.systems:
            print("No RetroArch playlists with games found - nothing to render."); pygame.quit(); return
        snap("1_systems")
        # the two largest systems, a third of the way into each list, so neighbours are visible
        big = sorted((i for i, s in enumerate(self.lib.systems) if not s["special"]),
                     key=lambda i: -len(self.lib.systems[i]["games"]))[:2] or [0]
        time.sleep(1.5)                                             # give the metadata thread a moment
        for n, i in enumerate(big, 2):
            self.si = i; self.screen_mode = "games"
            self.gi[self.sys["id"]] = len(self.games()) // 3; self.gpos = float(self.cur_gi())
            snap(f"{n}_games_{re.sub(r'[^a-z0-9]+', '_', self.sys['name'].lower())}")
        self.screen_mode = "systems"; self.si = 0; self.spos = 0.0; snap(f"{len(big) + 2}_systems_first")
        self.screen_mode = "quit"; snap(f"{len(big) + 3}_quit")
        # the button-hint bar in every controller style, stacked into one image
        self.si = big[0]; self.screen_mode = "games"; strips = []
        for st in GLYPHS:
            self.style = st; self.draw()
            strips.append(self.screen.subsurface((0, H - 110, W, 110)).copy())
        sheet = pygame.Surface((W, 110 * len(strips)))
        for k, strip in enumerate(strips): sheet.blit(strip, (0, 110 * k))
        pygame.image.save(sheet, f"{self.shot}/{len(big) + 4}_button_styles.png")
        pygame.quit()


if __name__ == "__main__":
    a = sys.argv[1:]
    shot = a[a.index("--shot") + 1] if "--shot" in a else None
    if shot: os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
    if not shot: start_log()
    try:
        App(windowed="--windowed" in a, shot=shot).run()
        log.info("Insert Coin closed")
    except BaseException as e:
        if not isinstance(e, SystemExit): log.exception("Insert Coin stopped because of an error")
        raise
