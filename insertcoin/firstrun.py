"""First-run setup on the pad (1.0 step 3): the screens. The work itself is in setup.py, shared with
`insert-coin --setup`, and runs in a thread so the screen keeps moving.

  welcome -> looking -> folders (or nofolders) -> working -> art (if the art server has pictures) -> done
                                       ^-------------------------- B on done (a folder forgotten) -----'
                          folders / nofolders -> browse (choose a folder by hand) -> folders

It opens by itself whenever the library has no games, and from the B menu ("Find games"). After it, the games
that need a test start (and the box art, if wanted) carry on in the background; the home screen shows how far
that has got, and the library is read again when it is done."""
import os, threading, time, pygame
from paths import HOME
from insertcoin import setup
from insertcoin.draw import H, W, rrect, text
from insertcoin.logs import log

ROWS = 8                                             # folders shown at once


def short(path): return path.replace(HOME, "~", 1)


class FirstRun:
    def start_firstrun(self, from_menu=False):
        self.fr = {"page": "welcome", "from_menu": from_menu, "found": [], "pick": set(), "sel": 0, "seen": 0,
                   "steps": [], "line": "", "quick": 0, "tests": 0, "art": None, "folders": []}
        self.screen_mode = "firstrun"

    # -- the work (threads; the screen only reads self.fr)
    def _look(self):
        fr = self.fr
        def counted(n): fr["seen"] = n
        try: found = setup.find_game_folders(progress=counted)
        except Exception as e: log.exception("Setup: looking for game folders"); found = []
        fr["found"], fr["pick"], fr["sel"] = found, {k for k, (_, _, likely) in enumerate(found) if likely}, 0
        fr["page"] = "folders" if found else "nofolders"
        log.info("Setup: %d folders with game files found", len(found))

    def _count(self):
        """The folder chosen by hand: how many game files it holds; it joins the list, ticked."""
        fr = self.fr; folder = fr["bdir"]
        def counted(n): fr["seen"] = n
        try: n = setup.count_game_files(folder, progress=counted)
        except Exception: log.exception("Setup: counting game files"); n = 0
        if not n:
            fr["page"] = "browse"; self.err(f"No game files in {short(folder)}"); return
        known = [k for k, (f, _, _) in enumerate(fr["found"]) if f == folder]
        if known: k = known[0]
        else: fr["found"].append((folder, n, True)); k = len(fr["found"]) - 1
        fr["pick"].add(k); fr["sel"] = k; fr["page"] = "folders"
        log.info("Setup: folder chosen by hand: %s (%d game files)", folder, n)

    # -- choosing a folder by hand
    def open_browser(self):
        fr = self.fr
        fr["bfrom"] = fr["page"]; fr["page"] = "browse"
        self.browse_to(fr.get("bdir") or HOME)

    def browse_to(self, folder, sel_name=None):
        fr = self.fr
        fr["bdir"], fr["blist"] = folder, setup.subfolders(folder)
        rows = self.browse_rows()
        fr["bsel"] = next((k for k, (kind, name) in enumerate(rows) if name == sel_name), 0)

    def browse_rows(self):
        """[(kind, name)]: use this folder, up one folder (not at the top), then the folders in it."""
        fr = self.fr
        return [("use", None)] + ([("up", None)] if fr["bdir"] != "/" else []) + [("dir", d) for d in fr["blist"]]

    def browse_up(self):
        fr = self.fr
        if fr["bdir"] == "/": return
        self.browse_to(os.path.dirname(fr["bdir"]), sel_name=os.path.basename(fr["bdir"])); self.sfx.play("back")

    def _work(self):
        fr, folders = self.fr, self.fr["folders"]
        fr["steps"] = [[key, title, "waiting", ""] for key, title in setup.STEPS] + [["art", "Box art", "waiting", ""]]
        def step(key, fn):
            row = next(r for r in fr["steps"] if r[0] == key); row[2] = "running"; fr["line"] = ""
            try: ok, note = fn(lambda t: fr.__setitem__("line", t))
            except Exception as e: log.exception("Setup step %s", key); ok, note = False, str(e)
            row[2], row[3] = ("done" if ok else "failed"), note; fr["line"] = ""
            return ok, note
        step("databases", setup.get_databases)
        step("cores", setup.get_cores)
        step("bios", lambda p: setup.get_bios(folders, p))
        report = {}
        def scan(p):
            report.update(setup.find_games(folders, p))
            n = sum(s["listed"] + len(s["new"]) + len(s["by_type"]) for s in report["systems"].values())
            return True, f"{n:,} games in {len(report['systems'])} systems"
        step("scan", scan)
        def add(p):
            fr["fresh"] = fr.get("fresh") or setup.library_is_empty()      # this setup makes the library
            fr["quick"] = setup.add_recognised(report, p, fresh=fr["fresh"]) if report else 0
            fr["added"] = fr.get("added", 0) + fr["quick"]
            fr["tests"] = setup.to_test(report) if report else 0
            setup.use_own_library()
            return True, f"{fr['quick']:,} added" + (f"; {fr['tests']:,} more to test-start" if fr["tests"] else "")
        step("add", add)
        def art(p):
            p("asking the art server what it has")
            fr["art"] = setup.art_estimate()
            pics, mb = fr["art"]
            return True, f"{pics:,} pictures available (about {mb:,} MB)" if pics else "nothing to download"
        step("art", art)
        fr["page"] = "art" if fr["art"] and fr["art"][0] else "done"

    def _thread(self, target):
        threading.Thread(target=target, daemon=True).start()

    # -- input
    def firstrun_press(self, act):
        fr = self.fr; page = fr["page"]
        if act == "start": act = "go"
        if page in ("welcome", "nofolders"):
            if page == "nofolders" and act in ("a", "go"): self.sfx.play("select"); self.open_browser()
            elif act in ("a", "go") or (page == "nofolders" and act == "y"):
                fr["page"] = "looking"; self.sfx.play("select"); self._thread(self._look)
            elif act == "b": self.leave_firstrun()
        elif page == "browse":
            rows = self.browse_rows(); sel = fr["bsel"]
            if act in ("up", "down"):
                new = max(0, min(len(rows) - 1, sel + (1 if act == "down" else -1)))
                if new != sel: fr["bsel"] = new; self.sfx.play("move")
            elif act in ("lb", "rb"):
                fr["bsel"] = max(0, min(len(rows) - 1, sel + (ROWS if act == "rb" else -ROWS))); self.sfx.play("move")
            elif act == "left": self.browse_up()
            elif act in ("a", "go", "right"):
                kind, name = rows[sel]
                if kind == "use" and act != "right":
                    fr["page"] = "looking"; fr["seen"] = 0; self.sfx.play("select"); self._thread(self._count)
                elif kind == "up": self.browse_up()
                elif kind == "dir": self.browse_to(os.path.join(fr["bdir"], name)); self.sfx.play("select")
            elif act == "b": fr["page"] = fr.get("bfrom", "folders"); self.sfx.play("back")
        elif page == "folders":
            n = len(fr["found"])                         # rows: the folders, Choose another folder (n), Continue (n + 1)
            if act in ("up", "down"):
                new = max(0, min(n + 1, fr["sel"] + (1 if act == "down" else -1)))
                if new != fr["sel"]: fr["sel"] = new; self.sfx.play("move")
            elif act == "a" and fr["sel"] < n:
                fr["pick"] ^= {fr["sel"]}; self.sfx.play("select")
            elif act == "a" and fr["sel"] == n:
                self.sfx.play("select"); self.open_browser()
            elif act in ("a", "go"):
                if not fr["pick"]: self.err("Tick at least one folder (A)"); return
                fr["folders"] = [fr["found"][k][0] for k in sorted(fr["pick"])]
                log.info("Setup: folders chosen: %s", ", ".join(fr["folders"]))
                fr["page"] = "working"; self.sfx.play("select"); self._thread(self._work)
            elif act == "b": fr["page"] = "welcome"; self.sfx.play("back")
        elif page == "art":
            if act in ("a", "go", "b"):
                fr["want_art"] = act != "b"; fr["page"] = "done"; self.sfx.play("select" if act != "b" else "back")
        elif page == "done":
            if act in ("a", "go"): self.finish_firstrun()
            elif act == "b":                                     # a folder forgotten: back to the list
                fr["page"], fr["sel"] = "folders", len(fr["found"]); self.sfx.play("back")

    def leave_firstrun(self):
        if self.fr["from_menu"] or self.lib.systems: self.screen_mode = "systems"; self.sfx.play("back")
        else: self.running = False; log.info("Exit (setup not done)")

    def finish_firstrun(self):
        fr = self.fr
        if fr["tests"] or fr.get("want_art"):
            try: setup.start_background(fr["folders"], art=bool(fr.get("want_art")))
            except Exception as e: log.exception("Setup: background run"); self.err(f"Couldn't start the background run: {e}")
        self.reload_library()
        self.screen_mode = "systems"; self.sfx.play("select")

    def reload_library(self):
        """Read the library again (after setup, or when the background run has added games)."""
        from insertcoin.settings import load_settings
        from insertcoin.meta import Meta
        sid = self.sys["id"] if self.lib.systems else None
        self.settings = load_settings()
        self.lib = self.make_library(); self.gi = {}
        self.meta = Meta({s["id"] for s in self.lib.systems if not s["special"]})
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid),
                       next((i for i, s in enumerate(self.lib.systems) if not s["special"]), 0))
        self.spos = float(self.si)

    # -- the background run, seen from the app
    def poll_background(self):
        now = time.time()
        if now < getattr(self, "_bg_next", 0): return
        self._bg_next = now + 2
        st = setup.read_status()
        self.bg = st if setup.running(st) else None
        if st and st.get("phase") == "done" and not st.get("seen"):
            setup.write_status(**dict(st, seen=True))
            self.img.forget_missing()                                    # pictures that arrived meanwhile
            if st.get("added"):
                self.reload_library()
                self.say(f"{st['added']:,} more games added (they passed their test start)", 5.0)

    def draw_background_note(self):
        st = getattr(self, "bg", None)
        if not st or self.screen_mode not in ("systems", "games"): return
        msg = (f"Test-starting new games: {st['n']:,} of {st['total']:,}" if st.get("phase") == "tests" and st.get("total")
               else "Downloading box art" if st.get("phase") == "art" else "Getting new games ready")
        f = self.fonts(22); w = f.size(msg)[0] + 40
        r = pygame.Rect(W - 70 - w, 96, w, 40)
        box = pygame.Surface(r.size, pygame.SRCALPHA); rrect(box, (0, 0, 0, 150), box.get_rect(), 20); self.screen.blit(box, r)
        text(self.screen, f, msg, r.center, (220, 224, 235), anchor="center", shadow=False)

    # -- drawing
    def draw_firstrun(self):
        fr = self.fr; page = fr["page"]
        self.draw_background((60, 70, 100))
        back = "Back" if fr["from_menu"] or self.lib.systems else "Exit"
        mid = lambda s, y, size=34, col=(220, 224, 235), bold=False: text(
            self.screen, self.fonts(size, bold), s, (W / 2, y), col, anchor="midtop", maxw=1700)
        if page == "welcome":
            self.draw_header("Welcome to Insert Coin", "Set up")
            mid("Let's find your games and get everything they need.", 330, 44, (255, 255, 255), True)
            mid("Insert Coin looks for game files in your home folder and on plugged-in drives;", 440)
            mid("you choose which folders to use. Then it gets the game databases, the emulators", 494)
            mid("and BIOS files, and builds your library.", 548)
            self.draw_hints([("a", "Start"), ("b", back)])
        elif page == "looking":
            self.draw_header("Finding your games", "Set up")
            mid("Looking for game files…", 420, 44, (255, 255, 255), True)
            mid(f"{fr['seen']:,} folders looked through", 500, 30, (190, 195, 210))
        elif page == "nofolders":
            self.draw_header("Finding your games", "Set up")
            mid("No game files were found in your home folder or on your drives.", 380, 44, (255, 255, 255), True)
            mid("Choose the folder your games are in, or copy them into your home folder", 470)
            mid("(for example into a folder called Games) and look again.", 524)
            self.draw_hints([("a", "Choose a folder"), ("y", "Look again"), ("b", back)])
        elif page == "folders":
            self.draw_header("Where are your games?", "Set up: tick the folders to use")
            n = len(fr["found"]); top = max(0, min(fr["sel"] - ROWS // 2, n + 2 - ROWS))
            for k in range(top, min(n + 2, top + ROWS)):
                y = 200 + (k - top) * 92; on = fr["sel"] == k
                r = pygame.Rect(260, y, W - 520, 78)
                rrect(self.screen, (230, 232, 240) if on else (45, 48, 64), r, 18)
                ink = (20, 22, 30) if on else (235, 238, 245)
                if k >= n:
                    label = "Choose another folder…" if k == n else "Continue"
                    text(self.screen, self.fonts(32, k > n), label, r.center, ink, anchor="center", shadow=False); continue
                folder, files, _ = fr["found"][k]
                box = pygame.Rect(r.x + 26, r.y + 21, 36, 36)
                pygame.draw.rect(self.screen, ink, box, 3, border_radius=6)
                if k in fr["pick"]:
                    pygame.draw.lines(self.screen, (60, 170, 90), False, [(box.x + 7, box.y + 18), (box.x + 15, box.y + 27), (box.x + 30, box.y + 8)], 5)
                text(self.screen, self.fonts(30, True), short(folder), (r.x + 86, r.y + 20), ink, maxw=r.w - 420, shadow=False)
                text(self.screen, self.fonts(26), f"{files:,} game files", (r.right - 30, r.y + 24), ink, anchor="topright", shadow=False)
            self.draw_hints([("a", "Continue" if fr["sel"] > n else "Choose" if fr["sel"] == n else "Tick"), ("b", "Back")])
        elif page == "browse":
            self.draw_header("Choose the folder your games are in", f"In {short(fr['bdir'])}")
            rows = self.browse_rows(); sel = fr["bsel"]; top = max(0, min(sel - ROWS // 2, len(rows) - ROWS))
            for k in range(top, min(len(rows), top + ROWS)):
                kind, name = rows[k]; on = sel == k
                r = pygame.Rect(260, 200 + (k - top) * 92, W - 520, 78)
                rrect(self.screen, (230, 232, 240) if on else (45, 48, 64), r, 18)
                ink = (20, 22, 30) if on else (235, 238, 245)
                if kind == "use":
                    text(self.screen, self.fonts(32, True), "Use this folder", r.center, ink, anchor="center", shadow=False)
                elif kind == "up":
                    text(self.screen, self.fonts(30), "‹  Up one folder", (r.x + 40, r.y + 20), ink, shadow=False)
                else:
                    text(self.screen, self.fonts(30, True), name, (r.x + 40, r.y + 20), ink, maxw=r.w - 120, shadow=False)
                    text(self.screen, self.fonts(30), "›", (r.right - 40, r.y + 20), ink, anchor="topright", shadow=False)
            if len(rows) == (1 if fr["bdir"] == "/" else 2):
                mid("No folders in here.", 200 + len(rows) * 92 + 40, 30, (190, 195, 210))
            kind = rows[sel][0]
            self.draw_hints([("a", {"use": "Use this folder", "up": "Up", "dir": "Open"}[kind]), ("b", "Back")])
        elif page == "working":
            self.draw_header("Getting everything ready", "Set up: this takes a few minutes")
            for k, (key, title, status, note) in enumerate(fr["steps"]):
                y = 230 + k * 100
                mark = {"waiting": "·", "running": "…", "done": "✓", "failed": "!"}[status]
                col = {"waiting": (150, 155, 175), "running": (255, 255, 255), "done": (120, 210, 140), "failed": (255, 170, 120)}[status]
                text(self.screen, self.fonts(36, True), mark, (330, y), col, anchor="midtop")
                text(self.screen, self.fonts(34, True), title, (380, y), col)
                sub = fr["line"] if status == "running" and fr["line"] else note
                if sub: text(self.screen, self.fonts(26), sub, (382, y + 46), (190, 195, 210), maxw=1300)
        elif page == "art":
            pics, mb = fr["art"]
            self.draw_header("Box art", "Set up")
            mid("Download box art for your games?", 380, 44, (255, 255, 255), True)
            mid(f"{pics:,} pictures, about {mb:,} MB. They download in the background while you play.", 470)
            self.draw_hints([("a", "Download"), ("b", "Not now")])
        elif page == "done":
            self.draw_header("Ready", "Set up")
            games = fr.get("added", fr["quick"])
            mid("You're ready to play!", 330, 48, (255, 255, 255), True)
            mid(f"{games:,} games are in your library." if games else "Your library is ready.", 440)
            if fr["tests"]:
                mid(f"{fr['tests']:,} more games are being test-started in the background;", 520)
                mid("they appear as they pass, and you can play meanwhile.", 574)
            if fr.get("want_art"): mid("Box art downloads in the background too.", 654)
            self.draw_hints([("a", "Let's play"), ("b", "Back")])
