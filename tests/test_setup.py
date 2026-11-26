"""First-run setup (1.0 step 3): finding the folders with games, the steps, the background run and its status,
the pad screens and `insert-coin --setup` in a terminal."""
import io, os, shutil, time, unittest
from contextlib import redirect_stdout
from unittest import mock
import support as S
import paths
from insertcoin import adding, bios, setup
from insertcoin.app import check_options

NES, MAME = S.NES, "MAME 2003-Plus"
HOME = f"{S.TMP}/sethome"


def files(folder, names):
    os.makedirs(folder, exist_ok=True)
    for n in names: open(f"{folder}/{n}", "wb").close()


def a_home():
    shutil.rmtree(HOME, ignore_errors=True); shutil.rmtree(f"{S.TMP}/otherdrive", ignore_errors=True)
    files(f"{HOME}/Documents/Retro/nes", [f"Star Pilot {k}.nes" for k in range(10)])
    files(f"{HOME}/Documents/Retro/arcade", [f"set{k}.zip" for k in range(60)])
    files(f"{HOME}/Documents/Retro", ["notes.txt"])
    files(f"{HOME}/Documents/letters", ["a.txt", "b.odt"])
    files(f"{HOME}/Downloads", ["x.zip", "y.zip"])                               # too few to suggest
    files(f"{HOME}/Music/old", [f"pack{k}.zip" for k in range(7)])               # a few archives: shown, not ticked
    files(f"{HOME}/.hidden/roms", [f"Comet {k}.nes" for k in range(20)])         # hidden folders aren't looked in
    files(f"{HOME}/Games/gb", [f"Pixel {k}.gb" for k in range(6)])
    files(f"{HOME}/Games/web", ["index.html"])
    files(f"{S.TMP}/otherdrive/Arcade", [f"set{k}.zip" for k in range(55)])
    os.symlink(f"{S.TMP}/otherdrive/Arcade", f"{HOME}/Arcade")                    # a linked folder on another drive
    os.symlink(HOME, f"{HOME}/Games/loop")                                        # a link loop


class FindingFolders(unittest.TestCase):
    def test_folders_with_games_are_suggested(self):
        a_home()
        got = setup.find_game_folders(roots=[HOME])
        self.assertEqual(got, [(f"{HOME}/Documents/Retro", 70, True), (f"{HOME}/Arcade", 55, True),
                               (f"{HOME}/Music/old", 7, False), (f"{HOME}/Games/gb", 6, True)])

    def test_choosing_in_the_terminal(self):
        found = [("/g/a", 70, True), ("/g/b", 7, False), ("/g/c", 6, True)]
        self.assertEqual(setup.choose_folders(found, ""), (["/g/a", "/g/c"], None))          # Enter: the marked ones
        self.assertEqual(setup.choose_folders(found, "2 1 2"), (["/g/b", "/g/a"], None))
        self.assertEqual(setup.choose_folders(found, S.TMP), ([S.TMP], None))               # a folder typed
        self.assertIn("not a number", setup.choose_folders(found, "9")[1])


class ByHand(unittest.TestCase):
    def test_disks_under_mnt_are_looked_through(self):
        S.reset()
        disk = f"{S.TMP}/mnt-here"; os.makedirs(f"{disk}/games-disk", exist_ok=True)
        real = os.scandir
        with mock.patch("os.scandir", lambda p: real(disk if p == "/mnt" else p)):
            self.assertIn(f"{disk}/games-disk", setup.drives())

    def test_counting_a_folder(self):
        S.reset()
        c = f"{S.TMP}/count"
        files(c, ["a.nes", "b.zip", "notes.txt"]); files(f"{c}/sub", ["c.sfc"]); files(f"{c}/.hidden", ["d.nes"])
        self.assertEqual(setup.count_game_files(f"{S.TMP}/count"), 3)


class Steps(unittest.TestCase):
    def setUp(self):
        S.reset(); shutil.rmtree(bios.OWN_SYSTEM, ignore_errors=True)

    def test_bios_files_found_with_the_games(self):
        files(f"{S.TMP}/g/snes/bios", ["BS-X.bin"])                                     # no checksum known: by name
        with open(f"{S.TMP}/g/gba_bios.bin", "wb") as f: f.write(b"not the real one")   # wrong checksum: left
        self.assertEqual(setup.find_bios([f"{S.TMP}/g"]), ["BS-X.bin"])
        self.assertTrue(os.path.exists(f"{bios.OWN_SYSTEM}/BS-X.bin"))
        self.assertFalse(os.path.exists(f"{bios.OWN_SYSTEM}/gba_bios.bin"))
        self.assertEqual(setup.find_bios([f"{S.TMP}/g"]), [])                            # never replaced

    def report(self):
        return {"systems": {NES: {"listed": 0, "new": [{"path": S.rom("nes/Star Pilot (USA).nes"), "name": "Star Pilot (USA)"}],
                                 "by_type": [{"path": S.rom("nes/Star Pilot (Hack).nes"), "name": None}], "copies": [], "not_games": []},
                            MAME: {"listed": 0, "new": [{"path": S.rom("arcade/galaxy.zip"), "name": "Galaxy Run"}],
                                   "by_type": [], "copies": [], "not_games": []}}}

    def test_recognised_games_go_in_without_a_start(self):
        shutil.rmtree(paths.RA, ignore_errors=True)
        os.makedirs(paths.CORES_DIR, exist_ok=True); open(f"{paths.CORES_DIR}/mesen_libretro.so", "a").close()
        starts = []
        real = adding.add_found
        def add_found(report, **kw):                     # what add_found would test-start goes to a counting starter
            return real(report, starter=lambda core, rom, env: (starts.append(rom), (True, "started"))[1], **kw)
        with mock.patch.object(adding, "add_found", add_found):
            self.assertEqual(setup.add_recognised(self.report()), 1)
            more = self.report(); more["systems"][NES]["new"] = [{"path": S.rom("nes/Comet Dash (USA).nes"), "name": "Comet Dash (USA)"}]
            self.assertEqual(setup.add_recognised(more), 0)                               # not empty now: background
            labels = [g["label"] for s in S.read(paths.LIBRARY)["systems"] for g in s["games"]]
            self.assertEqual(labels, ["Star Pilot (USA)"])
            self.assertEqual(setup.to_test(self.report()), 2)                             # the one added isn't counted
            with mock.patch.object(adding, "recognised", lambda r: {S.rom("nes/Comet Dash (USA).nes")}):
                self.assertEqual(setup.add_recognised(more, fresh=True), 1)               # the library this setup made
        self.assertEqual(starts, [])                                                       # nothing was test-started

    def test_with_retroarch_and_no_library_everything_waits_for_the_background(self):
        S.sample_library()
        if os.path.exists(paths.LIBRARY): os.remove(paths.LIBRARY)
        self.assertEqual(setup.add_recognised(self.report()), 0)
        self.assertFalse(os.path.exists(paths.LIBRARY))

    def test_databases_kept_when_there(self):
        os.makedirs(os.path.dirname(paths.DATABASES), exist_ok=True)
        from insertcoin import databases
        S.write(databases.MANIFEST, {"files": 151})
        with mock.patch.object(databases, "install", side_effect=AssertionError("no download")):
            self.assertEqual(setup.get_databases(), (True, "already there"))
        os.remove(databases.MANIFEST)
        with mock.patch.object(databases, "install", side_effect=OSError("no network")):
            ok, note = setup.get_databases()
        self.assertFalse(ok); self.assertIn("no network", note)


class Background(unittest.TestCase):
    def setUp(self):
        S.reset()
        if os.path.exists(setup.STATUS): os.remove(setup.STATUS)

    def test_the_background_run_reports_its_progress(self):
        seen = []
        def add_found(report, progress=None, **kw):
            progress(1, 2); seen.append(setup.read_status()); progress(2, 2)
            return {"added": {NES: 3}, "not_added": [{}]}
        arts = []
        with mock.patch("insertcoin.scanner.scan", return_value={"systems": {}}), \
             mock.patch.object(adding, "add_found", add_found), \
             mock.patch.object(setup, "get_art", lambda out=None: arts.append(1) or 0):
            setup.finish([S.TMP], art=True)
        self.assertEqual((seen[0]["phase"], seen[0]["n"], seen[0]["total"]), ("tests", 1, 2))
        st = setup.read_status()
        self.assertEqual((st["phase"], st["added"], st["not_added"]), ("done", 3, 1))
        self.assertEqual(len(arts), 2)                                                     # alongside, then for the new ones
        self.assertFalse(setup.running(st))
        self.assertTrue(setup.running({"phase": "tests", "pid": os.getpid()}))
        self.assertFalse(setup.running({"phase": "tests", "pid": 0x7ffffff0}))           # it stopped (closed, crashed)


class Options(unittest.TestCase):
    def test_setup_takes_folders(self):
        self.assertIsNone(check_options(["--setup"]))
        self.assertIsNone(check_options(["--setup", S.TMP]))
        self.assertIn("no such folder", check_options(["--setup", f"{S.TMP}/nothing"])[0])


class Terminal(unittest.TestCase):
    def test_the_whole_setup_in_a_terminal(self):
        S.reset(); a_home()
        calls = []
        rep = {"systems": {NES: {"listed": 0, "new": [], "by_type": [], "copies": [], "not_games": []}},
               "files": 6, "files_read": 6, "took": 0.1, "roots": [f"{HOME}/Games/gb"], "unknown": [], "unreadable": []}
        with mock.patch.object(setup, "find_game_folders", return_value=setup.find_game_folders(roots=[HOME])), \
             mock.patch.object(setup, "get_databases", lambda p=None: (calls.append("db"), (True, "151 downloaded"))[1]), \
             mock.patch.object(setup, "get_cores", lambda p=None: (calls.append("cores"), (True, "16 ready"))[1]), \
             mock.patch.object(setup, "get_bios", lambda f, p=None: (calls.append(("bios", tuple(f))), (True, "3 files"))[1]), \
             mock.patch.object(setup, "find_games", lambda f, p=None: rep), \
             mock.patch.object(setup, "add_recognised", lambda r, p=None: 12), \
             mock.patch.object(setup, "art_estimate", lambda: (40, 5)), \
             mock.patch.object(setup, "get_art", lambda out=None: calls.append("art")):
            answers = iter(["4", "y"])
            out = io.StringIO()
            with redirect_stdout(out): code = setup.terminal([], ask=lambda q: next(answers), interactive=True)
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["db", "cores", ("bios", (f"{HOME}/Games/gb",)), "art"])
        self.assertIn("12 games the databases recognise were added", out.getvalue())
        self.assertIn("* 1. ", out.getvalue()); self.assertIn("    3. ", out.getvalue())   # marked / not marked


class PadScreens(unittest.TestCase):
    def setUp(self):
        S.reset(); shutil.rmtree(paths.RA, ignore_errors=True)
        if os.path.exists(setup.STATUS): os.remove(setup.STATUS)
        import insert_coin as ic
        with mock.patch("shutil.which", return_value=None):
            self.app = ic.App(shot=f"{S.TMP}/shots")
        self.app._thread = lambda target: target()                       # do the work right away
        self.app.style = "xbox"; self.app.start_firstrun()

    def press(self, *acts):
        for a in acts: self.app.press(a); self.app.draw()

    def test_from_welcome_to_playing(self):
        app = self.app
        self.assertEqual((app.screen_mode, app.fr["page"]), ("firstrun", "welcome"))
        app.draw()
        found = [(f"{S.TMP}/a", 70, True), (f"{S.TMP}/b", 7, False)]
        started = []
        def add(report, p=None, fresh=False):
            S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": NES, "default_core": S.core("mesen_libretro.so"),
                    "games": [{"label": "Star Pilot (USA)", "path": S.rom("nes/Star Pilot (USA).nes"), "core": None,
                               "db": f"{NES}.lpl"}]}]})
            return 1
        with mock.patch.object(setup, "find_game_folders", return_value=found), \
             mock.patch.object(setup, "get_databases", lambda p=None: (True, "151 downloaded")), \
             mock.patch.object(setup, "get_cores", lambda p=None: (False, "15 ready; not installed: Stella")), \
             mock.patch.object(setup, "get_bios", lambda f, p=None: (True, "3 files")), \
             mock.patch.object(setup, "find_games", lambda f, p=None: {"systems": {NES: {"listed": 0, "new": [], "by_type": [], "copies": [], "not_games": []}}}), \
             mock.patch.object(setup, "add_recognised", add), mock.patch.object(setup, "to_test", lambda r: 25), \
             mock.patch.object(setup, "art_estimate", lambda: (40, 5)), \
             mock.patch.object(setup, "start_background", lambda f, art=False: started.append((f, art))):
            self.press("a")
            self.assertEqual((app.fr["page"], app.fr["pick"]), ("folders", {0}))     # the likely one is ticked
            self.press("down", "a", "up", "a")                                         # tick the second, untick the first
            self.press("down", "down", "down", "a")                                    # past Choose another folder: Continue
            self.assertEqual(app.fr["folders"], [f"{S.TMP}/b"])
            self.assertEqual(app.fr["page"], "art")
            steps = {k: (st, note) for k, _, st, note in app.fr["steps"]}
            self.assertEqual(steps["cores"], ("failed", "15 ready; not installed: Stella"))
            self.assertEqual(steps["add"][0], "done")
            self.press("a")                                                            # download box art
            self.assertEqual(app.fr["page"], "done")
            self.press("a")
        self.assertEqual(started, [([f"{S.TMP}/b"], True)])
        self.assertEqual(app.screen_mode, "systems")
        self.assertIn(NES, [s["id"] for s in app.lib.systems])
        self.assertEqual(app.settings["library"], "insertcoin")

    def test_nothing_ticked_and_no_folders(self):
        app = self.app
        with mock.patch.object(setup, "find_game_folders", return_value=[(f"{S.TMP}/b", 7, False)]):
            self.press("a", "down", "down", "a")
        self.assertEqual(app.fr["page"], "folders")                                    # nothing ticked: stays
        self.press("b", "b")
        self.assertFalse(app.running if hasattr(app, "running") else False)           # no games: B leaves
        app.start_firstrun()
        with mock.patch.object(setup, "find_game_folders", return_value=[]):
            self.press("a")
        self.assertEqual(app.fr["page"], "nofolders")

    def test_back_from_ready_to_add_a_forgotten_folder(self):
        app = self.app; calls = []
        found = [(f"{S.TMP}/a", 70, True), (f"{S.TMP}/b", 7, False)]
        def add(report, p=None, fresh=False):
            calls.append(fresh); return 10 if len(calls) == 1 else 5
        empty = {"systems": {NES: {"listed": 0, "new": [], "by_type": [], "copies": [], "not_games": []}}}
        with mock.patch.object(setup, "find_game_folders", return_value=found), \
             mock.patch.object(setup, "get_databases", lambda p=None: (True, "")), \
             mock.patch.object(setup, "get_cores", lambda p=None: (True, "")), \
             mock.patch.object(setup, "get_bios", lambda f, p=None: (True, "")), \
             mock.patch.object(setup, "find_games", lambda f, p=None: empty), \
             mock.patch.object(setup, "library_is_empty", side_effect=[True, False]), \
             mock.patch.object(setup, "add_recognised", add), mock.patch.object(setup, "to_test", lambda r: 0), \
             mock.patch.object(setup, "art_estimate", lambda: (0, 0)):
            self.press("a", "down", "down", "down", "a")                               # Continue with the first folder
            self.assertEqual(app.fr["page"], "done")
            self.press("b")                                                            # forgot one: back to the list
            self.assertEqual((app.fr["page"], app.fr["sel"]), ("folders", 2))          # on Choose another folder…
            self.press("up", "a", "down", "down", "a")                                 # tick the second, Continue
            self.assertEqual(app.fr["folders"], [f"{S.TMP}/a", f"{S.TMP}/b"])
            self.assertEqual(app.fr["page"], "done")
        self.assertEqual(calls, [True, True])               # the library this setup made still takes recognised games
        self.assertEqual(app.fr["added"], 15)

    def to_row(self, name):
        """Move the browser's selection onto a folder's row."""
        rows = self.app.browse_rows()
        k = next(i for i, (kind, n) in enumerate(rows) if n == name)
        self.app.fr["bsel"] = 0; self.press(*["down"] * k)

    def test_choosing_a_folder_by_hand(self):
        app = self.app
        games = f"{S.TMP}/Stuff/My Games"
        files(games, [f"Game {k}.nes" for k in range(6)])
        os.makedirs(f"{S.TMP}/Stuff/Empty", exist_ok=True); os.makedirs(f"{S.TMP}/.hidden", exist_ok=True)
        with mock.patch.object(setup, "find_game_folders", return_value=[(f"{S.TMP}/b", 7, False)]):
            self.press("a")
        self.press("down", "a")                                                        # Choose another folder…
        self.assertEqual((app.fr["page"], app.fr["bdir"]), ("browse", paths.HOME))
        self.assertNotIn(".hidden", app.fr["blist"])
        self.to_row("Stuff"); self.press("a")
        self.assertEqual(app.fr["bdir"], f"{S.TMP}/Stuff")
        self.to_row("Empty"); self.press("a")
        self.press("a")                                                                # Use this folder: no games in it
        self.assertEqual(app.fr["page"], "browse")
        self.press("left")                                                             # up, onto the folder it was in
        self.assertEqual((app.fr["bdir"], app.browse_rows()[app.fr["bsel"]][1]), (f"{S.TMP}/Stuff", "Empty"))
        self.to_row("My Games"); self.press("a")
        self.press("a")                                                                # Use this folder
        self.assertEqual(app.fr["page"], "folders")
        self.assertEqual(app.fr["found"][-1], (games, 6, True))
        self.assertEqual((app.fr["pick"], app.fr["sel"]), ({1}, 1))                    # ticked and selected
        self.press("down", "a")                                                        # the same folder again: no new row
        self.assertEqual(app.fr["bdir"], games)                                        # the browser opens where it was
        self.press("a"); self.assertEqual((len(app.fr["found"]), app.fr["pick"]), (2, {1}))
        app._thread = lambda target: None                                              # don't start the real work
        self.press("down", "down", "a")
        self.assertEqual((app.fr["page"], app.fr["folders"]), ("working", [games]))

    def test_no_folders_found_offers_choosing_one(self):
        app = self.app
        with mock.patch.object(setup, "find_game_folders", return_value=[]):
            self.press("a")
            self.assertEqual(app.fr["page"], "nofolders")
            self.press("a"); self.assertEqual(app.fr["page"], "browse")
            self.press("b"); self.assertEqual(app.fr["page"], "nofolders")             # back where it came from
            self.press("y"); self.assertEqual(app.fr["page"], "nofolders")             # looked again
        self.press("a"); self.press("up")
        self.assertEqual(app.browse_rows()[0][0], "use")
        app.browse_to("/"); self.assertNotIn(("up", None), app.browse_rows())          # nothing above the top

    def test_the_background_run_shows_and_its_games_appear(self):
        app = self.app
        S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": NES, "default_core": S.core("mesen_libretro.so"),
                "games": [{"label": "Star Pilot (USA)", "path": S.rom("nes/Star Pilot (USA).nes"), "core": None, "db": f"{NES}.lpl"}]}]})
        app.reload_library(); app.screen_mode = "systems"
        setup.write_status(pid=os.getpid(), phase="tests", n=5, total=25)
        app._bg_next = 0; app.poll_background(); app.draw()
        self.assertEqual(app.bg["n"], 5)
        setup.write_status(pid=os.getpid(), phase="done", added=4, not_added=21)
        app._bg_next = 0; app.poll_background()
        self.assertIsNone(app.bg)
        self.assertIn("4 more games added", app.toast[0])
        self.assertTrue(setup.read_status()["seen"])
        app.toast = None; app._bg_next = 0; app.poll_background()
        self.assertIsNone(app.toast)                                                   # said once

    def test_the_menu_opens_it_again(self):
        app = self.app
        S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": NES, "default_core": S.core("mesen_libretro.so"),
                "games": [{"label": "Star Pilot (USA)", "path": S.rom("nes/Star Pilot (USA).nes"), "core": None, "db": f"{NES}.lpl"}]}]})
        app.reload_library(); app.screen_mode = "quit"
        app.quit_sel = app.POWER_MENU.index("Find games"); self.press("a")
        self.assertEqual((app.screen_mode, app.fr["from_menu"]), ("firstrun", True))
        self.press("b")
        self.assertEqual(app.screen_mode, "systems")                                   # B goes back, not out


if __name__ == "__main__":
    unittest.main()
