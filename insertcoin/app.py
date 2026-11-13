"""The app: state, navigation, input and the main loop."""
import os, platform, pygame, subprocess, sys, time
from pygame._sdl2 import controller as sdlc
from insertcoin import __version__
from insertcoin.logs import log, start_log
from insertcoin.web import WebGame
from insertcoin.library import Library
from insertcoin.cores import not_builtin_systems
from insertcoin.meta import Meta
from insertcoin.media import Fonts, Images, Sounds
from insertcoin.settings import load_settings, save_settings
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

    # -- main loop
    def run(self):
        if self.shot: return self.screenshots()
        self.running = True
        while self.running:
            for e in pygame.event.get(): self.handle(e)
            self.tick_repeat(); self.draw(); pygame.display.flip(); self.clock.tick(60)
        pygame.quit()


def main():
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
