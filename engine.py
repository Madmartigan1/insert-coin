#!/usr/bin/env python3
"""Insert Coin's own game player (experimental): runs a libretro core directly, without RetroArch.

libretro is the small, MIT-licensed interface that emulator cores (Mesen, FBNeo, MAME 2003-Plus, ...)
speak. This file is the "frontend" side of it: it loads a core, gives it the game, shows its picture,
plays its sound, feeds it the controllers and keeps its save files.

    engine.py CORE.so ROM [--title NAME] [--windowed] [--frames N --shot FILE.png]

ROM may be a plain file, a zip, or RetroArch-style "archive.zip#file.nes".
In a game: Select + Start (or Esc) pauses and opens a small menu: Resume / Controls / Quit game.
Controls changes which button does what, for this game only (saved per game). The keyboard is
also passed to the core, so e.g. Tab opens MAME's own menu in arcade games.

Testing: --press NAME@FIRST-LAST holds a button during those frames (a RetroPad name such as
"start" or "b", or a keyboard key such as "tab"); repeat it for more presses.

Supported so far: cores that draw in software (NES, SNES, Mega Drive, Game Boy, arcade, Neo Geo...).
Cores that need the graphics card (N64, some PS1 modes) are a later step.
"""
import ctypes as C, os, re, sys, time, json, shutil, struct, tempfile, threading, zipfile

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
from pygame._sdl2 import controller as sdlc
from pygame._sdl2 import audio as sdla

HOME = os.path.expanduser("~")
RA = f"{HOME}/.config/retroarch"
APPDIR = f"{HOME}/.local/share/insert-coin"
SAVES = os.environ.get("INSERT_COIN_SAVES") or f"{APPDIR}/saves"      # override for tests
# BIOS files: Insert Coin's own folder once it has one, else the one RetroArch uses (Neo Geo BIOS lives there)
SYSTEM = f"{APPDIR}/system" if os.path.isdir(f"{APPDIR}/system") else f"{RA}/system"
CONFDIR = os.environ.get("INSERT_COIN_CONFIG") or f"{HOME}/.config/insert-coin"
W, H = 1920, 1080

def split_archive(path):
    """RetroArch's 'archive.zip#file.nes' -> ('archive.zip', 'file.nes'). Only a '#' straight after .zip / .7z
    counts: folder names may contain '#' themselves (e.g. '# Translations #')."""
    m = re.search(r"(?i)\.(zip|7z)#", path)
    return (path[:m.end() - 1], path[m.end():]) if m else (path, "")

def archive_names(path):
    """The files inside a .zip or .7z."""
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z: return z.namelist()
    out = sevenzip("l", "-slt", "-ba", path).decode(errors="replace")
    return [ln[7:] for ln in out.splitlines() if ln.startswith("Path = ")]

def archive_read(path, inner):
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z: return z.read(inner)
    return sevenzip("e", "-so", path, inner)

def sevenzip(*args):
    """.7z archives are opened with the 7-Zip program (package p7zip-full / 7zip)."""
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if not exe: raise SystemExit("[ERROR] This game is in a .7z archive: install 7-Zip (package p7zip-full or 7zip)")
    import subprocess
    r = subprocess.run([exe, *args], capture_output=True)
    if r.returncode: raise SystemExit(f"[ERROR] 7-Zip could not read {os.path.basename(args[-2] if args[0] == 'e' else args[-1])}")
    return r.stdout

def log(level, msg): print(f"[{level}] {msg}", flush=True)

# ---------------------------------------------------------------- libretro definitions
class SystemInfo(C.Structure):
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p), ("valid_extensions", C.c_char_p),
                ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]

class Geometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]

class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]

class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]

class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]

class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]

class InputDescriptor(C.Structure):
    _fields_ = [("port", C.c_uint), ("device", C.c_uint), ("index", C.c_uint), ("id", C.c_uint),
                ("description", C.c_char_p)]

class Message(C.Structure):
    _fields_ = [("msg", C.c_char_p), ("frames", C.c_uint)]

ENV_T = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_T = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
SAMPLE_T = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
BATCH_T = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_T = C.CFUNCTYPE(None)
STATE_T = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
LOG_T = C.CFUNCTYPE(None, C.c_int, C.c_char_p)          # really printf-style; only the format string is read

DEVICE_JOYPAD, DEVICE_KEYBOARD, DEVICE_ANALOG = 1, 3, 5
ID_MASK = 256                                            # "all buttons as a bitmask" (GET_INPUT_BITMASKS)
MEMORY_SAVE_RAM = 0
# RetroPad ids: B Y SELECT START UP DOWN LEFT RIGHT A X L R L2 R2 L3 R3
B_, Y_, SELECT, START, UP, DOWN, LEFT, RIGHT, A_, X_, L_, R_, L2, R2, L3, R3 = range(16)
RETROPAD_NAMES = {"b": B_, "y": Y_, "select": SELECT, "start": START, "up": UP, "down": DOWN, "left": LEFT,
                  "right": RIGHT, "a": A_, "x": X_, "l": L_, "r": R_, "l2": L2, "r2": R2, "l3": L3, "r3": R3}
# the buttons a game can have, in the order the Controls screen lists them (the d-pad isn't remappable)
REMAPPABLE = [B_, A_, Y_, X_, L_, R_, L2, R2, L3, R3, SELECT, START]
GENERIC_NAMES = {B_: "B", A_: "A", Y_: "Y", X_: "X", L_: "L", R_: "R", L2: "L2", R2: "R2", L3: "L3", R3: "R3",
                 SELECT: "Select", START: "Start"}
# what each RetroPad button is called on the controller in your hand (they sit by position: B bottom, A right,
# Y left, X top)
PAD_LABELS = {
    "xbox": {B_: "A", A_: "B", Y_: "X", X_: "Y", L_: "LB", R_: "RB", L2: "LT", R2: "RT", L3: "LS", R3: "RS",
             SELECT: "Back", START: "Start"},
    "playstation": {B_: "\u2715", A_: "\u25cb", Y_: "\u25a1", X_: "\u25b3", L_: "L1", R_: "R1", L2: "L2", R2: "R2",
                    L3: "L3", R3: "R3", SELECT: "Select", START: "Start"},
    "nintendo": {B_: "B", A_: "A", Y_: "Y", X_: "X", L_: "L", R_: "R", L2: "ZL", R2: "ZR", L3: "LS", R3: "RS",
                 SELECT: "\u2212", START: "+"},
    "keyboard": {B_: "Z", A_: "X", Y_: "A", X_: "S", L_: "Q", R_: "W", L2: "-", R2: "-", L3: "-", R3: "-",
                 SELECT: "R-Shift", START: "Enter"},
}
PAD_LABELS["snes"] = {**PAD_LABELS["nintendo"], SELECT: "Select", START: "Start"}
PAD_LABELS["generic"] = PAD_LABELS["xbox"]


def retro_keymap():
    """libretro key codes (SDL 1.2 numbering) -> pygame keys, for passing the keyboard to the core."""
    k = {c: c for c in list(range(32, 127)) + [8, 9, 13, 127]}   # printable keys, Backspace, Tab, Return, Delete
    k.pop(27, None)                                               # Esc belongs to Insert Coin (the pause menu)
    for i in range(10): k[256 + i] = getattr(pygame, f"K_KP{i}", None) or getattr(pygame, f"K_KP_{i}")
    k.update({266: pygame.K_KP_PERIOD, 267: pygame.K_KP_DIVIDE, 268: pygame.K_KP_MULTIPLY, 269: pygame.K_KP_MINUS,
              270: pygame.K_KP_PLUS, 271: pygame.K_KP_ENTER, 273: pygame.K_UP, 274: pygame.K_DOWN, 275: pygame.K_RIGHT,
              276: pygame.K_LEFT, 277: pygame.K_INSERT, 278: pygame.K_HOME, 279: pygame.K_END, 280: pygame.K_PAGEUP,
              281: pygame.K_PAGEDOWN, 303: pygame.K_RSHIFT, 304: pygame.K_LSHIFT, 305: pygame.K_RCTRL,
              306: pygame.K_LCTRL, 307: pygame.K_RALT, 308: pygame.K_LALT})
    for i in range(1, 16): k[281 + i] = getattr(pygame, f"K_F{i}")
    return k

# libretro pixel formats -> (bytes per pixel, surface depth, colour masks)
PIXFMT = {0: (2, 16, (0x7C00, 0x03E0, 0x001F, 0)),      # 0RGB1555 (the default)
          1: (4, 32, (0xFF0000, 0xFF00, 0xFF, 0)),       # XRGB8888
          2: (2, 16, (0xF800, 0x07E0, 0x001F, 0))}       # RGB565


# ---------------------------------------------------------------- sound
class AudioOut:
    """A small buffer between the core (which produces sound each frame) and the sound card. The core is
    run just fast enough to keep it filled, which also keeps the game at its own correct speed."""
    def __init__(self, rate):
        self.buf = bytearray(); self.lock = threading.Lock(); self.rate = rate; self.produced = 0
        self.target = int(rate * 0.05) * 4                    # aim for ~50 ms of sound queued
        self.limit = self.target * 4
        self.dev = sdla.AudioDevice(None, False, int(round(rate)), sdla.AUDIO_S16, 2, 512, 0, self._feed)
        self.dev.pause(0)

    def _feed(self, dev, view):
        try:                                                  # runs on SDL's audio thread: never let it raise
            mv = memoryview(view); n = mv.nbytes
            with self.lock:
                take = min(n, len(self.buf)); mv[:take] = self.buf[:take]; del self.buf[:take]
            if take < n: mv[take:] = bytes(n - take)
        except Exception:
            pass

    def push(self, data):
        with self.lock:
            self.buf += data; self.produced += len(data)
            if len(self.buf) > self.limit: del self.buf[:len(self.buf) - self.limit]

    def queued(self):
        return len(self.buf)

    def close(self):
        try: self.dev.pause(1); self.dev.close()
        except Exception: pass


# ---------------------------------------------------------------- the player
class Player:
    def __init__(self, core_path, rom, windowed=False, frames=None, shot=None, press=None, title=None):
        self.core_path, self.rom, self.frames_left, self.shot = core_path, rom, frames, shot
        self.lib = C.CDLL(core_path)
        self.keep = []                                        # ctypes objects the core holds pointers to
        self.options, self.opt_buf = {}, {}
        self.pixfmt = 0; self.rotation = 0; self.frame = None; self.surf = None
        self.running = True; self.audio = None; self.tmpdir = None
        self.paused = False; self.menu_sel = 0; self.combo_down = False
        self.mode = "pause"                                   # pause menu: "pause", "controls" or "wait" (for a button)
        self.descs = {}; self.remap = {}; self.ctl_sel = 0; self.wait_until = 0; self.style = "keyboard"
        self.fno = 0; self.press = press or []; self.bits = [0]; self.sticks = []
        self.keymap = None; self.title = title; self.keys = (); self.held_keys = set()
        fp = pygame.font.match_font("ubuntu,notosans,dejavusans", bold=True)
        self.font = lambda n, _c={}: _c.setdefault(n, pygame.font.Font(fp, n))
        self.av = AVInfo()                                    # some cores report their size while loading

        flags = 0 if shot else pygame.SCALED | (0 if windowed else pygame.FULLSCREEN)
        self.screen = pygame.display.set_mode((W, H), flags, vsync=0 if shot else 1)
        pygame.display.set_caption("Insert Coin"); pygame.mouse.set_visible(False)
        self.pads = []; self.open_pads()
        if self.pads: self.style = self.pads[0][1]

        self.info = SystemInfo(); self.lib.retro_get_system_info(C.byref(self.info))
        self.name = self.info.library_name.decode(errors="replace")
        log("INFO", f"Core: {self.name} {self.info.library_version.decode(errors='replace')}")
        self.load_ra_options()
        self.cbs = [ENV_T(self.env), VIDEO_T(self.video), SAMPLE_T(self.sample), BATCH_T(self.batch),
                    POLL_T(self.poll), STATE_T(self.state)]
        self.log_cb = LOG_T(self.core_log)
        L = self.lib
        L.retro_load_game.restype = C.c_bool
        L.retro_get_memory_data.restype = C.c_void_p; L.retro_get_memory_size.restype = C.c_size_t
        # same order as RetroArch: environment first, then init, then the other callbacks (some cores need it)
        L.retro_set_environment(self.cbs[0])
        L.retro_init()
        L.retro_set_video_refresh(self.cbs[1])
        L.retro_set_audio_sample(self.cbs[2]); L.retro_set_audio_sample_batch(self.cbs[3])
        L.retro_set_input_poll(self.cbs[4]); L.retro_set_input_state(self.cbs[5])
        self.load_game()
        self.av = AVInfo(); L.retro_get_system_av_info(C.byref(self.av))
        g, t = self.av.geometry, self.av.timing
        log("INFO", f"Video {g.base_width}x{g.base_height} aspect {g.aspect_ratio:.3f}, {t.fps:.3f} fps, sound {t.sample_rate:.0f} Hz")
        for port in range(2): L.retro_set_controller_port_device(port, DEVICE_JOYPAD)
        try: self.audio = AudioOut(t.sample_rate)
        except Exception as e: log("WARN", f"No sound: {e}")
        self.load_sram(); self.load_remap()
        self.keymap = {rk: pk for rk, pk in retro_keymap().items() if pk not in self.KEYS}   # pad keys stay pad keys
        self.clock = pygame.time.Clock()

    # -- core options: the core's defaults, with the user's RetroArch choices on top
    def load_ra_options(self):
        self.user_opts = {}
        for p in (f"{RA}/retroarch-core-options.cfg", f"{RA}/config/{self.name}/{self.name}.opt"):
            try:
                for ln in open(p, errors="replace"):
                    if "=" in ln:
                        k, v = ln.split("=", 1); self.user_opts[k.strip()] = v.strip().strip('"')
            except OSError: pass

    def opt_value(self, key):
        v = self.user_opts.get(key, self.options.get(key))
        if v is None: return None
        if key not in self.opt_buf or self.opt_buf[key].value != v.encode():
            self.opt_buf[key] = C.create_string_buffer(v.encode())
        return C.cast(self.opt_buf[key], C.c_char_p)

    # -- the environment callback: the core asks the frontend questions and tells it things
    def env(self, cmd, data):
        cmd &= 0xFFFF                                        # drop the "experimental" / "private" flags
        try:
            if cmd == 1:                                     # SET_ROTATION
                self.rotation = C.cast(data, C.POINTER(C.c_uint))[0] % 4; return True
            if cmd == 2: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True     # GET_OVERSCAN
            if cmd == 3: C.cast(data, C.POINTER(C.c_bool))[0] = True; return True      # GET_CAN_DUPE
            if cmd == 6:                                     # SET_MESSAGE
                m = C.cast(data, C.POINTER(Message))[0]
                if m.msg: log("INFO", "Core message: " + m.msg.decode(errors="replace"))
                return True
            if cmd == 7: self.running = False; return True   # SHUTDOWN
            if cmd == 8: return True                         # SET_PERFORMANCE_LEVEL
            if cmd in (9, 30, 31):                           # SYSTEM / CORE_ASSETS / SAVE directory
                d = SYSTEM if cmd != 31 else f"{SAVES}/{self.name}"
                os.makedirs(d, exist_ok=True)
                return self.give_string(data, d)
            if cmd == 10:                                    # SET_PIXEL_FORMAT
                f = C.cast(data, C.POINTER(C.c_int))[0]
                if f in PIXFMT: self.pixfmt = f; self.surf = None; return True
                return False
            if cmd == 11:                                    # SET_INPUT_DESCRIPTORS: the game's names for its buttons
                arr = C.cast(data, C.POINTER(InputDescriptor)); i = 0; d = {}
                while arr[i].description:
                    x = arr[i]
                    if x.port == 0 and x.device & 0xFF == DEVICE_JOYPAD and x.id in REMAPPABLE:
                        d.setdefault(x.id, x.description.decode(errors="replace").strip())
                    i += 1
                self.descs = d; return True
            if cmd in (34, 35, 36, 42, 44, 53, 55, 63, 65, 69): return True           # info we can safely accept
            if cmd == 15:                                    # GET_VARIABLE
                v = C.cast(data, C.POINTER(Variable))[0]
                val = self.opt_value(v.key.decode()) if v.key else None
                C.cast(data, C.POINTER(Variable))[0].value = val
                return val is not None
            if cmd == 16:                                    # SET_VARIABLES: "Description; first|second|..."
                arr = C.cast(data, C.POINTER(Variable)); i = 0
                while arr[i].key:
                    desc = (arr[i].value or b"").decode(errors="replace")
                    choices = desc.split(";", 1)[-1].strip().split("|")
                    self.options[arr[i].key.decode()] = choices[0]; i += 1
                return True
            if cmd == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True    # GET_VARIABLE_UPDATE
            if cmd == 18: return True                        # SET_SUPPORT_NO_GAME
            if cmd == 19: return self.give_string(data, self.core_path)                 # GET_LIBRETRO_PATH
            if cmd == 24: C.cast(data, C.POINTER(C.c_uint64))[0] = (1 << DEVICE_JOYPAD) | (1 << DEVICE_KEYBOARD) | (1 << DEVICE_ANALOG); return True
            if cmd == 27:                                    # GET_LOG_INTERFACE
                C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(self.log_cb, C.c_void_p).value; return True
            if cmd == 32:                                    # SET_SYSTEM_AV_INFO
                self.av = C.cast(data, C.POINTER(AVInfo))[0]; return True
            if cmd == 37:                                    # SET_GEOMETRY
                self.av.geometry = C.cast(data, C.POINTER(Geometry))[0]; return True
            if cmd == 38: return self.give_string(data, "Player 1")                     # GET_USERNAME
            if cmd == 39: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True        # GET_LANGUAGE: English
            if cmd == 47:
                if data: C.cast(data, C.POINTER(C.c_int))[0] = 3                       # audio + video on
                return True
            if cmd == 49:
                if data: C.cast(data, C.POINTER(C.c_bool))[0] = False                  # not fast-forwarding
                return True
            if cmd == 50: C.cast(data, C.POINTER(C.c_float))[0] = 60.0; return True    # GET_TARGET_REFRESH_RATE
            if cmd == 51: return True                        # GET_INPUT_BITMASKS: yes
            if cmd == 61: C.cast(data, C.POINTER(C.c_uint))[0] = 4; return True        # GET_INPUT_MAX_USERS
            if cmd == 60:                                    # SET_MESSAGE_EXT (msg is the first field)
                p = C.cast(data, C.POINTER(C.c_char_p))[0]
                if p: log("INFO", "Core message: " + p.decode(errors="replace"))
                return True
        except Exception as e:
            log("WARN", f"Environment call {cmd} failed: {e}")
        return False                                         # anything else: "not supported", cores cope

    def give_string(self, data, s):
        b = C.create_string_buffer(s.encode()); self.keep.append(b)
        C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(b, C.c_void_p).value
        return True

    def core_log(self, level, fmt):
        if level >= 2 and fmt:                               # warnings and errors only
            log("WARN" if level == 2 else "ERROR", fmt.decode(errors="replace").strip().replace("%s", "…"))

    # -- loading the game (zips handled like RetroArch: extract unless the core reads zips itself)
    def load_game(self):
        exts = [e.lower() for e in (self.info.valid_extensions or b"").decode().split("|") if e]
        path, inner = split_archive(self.rom)
        if not os.path.exists(path): raise SystemExit(f"[ERROR] ROM not found: {path}")
        data = None
        kind = path.lower().rsplit(".", 1)[-1]
        if not inner and kind in ("zip", "7z") and kind not in exts:
            inner = next((n for n in archive_names(path) if n.rsplit(".", 1)[-1].lower() in exts), "")
            if not inner: raise SystemExit(f"[ERROR] No file the core can read inside {os.path.basename(path)}")
        if inner:
            data = archive_read(path, inner)
            self.tmpdir = tempfile.mkdtemp(prefix="insert-coin-")
            path = os.path.join(self.tmpdir, os.path.basename(inner))
            with open(path, "wb") as f: f.write(data)
        elif not self.info.need_fullpath:
            data = open(path, "rb").read()
        self.game_name = os.path.splitext(os.path.basename(inner or path))[0]
        gi = GameInfo(path.encode(), None, 0, None)
        if data is not None and not self.info.need_fullpath:
            self.romdata = C.create_string_buffer(data, len(data))
            gi.data, gi.size = C.cast(self.romdata, C.c_void_p), len(data)
        log("INFO", f"Loading {self.game_name}")
        if not self.lib.retro_load_game(C.byref(gi)):
            raise SystemExit("[ERROR] Failed to load content: the core could not start this game")

    # -- battery saves (.srm): ours, starting from RetroArch's copy the first time
    def sram_path(self): return f"{SAVES}/{self.name}/{self.game_name}.srm"

    def load_sram(self):
        size = self.lib.retro_get_memory_size(MEMORY_SAVE_RAM); ptr = self.lib.retro_get_memory_data(MEMORY_SAVE_RAM)
        if not size or not ptr: return
        p = self.sram_path(); ra = f"{RA}/saves/{self.name}/{self.game_name}.srm"
        if not os.path.exists(p) and os.path.exists(ra):
            os.makedirs(os.path.dirname(p), exist_ok=True); shutil.copy2(ra, p)
            log("INFO", "Imported the battery save from RetroArch")
        if os.path.exists(p):
            b = open(p, "rb").read()[:size]; C.memmove(ptr, b, len(b)); log("INFO", "Battery save loaded")

    def save_sram(self):
        size = self.lib.retro_get_memory_size(MEMORY_SAVE_RAM); ptr = self.lib.retro_get_memory_data(MEMORY_SAVE_RAM)
        if not size or not ptr: return
        os.makedirs(os.path.dirname(self.sram_path()), exist_ok=True)
        tmp = self.sram_path() + ".tmp"
        with open(tmp, "wb") as f: f.write(C.string_at(ptr, size))
        os.replace(tmp, self.sram_path())

    # -- per-game button layout ("Controls" in the pause menu)
    def remap_path(self): return f"{CONFDIR}/remaps/{self.name}/{self.game_name}.json"

    def load_remap(self):
        try:
            m = json.load(open(self.remap_path()))["map"]
            self.remap = {int(t): int(s) for t, s in m.items() if int(t) in REMAPPABLE and int(s) in REMAPPABLE}
            if self.remap: log("INFO", f"Using this game's own button layout ({len(self.remap)} changed)")
        except (OSError, ValueError, KeyError, TypeError):
            self.remap = {}

    def save_remap(self):
        try:
            p = self.remap_path()
            if not self.remap:
                if os.path.exists(p): os.remove(p)
                return
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + ".tmp", "w") as f: json.dump({"map": {str(t): s for t, s in self.remap.items()}}, f, indent=1)
            os.replace(p + ".tmp", p)
        except OSError as e:
            log("WARN", f"Could not save the button layout: {e}")

    def assign(self, target, source):
        """The button in your hand that used to give `source` now gives the game's `target`; whichever game button
        it gave before takes over target's old button, so no button does two things and none is lost."""
        cur = lambda t: self.remap.get(t, t)
        old = cur(target)
        other = next((t for t in REMAPPABLE if t != target and cur(t) == source), None)
        self.remap[target] = source
        if other is not None: self.remap[other] = old
        self.remap = {t: s for t, s in self.remap.items() if t != s}
        self.save_remap()
        log("INFO", f"Controls: {self.button_name(target)} on {self.pad_label(source)}")

    def apply_remap(self, bits):
        if not self.remap: return bits
        out = bits & ~sum(1 << t for t in REMAPPABLE)
        for t in REMAPPABLE:
            if bits >> self.remap.get(t, t) & 1: out |= 1 << t
        return out

    def targets(self):
        """The game's buttons: the ones the core named, or the usual set if it named none."""
        return [t for t in REMAPPABLE if t in self.descs] or [B_, A_, Y_, X_, L_, R_, SELECT, START]

    def button_name(self, t): return self.descs.get(t) or GENERIC_NAMES[t]

    def pad_label(self, rid): return PAD_LABELS.get(self.style, PAD_LABELS["xbox"]).get(rid, "?")

    # -- picture
    def video(self, data, w, h, pitch):
        if not data: return                                  # "same frame as before"
        bpp, depth, masks = PIXFMT[self.pixfmt]
        if self.surf is None or self.surf.get_size() != (pitch // bpp, h) or self.surf.get_pitch() != pitch:
            self.surf = pygame.Surface((pitch // bpp, h), 0, depth, masks)
        buf = C.string_at(data, pitch * h)
        if self.surf.get_pitch() == pitch: self.surf.get_buffer().write(buf)
        else:
            sp = self.surf.get_pitch(); px = self.surf.get_buffer()
            for y in range(h): px.write(buf[y * pitch:(y + 1) * pitch], y * sp)
        self.frame = self.surf.subsurface((0, 0, w, h))

    def present(self):
        self.screen.fill((0, 0, 0))
        if self.frame:
            img = pygame.transform.rotate(self.frame, 90 * self.rotation) if self.rotation else self.frame
            g = self.av.geometry
            aspect = g.aspect_ratio if g.aspect_ratio > 0 else self.frame.get_width() / self.frame.get_height()
            if self.rotation % 2: aspect = 1 / aspect
            th = H; tw = round(th * aspect)
            if tw > W: tw = W; th = round(W / aspect)
            self.screen.blit(pygame.transform.scale(img, (tw, th)), ((W - tw) // 2, (H - th) // 2))  # sharp pixels
        if self.paused: self.draw_menu()
        pygame.display.flip()

    # -- sound
    def sample(self, l, r):
        if self.audio: self.audio.push(struct.pack("<hh", l, r))

    def batch(self, data, frames):
        if self.audio and data: self.audio.push(C.string_at(data, frames * 4))
        return frames

    # -- controllers: port 1 = keyboard + first pad, port 2 = second pad ...
    def open_pads(self):
        """Open each controller once and keep it (re-opening a pad SDL already has open can leave a stale copy)."""
        have = {}
        for c, st in self.pads:
            try:
                if c.attached(): have[c.as_joystick().get_instance_id()] = (c, st)
            except Exception: pass
        pads = []
        for i in range(sdlc.get_count()):
            if not sdlc.is_controller(i): continue
            try:
                j = pygame.joystick.Joystick(i); iid = j.get_instance_id()
                if iid in have: pads.append(have[iid]); continue
                c = sdlc.Controller(i)
                style = controller_style(c.name, j.get_guid()) if controller_style else "xbox"
                pads.append((c, style))
            except Exception: pass
        if [id(c) for c, _ in pads] != [id(c) for c, _ in self.pads]:
            self.pads = pads
            log("INFO", "Controllers: " + (", ".join(f"{c.name} ({s})" for c, s in pads) or "keyboard only"))

    @staticmethod
    def button_pairs(style):
        """(RetroPad id, SDL button) for a controller family."""
        # RetroPad buttons sit by position (B bottom, A right). SDL already reports Xbox, PlayStation and SNES-replica
        # pads by position; Nintendo's own pads are reported by printed label, so their letters line up directly.
        nin = style == "nintendo"
        return [(B_, pygame.CONTROLLER_BUTTON_B if nin else pygame.CONTROLLER_BUTTON_A),
                 (A_, pygame.CONTROLLER_BUTTON_A if nin else pygame.CONTROLLER_BUTTON_B),
                 (Y_, pygame.CONTROLLER_BUTTON_Y if nin else pygame.CONTROLLER_BUTTON_X),
                 (X_, pygame.CONTROLLER_BUTTON_X if nin else pygame.CONTROLLER_BUTTON_Y),
                 (SELECT, pygame.CONTROLLER_BUTTON_BACK), (START, pygame.CONTROLLER_BUTTON_START),
                 (L_, pygame.CONTROLLER_BUTTON_LEFTSHOULDER), (R_, pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
                 (L3, pygame.CONTROLLER_BUTTON_LEFTSTICK), (R3, pygame.CONTROLLER_BUTTON_RIGHTSTICK),
                 (UP, pygame.CONTROLLER_BUTTON_DPAD_UP), (DOWN, pygame.CONTROLLER_BUTTON_DPAD_DOWN),
                 (LEFT, pygame.CONTROLLER_BUTTON_DPAD_LEFT), (RIGHT, pygame.CONTROLLER_BUTTON_DPAD_RIGHT)]

    def pad_bits(self, c, style):
        g = c.get_button
        def ax(a): return c.get_axis(a) / 32767
        bits = 0
        for rid, btn in self.button_pairs(style):
            if g(btn): bits |= 1 << rid
        if ax(pygame.CONTROLLER_AXIS_TRIGGERLEFT) > .5: bits |= 1 << L2
        if ax(pygame.CONTROLLER_AXIS_TRIGGERRIGHT) > .5: bits |= 1 << R2
        x, y = ax(pygame.CONTROLLER_AXIS_LEFTX), ax(pygame.CONTROLLER_AXIS_LEFTY)   # left stick also works as a d-pad
        if x < -.5: bits |= 1 << LEFT
        if x > .5: bits |= 1 << RIGHT
        if y < -.5: bits |= 1 << UP
        if y > .5: bits |= 1 << DOWN
        return bits

    KEYS = {pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT,
            pygame.K_z: B_, pygame.K_x: A_, pygame.K_a: Y_, pygame.K_s: X_, pygame.K_q: L_, pygame.K_w: R_,
            pygame.K_RETURN: START, pygame.K_RSHIFT: SELECT, pygame.K_BACKSPACE: SELECT}

    def poll(self):
        self.fno += 1
        keys = pygame.key.get_pressed()
        kb = sum(1 << rid for k, rid in self.KEYS.items() if keys[k])
        bits = [self.pad_bits(c, s) for c, s in self.pads] or [0]
        bits[0] |= kb
        self.held_keys = set()
        for name, a, b in self.press:                         # test presses (--press)
            if a <= self.fno <= b:
                if name in RETROPAD_NAMES: bits[0] |= 1 << RETROPAD_NAMES[name]
                else: self.held_keys.add(pygame.key.key_code(name))
        self.keys = keys
        self.bits = [self.apply_remap(b) for b in bits]
        self.sticks = [[(c.get_axis(pygame.CONTROLLER_AXIS_LEFTX), c.get_axis(pygame.CONTROLLER_AXIS_LEFTY)),
                        (c.get_axis(pygame.CONTROLLER_AXIS_RIGHTX), c.get_axis(pygame.CONTROLLER_AXIS_RIGHTY))]
                       for c, _ in self.pads]

    def state(self, port, device, index, id_):
        device &= 0xFF
        if device == DEVICE_JOYPAD:
            bits = self.bits[port] if port < len(self.bits) else 0
            if id_ == ID_MASK: return bits - 0x10000 if bits & 0x8000 else bits   # as a signed 16-bit value
            return 1 if bits >> id_ & 1 else 0
        if device == DEVICE_KEYBOARD:                          # the keyboard, for cores that read it (MAME: Tab menu, ...)
            pk = self.keymap.get(id_) if self.keymap else None
            if pk is None or self.paused: return 0
            try: return 1 if self.keys[pk] or pk in self.held_keys else 0
            except (IndexError, AttributeError): return 0
        if device == DEVICE_ANALOG and port < len(self.sticks) and index < 2 and id_ < 2:
            return max(-32767, min(32767, self.sticks[port][index][id_]))
        return 0

    # -- main loop
    MENU = ("Resume", "Controls", "Quit game")
    WAIT_S = 5                                               # seconds to press a button before it gives up

    def pad_style(self, iid):
        for c, st in self.pads:
            try:
                if c.as_joystick().get_instance_id() == iid: return st
            except Exception: pass
        return self.pads[0][1] if self.pads else "keyboard"

    def events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT: self.running = False; continue
            if e.type in (pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED): self.open_pads(); continue
            if e.type == pygame.CONTROLLERBUTTONDOWN: self.style = self.pad_style(e.instance_id)
            elif e.type == pygame.KEYDOWN and e.key != pygame.K_ESCAPE: self.style = "keyboard"
            if self.paused and self.mode == "wait":            # waiting for the button to give a game action
                src = None
                if e.type == pygame.CONTROLLERBUTTONDOWN:
                    src = next((rid for rid, b in self.button_pairs(self.style) if b == e.button and rid in REMAPPABLE), None)
                elif e.type == pygame.CONTROLLERAXISMOTION and e.value > 16000 and e.axis in (
                        pygame.CONTROLLER_AXIS_TRIGGERLEFT, pygame.CONTROLLER_AXIS_TRIGGERRIGHT):
                    self.style = self.pad_style(e.instance_id)
                    src = L2 if e.axis == pygame.CONTROLLER_AXIS_TRIGGERLEFT else R2
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE: self.mode = "controls"; continue
                    src = self.KEYS.get(e.key)
                    if src not in REMAPPABLE: src = None
                if src is not None:
                    self.assign(self.targets()[self.ctl_sel], src); self.mode = "controls"
                continue
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if self.paused and self.mode == "controls": self.mode = "pause"
                    else: self.set_pause(not self.paused)
                elif self.paused: self.menu_key({pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_RETURN: "ok",
                                                 pygame.K_KP_ENTER: "ok", pygame.K_BACKSPACE: "back"}.get(e.key))
            elif e.type == pygame.CONTROLLERBUTTONDOWN and self.paused:
                self.menu_key({pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
                               pygame.CONTROLLER_BUTTON_A: "ok", pygame.CONTROLLER_BUTTON_B: "back"}.get(e.button))
            elif e.type == pygame.CONTROLLERAXISMOTION and self.paused and e.axis == pygame.CONTROLLER_AXIS_LEFTY and abs(e.value) > 20000:
                self.menu_key("up" if e.value < 0 else "down")
        if self.paused and self.mode == "wait" and time.time() > self.wait_until: self.mode = "controls"
        # Select + Start together (on any pad) opens the menu; a second press closes it
        both = any(c.get_button(pygame.CONTROLLER_BUTTON_BACK) and c.get_button(pygame.CONTROLLER_BUTTON_START) for c, _ in self.pads)
        if both and not self.combo_down: self.set_pause(not self.paused)
        self.combo_down = both

    def set_pause(self, on):
        self.paused = on; self.menu_sel = 0; self.mode = "pause"
        if not on and self.audio:
            with self.audio.lock: self.audio.buf.clear()          # no stale sound after a pause
        log("INFO", "Paused" if on else "Resumed")

    def menu_key(self, k):
        if self.mode == "controls": return self.controls_key(k)
        if k == "up": self.menu_sel = (self.menu_sel - 1) % len(self.MENU)
        elif k == "down": self.menu_sel = (self.menu_sel + 1) % len(self.MENU)
        elif k == "back": self.set_pause(False)
        elif k == "ok":
            item = self.MENU[self.menu_sel]
            if item == "Resume": self.set_pause(False)
            elif item == "Controls": self.mode = "controls"; self.ctl_sel = 0
            else: log("INFO", "Quit chosen from the game menu"); self.running = False

    def controls_rows(self): return self.targets() + ["reset", "done"]

    def controls_key(self, k):
        rows = self.controls_rows()
        if k == "up": self.ctl_sel = (self.ctl_sel - 1) % len(rows)
        elif k == "down": self.ctl_sel = (self.ctl_sel + 1) % len(rows)
        elif k == "back": self.mode = "pause"
        elif k == "ok":
            r = rows[self.ctl_sel]
            if r == "done": self.mode = "pause"
            elif r == "reset":
                self.remap = {}; self.save_remap(); log("INFO", "Controls: back to the standard layout")
            else: self.mode = "wait"; self.wait_until = time.time() + self.WAIT_S

    def draw_menu(self):
        if getattr(self, "mode", "pause") != "pause": return self.draw_controls()
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 160)); self.screen.blit(dim, (0, 0))
        box = pygame.Rect(0, 0, 560, 150 + 96 * len(self.MENU)); box.center = (W // 2, H // 2)
        pygame.draw.rect(self.screen, (28, 30, 42), box, border_radius=28)
        pygame.draw.rect(self.screen, (90, 95, 115), box, 3, border_radius=28)
        t = self.font(40).render("Paused", True, (255, 255, 255)); self.screen.blit(t, t.get_rect(midtop=(W // 2, box.top + 36)))
        for k, label in enumerate(self.MENU):
            r = pygame.Rect(0, 0, 420, 72); r.center = (W // 2, box.top + 150 + k * 96)
            on = k == self.menu_sel
            pygame.draw.rect(self.screen, (230, 232, 240) if on else (55, 58, 75), r, border_radius=20)
            t = self.font(32).render(label, True, (20, 22, 30) if on else (230, 232, 240)); self.screen.blit(t, t.get_rect(center=r.center))

    def glyph(self, text, center, on=False):
        """A button as printed on the pad, in a small pill."""
        f = self.symfont(30)
        t = f.render(text, True, (20, 22, 30) if not on else (255, 255, 255))
        r = pygame.Rect(0, 0, max(64, t.get_width() + 32), 50); r.center = center
        pygame.draw.rect(self.screen, (200, 204, 216) if not on else (60, 64, 84), r, border_radius=25)
        self.screen.blit(t, t.get_rect(center=r.center))

    def symfont(self, n, _c={}):
        if n not in _c:
            fp = pygame.font.match_font("dejavusans,notosanssymbols,notosans", bold=True)   # has the PlayStation shapes
            _c[n] = pygame.font.Font(fp, n)
        return _c[n]

    def draw_controls(self):
        dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 190)); self.screen.blit(dim, (0, 0))
        rows = self.controls_rows(); show = 13; rh = 56
        top = max(0, min(self.ctl_sel - show // 2, len(rows) - show))
        vis = rows[top:top + show]
        box = pygame.Rect(0, 0, 900, 220 + rh * len(vis)); box.center = (W // 2, H // 2)
        pygame.draw.rect(self.screen, (28, 30, 42), box, border_radius=28)
        pygame.draw.rect(self.screen, (90, 95, 115), box, 3, border_radius=28)
        t = self.font(40).render("Controls", True, (255, 255, 255)); self.screen.blit(t, t.get_rect(midtop=(W // 2, box.top + 30)))
        t = self.font(24).render(f"For this game only  \u00b7  {self.title or self.game_name}"[:80], True, (160, 165, 185))
        self.screen.blit(t, t.get_rect(midtop=(W // 2, box.top + 84)))
        for k, r in enumerate(vis):
            i = top + k; on = i == self.ctl_sel
            row = pygame.Rect(0, 0, 780, rh - 10); row.midtop = (W // 2, box.top + 130 + k * rh)
            pygame.draw.rect(self.screen, (230, 232, 240) if on else (45, 48, 64), row, border_radius=18)
            col = (20, 22, 30) if on else (230, 232, 240)
            if r in ("reset", "done"):
                label = "Reset to standard layout" if r == "reset" else "Done"
                t = self.font(28).render(label, True, col); self.screen.blit(t, t.get_rect(center=row.center))
                continue
            name = self.button_name(r)
            changed = r in self.remap
            t = self.font(28).render(name[:34] + ("  \u2022" if changed else ""), True, col)
            self.screen.blit(t, t.get_rect(midleft=(row.left + 28, row.centery)))
            if self.mode == "wait" and on:
                left = max(0, int(self.wait_until - time.time() + 0.99))
                t = self.font(26).render(f"Press a button\u2026 {left}", True, (200, 60, 60))
                self.screen.blit(t, t.get_rect(midright=(row.right - 24, row.centery)))
            else:
                self.glyph(self.pad_label(self.remap.get(r, r)), (row.right - 70, row.centery), on)
        hint = ("Press the button you want for it  \u00b7  Esc to cancel" if self.mode == "wait" else
                "Choose a game button, then press the button you want for it  \u00b7  \u2022 = changed")
        t = self.font(22).render(hint, True, (160, 165, 185)); self.screen.blit(t, t.get_rect(midbottom=(W // 2, box.bottom - 24)))

    def run(self):
        last_save = time.time(); frames = 0
        try:
            while self.running:
                self.events()
                ran = 0
                if self.paused:
                    self.present(); self.clock.tick(60); continue
                if self.audio:                               # run the core just fast enough to keep the sound fed
                    while self.running and self.audio.queued() < self.audio.target and ran < 4:
                        self.lib.retro_run(); ran += 1
                else:
                    self.lib.retro_run(); ran = 1
                frames += ran
                if ran: self.present()
                else: pygame.time.wait(1)
                if not self.audio or self.shot: self.clock.tick(self.av.timing.fps or 60)
                if self.frames_left is not None and frames >= self.frames_left: break
                if time.time() - last_save > 30: self.save_sram(); last_save = time.time()
        finally:
            if self.shot and self.frame: pygame.image.save(self.screen, self.shot); log("INFO", f"Screenshot: {self.shot}")
            self.save_sram()
            # the save is safe now; if a core (or the sound device) hangs while closing, don't leave the player stuck
            snd = f", {self.audio.produced / 4 / self.audio.rate:.1f} s of sound" if self.audio else ", no sound"
            def watchdog():
                log("WARN", "The core did not close within 8 s; leaving anyway")
                log("INFO", f"Content ran for {frames} frames ({frames / (self.av.timing.fps or 60):.1f} s of game){snd}")
                if self.tmpdir: shutil.rmtree(self.tmpdir, ignore_errors=True)
                os._exit(0)
            wd = threading.Timer(8, watchdog); wd.daemon = True; wd.start()
            try: pygame.display.quit()                        # back to Insert Coin's screen straight away
            except Exception: pass
            if self.audio: self.audio.close()
            self.lib.retro_unload_game(); self.lib.retro_deinit()
            wd.cancel()
            if self.tmpdir: shutil.rmtree(self.tmpdir, ignore_errors=True)
            log("INFO", f"Content ran for {frames} frames ({frames / (self.av.timing.fps or 60):.1f} s of game){snd}")


try:                                                         # reuse Insert Coin's controller-family detection
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from insert_coin import controller_style
except Exception:
    controller_style = None


def main():
    a = sys.argv[1:]
    if len(a) < 2: print(__doc__); sys.exit(2)
    frames = int(a[a.index("--frames") + 1]) if "--frames" in a else None
    shot = a[a.index("--shot") + 1] if "--shot" in a else None
    pygame.display.init(); pygame.joystick.init(); sdlc.init(); pygame.font.init()
    from pygame._sdl2 import sdl2
    sdl2.init_subsystem(sdl2.INIT_AUDIO)                     # SDL's audio system, without pygame's mixer: we feed the device ourselves
    press = []
    for k, x in enumerate(a):
        if x == "--press" and k + 1 < len(a):
            name, rng = a[k + 1].rsplit("@", 1); f0, f1 = (rng.split("-") + [rng])[:2]
            press.append((name.lower(), int(f0), int(f1)))
    title = a[a.index("--title") + 1] if "--title" in a else None
    p = Player(a[0], a[1], windowed="--windowed" in a, frames=frames, shot=shot, press=press, title=title)
    p.run(); pygame.quit()


if __name__ == "__main__":
    main()
