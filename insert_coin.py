#!/usr/bin/env python3
"""Insert Coin - a controller-driven, console-style front end for RetroArch.

It reads RetroArch's own playlists, thumbnails, favorites and history, and
launches games with each game's assigned core: through RetroArch, or in its own
built-in player (engine.py, beta; B menu > Player). Nothing is duplicated:
whatever works in RetroArch works here.

Controls (Xbox-style pad; keyboard in brackets)
  D-pad / left stick  move            [arrows]
  A                   open / play     [Enter]
  B                   back            [Backspace / Esc]
  Y                   toggle favorite [F]
  X                   versions of a game [V]
  LB / RB             previous / next letter   [PageUp / PageDown]
  Menu sounds can be switched off in the B menu (saved in ~/.config/insert-coin/settings.json).
  In a game: Select+Start opens the game menu (Resume / Quit game, or RetroArch's Quick Menu).
  Browser and Flash games (~/.config/insert-coin/browser_games.json): Select+Start returns here.

Options: --windowed   run in a window (for testing)
         --shot DIR   render sample screens to PNG files and exit (no display needed)
"""
__version__ = "0.4.3"

import json, os, re, sys, time, random, threading, subprocess, collections, logging, faulthandler, platform, signal, shutil
import ctypes, fcntl, functools, http.server, urllib.parse

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


class WebGame(Game):
    """A browser game: a folder with an HTML start page, listed in browser_games.json. Insert Coin serves the
    folder on 127.0.0.1 and opens the page full-screen in a browser (see App.launch_browser)."""
    __slots__ = ("folder", "start", "art", "info", "buttons")

    def __init__(self, spec, playlist):
        self.folder = os.path.expanduser(spec["folder"])
        self.start = spec.get("start") or "index.html"
        self.label = spec.get("title") or os.path.basename(self.folder.rstrip("/"))
        self.path = os.path.join(self.folder, self.start)
        self.core = None; self.db = playlist; self.system = playlist; self.versions = None
        self.title = self.label; self.letter = letter_of(self.label); self.key = sort_key(self.label)
        art = {k: os.path.join(self.folder, os.path.expanduser(spec[k])) for k in ("boxart", "title_screen", "snap") if spec.get(k)}
        first = next(iter(art.values()), "")
        self.art = {"Named_Boxarts": art.get("boxart", first), "Named_Titles": art.get("title_screen", first),
                    "Named_Snaps": art.get("snap", first)}
        self.info = [str(spec.get("year") or ""), spec.get("publisher") or ""] if spec.get("year") or spec.get("publisher") else None
        self.buttons = spec.get("buttons") or {}                    # Flash games: pad button -> key

    @property
    def flash(self): return self.start.lower().endswith(".swf")

    def thumb(self, kind):
        return self.art.get(kind, "")


def load_web_playlists():
    """browser_games.json in the config folder: {"playlists": [{"name", "maker", "color", "games": [{"title",
    "folder", "start", "boxart", "title_screen", "snap", "year", "publisher"}]}]}. Image paths are relative to the
    game's folder (or absolute). Games whose folder or start page is missing are skipped."""
    try:
        with open(f"{CONFDIR}/browser_games.json", encoding="utf-8") as f: d = json.load(f)
    except FileNotFoundError: return []
    except Exception as e: log.warning("browser_games.json could not be read: %s", e); return []
    out = []
    for p in d.get("playlists", []):
        name = p.get("name") or "Browser games"
        games = []
        for spec in p.get("games", []):
            try:
                g = WebGame(spec, name)
                if os.path.isfile(g.path): games.append(g)
                else: log.warning("Browser game not found: %s", g.path)
            except Exception as e: log.warning("Browser game skipped (%s): %s", e, spec)
        if games:
            col = tuple(p.get("color") or (230, 90, 60))[:3]
            out.append({"id": "web:" + name, "name": name, "maker": p.get("maker") or "Browser games", "color": col,
                        "games": sorted(games, key=lambda g: g.key), "special": None})
    return out


# ---------------------------------------------------------------- browser games: local server, browser, pad watch
RUFFLE = f"{APPDIR}/ruffle"                                         # Ruffle's self-hosted web build: plays Flash (.swf)
FLASH_PAGE = "__insert_coin_flash__.html"
# Flash games only know the keyboard: pad button -> key(s) it presses (Ruffle's names; overridable per game with
# "buttons"; "X+Space" presses both)
FLASH_BUTTONS = {"dpad-up": "Up", "dpad-down": "Down", "dpad-left": "Left", "dpad-right": "Right",
                 "south": "Space", "east": "Enter", "west": "Z", "north": "X", "start": "Enter"}
PAD_INDEX = {"south": 0, "east": 1, "west": 2, "north": 3, "left-trigger": 4, "right-trigger": 5, "select": 8, "start": 9,
             "dpad-up": 12, "dpad-down": 13, "dpad-left": 14, "dpad-right": 15}      # the browser's standard layout
KEYCODES = {"Up": 38, "Down": 40, "Left": 37, "Right": 39, "Space": 32, "Enter": 13, "Shift": 16, "Ctrl": 17,
            "Alt": 18, "Tab": 9, "Escape": 27, "Backspace": 8, **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}}
KEYNAMES = {"Up": ("ArrowUp", "ArrowUp"), "Down": ("ArrowDown", "ArrowDown"), "Left": ("ArrowLeft", "ArrowLeft"),
            "Right": ("ArrowRight", "ArrowRight"), "Space": (" ", "Space"), "Enter": ("Enter", "Enter"),
            "Shift": ("Shift", "ShiftLeft"), "Ctrl": ("Control", "ControlLeft"), "Alt": ("Alt", "AltLeft"),
            "Tab": ("Tab", "Tab"), "Escape": ("Escape", "Escape"), "Backspace": ("Backspace", "Backspace"),
            **{c: (c.lower(), "Key" + c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}, **{c: (c, "Digit" + c) for c in "0123456789"}}


def flash_page(swf, title, buttons=None, native=False):
    """A full-screen page that plays one .swf with Ruffle, the pad's buttons pressing the keys the game uses.

    Ruffle presses the keys for most buttons itself. The page handles the pad's select button (A on Xbox pads, Cross
    on PlayStation, the right-hand A on Nintendo-style pads, as in Insert Coin's menus) and any button set to several
    keys: many Flash menus are mouse-only, so the right stick moves a pointer and, while it shows, that button
    clicks; otherwise it presses its keys. Any other button hides the pointer at once, so it never gets in the way.
    native=True: Insert Coin sends real keys and mouse input itself (FlashPad), so the page leaves the pad alone."""
    keys = lambda v: [k for k in str(v).split("+") if k in KEYCODES]
    mapping = {b: keys(v) for b, v in {**FLASH_BUTTONS, **(buttons or {})}.items() if b in PAD_INDEX}
    ev = lambda k: {"key": KEYNAMES[k][0], "code": KEYNAMES[k][1], "keyCode": KEYCODES[k]}
    page = {name: [ev(k) for k in ks] for name, ks in mapping.items()}      # all buttons, for the page's own handling
    cfg = {"autoplay": "on", "unmuteOverlay": "hidden", "splashScreen": False, "letterbox": "on", "contextMenu": "off",
           "showSwfDownload": False}
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;")
    return f"""<!doctype html><meta charset="utf-8"><title>{esc(title)}</title>
<style>html,body{{margin:0;height:100%;background:#000;overflow:hidden}}ruffle-player{{width:100vw;height:100vh;display:block}}
#ptr{{position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:9;display:none;
border-left:11px solid transparent;border-right:11px solid transparent;border-bottom:26px solid #fff;
margin-left:-11px;filter:drop-shadow(0 0 2px #000) drop-shadow(0 0 1px #000);transform-origin:50% 0;rotate:-30deg}}</style>
<script>
const MAP = {json.dumps(page)}, INDEX = {json.dumps(PAD_INDEX)}, NATIVE = {json.dumps(bool(native))};
// The select button depends on the pad (as in Insert Coin's menus); the browser's layout is by position.
const selectButton = id => /057e|nintendo|0583.{{0,12}}2060|snes/i.test(id) ? "east" : "south";
const mineFor = id => {{ const m = new Set([selectButton(id)]);
  for (const [b, ks] of Object.entries(MAP)) if (ks.length > 1) m.add(b); return m; }};
// Ruffle presses the keys for the buttons the page doesn't handle; set once the first pad is seen.
window.RufflePlayer = {{config: {json.dumps(cfg)}}};
const ruffleMapping = id => {{ const out = {{}}, mine = mineFor(id); if (NATIVE) return out;
  for (const [b, ks] of Object.entries(MAP)) if (!mine.has(b) && ks.length) out[b] = ks[0].keyCode; return out; }};
</script>
<script src="/__ruffle__/ruffle.js"></script>
<div id="ptr"></div>
<script>
window.addEventListener("load", () => {{
  const pads = () => [...(navigator.getGamepads ? navigator.getGamepads() : [])].filter(Boolean);
  const ptr = document.getElementById("ptr");
  let p = null;
  const start = id => {{                         // the player, with Ruffle's button mapping for this pad
    window.RufflePlayer.config.gamepadButtonMapping = ruffleMapping(id);
    p = window.RufflePlayer.newest().createPlayer(); document.body.appendChild(p);
    p.load({{url: {json.dumps(urllib.parse.quote(swf))}}}).then(() => p.focus());
    p.focus(); window.addEventListener("click", () => p.focus());
  }};
  // (browsers only list a pad once it's been used on the page, so this is usually the standard layout: A / Cross)
  start((pads()[0] || {{}}).id || "");
  const target = () => (p && p.shadowRoot && p.shadowRoot.querySelector("canvas")) || p;
  // Ruffle reads offsetX/Y, and Chrome works those out for page-made pointer events as if unscaled: at 2x display
  // scaling a click would land at half the distance. Measure that per event and compensate, so any scaling works.
  const scale = (c, r) => {{ let k = 1;
    c.addEventListener("ic-measure", e => {{ if (e.offsetX > 0) k = 100 / e.offsetX; }}, {{once: true}});
    c.dispatchEvent(new PointerEvent("ic-measure", {{clientX: r.left + 100, clientY: r.top + 100}})); return k; }};
  const mouse = (type, buttons) => {{ const c = target(); if (!c) return;
    const r = c.getBoundingClientRect(), k = scale(c, r);
    c.dispatchEvent(new PointerEvent(type, {{bubbles: true, composed: true, clientX: r.left + (x - r.left) * k,
        clientY: r.top + (y - r.top) * k, pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons}})); }};
  const key = (type, k) => p && p.dispatchEvent(new KeyboardEvent(type, {{key: k.key, code: k.code, keyCode: k.keyCode,
      which: k.keyCode, bubbles: true, composed: true}}));
  // armed: the pointer was moved since its last click, so the select button clicks; after a click it goes back to
  // the game ("press space to continue" right after choosing a menu item) until the pointer is moved again.
  let x = innerWidth / 2, y = innerHeight / 2, shown = -1e9, armed = false, prev = {{}}, held = {{}};
  // native: Insert Coin moves the real mouse (DevTools input); the arrow just shows where it is
  let nx = x, ny = y, nshown = -1e9;
  if (NATIVE) for (const t of ["pointermove", "pointerdown"]) addEventListener(t, e => {{
    nx = e.clientX; ny = e.clientY; nshown = performance.now(); }}, true);
  (function tick() {{
    const g = pads()[0];
    if (g && p && !NATIVE) {{
      const mine = mineFor(g.id), sel = selectButton(g.id), now = performance.now();
      const ax = g.axes[2] || 0, ay = g.axes[3] || 0, dz = 0.2;
      if (Math.abs(ax) > dz || Math.abs(ay) > dz) {{                // the right stick moves the pointer
        const sp = 14 * Math.max(Math.abs(ax), Math.abs(ay));
        x = Math.min(innerWidth - 1, Math.max(0, x + ax * sp)); y = Math.min(innerHeight - 1, Math.max(0, y + ay * sp));
        shown = now; armed = true; mouse("pointermove", held.click ? 1 : 0);
      }}
      const on = i => !!(g.buttons[i] && (g.buttons[i].pressed || g.buttons[i].value > 0.5));
      // pressing anything for the game (D-pad, other buttons) puts the pointer away straight away
      for (const [b, i] of Object.entries(INDEX)) if (b !== sel && on(i) && !prev[i] && !mine.has(b)) {{ shown = -1e9; armed = false; }}
      const pointing = armed && now - shown < 3000;
      // RT / right-stick click always click; the select button clicks while the pointer shows
      const clickNow = on(7) || on(11) || (on(INDEX[sel]) && (pointing || held.click === "sel"));
      if (clickNow && !held.click) {{ held.click = on(INDEX[sel]) && pointing ? "sel" : "rt"; shown = now; armed = false; mouse("pointerdown", 1); p.focus(); }}
      else if (!clickNow && held.click) {{ held.click = null; shown = now; mouse("pointerup", 0); }}
      // the page's own buttons press their keys (when not clicking)
      for (const b of mine) {{
        const i = INDEX[b], down = on(i) && !(b === sel && held.click === "sel");
        if (down && !held[b]) {{ held[b] = true; for (const k of MAP[b] || []) key("keydown", k); }}
        else if (!down && held[b]) {{ held[b] = false; for (const k of MAP[b] || []) key("keyup", k); }}
      }}
      for (const i of Object.values(INDEX)) prev[i] = on(i);
    }}
    if (NATIVE) {{ x = nx; y = ny; shown = nshown; armed = true; }}
    const vis = performance.now() - shown < 3000;
    ptr.style.display = vis ? "block" : "none"; ptr.style.opacity = armed ? 1 : 0.45;
    if (vis) ptr.style.translate = x + "px " + y + "px";
    requestAnimationFrame(tick);
  }})();
}});
</script>"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    flash = None                                    # (swf, title, buttons, native) when serving a Flash game

    def log_message(self, *a): pass

    def end_headers(self):                                          # always the files on disk, never a stale copy
        self.send_header("Cache-Control", "no-store"); super().end_headers()

    def translate_path(self, path):
        if path.startswith("/__ruffle__/"):                         # Ruffle's files, from Insert Coin's own folder
            name = os.path.basename(urllib.parse.unquote(path.split("?")[0]))
            return os.path.join(RUFFLE, name)
        return super().translate_path(path)

    def do_GET(self):
        if self.flash and self.path.split("?")[0] == "/" + FLASH_PAGE:
            body = flash_page(*self.flash).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        super().do_GET()


QuietHandler.extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm",
                               ".swf": "application/x-shockwave-flash", ".js": "text/javascript"}


def serve_folder(folder, flash=None):
    """Serve one game folder on 127.0.0.1 at a free port, in a background thread. Only this computer can reach it.
    flash=(swf, title, buttons) also serves a page that plays that .swf with Ruffle."""
    handler = type("Handler", (QuietHandler,), {"flash": flash})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(handler, directory=folder))
    srv.daemon_threads = True
    srv.handle_error = lambda *a: None                              # the browser hanging up mid-file is normal
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def find_browser():
    for b in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave-browser", "firefox"):
        p = shutil.which(b)
        if p: return p
    return None


def browser_command(exe, url, windowed=False):
    """Full-screen (kiosk) browser in its own profile, so the user's normal browser and its windows are untouched;
    sound may start without a click first."""
    prof = f"{APPDIR}/browser/" + ("firefox" if "firefox" in os.path.basename(exe) else "chrome")
    os.makedirs(prof, exist_ok=True)
    if "firefox" in os.path.basename(exe):
        with open(f"{prof}/user.js", "w") as f:
            for k, v in (("media.autoplay.default", "0"), ("browser.shell.checkDefaultBrowser", "false"),
                         ("browser.sessionstore.resume_from_crash", "false"), ("datareporting.policy.dataSubmissionEnabled", "false"),
                         ("browser.aboutwelcome.enabled", "false"), ("trailhead.firstrun.didSeeAboutWelcome", "true")):
                f.write(f'user_pref("{k}", {v});\n')
        return [exe, "--no-remote", "--profile", prof] + ([] if windowed else ["--kiosk"]) + [url]
    try:                                                            # no "restore pages?" bubble after being closed
        pf = f"{prof}/Default/Preferences"
        with open(pf) as f: d = json.load(f)
        d.setdefault("profile", {}).update(exit_type="Normal", exited_cleanly=True)
        with open(pf, "w") as f: json.dump(d, f)
    except Exception: pass
    return [exe, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check", "--disable-session-crashed-bubble",
            "--autoplay-policy=no-user-gesture-required", "--disable-features=Translate,MediaRouter", "--password-store=basic",
            "--noerrdialogs"] + (["--window-size=1280,760", f"--app={url}"] if windowed else ["--kiosk", "--start-fullscreen", url])


def stale_browsers():
    """Main processes of browsers running with Insert Coin's own profile. Chrome rewrites its command line into one
    space-separated string, so match on the text rather than on separate arguments."""
    prof = f"{APPDIR}/browser/"; pids = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == os.getpid(): continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f: cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError: continue
        if (f"--user-data-dir={prof}" in cmd or f"--profile {prof}" in cmd) and "--type=" not in cmd:
            pids.append(int(d))                                      # not its helper processes (--type=renderer, ...)
    return pids


def close_stale_browsers():
    """Close any browser still running with Insert Coin's own profile (left open, or from a copy of Insert Coin that
    was stopped): a new game would otherwise be handed to it, and the new browser would exit straight away."""
    pids = stale_browsers()
    for pid in pids:
        log.info("Closing a browser left open (pid %d)", pid)
        try: os.kill(pid, signal.SIGTERM)
        except OSError: pass
    t = time.time()
    while pids and time.time() - t < 3:
        pids = [p for p in pids if os.path.exists(f"/proc/{p}")]; time.sleep(0.1)
    for pid in pids:
        try: os.kill(pid, signal.SIGKILL)
        except OSError: pass


class PageInput:
    """Genuine keyboard and mouse input for one browser page, through Chrome's DevTools protocol over a private pipe
    (--remote-debugging-pipe: no network port, nothing else can connect). Some Flash screens only answer real, held
    key presses, which neither a page script nor Ruffle's own gamepad support produce; these do, and they go to the
    game's page only, never to another window."""
    KEYS = {"Up": ("ArrowUp", "ArrowUp", 38), "Down": ("ArrowDown", "ArrowDown", 40), "Left": ("ArrowLeft", "ArrowLeft", 37),
            "Right": ("ArrowRight", "ArrowRight", 39), "Space": (" ", "Space", 32), "Enter": ("Enter", "Enter", 13),
            "Shift": ("Shift", "ShiftLeft", 16), "Ctrl": ("Control", "ControlLeft", 17), "Alt": ("Alt", "AltLeft", 18),
            "Tab": ("Tab", "Tab", 9), "Escape": ("Escape", "Escape", 27), "Backspace": ("Backspace", "Backspace", 8),
            **{c: (c.lower(), "Key" + c, ord(c)) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
            **{c: (c, "Digit" + c, ord(c)) for c in "0123456789"}}
    SYMS = KEYS                                                     # the key names FlashPad accepts

    def __init__(self):
        self.to_chrome = os.pipe(); self.from_chrome = os.pipe()     # Chrome reads fd 3, writes fd 4
        self.out = os.fdopen(self.to_chrome[1], "wb", buffering=0)
        self.n = 0; self.session = None; self.lock = threading.Lock(); self.replies = {}; self.cv = threading.Condition()
        self.keys = set(); self.button = False; self.x = self.y = 0.0; self.w, self.h = 1280, 720; self.scale = 1.0
        self.started = False

    def child_fds(self):
        """Run in the browser process before it starts: put the pipe ends where Chrome expects them."""
        r = fcntl.fcntl(self.to_chrome[0], fcntl.F_DUPFD, 10); w = fcntl.fcntl(self.from_chrome[1], fcntl.F_DUPFD, 10)
        os.dup2(r, 3); os.dup2(w, 4)                                 # (via high numbers: either end may be 3 or 4)

    def connected(self):
        """After the browser started: our copies of its ends are closed, replies are read in the background."""
        os.close(self.to_chrome[0]); os.close(self.from_chrome[1])
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b""
        with os.fdopen(self.from_chrome[0], "rb", buffering=0) as f:
            while True:
                chunk = f.read(65536)
                if not chunk: break
                buf += chunk
                while b"\0" in buf:
                    msg, buf = buf.split(b"\0", 1)
                    try: m = json.loads(msg)
                    except ValueError: continue
                    if "id" in m:
                        with self.cv:
                            self.replies[m["id"]] = m; self.cv.notify_all()
                            if len(self.replies) > 500:              # replies nobody waited for
                                for k in sorted(self.replies)[:-50]: self.replies.pop(k, None)

    def done(self, i):
        with self.cv:
            if i in self.replies: self.replies.pop(i); return True
        return False

    def send(self, method, wait=False, timeout=3.0, **params):
        """Send a command; with wait, return its result. Returns the message id otherwise."""
        with self.lock:
            self.n += 1; i = self.n
            msg = {"id": i, "method": method, "params": params}
            if self.session and not method.startswith("Target."): msg["sessionId"] = self.session
            try: self.out.write(json.dumps(msg).encode() + b"\0")
            except OSError: return None
        if not wait: return i
        end = time.time() + timeout
        with self.cv:
            while i not in self.replies and time.time() < end: self.cv.wait(end - time.time())
            return self.replies.pop(i, {}).get("result")

    def attach(self):
        """Find the game's page, attach to it, and wait for Ruffle to have loaded the game. True once ready (called
        again until then)."""
        if not self.session:
            r = self.send("Target.getTargets", wait=True) or {}
            page = next((t for t in r.get("targetInfos", []) if t.get("type") == "page"), None)
            if not page: return False
            r = self.send("Target.attachToTarget", wait=True, targetId=page["targetId"], flatten=True) or {}
            self.session = r.get("sessionId")
            if not self.session: return False
        r = self.send("Runtime.evaluate", wait=True, returnByValue=True,
                      expression="(() => { const p = document.querySelector('ruffle-player'); return !!p && p.readyState === 2; })()") or {}
        if not (r.get("result") or {}).get("value") or not self.measure(): return False
        # Ruffle takes the first click on a loaded game for itself (it doesn't reach the game), so make that click
        # here, on the edge of the page, where the game is letterboxed and nothing can be hit.
        for t in ("mousePressed", "mouseReleased"):
            self.send("Input.dispatchMouseEvent", type=t, x=1, y=self.h // 2, button="left", buttons=1 if t == "mousePressed" else 0, clickCount=1)
        return True

    def measure(self):
        r = self.send("Runtime.evaluate", wait=True, expression="[innerWidth, innerHeight]", returnByValue=True) or {}
        v = (r.get("result") or {}).get("value")
        if not v: return False
        self.w, self.h = v; self.scale = max(0.5, self.h / 1080)
        if not self.started: self.x, self.y = self.w / 2, self.h / 2
        return True

    def key(self, name, down):
        k, code, vk = self.KEYS[name]
        p = dict(key=k, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        if down:
            self.send("Input.dispatchKeyEvent", type="rawKeyDown", **p)
            if len(k) == 1: self.send("Input.dispatchKeyEvent", type="char", text=k, **p)
            self.keys.add(name)
        else:
            self.send("Input.dispatchKeyEvent", type="keyUp", **p); self.keys.discard(name)

    def centre(self): self.started = True

    def move(self, dx, dy):
        """Moves are coalesced: a new position goes out only once Chrome has handled the last one (it handles input
        in turn, behind the game; 60 moves a second would queue up and delay clicks and keys)."""
        self.x = min(self.w - 1, max(0, self.x + dx)); self.y = min(self.h - 1, max(0, self.y + dy))
        self.moved = True; self.flush()

    def flush(self):
        if not getattr(self, "moved", False): return
        if getattr(self, "move_id", None) and not self.done(self.move_id): return
        self.moved = False
        self.move_id = self.send("Input.dispatchMouseEvent", type="mouseMoved", x=self.x, y=self.y,
                                 button="left" if self.button else "none", buttons=1 if self.button else 0)

    def click(self, down):
        if getattr(self, "moved", False):                           # the pointer's latest position first
            self.moved = False; self.send("Input.dispatchMouseEvent", type="mouseMoved", x=self.x, y=self.y, button="none", buttons=0)
        self.send("Input.dispatchMouseEvent", type="mousePressed" if down else "mouseReleased", x=self.x, y=self.y,
                  button="left", buttons=1 if down else 0, clickCount=1)
        self.button = down

    def release_all(self):
        for k in list(self.keys): self.key(k, False)
        if self.button: self.click(False)

    def close(self):
        try: self.release_all(); self.out.close()
        except Exception: pass


class FlashPad:
    """The pad as a keyboard and mouse for a Flash game (sent through PageInput). Buttons are named by position, as in
    browser_games.json ("south" is A on an Xbox pad); the left stick also works as the D-pad. The right stick moves
    the mouse pointer; once it has moved, the pad's select button (A / Cross / Nintendo's A, as in Insert Coin's
    menus) clicks. After a click, or as soon as any other button is pressed, it is the game's button again."""
    C = pygame
    POS = {"south": C.CONTROLLER_BUTTON_A, "east": C.CONTROLLER_BUTTON_B, "west": C.CONTROLLER_BUTTON_X,
           "north": C.CONTROLLER_BUTTON_Y, "left-trigger": C.CONTROLLER_BUTTON_LEFTSHOULDER,
           "right-trigger": C.CONTROLLER_BUTTON_RIGHTSHOULDER, "select": C.CONTROLLER_BUTTON_BACK,
           "start": C.CONTROLLER_BUTTON_START, "dpad-up": C.CONTROLLER_BUTTON_DPAD_UP,
           "dpad-down": C.CONTROLLER_BUTTON_DPAD_DOWN, "dpad-left": C.CONTROLLER_BUTTON_DPAD_LEFT,
           "dpad-right": C.CONTROLLER_BUTTON_DPAD_RIGHT}
    # SDL names a Nintendo pad's buttons by their labels: the bottom one is "B"
    POS_NINTENDO = {**POS, "south": C.CONTROLLER_BUTTON_B, "east": C.CONTROLLER_BUTTON_A,
                    "west": C.CONTROLLER_BUTTON_Y, "north": C.CONTROLLER_BUTTON_X}
    STICK = {"dpad-left": (C.CONTROLLER_AXIS_LEFTX, -1), "dpad-right": (C.CONTROLLER_AXIS_LEFTX, 1),
             "dpad-up": (C.CONTROLLER_AXIS_LEFTY, -1), "dpad-down": (C.CONTROLLER_AXIS_LEFTY, 1)}

    def __init__(self, xin, buttons):
        self.xin = xin
        self.map = {b: [k for k in str(v).split("+") if k in PageInput.SYMS] for b, v in {**FLASH_BUTTONS, **(buttons or {})}.items()
                    if b in self.POS}
        self.held = {}; self.armed = False; self.clicking = False; self.started = False

    def tick(self, pads):
        """pads: [(controller, style)]. Reads them and sends what changed."""
        if not pads: return
        nin = pads[0][1] in ("nintendo", "snes")
        sel = "east" if nin else "south"
        down = {b: False for b in self.map}; rx = ry = 0.0
        for c, style in pads:
            pos = self.POS_NINTENDO if style == "nintendo" else self.POS
            try:
                for b in self.map: down[b] = down[b] or bool(c.get_button(pos[b]))
                for b, (ax, sign) in self.STICK.items():
                    if c.get_axis(ax) * sign > 16000: down[b] = True
                vx, vy = c.get_axis(self.C.CONTROLLER_AXIS_RIGHTX) / 32767, c.get_axis(self.C.CONTROLLER_AXIS_RIGHTY) / 32767
                if abs(vx) + abs(vy) > abs(rx) + abs(ry): rx, ry = vx, vy
            except Exception: pass
        mag = max(abs(rx), abs(ry))
        if mag > 0.2:                                               # the right stick moves the mouse pointer
            if not self.started: self.xin.centre(); self.started = True
            sp = self.xin.scale * (2 + 16 * mag * mag) / max(mag, 1e-6)
            self.xin.move(rx * sp, ry * sp); self.armed = True
        for b in self.map:                                          # anything else is for the game: pointer done
            if b != sel and down[b] and not self.held.get(b): self.armed = False
        if down[sel] and not self.held.get(sel) and self.armed:     # a click
            self.clicking = True; self.armed = False; self.xin.click(True)
        elif not down[sel] and self.clicking:
            self.clicking = False; self.xin.click(False)
        for b, keys in self.map.items():
            want = down[b] and not (b == sel and self.clicking)
            if want != bool(self.held.get(b + ":k")):
                for k in keys: self.xin.key(k, want)
                self.held[b + ":k"] = want
            self.held[b] = down[b]
        self.xin.flush()

    def release(self):
        self.held = {}; self.clicking = False; self.xin.release_all()


def sdl_controller_update():
    """SDL_GameControllerUpdate from the SDL library pygame uses: refreshes the controllers' button states while
    Insert Coin has no window (pygame's event functions need one). None if it can't be found."""
    try:
        lib = next((ln.split()[-1] for ln in open("/proc/self/maps") if re.search(r"/libSDL2-2\.0\.so|/libSDL2-2-[0-9a-f]+\.0\.so", ln)), None)
        return ctypes.CDLL(lib or "libSDL2-2.0.so.0").SDL_GameControllerUpdate
    except Exception:
        return None


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
        if isinstance(g, WebGame): return g.info                     # year / publisher from browser_games.json
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

# cores the built-in player runs (all draw in software; each was test-booted). N64 needs the graphics card: RetroArch.
ENGINE_CORES = {"mesen_libretro.so", "fbneo_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so",
                "fbalpha2012_cps3_libretro.so", "mesen-s_libretro.so", "vbam_libretro.so", "blastem_libretro.so",
                "picodrive_libretro.so", "mednafen_supergrafx_libretro.so", "mednafen_ngp_libretro.so",
                "pcsx_rearmed_libretro.so", "stella_libretro.so"}
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


def n_games(n):
    return f"{n:,} game" + ("" if n == 1 else "s")


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
        if not isinstance(g, WebGame) and subprocess.run(["pgrep", "-x", "retroarch"], capture_output=True).returncode == 0:
            self.err("Close RetroArch first to change favorites"); return
        added = self.lib.toggle_favorite(g)
        self.sfx.play("fav_on" if added else "fav_off")
        self.say(("Added to Favorites: " if added else "Removed from Favorites: ") + g.title)
        sid = self.sys["id"]; self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0)
        if self.sys["id"] != sid: self.screen_mode = "systems"

    def launch(self, g):
        if isinstance(g, WebGame): return self.launch_browser(g)
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
                    rc = subprocess.run([sys.executable, f"{HERE}/engine.py", g.core, g.path, "--title", g.title] + (["--windowed"] if self.windowed else []),
                                        stdout=out, stderr=subprocess.STDOUT).returncode
                if rc and time.time() - t0 < 10:                     # didn't start: let RetroArch try it instead
                    log.warning("Built-in player could not start it (exit %s), trying RetroArch", rc)
                    try:
                        errs = [ln.rstrip() for ln in open(ralog, errors="replace") if "[ERROR]" in ln]
                        for ln in errs[-5:]: log.warning("  engine: %s", ln)
                    except Exception: pass
                    engine, who, kind = False, "RetroArch", "retroarch"
                    ralog = f"{LOGDIR}/retroarch-last.log"; t0 = time.time()
                    if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/retroarch-previous.log")
            if not engine:
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
        if rc is not None and took >= 3:
            try: self.lib.note_launch(g, t0)                        # so browser games sort into Recently Played
            except Exception as e: log.warning("Could not note the launch: %s", e)
        self.back_from_game()
        quit_by_user = False
        if engine:
            try: quit_by_user = "Quit chosen from the game menu" in open(ralog, errors="replace").read()
            except OSError: pass
        if took < 3 and not quit_by_user: self.err("The game closed straight away - it may need a different core")

    def back_from_game(self):
        """The game has ended: screen, controllers (they may have changed), sound, and the lists back."""
        pygame.display.init(); self.open_display(); self.rescan_pads(); self.sfx.open()
        self.img.cache.clear(); self.prev_bg = None
        pygame.event.clear(); self.hold.clear()
        sid, gid = self.sys["id"], self.cur_gi()
        self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.gi[sid] = gid

    def launch_browser(self, g):
        """A browser game: serve its folder on 127.0.0.1 (a random port, nothing reachable from outside), open the
        start page full-screen in its own browser profile, and watch the controllers for Select + Start, which
        closes the browser and comes back here. The page itself reads the pad through the Gamepad API."""
        if not os.path.isfile(g.path): self.err("Game file not found"); return
        br = find_browser()
        if not br: self.err("Browser games need Google Chrome, Chromium or Firefox"); return
        if g.flash and not os.path.isfile(f"{RUFFLE}/ruffle.js"):
            self.err("Flash games need Ruffle - see the README (Browser and Flash games)"); return
        self.sfx.play("coin"); self.draw(); self.splash(g, web=True)
        self.sfx.finish(); self.sfx.close()
        os.makedirs(LOGDIR, exist_ok=True)
        ralog = f"{LOGDIR}/browser-last.log"
        if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/browser-previous.log")
        server = rc = None; quit_by_user = False; t0 = time.time()
        try:
            flashpad = None                                         # Chrome-family browsers: genuine input via DevTools
            if g.flash and "firefox" not in os.path.basename(br): flashpad = FlashPad(PageInput(), g.buttons)
            server = serve_folder(g.folder, (g.start, g.title, g.buttons, flashpad is not None) if g.flash else None)
            url = f"http://127.0.0.1:{server.server_address[1]}/" + (FLASH_PAGE if g.flash else urllib.parse.quote(g.start))
            close_stale_browsers()
            cmd = browser_command(br, url, self.windowed) + (["--remote-debugging-pipe"] if flashpad else [])
            log.info("Launch (browser, %s): %s | %s", os.path.basename(br), g.label, g.path)
            pygame.display.quit()
            with open(ralog, "w") as out:
                if flashpad:                                        # the pipe goes to the browser as fds 3 and 4
                    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                                            close_fds=False, preexec_fn=flashpad.xin.child_fds)
                    flashpad.xin.connected()
                else:
                    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
                quit_by_user = self.watch_quit_combo(proc, flashpad)
                if quit_by_user:
                    log.info("Select + Start: closing the browser")
                    for sig, wait in ((signal.SIGTERM, 4), (signal.SIGKILL, 2)):
                        try: os.killpg(proc.pid, sig)
                        except ProcessLookupError: break
                        try: proc.wait(wait); break
                        except subprocess.TimeoutExpired: pass
                rc = proc.wait()
        except Exception as e:
            self.err(f"Could not start the browser: {e}"); log.exception("Browser game failed")
        finally:
            if server: server.shutdown(); server.server_close()
            if flashpad: flashpad.xin.close()
        took = time.time() - t0
        log.info("Browser game ended after %d min %02d s (%s, exit %s)", took // 60, took % 60,
                 "Select + Start" if quit_by_user else "browser closed", rc)
        if rc is not None and took >= 3:
            try: self.lib.note_launch(g, t0)
            except Exception as e: log.warning("Could not update Recently Played: %s", e)
        if not pygame.display.get_init(): self.back_from_game()
        else: self.sfx.open()
        if rc is not None and took < 3 and not quit_by_user: self.err("The browser closed straight away - see browser-last.log")

    def watch_quit_combo(self, proc, flash=None):
        """While the browser runs (Insert Coin has no window then, so no events): read the controllers directly,
        and return True when Select + Start (Back + Start, Share + Options...) is held on any of them.
        flash: a FlashPad that turns the pad into keys and a mouse, used only while the game's window is active."""
        update = sdl_controller_update()
        pads = [(c, self.pad_style.get(c.as_joystick().get_instance_id(), "xbox")) for c in self.pads.values()]
        n = sdlc.get_count(); last_check = time.time(); ready = False; ready_at = 0
        BACK, START = pygame.CONTROLLER_BUTTON_BACK, pygame.CONTROLLER_BUTTON_START
        try:
            while proc.poll() is None:
                time.sleep(0.016 if flash else 0.03)
                if not update: continue
                update()
                if time.time() - last_check > 2:                    # a pad plugged in while the game runs
                    last_check = time.time()
                    if sdlc.get_count() != n:
                        n = sdlc.get_count(); pads = []
                        for i in range(n):
                            try:
                                if sdlc.is_controller(i):
                                    c = sdlc.Controller(i); j = c.as_joystick()
                                    pads.append((c, controller_style(c.name, j.get_guid())))
                            except Exception: pass
                for c, _ in pads:
                    try:
                        if c.get_button(BACK) and c.get_button(START): return True
                    except Exception: pass
                if flash:
                    if time.time() - ready_at > (3 if ready else 0.5):  # find the page; then re-check its size
                        ready_at = time.time()
                        was = ready
                        try: ready = flash.xin.measure() if ready else flash.xin.attach()
                        except Exception: ready = False
                        if ready and not was: log.info("Flash: pad controls ready")
                    if ready: flash.tick(pads)
            return False
        finally:
            if flash: flash.release()

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
            text(tile, self.fonts(int(24 * sc)), f"{sy['maker']}  ·  {n_games(len(sy['games']))}", (28 * sc, h - 42 * sc), (215, 220, 230), maxw=w - 40)
            mask = pygame.Surface((w, h), pygame.SRCALPHA); rrect(mask, (255, 255, 255, 255), mask.get_rect(), 26)
            tile.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            if ad > 0.5: tile.set_alpha(int(255 * max(0.35, 1 - 0.3 * ad)))
            self.screen.blit(tile, rect)
            if ad < 0.5: rrect(self.screen, (255, 255, 255), rect.inflate(10, 10), 30, 5)
        dots_w = n * 22; x0 = W / 2 - dots_w / 2
        for i in range(n):
            pygame.draw.circle(self.screen, (255, 255, 255) if i == self.si else (110, 115, 130), (x0 + i * 22 + 11, 790), 6 if i == self.si else 4)
        text(self.screen, self.fonts(30), s["maker"] if s["special"] else n_games(len(s['games'])), (W / 2, 850), (210, 215, 228), anchor="midtop")
        if hints: self.draw_hints([("a", "Open"), ("b", "Power")])

    def draw_games(self, hints=True):
        s = self.sys; gs = self.games(); i = self.cur_gi(); g = gs[i] if gs else None
        self.draw_background(s["color"], g)
        self.draw_header(s["name"], f"{n_games(len(gs))}  ·  {i + 1:,} / {len(gs):,}")
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
            if not g.core and not isinstance(g, WebGame):
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

    def splash(self, g, engine=False, web=False):
        self.screen.fill((0, 0, 0))
        im = self.img.get(g.thumb("Named_Boxarts"), 420, 520)
        if im: self.screen.blit(im, im.get_rect(center=(W / 2, H / 2 - 60)))
        text(self.screen, self.fonts(44, True), g.title, (W / 2, H / 2 + 250), anchor="midtop", maxw=1500)
        combo = self.pad_quit.get(self.cur_pad, QUIT_COMBO[self.style]) if self.style != 'keyboard' else 'Esc'
        note = (f"{combo} returns to Insert Coin" if self.style != "keyboard" else "Alt + F4 returns to Insert Coin") if web \
            else f"{combo} opens the game menu"
        text(self.screen, self.fonts(26), f"Starting…   ({note})", (W / 2, H / 2 + 320), (180, 185, 200), anchor="midtop")
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
