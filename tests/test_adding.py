"""Adding found games (step 4b): only games that start are added, to Insert Coin's library only; the rest are
listed with the reason, never deleted."""
import os, subprocess, unittest
from unittest import mock
import support as S
import paths
from insertcoin import adding
from insertcoin.retroarch import RetroArch

NES, MAME, N64 = S.NES, "MAME 2003-Plus", "Nintendo - Nintendo 64"


def report():
    """A scan report (as the scanner writes it) with games of every kind."""
    g = lambda rel: S.rom(rel)
    return {"systems": {
        NES: {"listed": 10, "new": [{"path": g("new/Comet Run (USA).zip") + "#Comet Run (USA).nes", "name": "Comet Run (USA)"},
                                    {"path": g("new/Dark Run (USA).nes"), "name": "Dark Run (USA)"}],
              "by_type": [{"path": g("new/Comet Run (Hack).nes"), "name": None}],
              "copies": [{"path": g("new/copy/Star Pilot (USA).nes"), "of": "x"}], "not_games": []},
        MAME: {"listed": 0, "new": [{"path": g("arcade/galaxy.zip"), "name": "Galaxy Run"}],
               "by_type": [], "copies": [], "not_games": []},
        N64: {"listed": 0, "new": [{"path": g("n64/Byte Rally (USA).z64"), "name": "Byte Rally (USA)"}],
              "by_type": [], "copies": [], "not_games": []}}}


class FakeStarts:
    """Stands in for the test start: which (game file, core) pairs start."""
    def __init__(self, fails=()):
        self.fails, self.calls = set(fails), []

    def __call__(self, core, rom, env):
        self.calls.append((os.path.basename(core), os.path.basename(rom)))
        assert env["INSERT_COIN_SAVES"] != paths.SAVES and env["INSERT_COIN_SYSTEM"] != paths.SYSTEM   # a sandbox
        for f in self.fails:
            if f in rom: return False, "black screen for 60 seconds"
        return True, "started"


class Adding(unittest.TestCase):
    def setUp(self):
        S.sample_library()
        self.ra_before = {p: S.read(p) for p in (f"{S.RA}/playlists/{NES}.lpl",)}

    def games(self, system):
        return {g["label"]: g for s in S.read(paths.LIBRARY)["systems"] if s["name"] == system for g in s["games"]}

    def test_adds_games_that_start_and_lists_the_rest(self):
        S.core("mupen64plus_next_libretro.so")                                                  # N64 is test-started too
        r = adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        nes = self.games(NES)
        self.assertIn("Comet Run (USA)", nes); self.assertIn("Comet Run (Hack)", nes)            # name from the file
        self.assertNotIn("Dark Run (USA)", nes)
        self.assertEqual(sum(1 for s in S.read(paths.LIBRARY)["systems"] if s["name"] == NES for g in s["games"]), 10 + 2)
        c = nes["Comet Run (USA)"]
        self.assertEqual((c["core"], c["db"]), (None, f"{NES}.lpl"))                             # the playlist's own core
        self.assertEqual(r["added"], {NES: 2, MAME: 1, N64: 1})
        self.assertIn("Byte Rally (USA)", self.games(N64))
        self.assertEqual({(g["name"], g["why"].split(":")[0]) for g in r["not_added"]},
                         {("Dark Run (USA)", "black screen for 60 seconds")})
        self.assertEqual(len(S.read(adding.NOT_ADDED)["games"]), 1)
        self.assertTrue(os.path.exists(r["backup"]))
        self.assertTrue(os.path.exists(S.rom("new/Dark Run (USA).nes")))                         # never deleted
        self.assertEqual({p: S.read(p) for p in self.ra_before}, self.ra_before)                 # RetroArch's unchanged
        self.assertFalse(os.path.exists(f"{S.RA}/playlists/{MAME}.lpl"))
        self.assertNotIn("galaxy.zip", str(S.read(RetroArch.HISTORY)) if os.path.exists(RetroArch.HISTORY) else "")

    def test_arcade_sets_try_the_other_arcade_cores(self):
        calls = []
        def starter(core, rom, env):
            calls.append(os.path.basename(core))
            return ("fbneo" in core and "galaxy" in rom) or "galaxy" not in rom, "black screen for 60 seconds"
        adding.add_found(report(), starter=starter, workers=1)
        g = self.games(MAME)["Galaxy Run"]
        self.assertEqual(os.path.basename(g["core"]), "fbneo_libretro.so")                     # the core that started it
        self.assertIn("mame2003_plus_libretro.so", calls)                                       # tried first
        self.assertNotIn("mame2003_libretro.so", calls)                                         # not installed: skipped

    def test_the_reason_given_is_the_playlists_own_core(self):
        def starter(core, rom, env):
            if "galaxy" not in rom: return True, "started"
            return False, "missing ROM files" if "mame2003_plus" in core else "could not be loaded: driver not found"
        r = adding.add_found(report(), starter=starter, workers=1)
        why = next(g["why"] for g in r["not_added"] if g["name"] == "Galaxy Run")
        self.assertEqual(why, "missing ROM files (also tried: fbneo)")
        self.assertIn("(core not installed: 1, missing ROM files: 1)", adding.summary(r))   # no N64 core here

    def test_mega_drive_games_get_a_second_core(self):
        S.core("blastem_libretro.so"); S.core("picodrive_libretro.so")
        rep = {"systems": {"Sega - Mega Drive - Genesis": {"listed": 0, "by_type": [], "copies": [], "not_games": [],
               "new": [{"path": S.rom("md/Turbo Tanks (USA).smd"), "name": "Turbo Tanks (USA)"},
                       {"path": S.rom("md/Byte Rally (USA).md"), "name": "Byte Rally (USA)"}]}}}
        calls = []
        def starter(core, rom, env):
            calls.append((os.path.basename(core), os.path.basename(rom)))
            return "picodrive" in core or rom.endswith(".md"), "stopped with an error"
        adding.add_found(rep, starter=starter, workers=1)
        md = self.games("Sega - Mega Drive - Genesis")
        self.assertEqual(os.path.basename(md["Turbo Tanks (USA)"]["core"]), "picodrive_libretro.so")
        self.assertIsNone(md["Byte Rally (USA)"]["core"])                                     # its usual core
        self.assertEqual(calls, [("blastem_libretro.so", "Turbo Tanks (USA).smd"), ("picodrive_libretro.so", "Turbo Tanks (USA).smd"),
                                 ("blastem_libretro.so", "Byte Rally (USA).md")])

    def test_tested_again_when_other_cores_would_be_tried(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        with mock.patch.dict(adding.SECOND_CORES, {NES: ("fbneo_libretro.so",)}):
            again = FakeStarts(fails=["Dark Run"])
            adding.add_found(report(), starter=again, workers=1)
        self.assertEqual(again.calls, [("mesen_libretro.so", "Dark Run (USA).nes")] * 2 + [("fbneo_libretro.so", "Dark Run (USA).nes")] * 2)

    def test_a_black_screen_gets_a_second_start(self):
        calls = []
        def starter(core, rom, env):
            calls.append(os.path.basename(rom))
            second = "Dark Run" in rom and calls.count(os.path.basename(rom)) == 2
            return ("Dark Run" not in rom or second), "black screen for 60 seconds"
        r = adding.add_found(report(), starter=starter, workers=1)
        self.assertEqual(calls.count("Dark Run (USA).nes"), 2)
        self.assertIn("Dark Run (USA)", self.games(NES))
        self.assertEqual(r["added"][NES], 3)

    def test_retry_gives_black_screen_games_more_starts(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)       # black twice: left out
        calls = []
        def starter(core, rom, env):
            calls.append(os.path.basename(rom))
            return calls.count("Dark Run (USA).nes") == 5, "black screen for 60 seconds"
        r = adding.add_found(report(), starter=starter, workers=1, retry=True)
        self.assertEqual(calls, ["Dark Run (USA).nes"] * 5)                     # only the black-screen game, until it starts
        self.assertIn("Dark Run (USA)", self.games(NES))
        self.assertEqual((r["added"], r["retried"]), ({NES: 1}, 1))
        self.assertNotIn("Dark Run (USA)", [g["name"] for g in r["not_added"]])
        self.assertIn("got up to 6 starts", adding.summary(r))

    def test_retry_gives_up_after_the_last_start(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        again = FakeStarts(fails=["Dark Run"])
        r = adding.add_found(report(), starter=again, workers=1, retry=True)
        self.assertEqual(again.calls, [("mesen_libretro.so", "Dark Run (USA).nes")] * adding.RETRY_STARTS)
        self.assertEqual((r["added"], r["backup"]), ({}, None))
        self.assertIn("Dark Run (USA)", [g["name"] for g in r["not_added"]])
        self.assertEqual(adding.add_found(report(), starter=again, workers=1)["started_now"], 0)   # no retry: cached

    def test_games_added_earlier_are_tested_again_when_the_rules_change(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        listed_before = [g for g in self.games(NES).values() if not g.get("added")]
        stricter = FakeStarts(fails=["Dark Run", "Comet Run (USA)"])
        with mock.patch.object(adding, "RULES", adding.RULES + 1):
            r = adding.add_found(report(), starter=stricter, workers=1)
        nes = self.games(NES)
        self.assertNotIn("Comet Run (USA)", nes)                                                # out again
        self.assertIn("Comet Run (Hack)", nes)                                                  # still passes
        self.assertEqual([g for g in nes.values() if not g.get("added")], listed_before)        # yours: untouched
        self.assertEqual(r["taken_out"], {NES: 1})
        self.assertIn("Comet Run (USA)", [g["name"] for g in r["not_added"]])
        self.assertTrue(os.path.exists(r["backup"]))
        self.assertTrue(os.path.exists(S.rom("new/Comet Run (USA).zip")))                       # never deleted
        self.assertIn(("mesen_libretro.so", "Comet Run (Hack).nes"), stricter.calls)            # all re-judged

    def test_a_second_run_tests_nothing_and_adds_nothing_twice(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        before = S.read(paths.LIBRARY)
        again = FakeStarts(fails=["Dark Run"])
        r = adding.add_found(report(), starter=again, workers=1)
        self.assertEqual(again.calls, [])
        self.assertEqual(S.read(paths.LIBRARY), before)
        self.assertEqual((r["added"], r["backup"], len(r["not_added"])), ({}, None, 2))

    def test_a_changed_file_is_tested_again(self):
        adding.add_found(report(), starter=FakeStarts(fails=["Dark Run"]), workers=1)
        p = S.rom("new/Dark Run (USA).nes")
        with open(p, "wb") as f: f.write(b"fixed dump")
        again = FakeStarts()
        r = adding.add_found(report(), starter=again, workers=1)
        self.assertEqual(again.calls, [("mesen_libretro.so", "Dark Run (USA).nes")])
        self.assertEqual(r["added"], {NES: 1})
        self.assertIn("Dark Run (USA)", self.games(NES))

    def test_an_unreadable_library_is_left_alone(self):
        os.makedirs(os.path.dirname(paths.LIBRARY), exist_ok=True)
        with open(paths.LIBRARY, "w") as f: f.write("{ broken")
        with self.assertRaises(ValueError): adding.add_found(report(), starter=FakeStarts(), workers=1)
        with open(paths.LIBRARY) as f: self.assertEqual(f.read(), "{ broken")


class TestStart(unittest.TestCase):
    """How the built-in player's answer is read."""
    def answer(self, out="", rc=0, timeout=False):
        def run(*a, **k):
            if timeout: raise subprocess.TimeoutExpired("engine", 1)
            return subprocess.CompletedProcess(a, rc, out, "")
        with mock.patch.object(adding.subprocess, "run", run): return adding.test_start("core.so", "game.nes", {})

    def test_answers(self):
        self.assertEqual(self.answer("[INFO] Probe: 3 of 120 frames lit\n"), (True, "started"))
        self.assertEqual(self.answer("[INFO] Probe: 0 of 120 frames lit\n"), (False, "black screen for 60 seconds"))
        ok, why = self.answer("[ERROR] Failed to load content: the core could not start this game\n", rc=1)
        self.assertFalse(ok); self.assertTrue(why.startswith("could not be loaded"), why)
        self.assertEqual(self.answer(rc=-11), (False, "crashed (signal 11)"))
        ok, why = self.answer("[ERROR] The player stopped with an error: ValueError()\n", rc=1)
        self.assertTrue(why.startswith("stopped with an error"), why)
        self.assertFalse(self.answer(timeout=True)[0])
        ok, why = self.answer("[ERROR] [FBNeo] ROM at index 3 with name x and CRC 0x1234 is required\n"
                              "[INFO] Probe: 120 of 120 frames lit\n")                         # its error screen
        self.assertEqual((ok, why.split(":")[0]), (False, "missing ROM files"))


if __name__ == "__main__":
    unittest.main()
