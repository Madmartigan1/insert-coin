"""A computer without RetroArch: the settings Insert Coin starts with, an empty library of its own, games added
from a scan straight into it (recognised console games without a test start), cores from Insert Coin's own
folder, and nothing ever written where RetroArch would be."""
import os, shutil, unittest, zipfile
from unittest import mock
import support as S
import paths
from insertcoin import adding, ownlib, settings
from insertcoin.app import check_options
from insertcoin.games import Game

NES, MAME, MD = S.NES, "MAME 2003-Plus", "Sega - Mega Drive - Genesis"


def no_retroarch():
    """A home folder where RetroArch was never installed (nothing under ~/.config/retroarch)."""
    S.reset()
    shutil.rmtree(paths.RA, ignore_errors=True)


def own_cores(*files):
    os.makedirs(paths.CORES_DIR, exist_ok=True)
    for f in files: open(f"{paths.CORES_DIR}/{f}", "a").close()


class FakeStarts:
    def __init__(self, fails=()): self.fails, self.calls = set(fails), []

    def __call__(self, core, rom, env):
        self.calls.append((os.path.basename(core), os.path.basename(rom)))
        return (False, "black screen for 60 seconds") if any(f in rom for f in self.fails) else (True, "started")


def report():
    g = S.rom
    return {"systems": {
        NES: {"listed": 0, "new": [{"path": g("nes/Star Pilot (USA).nes"), "name": "Star Pilot (USA)"},
                                   {"path": g("nes/Comet Dash (USA).nes"), "name": "Comet Dash (USA)"}],
              "by_type": [{"path": g("nes/Star Pilot (Hack).nes"), "name": None},
                          {"path": g("nes/Broken Run (Hack).nes"), "name": None}], "copies": [], "not_games": []},
        MAME: {"listed": 0, "new": [{"path": g("arcade/galaxy.zip"), "name": "Galaxy Run"},
                                    {"path": g("arcade/broken.zip"), "name": "Broken Run"}],
               "by_type": [], "copies": [], "not_games": []}}}


class Settings(unittest.TestCase):
    def test_without_retroarch_the_own_library_and_the_built_in_player(self):
        no_retroarch()
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(settings.retroarch_installed())
            s = settings.load_settings()
        self.assertEqual((s["library"], s["engine"]), ("insertcoin", True))

    def test_with_retroarch_nothing_changes(self):
        S.sample_library()
        with mock.patch("shutil.which", return_value="/usr/bin/retroarch"):
            s = settings.load_settings()
        self.assertEqual((s["library"], s["engine"]), ("retroarch", False))

    def test_saved_settings_still_win(self):
        no_retroarch(); S.write(f"{paths.CONFDIR}/settings.json", {"engine": False})
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(settings.load_settings()["engine"])


class EmptyLibrary(unittest.TestCase):
    def test_an_empty_library_of_its_own(self):
        no_retroarch()
        kind, src, note = ownlib.open_source("insertcoin")
        self.assertEqual((kind, note), ("insertcoin", None))                       # not "imported": nothing to import
        self.assertEqual(src.playlists(), [])
        doc = S.read(paths.LIBRARY)
        self.assertEqual(doc["systems"], []); self.assertNotIn("imported_from", doc)
        self.assertFalse(os.path.exists(paths.RA))                                  # nothing made for RetroArch

    def test_favorites_and_history_never_create_retroarch_files(self):
        no_retroarch(); own_cores("mesen_libretro.so")
        S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": NES, "default_core": f"{paths.CORES_DIR}/mesen_libretro.so",
                "games": [{"label": "Star Pilot (USA)", "path": S.rom("nes/Star Pilot (USA).nes"), "core": None, "db": f"{NES}.lpl"}]}]})
        src = ownlib.OwnLibrary()
        g = Game("Star Pilot (USA)", S.rom("nes/Star Pilot (USA).nes"), f"{paths.CORES_DIR}/mesen_libretro.so", f"{NES}.lpl")
        with self.assertNoLogs(level="WARNING"):
            src.set_favorite(g, True); src.add_history(g)
        self.assertEqual([e.label for e in src.favorites()], ["Star Pilot (USA)"])
        self.assertFalse(os.path.exists(paths.RA))

    def test_a_missing_core_path_falls_back_to_insert_coins_copy(self):
        no_retroarch(); own_cores("mesen_libretro.so", "fbneo_libretro.so")
        S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": NES, "default_core": "/gone/retroarch/cores/mesen_libretro.so",
                "games": [{"label": "Star Pilot (USA)", "path": S.rom("nes/Star Pilot (USA).nes"), "core": None, "db": f"{NES}.lpl"},
                          {"label": "Odd One", "path": S.rom("nes/Odd One.nes"), "core": "/gone/fbneo_libretro.so", "db": f"{NES}.lpl"},
                          {"label": "No Core", "path": S.rom("nes/No Core.nes"), "core": "/gone/nothing_libretro.so", "db": f"{NES}.lpl"}]}]})
        (_, entries), = ownlib.OwnLibrary().playlists()
        cores = {e.label: e.core for e in entries}
        self.assertEqual(cores["Star Pilot (USA)"], f"{paths.CORES_DIR}/mesen_libretro.so")
        self.assertEqual(cores["Odd One"], f"{paths.CORES_DIR}/fbneo_libretro.so")
        self.assertEqual(cores["No Core"], f"{paths.CORES_DIR}/mesen_libretro.so")    # unknown: the playlist's

    def test_with_retroarch_the_core_paths_stay_as_they_were(self):
        S.sample_library()
        ra_core = S.core("mesen_libretro.so"); own_cores("mesen_libretro.so")
        self.assertEqual(ownlib.installed_core(ra_core), ra_core)


class FromScratch(unittest.TestCase):
    def setUp(self):
        no_retroarch(); own_cores("mesen_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so", "fbneo_libretro.so")

    def games(self, system):
        return {g["label"]: g for s in S.read(paths.LIBRARY)["systems"] if s["name"] == system for g in s["games"]}

    def test_recognised_console_games_go_straight_in(self):
        starts = FakeStarts(fails=["Broken", "broken"])
        r = adding.add_found(report(), starter=starts, workers=1)
        nes = self.games(NES)
        self.assertEqual(set(nes), {"Star Pilot (USA)", "Comet Dash (USA)", "Star Pilot (Hack)"})
        started = {rom for _, rom in starts.calls}
        self.assertNotIn("Star Pilot (USA).nes", started); self.assertNotIn("Comet Dash (USA).nes", started)
        self.assertIn("Star Pilot (Hack).nes", started)                                  # known only by type: started
        self.assertIn("galaxy.zip", started)                                             # arcade sets: always started
        self.assertEqual(set(self.games(MAME)), {"Galaxy Run"})
        self.assertEqual({g["name"] for g in r["not_added"]}, {"Broken Run (Hack)", "Broken Run"})
        self.assertEqual(r["recognised"], 2)
        sy = next(s for s in S.read(paths.LIBRARY)["systems"] if s["name"] == NES)
        self.assertEqual(sy["default_core"], f"{paths.CORES_DIR}/mesen_libretro.so")    # Insert Coin's own core
        text = adding.summary(r)
        self.assertIn("2 console games recognised by their checksum went straight in", text)
        self.assertNotIn("RetroArch's playlists", text)                                  # there are none
        self.assertFalse(os.path.exists(paths.RA))

    def test_a_library_with_games_still_tests_everything(self):
        adding.add_found(report(), starter=FakeStarts(), workers=1)
        rep = {"systems": {NES: {"listed": 3, "new": [{"path": S.rom("nes/Moon Raiders (USA).nes"), "name": "Moon Raiders (USA)"}],
                                 "by_type": [], "copies": [], "not_games": []}}}
        starts = FakeStarts()
        r = adding.add_found(rep, starter=starts, workers=1)
        self.assertIn(("mesen_libretro.so", "Moon Raiders (USA).nes"), starts.calls)
        self.assertEqual(r.get("recognised"), 0)

    def test_the_games_open_with_insert_coins_cores(self):
        adding.add_found(report(), starter=FakeStarts(), workers=1)
        playlists = dict(ownlib.OwnLibrary().playlists())
        self.assertTrue(all(e.core and e.core.startswith(paths.CORES_DIR + "/") for es in playlists.values() for e in es))


class UnknownSets(unittest.TestCase):
    def test_a_set_no_database_names_is_tried_under_its_set_name(self):
        rep = {"systems": {MAME: {"listed": 0, "new": [], "by_type": [{"path": S.rom("arcade/oldset.zip"), "name": None}],
                                  "copies": [], "not_games": []}}}
        self.assertEqual(adding.candidates(rep), [(MAME, S.rom("arcade/oldset.zip"), "oldset")])
        self.assertEqual(adding.recognised(rep), set())                                 # never trusted: started

    def test_older_cps3_sets_get_the_cps3_core_last(self):
        for pl in ("MAME 2003-Plus", "FBNeo - Arcade Games"):
            self.assertEqual(adding.ARCADE_CORES[pl][-1], "fbalpha2012_cps3_libretro.so")


class SecondCores(unittest.TestCase):
    def test_super_nintendo_games_get_snes9x_from_insert_coins_folder(self):
        """RetroArch has Mesen-S; Snes9x is only in Insert Coin's folder (--cores downloads it)."""
        S.sample_library(); mesen_s = S.core("mesen-s_libretro.so"); own_cores("snes9x_libretro.so")
        snes = "Nintendo - Super Nintendo Entertainment System"
        self.assertEqual(adding.cores_to_try(snes, {snes: mesen_s}), [mesen_s, f"{paths.CORES_DIR}/snes9x_libretro.so"])


def fbneo_database(*sets):
    """Insert Coin's copy of FBNeo's database, knowing these set names."""
    def st(text): b = text.encode(); return bytes([0xa0 | len(b)]) + b
    recs = b"".join(bytes([0x82]) + st("name") + st(n.title()) + st("rom_name") + st(f"{n}.zip") for n in sets)
    os.makedirs(paths.DATABASES, exist_ok=True)
    with open(f"{paths.DATABASES}/FBNeo - Arcade Games.rdb", "wb") as f: f.write(b"RARCHDB\0" + b"\0" * 8 + recs + b"\xc0")
    adding._fbneo_sets = None


class FBNeoErrorScreen(unittest.TestCase):
    """FBNeo 'starts' a set whose name it doesn't know, showing its own 'Romset is unknown' screen."""
    def setUp(self):
        no_retroarch(); own_cores("mame2003_plus_libretro.so", "mame2003_libretro.so", "fbneo_libretro.so",
                                  "fbalpha2012_cps3_libretro.so")
        fbneo_database("galaxy")
        self.addCleanup(setattr, adding, "_fbneo_sets", None)
        self.rep = {"systems": {MAME: {"listed": 0, "new": [], "copies": [], "not_games": [],
                                       "by_type": [{"path": S.rom("arcade/oldset.zip"), "name": None}]}}}
        self.calls = []

    def only_fbneo_starts(self, core, rom, env):                 # the MAME cores refuse it; FBNeo shows its screen
        self.calls.append(os.path.basename(core))
        return ("fbneo" in core, "started" if "fbneo" in core else "could not be loaded: NOT FOUND")

    def test_fbneo_is_not_asked_about_a_set_it_doesnt_know(self):
        r = adding.add_found(self.rep, starter=self.only_fbneo_starts, workers=1)
        self.assertNotIn("fbneo_libretro.so", self.calls)
        self.assertEqual(r["added"], {})
        self.assertIn("also tried: mame2003, fbneo", r["not_added"][0]["why"])
        self.assertTrue(adding.fbneo_unknown(S.rom("arcade/oldset.zip")))
        self.assertFalse(adding.fbneo_unknown(S.rom("arcade/galaxy.zip")))
        self.assertFalse(adding.fbneo_unknown(S.rom("nes/Star Pilot.zip#Star Pilot.nes")))    # not an arcade set

    def test_games_that_passed_on_that_screen_are_taken_out_again(self):
        adding._fbneo_sets = set()                                # an earlier run: no FBNeo database to ask
        with mock.patch.object(adding, "fbneo_sets", return_value=set()):
            adding.add_found(self.rep, starter=self.only_fbneo_starts, workers=1)
        self.assertIn("oldset", {g["label"] for s in S.read(paths.LIBRARY)["systems"] for g in s["games"]})
        adding._fbneo_sets = None
        r = adding.add_found(self.rep, starter=self.only_fbneo_starts, workers=1)
        self.assertEqual(r["taken_out"], {MAME: 1})
        self.assertNotIn("oldset", {g["label"] for s in S.read(paths.LIBRARY)["systems"] for g in s["games"]})

    def test_without_fbneos_database_nothing_is_skipped(self):
        os.remove(f"{paths.DATABASES}/FBNeo - Arcade Games.rdb"); adding._fbneo_sets = None
        self.assertFalse(adding.fbneo_unknown(S.rom("arcade/oldset.zip")))


class CachedStarts(unittest.TestCase):
    def test_a_core_added_at_the_end_keeps_the_games_that_started(self):
        a, b, c = "/c/mame2003_plus_libretro.so", "/c/fbneo_libretro.so", "/c/fbalpha2012_cps3_libretro.so"
        self.assertTrue(adding.same_tries({"tries": [a, b], "passed": True, "core": b}, [a, b, c]))
        self.assertTrue(adding.same_tries({"tries": [a, b], "passed": False, "core": a}, [a, b]))
        self.assertFalse(adding.same_tries({"tries": [a, b], "passed": False, "core": a}, [a, b, c]))   # failed: try c
        self.assertFalse(adding.same_tries({"tries": [a, b], "passed": True, "core": b}, [b, a]))       # order changed
        self.assertFalse(adding.same_tries({"tries": [a], "passed": True, "core": a}, [c, a]))          # a core before it


@unittest.skipUnless(shutil.which("7z") or shutil.which("7za") or shutil.which("7zz"), "no 7-Zip here")
class OddZips(unittest.TestCase):
    """Zips some old tools wrote, which Python's zip reader refuses ('Corrupt extra field'); the files are fine."""
    def test_the_player_reads_them_with_7zip(self):
        import engine
        p = f"{S.TMP}/oddset.zip"
        zi = zipfile.ZipInfo("chip1.bin"); zi.extra = b"\x22\x3d\xff\x00"         # an extra field that runs past its end
        with zipfile.ZipFile(p, "w") as z: z.writestr(zi, b"chip data")
        with self.assertRaises(zipfile.BadZipFile): zipfile.ZipFile(p)
        self.assertEqual(engine.archive_names(p), ["chip1.bin"])
        self.assertEqual(engine.archive_read(p, "chip1.bin"), b"chip data")


class ScanFolder(unittest.TestCase):
    def test_a_folder_after_scan(self):
        self.assertIsNone(check_options(["--scan", "--add", S.TMP]))
        self.assertIsNone(check_options(["--scan", S.TMP]))
        got = check_options(["--scan", "--add", f"{S.TMP}/not-there"])
        self.assertEqual(got[1], 2); self.assertIn("no such folder", got[0])
        got = check_options(["--cores", S.TMP])                                          # only --scan takes a folder
        self.assertEqual(got[1], 2); self.assertIn("unknown option", got[0])


if __name__ == "__main__":
    unittest.main()
