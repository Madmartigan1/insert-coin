"""Browser and Flash games: playlists, the Flash page, the local server and the browser."""
import functools, http.server, json, os, shutil, signal, threading, time, urllib.parse
from paths import APPDIR, CONFDIR
from insertcoin.logs import log
from insertcoin.names import letter_of, sort_key
from insertcoin.games import Game


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
# Flash games only know the keyboard: pad button -> the key it presses (Ruffle's names; overridable per game with
# "buttons"; Ruffle presses one key per button, so of "X+Space" only X is used here)
FLASH_BUTTONS = {"dpad-up": "Up", "dpad-down": "Down", "dpad-left": "Left", "dpad-right": "Right",
                 "south": "Space", "east": "Enter", "west": "Z", "north": "X", "start": "Enter"}
PAD_INDEX = {"south": 0, "east": 1, "west": 2, "north": 3, "left-trigger": 4, "right-trigger": 5, "select": 8, "start": 9,
             "dpad-up": 12, "dpad-down": 13, "dpad-left": 14, "dpad-right": 15}      # the browser's standard layout
KEYCODES = {"Up": 38, "Down": 40, "Left": 37, "Right": 39, "Space": 32, "Enter": 13, "Shift": 16, "Ctrl": 17,
            "Alt": 18, "Tab": 9, "Escape": 27, "Backspace": 8, **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}}


def flash_page(swf, title, buttons=None, native=False):
    """A full-screen page that plays one .swf with Ruffle, the pad's buttons pressing the keys the game uses.

    Ruffle presses the key for every button itself (its gamepadButtonMapping). The page never sends keys: on the
    user's screen page-made keys stopped reaching games (2026-11-10), while Ruffle's own mapping kept working.
    Many Flash menus are mouse-only, so the right stick moves a pointer and, while it shows, the pad's select button
    (A on Xbox pads, Cross on PlayStation, the right-hand A on Nintendo-style pads, as in Insert Coin's menus) also
    clicks. Any other button hides the pointer at once, so it never gets in the way.
    native=True: Insert Coin sends real keys and mouse input itself (FlashPad), so the page leaves the pad alone."""
    keys = lambda v: [k for k in str(v).split("+") if k in KEYCODES]
    mapping = {b: keys(v) for b, v in {**FLASH_BUTTONS, **(buttons or {})}.items() if b in PAD_INDEX}
    ruffle_map = {name: KEYCODES[ks[0]] for name, ks in mapping.items() if ks}   # Ruffle: one key per button
    cfg = {"autoplay": "on", "unmuteOverlay": "hidden", "splashScreen": False, "letterbox": "on", "contextMenu": "off",
           "showSwfDownload": False}
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;")
    return f"""<!doctype html><meta charset="utf-8"><title>{esc(title)}</title>
<style>html,body{{margin:0;height:100%;background:#000;overflow:hidden}}ruffle-player{{width:100vw;height:100vh;display:block}}
#ptr{{position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:9;display:none;
border-left:11px solid transparent;border-right:11px solid transparent;border-bottom:26px solid #fff;
margin-left:-11px;filter:drop-shadow(0 0 2px #000) drop-shadow(0 0 1px #000);transform-origin:50% 0;rotate:-30deg}}</style>
<script>
const INDEX = {json.dumps(PAD_INDEX)}, NATIVE = {json.dumps(bool(native))};
// The select button depends on the pad (as in Insert Coin's menus); the browser's layout is by position.
const selectButton = id => /057e|nintendo|0583.{{0,12}}2060|snes/i.test(id) ? "east" : "south";
// Ruffle presses the key for every button (none when Insert Coin sends real input itself).
window.RufflePlayer = {{config: {{...{json.dumps(cfg)}, gamepadButtonMapping: NATIVE ? {{}} : {json.dumps(ruffle_map)}}}}};
</script>
<script src="/__ruffle__/ruffle.js"></script>
<div id="ptr"></div>
<script>
window.addEventListener("load", () => {{
  const pads = () => [...(navigator.getGamepads ? navigator.getGamepads() : [])].filter(Boolean);
  const ptr = document.getElementById("ptr");
  let p = null;
  p = window.RufflePlayer.newest().createPlayer(); document.body.appendChild(p);
  p.load({{url: {json.dumps(urllib.parse.quote(swf))}}}).then(() => p.focus());
  p.focus(); window.addEventListener("click", () => p.focus());
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
      const sel = selectButton(g.id), now = performance.now();
      const ax = g.axes[2] || 0, ay = g.axes[3] || 0, dz = 0.2;
      if (Math.abs(ax) > dz || Math.abs(ay) > dz) {{                // the right stick moves the pointer
        const sp = 14 * Math.max(Math.abs(ax), Math.abs(ay));
        x = Math.min(innerWidth - 1, Math.max(0, x + ax * sp)); y = Math.min(innerHeight - 1, Math.max(0, y + ay * sp));
        shown = now; armed = true; mouse("pointermove", held.click ? 1 : 0);
      }}
      const on = i => !!(g.buttons[i] && (g.buttons[i].pressed || g.buttons[i].value > 0.5));
      // pressing anything for the game (D-pad, other buttons) puts the pointer away straight away
      for (const [b, i] of Object.entries(INDEX)) if (b !== sel && on(i) && !prev[i]) {{ shown = -1e9; armed = false; }}
      const pointing = armed && now - shown < 3000;
      // RT / right-stick click always click; the select button clicks while the pointer shows
      const clickNow = on(7) || on(11) || (on(INDEX[sel]) && (pointing || held.click === "sel"));
      if (clickNow && !held.click) {{ held.click = on(INDEX[sel]) && pointing ? "sel" : "rt"; shown = now; armed = false; mouse("pointerdown", 1); p.focus(); }}
      else if (!clickNow && held.click) {{ held.click = null; shown = now; mouse("pointerup", 0); }}
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
