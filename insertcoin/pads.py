"""Controllers: opening pads, hot-plugging, and setting up unrecognised ones."""
import json, os, pygame
from pygame._sdl2 import controller as sdlc
from paths import CONFDIR
from insertcoin.logs import log
from insertcoin.controllers import QUIT_COMBO, SETUP_STEPS, controller_style, quit_combo
class Pads:

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
