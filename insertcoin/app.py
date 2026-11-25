"""The app: state, navigation, input and the main loop."""
import os, platform, pygame, shutil, subprocess, sys, time
from pygame._sdl2 import controller as sdlc
from insertcoin import __version__
from insertcoin.logs import log, start_log
from insertcoin.web import WebGame
from insertcoin.library import Library
from insertcoin.ownlib import open_source
from insertcoin.cores import not_builtin_systems
from insertcoin.meta import Meta
from insertcoin.media import Fonts, Images, Sounds
from insertcoin.settings import load_settings, retroarch_installed, save_settings
from insertcoin.draw import H, W
from insertcoin.launch import Launcher
from insertcoin.pads import Pads
from insertcoin.screens import Screens


# ---------------------------------------------------------------- the app
class App(Pads, Launcher, Screens):
    def __init__(self, windowed=False, shot=None):
        self.windowed, self.shot = windowed, shot
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init(); sdlc.init()
        self.settings = load_settings()
        self.sfx = Sounds(enabled=self.settings["sound"], start=not shot)
        self.open_display()
        self.fonts = Fonts()
        self.lib = self.make_library()
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
        self.q = ""; self.kpos = (1, 0); self.preview = []; self.back_to = (self.si, "systems")   # the search screen
        self.in_results, self.rsel = False, 0          # the pad is on the list of games beside the keyboard, at rsel
        self.clock = pygame.time.Clock()
        if self.lib_note: self.say(self.library_message(), 4.0)

    # -- display / input
    def open_display(self):
        flags = 0 if self.shot else pygame.SCALED | (0 if self.windowed else pygame.FULLSCREEN)
        self.screen = pygame.display.set_mode((W, H), flags, vsync=0 if self.shot else 1)
        pygame.display.set_caption("Insert Coin")
        pygame.mouse.set_visible(bool(self.windowed))

    def make_library(self):
        """The game library from the source the "library" setting names (RetroArch's playlists or Insert Coin's)."""
        self.lib_kind, source, self.lib_note = open_source(self.settings.get("library"))
        log.info("Library: %s", "Insert Coin (beta)" if self.lib_kind == "insertcoin" else "RetroArch playlists")
        lib = Library(one_per_game=self.settings["one_per_game"], source=source)
        lib.info_of = self.game_info
        return lib

    def game_info(self, g):
        """[year, publisher, developer] from RetroArch's databases (or browser_games.json); None if unknown or
        not loaded yet. Search uses it for years and company names."""
        return self.meta.get(g) if getattr(self, "meta", None) else None

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
            if self.sys["special"] == "search": return self.open_search()
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
            elif choice.startswith("Library"): self.toggle_library()
            else: self.sfx.play("select"); self.setup_from_menu()

    def toggle_grouping(self):
        """One entry per game (copies hidden, versions under X) or every ROM, exactly as the playlists list them."""
        self.settings["one_per_game"] = not self.settings["one_per_game"]
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        sid = self.sys["id"] if self.lib.systems else None
        self.lib = self.make_library(); self.gi = {}
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.spos = float(self.si)
        self.sfx.play("select")
        total = sum(len(s["games"]) for s in self.lib.systems if not s["special"])
        self.say(f"One entry per game: {total:,} games (other versions under X)" if self.settings["one_per_game"]
                 else f"Showing every ROM: {total:,} entries", 3.0)

    def toggle_library(self):
        """RetroArch's playlists or Insert Coin's own library (imported from RetroArch the first time)."""
        self.settings["library"] = "retroarch" if self.settings.get("library") == "insertcoin" else "insertcoin"
        sid = self.sys["id"] if self.lib.systems else None
        self.lib = self.make_library(); self.gi = {}
        if self.lib_kind != self.settings["library"]: self.settings["library"] = self.lib_kind   # it fell back
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.spos = float(self.si)
        self.sfx.play("select")
        self.say(self.library_message(), 3.0)

    def library_message(self):
        """What the library switch says: which library, and how many games it shows in the current Games mode."""
        if self.lib_note and self.lib_note != "imported": return self.lib_note          # it fell back to RetroArch
        total = sum(len(s["games"]) for s in self.lib.systems if not s["special"])
        count = f"{total:,} games" if self.settings["one_per_game"] else f"{total:,} entries"
        if self.lib_kind != "insertcoin": return f"Library: RetroArch playlists - {count}"
        return f"Library: Insert Coin (beta) - {count}" + (" (imported from RetroArch)" if self.lib_note else "")

    def toggle_engine(self):
        if not retroarch_installed():                               # nothing to switch to
            self.settings["engine"] = True; self.sfx.play("back")
            self.say("RetroArch isn't installed: every game runs in the built-in player", 3.0); return
        self.settings["engine"] = not self.settings.get("engine")
        try: save_settings(self.settings)
        except Exception as e: self.say(f"Could not save the setting: {e}")
        self.sfx.play("select")
        left = not_builtin_systems()
        on = "Built-in player: " + (f"every system except {' and '.join(left)} runs without RetroArch" if left
                                    else "every system runs without RetroArch")
        self.say(on if self.settings["engine"] else "All games run in RetroArch", 3.0)

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

    # -- search: an on-screen keyboard (or the real one); results open in the Search list
    KEYS = ["1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM", ("Space", "Delete", "Search")]

    def open_search(self):
        if self.screen_mode not in ("systems", "games") or not any(s["id"] == "search" for s in self.lib.systems): return
        self.back_to = (self.si, self.screen_mode)
        self.q = self.lib.query; self.preview = self.lib.search(self.q); self.in_results, self.rsel = False, 0
        self.screen_mode = "search"; self.hold.clear(); self.sfx.play("menu")

    def type_key(self, ch):
        """Add a letter (or space), delete one, and update the matches shown beside the keyboard."""
        if ch == "Delete": self.q = self.q[:-1]
        elif ch == "Space": self.q = self.q + " " if self.q and not self.q.endswith(" ") else self.q
        elif len(self.q) < 40: self.q += ch.lower()
        self.preview = self.lib.search(self.q); self.rsel = 0; self.in_results = False; self.sfx.play("move")

    def run_search(self, at=0):
        """Show what was found in the Search list (on the home screen's Search tile), at game number `at`."""
        if not self.q.strip(): self.err("Type part of a game's name first"); return
        found = self.lib.set_search(self.q)
        if not found: self.err(f"No games found for \u201c{self.q.strip()}\u201d"); return
        self.si = next(i for i, s in enumerate(self.lib.systems) if s["id"] == "search")
        at = min(at, len(found) - 1); self.gi["search"] = at; self.gpos = float(at); self.spos = float(self.si)
        self.screen_mode = "games"; self.sfx.play("select")

    def key_at(self, row, col):
        keys = self.KEYS[row]; return keys[min(col, len(keys) - 1)]

    def move_key(self, act):
        """Move on the keyboard; up and down keep to the key nearest the same spot."""
        row, col = self.kpos
        if act == "right" and min(col, len(self.KEYS[row]) - 1) == len(self.KEYS[row]) - 1 and self.preview:
            self.in_results = True; self.rsel = min(self.rsel, len(self.preview) - 1)   # off the right edge: the games
            self.sfx.play("move"); return
        if act in ("left", "right"):
            n = len(self.KEYS[row]); col = (min(col, n - 1) + (1 if act == "right" else -1)) % n
        else:
            frac = (min(col, len(self.KEYS[row]) - 1) + 0.5) / len(self.KEYS[row])
            row = (row + (1 if act == "down" else -1)) % len(self.KEYS)
            col = min(len(self.KEYS[row]) - 1, int(frac * len(self.KEYS[row])))
        self.kpos = (row, col); self.sfx.play("move")

    RESULT_ROWS = 9                                     # games shown at once beside the keyboard

    def results_press(self, act):
        """On the list of games beside the keyboard: move, page with LB / RB, A plays, Y stars it as a favorite,
        Start opens the full list (box art, versions) at that game, Left or B goes back to the keyboard."""
        n = len(self.preview)
        if act in ("up", "down", "lb", "rb"):
            step = {"up": -1, "down": 1, "lb": -self.RESULT_ROWS, "rb": self.RESULT_ROWS}[act]
            new = max(0, min(n - 1, self.rsel + step))
            if new != self.rsel: self.rsel = new; self.sfx.play("move")
        elif act == "a": self.launch(self.preview[self.rsel])
        elif act == "y": self.favorite(self.preview[self.rsel])
        elif act == "start": self.run_search(at=self.rsel)
        elif act in ("left", "b"): self.in_results = False; self.sfx.play("back")

    def search_press(self, act):
        if self.in_results and self.preview: return self.results_press(act)
        self.in_results = False
        if act in ("left", "right", "up", "down"): self.move_key(act)
        elif act == "a":
            k = self.key_at(*self.kpos)
            self.run_search() if k == "Search" else self.type_key(k)
        elif act == "x": self.type_key("Delete")
        elif act == "y": self.type_key("Space")
        elif act == "start": self.run_search()
        elif act == "b":
            self.si, mode = self.back_to; self.screen_mode = "systems" if mode not in ("systems", "games") else mode
            self.sfx.play("back")

    def back(self):
        if self.screen_mode == "games" and self.sys["id"] == "search":    # from the results: back to the keyboard
            self.back_to = (self.si, "systems"); self.q = self.lib.query; self.preview = self.lib.search(self.q)
            self.screen_mode = "search"; self.sfx.play("back")
        elif self.screen_mode == "games": self.screen_mode = "systems"; self.sfx.play("back")
        elif self.screen_mode == "versions": self.screen_mode = "games"; self.sfx.play("back")
        elif self.screen_mode == "systems": self.screen_mode = "quit"; self.quit_sel = 0; self.sfx.play("menu")
        else: self.screen_mode = "systems"; self.sfx.play("back")

    def favorite(self, g=None):
        """Star or unstar a game: the one given (search results beside the keyboard), else the chosen one."""
        g = g or (self.cur_game() if self.screen_mode == "games" else None)
        if not g: return
        if not isinstance(g, WebGame) and subprocess.run(["pgrep", "-x", "retroarch"], capture_output=True).returncode == 0:
            self.err("Close RetroArch first to change favorites"); return
        added = self.lib.toggle_favorite(g)
        self.sfx.play("fav_on" if added else "fav_off")
        self.say(("Added to Favorites: " if added else "Removed from Favorites: ") + g.title)
        sid = self.sys["id"]; bi, bmode = self.back_to
        back_id = self.lib.systems[bi]["id"] if bi < len(self.lib.systems) else None
        self.lib.refresh_specials()                                  # the Favorites tile may come or go: find them again
        where = lambda i: next((k for k, s in enumerate(self.lib.systems) if s["id"] == i), None)
        self.si = where(sid) or 0
        if self.screen_mode == "search":                             # stay on the search screen; B goes back as before
            k = where(back_id); self.back_to = (k, bmode) if k is not None else (0, "systems")
        elif self.sys["id"] != sid: self.screen_mode = "systems"

    # -- input handling with key repeat
    REPEAT_FIRST, REPEAT = 0.32, 0.075

    def press(self, act):
        if not self.lib.systems:                                    # empty setup: only "exit" does anything
            if act == "b": self.running = False; log.info("Exit (no games found)")
            return
        if self.screen_mode == "search": return self.search_press(act)
        if act == "start": act = "a"                                 # Start chooses, as before, outside search
        if act == "search": return self.open_search()
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
             pygame.K_f: "y", pygame.K_v: "x", pygame.K_PAGEUP: "lb", pygame.K_PAGEDOWN: "rb", pygame.K_SLASH: "search"}
        B = {pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
             pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
             pygame.CONTROLLER_BUTTON_A: "a", pygame.CONTROLLER_BUTTON_B: "b", pygame.CONTROLLER_BUTTON_Y: "y",
             pygame.CONTROLLER_BUTTON_X: "x",
             pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "lb", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb",
             pygame.CONTROLLER_BUTTON_START: "start", pygame.CONTROLLER_BUTTON_BACK: "b",
             pygame.CONTROLLER_BUTTON_RIGHTSTICK: "search"}
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
        if self.screen_mode == "search" and e.type == pygame.KEYDOWN and self.type_on_keyboard(e): return
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

    def type_on_keyboard(self, e):
        """On the search screen a real keyboard types: letters, digits, space, Backspace, Enter searches.
        Returns True when the key was used here."""
        if e.key == pygame.K_BACKSPACE: self.type_key("Delete"); return True
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER): self.run_search(at=self.rsel if self.in_results else 0); return True
        if e.key == pygame.K_SPACE: self.type_key("Space"); return True
        ch = e.unicode or ""
        if len(ch) == 1 and ch.isalnum() and ch.isascii(): self.type_key(ch); return True
        return False

    def tick_repeat(self):
        now = time.time()
        for act, t in list(self.hold.items()):
            if act in ("left", "right", "up", "down") and now >= t:
                self.press(act); self.hold[act] = now + self.REPEAT

    # -- main loop
    def run(self):
        if self.shot: return self.screenshots()
        self.running = True
        while self.running:
            for e in pygame.event.get(): self.handle(e)
            self.tick_repeat(); self.draw(); pygame.display.flip(); self.clock.tick(60)
        pygame.quit()


USAGE = """Insert Coin {version} - a controller-driven, console-style game launcher.

Usage: insert-coin [option]

With no option it opens Insert Coin (full screen).

Options:
  --windowed             open it in a window instead
  --scan [FOLDER]        look through your game folders and report games not listed yet (changes nothing);
                         name the folder that holds your games when the library has none yet
  --scan --add           test-start the games found and add those that start to Insert Coin's library
  --scan --add --retry   the same, giving games left out for a black screen more starts
  --cores                copy the built-in player's emulator cores into Insert Coin's own folder
  --databases            download the game databases (which game a file is, its year and publisher)
  --bios                 check the BIOS files (and give Insert Coin its own BIOS folder, copied from RetroArch's)
  --copy-art             copy RetroArch's box art into Insert Coin's own art folder, and check every picture
  --shot DIR             render sample screens to PNG files and exit (no display needed)
  --help, -h             show this help

More: https://github.com/Madmartigan1/insert-coin#usage"""
OPTIONS = {"--windowed", "--scan", "--add", "--retry", "--cores", "--databases", "--bios", "--copy-art", "--shot", "--help", "-h"}


def check_options(a):
    """None if the options are fine to run, else what to print and the exit code. An unknown option never opens
    the full-screen app: it may have been a mistyped command."""
    if "--help" in a or "-h" in a: return USAGE.format(version=__version__), 0
    rest = a[:a.index("--shot")] + a[a.index("--shot") + 2:] if "--shot" in a else a
    if "--shot" in a and len(a) <= a.index("--shot") + 1: return "insert-coin: --shot needs a folder\nTry: insert-coin --help", 2
    folders = [o for o in rest if not o.startswith("-")] if "--scan" in rest else []
    missing = [f for f in folders if not os.path.isdir(os.path.expanduser(f))]
    if missing: return f"insert-coin: no such folder: {missing[0]}\nTry: insert-coin --help", 2
    unknown = [o for o in rest if o not in OPTIONS and o not in folders]
    if unknown: return f"insert-coin: unknown option {unknown[0]}\nTry: insert-coin --help", 2
    if ("--add" in a or "--retry" in a) and "--scan" not in a:
        return "insert-coin: --add and --retry go with --scan (insert-coin --scan --add)\nTry: insert-coin --help", 2
    if "--retry" in a and "--add" not in a: return "insert-coin: --retry goes with --scan --add\nTry: insert-coin --help", 2
    return None



class Progress:
    """A progress line in the terminal that updates in place. Shorter text is padded so nothing of a longer
    earlier line is left behind, and clear() wipes it before the results are printed."""
    def __init__(self, out=None): self.width, self.out = 0, out

    def _print(self, text): print(text, end="", flush=True, file=self.out)

    def show(self, text):
        self._print("\r" + text.ljust(self.width)); self.width = max(self.width, len(text))

    def clear(self):
        if self.width: self._print("\r" + " " * self.width + "\r"); self.width = 0

    def keep(self):
        """Leave the last progress text on screen as a record and go on below it."""
        if self.width: self._print("\n"); self.width = 0

def main():
    a = sys.argv[1:]
    problem = check_options(a)
    if problem:
        print(problem[0], file=sys.stdout if problem[1] == 0 else sys.stderr)
        raise SystemExit(problem[1])
    shot = a[a.index("--shot") + 1] if "--shot" in a else None
    if shot: os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
    if not shot: start_log()
    if "--bios" in a:                    # Insert Coin's own BIOS folder, and what's in it
        from insertcoin import bios
        copied, created = bios.set_up_own()
        print(bios.summary(bios.check(bios.OWN_SYSTEM), bios.OWN_SYSTEM, copied, created))
        return
    if "--copy-art" in a:                # Insert Coin's own art folder: a checked copy of RetroArch's
        from insertcoin import artwork
        from paths import RA_THUMBNAILS, THUMBNAILS
        if not os.path.isdir(RA_THUMBNAILS): print(f"RetroArch has no art folder ({RA_THUMBNAILS}): nothing to copy."); return
        if artwork.same_folder(RA_THUMBNAILS, THUMBNAILS):
            print("RetroArch's art folder already is Insert Coin's: nothing to copy."); return
        files = artwork.pictures(RA_THUMBNAILS)
        need = artwork.size_of(RA_THUMBNAILS, [f for f in files if not os.path.lexists(os.path.join(THUMBNAILS, f))])
        os.makedirs(THUMBNAILS, exist_ok=True)
        free = shutil.disk_usage(THUMBNAILS).free
        if need > free * 0.9:
            print(f"Not enough free space: the copy needs {need / 1e9:.1f} GB and {free / 1e9:.1f} GB is free. Nothing was copied."); return
        print(f"Copying {len(files):,} pictures ({need / 1e9:.1f} GB to copy) into {THUMBNAILS}...")
        line = Progress()
        bar = lambda what: (lambda n, t: line.show(f"  {what} {n:,} of {t:,}..."))
        copied, kept, failed = artwork.copy(progress=bar("copied"))
        line.keep(); print("Checking every picture byte for byte...")
        problems = artwork.verify(progress=bar("checked"))
        line.keep(); print("Checking every game's pictures in both folders...")
        print(artwork.summary(copied, kept, failed, problems, artwork.coverage(artwork.library_games())))
        return
    if "--databases" in a:               # Insert Coin's own game databases (no longer RetroArch's)
        from insertcoin import databases
        line = Progress()
        print("Downloading the game databases from the libretro buildbot...")
        try:
            info = databases.install(progress=lambda got, total: line.show(
                f"  {got / 2**20:.1f} of {total / 2**20:.1f} MB" if total else f"  {got / 2**20:.1f} MB"))
        except (databases.DatabaseError, OSError) as e:
            line.clear(); print(f"Could not get the game databases: {e}\nNothing was changed."); raise SystemExit(1)
        line.clear(); print(databases.summary(info))
        return
    if "--cores" in a:                   # copy (or download) the built-in player's cores into Insert Coin's folder
        from insertcoin import coreinstall
        print("Putting the built-in player's cores in Insert Coin's own folder (each one is test-loaded first)...")
        line = Progress()
        results = coreinstall.install(progress=lambda n, t, f: line.show(f"  {n} of {t}: {f}"))
        line.clear(); print(coreinstall.summary(results))
        return
    if "--scan" in a:                    # report what a scan finds (changes nothing); with --add, test-start and add them
        from insertcoin.scanner import default_roots, listed_games, scan, summary
        folders = [os.path.abspath(os.path.expanduser(o)) for o in a if not o.startswith("-")]
        if not folders and not default_roots([p for _, p in listed_games()]):
            print("Your library has no games yet, so Insert Coin doesn't know where to look. Name the folder that holds\n"
                  "your games, for example:  insert-coin --scan --add ~/Games"); raise SystemExit(2)
        print("Scanning your game folders (the first scan reads every archive's index; later ones only what changed)...")
        line = Progress()
        report = scan(roots=folders or None, progress=lambda n: line.show(f"  {n:,} files..."))
        line.clear(); print(summary(report))
        if "--add" in a:
            from insertcoin import adding
            print("\nTest-starting the games found (60 seconds of game time each, no window or sound)...")
            result = adding.add_found(report, retry="--retry" in a, progress=lambda n, t: line.show(f"  {n:,} of {t:,}..."))
            line.clear(); print(adding.summary(result))
        return
    try:
        App(windowed="--windowed" in a, shot=shot).run()
        log.info("Insert Coin closed")
    except KeyboardInterrupt:                                      # Ctrl+C in the terminal: an ordinary way to close it
        log.info("Insert Coin closed (Ctrl+C in the terminal)")
        raise SystemExit(130)
    except BaseException as e:
        if not isinstance(e, SystemExit): log.exception("Insert Coin stopped because of an error")
        raise
