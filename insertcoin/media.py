"""Images (loaded off the main thread), fonts and menu sounds."""
import collections, os, pygame, threading, time


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


# ---------------------------------------------------------------- fonts
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
