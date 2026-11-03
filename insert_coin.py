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
  In a game: Select+Start quits back here, click both sticks for RetroArch's menu.

Options: --windowed   run in a window (for testing)
         --shot DIR   render sample screens to PNG files and exit (no display needed)
"""
__version__ = "0.1.0"

import json, os, re, sys, time, random, threading, subprocess, collections

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from pygame._sdl2 import controller as sdlc

HOME = os.path.expanduser("~")
RA = f"{HOME}/.config/retroarch"
APPDIR = f"{HOME}/.local/share/insert-coin"
CACHE = f"{HOME}/.cache/insert-coin"
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
input_quit_gamepad_combo = "4"
quit_press_twice = "false"
input_menu_toggle_gamepad_combo = "2"
video_fullscreen = "true"
"""


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
    __slots__ = ("label", "path", "core", "db", "title", "letter", "key", "system")

    def __init__(self, it, playlist_db, default_core):
        self.label = it.get("label") or os.path.splitext(os.path.basename(it["path"].split("#")[0]))[0]
        self.path = it["path"]
        c = it.get("core_path") or ""
        self.core = c if c not in ("", "DETECT") and os.path.exists(c) else default_core
        self.db = it.get("db_name") or playlist_db
        self.title = clean_title(self.label)
        self.letter = letter_of(self.label)
        self.key = sort_key(self.label)
        self.system = (self.db or "")[:-4] if (self.db or "").endswith(".lpl") else self.db

    def thumb(self, kind):
        return f"{RA}/thumbnails/{thumb_system(self.db)}/{kind}/{sanitize(self.label)}.png"


class Library:
    def __init__(self):
        self.defaults = {}
        self.systems = []          # list of dicts: id, name, maker, color, games, special
        self.load()

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f: return json.load(f)
        except Exception: return None

    def load(self):
        self.systems = []
        pls = {}
        for f in sorted(os.listdir(f"{RA}/playlists")):
            if f.endswith(".lpl"):
                d = self._read(f"{RA}/playlists/{f}")
                if d: pls[f[:-4]] = d
        for name, d in pls.items():
            dc = d.get("default_core_path") or ""
            self.defaults[name + ".lpl"] = dc if dc and os.path.exists(dc) else None
        for name, d in sorted(pls.items(), key=lambda kv: (ORDER.get(kv[0], 99), kv[0])):
            games = [Game(it, name + ".lpl", self.defaults[name + ".lpl"]) for it in d.get("items", []) if it.get("path")]
            if not games: continue                                  # tidy: hide empty systems
            games.sort(key=lambda g: g.key)
            fn, maker, col = FRIENDLY.get(name, (name.split(" - ")[-1], name.split(" - ")[0], (90, 100, 130)))
            self.systems.append({"id": name, "name": fn, "maker": maker, "color": col, "games": games, "special": None})
        self.favorites_raw = (self._read(f"{RA}/content_favorites.lpl") or {"version": "1.5", "items": []})
        self.refresh_specials()

    def _special_games(self, items):
        out = []
        for it in items:
            if not it.get("path") or not os.path.exists(it["path"].split("#")[0]): continue
            db = it.get("db_name") or ""
            out.append(Game(it, db, self.defaults.get(db)))
        return out

    def refresh_specials(self):
        self.systems = [s for s in self.systems if not s["special"]]
        hist = self._read(f"{RA}/content_history.lpl") or {"items": []}
        self.favorites_raw = self._read(f"{RA}/content_favorites.lpl") or {"version": "1.5", "items": []}
        fav = sorted(self._special_games(self.favorites_raw.get("items", [])), key=lambda g: g.key)
        seen, rec = set(), []
        for g in self._special_games(hist.get("items", [])):
            if g.path not in seen: seen.add(g.path); rec.append(g)
        specials = []
        if fav: specials.append({"id": "favorites", "name": "Favorites", "maker": "Your picks", "color": (230, 180, 40), "games": fav, "special": "fav"})
        if rec: specials.append({"id": "recent", "name": "Recently Played", "maker": "Pick up where you left off", "color": (60, 170, 200), "games": rec[:60], "special": "recent"})
        self.systems = specials + self.systems
        self.fav_paths = {it.get("path") for it in self.favorites_raw.get("items", [])}

    def toggle_favorite(self, g):
        items = self.favorites_raw.setdefault("items", [])
        if g.path in self.fav_paths:
            items[:] = [it for it in items if it.get("path") != g.path]; added = False
        else:
            items.append({"path": g.path, "label": g.label, "core_path": g.core or "DETECT",
                          "core_name": "DETECT" if not g.core else os.path.basename(g.core).replace("_libretro.so", ""),
                          "crc32": "00000000|crc", "db_name": g.db or ""}); added = True
        self.favorites_raw.setdefault("version", "1.5")
        p = f"{RA}/content_favorites.lpl"; tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.favorites_raw, f, indent=2)
        os.replace(tmp, p)
        self.fav_paths = {it.get("path") for it in items}
        return added


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
        rom = os.path.splitext(os.path.basename(g.path.split("#")[0]))[0]
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
        pygame.init(); sdlc.init()
        self.open_display()
        self.fonts = Fonts()
        self.lib = Library()
        self.meta = Meta({s["id"] for s in self.lib.systems if not s["special"]})
        self.img = Images(sync=bool(shot))
        self.pads = {}
        self.open_pads()
        self.screen_mode = "systems"                              # systems | games | quit
        self.si = next((i for i, s in enumerate(self.lib.systems) if not s["special"]), 0)
        self.gi = {}                                              # system id -> selected game index
        self.spos = float(self.si); self.gpos = 0.0
        self.toast = None; self.jump = None
        self.prev_bg = None; self.bg_change = 0
        self.hold = {}; self.quit_sel = 1
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
                try: self.pads[i] = sdlc.Controller(i)
                except Exception: pass

    # -- current state helpers
    @property
    def sys(self): return self.lib.systems[self.si]

    def games(self): return self.sys["games"]

    def cur_gi(self): return min(self.gi.get(self.sys["id"], 0), max(0, len(self.games()) - 1))

    def cur_game(self):
        g = self.games(); return g[self.cur_gi()] if g else None

    def say(self, msg, secs=2.0): self.toast = (msg, time.time() + secs)

    # -- actions
    def move(self, d):
        if self.screen_mode == "systems":
            self.si = (self.si + d) % len(self.lib.systems)
        elif self.screen_mode == "games":
            n = len(self.games())
            if n: self.gi[self.sys["id"]] = max(0, min(n - 1, self.cur_gi() + d))
        elif self.screen_mode == "quit":
            self.quit_sel = 1 - self.quit_sel

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
        self.gi[self.sys["id"]] = j; self.jump = (gs[j].letter, time.time() + 0.9)

    def accept(self):
        if self.screen_mode == "systems":
            self.screen_mode = "games"; self.gpos = float(self.cur_gi())
        elif self.screen_mode == "games":
            g = self.cur_game()
            if g: self.launch(g)
        elif self.screen_mode == "quit":
            if self.quit_sel == 0: self.running = False
            else: self.screen_mode = "systems"

    def back(self):
        if self.screen_mode == "games": self.screen_mode = "systems"
        elif self.screen_mode == "systems": self.screen_mode = "quit"; self.quit_sel = 1
        else: self.screen_mode = "systems"

    def favorite(self):
        g = self.cur_game() if self.screen_mode == "games" else None
        if not g: return
        if subprocess.run(["pgrep", "-x", "retroarch"], capture_output=True).returncode == 0:
            self.say("Close RetroArch first to change favorites"); return
        added = self.lib.toggle_favorite(g)
        self.say(("Added to Favorites: " if added else "Removed from Favorites: ") + g.title)
        sid = self.sys["id"]; self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0)
        if self.sys["id"] != sid: self.screen_mode = "systems"

    def launch(self, g):
        if not g.core:
            self.say("No core is set for this game yet - assign one in RetroArch"); return
        if not os.path.exists(g.path.split("#")[0]):
            self.say("ROM file not found"); return
        self.draw(); self.splash(g)
        os.makedirs(APPDIR, exist_ok=True)
        with open(f"{APPDIR}/launch.cfg", "w") as f: f.write(LAUNCH_CFG)
        pygame.display.quit()
        t0 = time.time()
        try:
            subprocess.run(["retroarch", "-L", g.core, g.path, f"--appendconfig={APPDIR}/launch.cfg"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.say(f"Could not start RetroArch: {e}")
        pygame.display.init(); self.open_display(); self.open_pads()
        self.img.cache.clear(); self.prev_bg = None
        pygame.event.clear(); self.hold.clear()
        sid, gid = self.sys["id"], self.cur_gi()
        self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.gi[sid] = gid
        if time.time() - t0 < 3: self.say("The game closed straight away - it may need a different core")

    # -- input handling with key repeat
    REPEAT_FIRST, REPEAT = 0.32, 0.075

    def press(self, act):
        if act in ("left", "right", "up", "down"):
            d = -1 if act in ("left", "up") else 1
            if self.screen_mode == "games" and act in ("up", "down"): d *= 10
            self.move(d)
        elif act == "a": self.accept()
        elif act == "b": self.back()
        elif act == "y": self.favorite()
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
             pygame.K_f: "y", pygame.K_PAGEUP: "lb", pygame.K_PAGEDOWN: "rb"}
        B = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
             pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
             pygame.CONTROLLER_BUTTON_A: "a", pygame.CONTROLLER_BUTTON_B: "b", pygame.CONTROLLER_BUTTON_Y: "y",
             pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "lb", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb",
             pygame.CONTROLLER_BUTTON_START: "a", pygame.CONTROLLER_BUTTON_BACK: "b"}
        if e.type == pygame.QUIT: self.running = False
        elif e.type == pygame.KEYDOWN and e.key in K: self.set_hold(K[e.key], True)
        elif e.type == pygame.KEYUP and e.key in K: self.set_hold(K[e.key], False)
        elif e.type == pygame.CONTROLLERBUTTONDOWN and e.button in B: self.set_hold(B[e.button], True)
        elif e.type == pygame.CONTROLLERBUTTONUP and e.button in B: self.set_hold(B[e.button], False)
        elif e.type == pygame.CONTROLLERAXISMOTION and e.axis in (pygame.CONTROLLER_AXIS_LEFTX, pygame.CONTROLLER_AXIS_LEFTY):
            neg, pos = ("left", "right") if e.axis == pygame.CONTROLLER_AXIS_LEFTX else ("up", "down")
            v = e.value / 32767
            self.set_hold(neg, v < -0.55); self.set_hold(pos, v > 0.55)
        elif e.type == pygame.CONTROLLERDEVICEADDED: self.open_pads()
        elif e.type == pygame.CONTROLLERDEVICEREMOVED: self.pads = {}; self.open_pads()

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

    def draw_hints(self, hints):
        x = W / 2 - sum(self.fonts(26).size(t)[0] + 90 for _, t in hints) / 2
        y = H - 70
        colors = {"A": (90, 190, 90), "B": (220, 80, 70), "Y": (230, 190, 50), "LB": (120, 130, 150), "RB": (120, 130, 150)}
        for btn, label in hints:
            c = colors.get(btn, (120, 130, 150))
            if len(btn) == 1:
                pygame.draw.circle(self.screen, c, (x + 22, y + 16), 21)
                text(self.screen, self.fonts(24, True), btn, (x + 22, y + 16), anchor="center", shadow=False)
                x += 54
            else:
                for part in btn.split():
                    r = pygame.Rect(x, y - 3, 64, 38); rrect(self.screen, c, r, 10)
                    text(self.screen, self.fonts(22, True), part, r.center, anchor="center", shadow=False)
                    x += 74
                x += 2
            r = text(self.screen, self.fonts(26), label, (x, y + 16), (225, 228, 238), anchor="midleft"); x = r.right + 36

    def draw_systems(self):
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
        self.draw_hints([("A", "Open"), ("B", "Power")])

    def draw_games(self):
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
                if gs[j].path in self.lib.fav_paths:
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
        else:
            text(self.screen, self.fonts(40), "No games here", (W / 2, H / 2), anchor="center")
        if self.jump and time.time() < self.jump[1]:
            box = pygame.Surface((220, 220), pygame.SRCALPHA); rrect(box, (0, 0, 0, 190), box.get_rect(), 30)
            self.screen.blit(box, (cx - 110, cy - 110))
            text(self.screen, self.fonts(150, True), self.jump[0], (cx, cy), anchor="center")
        self.draw_hints([("A", "Play"), ("B", "Back"), ("Y", "Favorite"), ("LB RB", "Jump A–Z")])

    def draw_quit(self):
        self.draw_systems()
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 170)); self.screen.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 760, 330); box.center = (W / 2, H / 2)
        rrect(self.screen, (28, 30, 42), box, 28); rrect(self.screen, (90, 95, 115), box, 28, 3)
        text(self.screen, self.fonts(44, True), "Exit Insert Coin?", (W / 2, box.top + 60), anchor="midtop")
        for k, lbl in enumerate(("Exit", "Stay")):
            r = pygame.Rect(0, 0, 250, 80); r.center = (W / 2 + (-150 if k == 0 else 150), box.bottom - 95)
            rrect(self.screen, (230, 232, 240) if self.quit_sel == k else (55, 58, 75), r, 20)
            text(self.screen, self.fonts(34, True), lbl, r.center, (20, 22, 30) if self.quit_sel == k else (230, 232, 240), anchor="center", shadow=False)

    def splash(self, g):
        self.screen.fill((0, 0, 0))
        im = self.img.get(g.thumb("Named_Boxarts"), 420, 520)
        if im: self.screen.blit(im, im.get_rect(center=(W / 2, H / 2 - 60)))
        text(self.screen, self.fonts(44, True), g.title, (W / 2, H / 2 + 250), anchor="midtop", maxw=1500)
        text(self.screen, self.fonts(26), "Starting…   (Select + Start quits the game)", (W / 2, H / 2 + 320), (180, 185, 200), anchor="midtop")
        pygame.display.flip()

    def draw(self):
        self.img.pump()
        {"systems": self.draw_systems, "games": self.draw_games, "quit": self.draw_quit}[self.screen_mode]()
        if self.toast and time.time() < self.toast[1]:
            f = self.fonts(30); w = f.size(self.toast[0])[0] + 60
            r = pygame.Rect(0, 0, w, 64); r.midtop = (W / 2, 150)
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
        snap("1_systems")
        self.si = next(i for i, s in enumerate(self.lib.systems) if s["id"] == "FBNeo - Arcade Games")
        self.screen_mode = "games"
        gs = self.games(); self.gi[self.sys["id"]] = next((k for k, g in enumerate(gs) if "super spy" in g.label.lower()), 0)
        self.gpos = float(self.cur_gi()); self.lib.fav_paths = set(self.lib.fav_paths) | {self.cur_game().path}; time.sleep(1.5); snap("2_games_arcade")
        self.si = next(i for i, s in enumerate(self.lib.systems) if s["id"].startswith("Nintendo - Super")); self.gpos = 0.0
        self.jump_letter(1); self.jump_letter(1); self.gpos = float(self.cur_gi()); self.jump = None; snap("3_games_snes")
        self.screen_mode = "systems"; self.si = 0; self.spos = 0.0; snap("4_systems_favorites")
        self.screen_mode = "quit"; snap("5_quit")
        pygame.quit()


if __name__ == "__main__":
    a = sys.argv[1:]
    shot = a[a.index("--shot") + 1] if "--shot" in a else None
    if shot: os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
    App(windowed="--windowed" in a, shot=shot).run()
