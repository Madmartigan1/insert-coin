"""Optional DevTools-pipe input for Flash games (off: FLASH_DEVTOOLS_INPUT = False)."""
import fcntl, json, os, pygame, threading, time
from insertcoin.web import FLASH_BUTTONS


# Off: with it, the physical keyboard stopped working on some Flash screens (user test, 2026-11-09), and it still
# couldn't get the pad past one game's "press space to continue". The page reads the pad instead (flash_page).
FLASH_DEVTOOLS_INPUT = False


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
        self.stats = {}                                             # key -> presses sent, and "click", for the log
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
        if down: self.stats[name] = self.stats.get(name, 0) + 1
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
        if down: self.stats["click"] = self.stats.get("click", 0) + 1
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

    MIN_HOLD = 0.15                                                 # s: Flash games often check keys a few times a second

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
        now = time.time()
        for b, keys in self.map.items():
            want = down[b] and not (b == sel and self.clicking)
            if not want and self.held.get(b + ":k") and now - self.held.get(b + ":t", 0) < self.MIN_HOLD:
                want = True                                         # a quick tap is held long enough to be seen
            if want != bool(self.held.get(b + ":k")):
                for k in keys: self.xin.key(k, want)
                self.held[b + ":k"] = want
                if want: self.held[b + ":t"] = now
            self.held[b] = down[b]
        self.xin.flush()

    def release(self):
        self.held = {}; self.clicking = False; self.xin.release_all()
