"""Insert Coin's own library: imported from RetroArch, the same games, and RetroArch's lists if it can't be read."""
import json, os, unittest
import support as S
import paths
from insertcoin.library import Library
from insertcoin.ownlib import OwnLibrary, import_retroarch, open_source
from insertcoin.retroarch import RetroArch


def dump(lib):
    return {s["id"]: [(g.label, g.path, g.core, g.db, [v.path for v in g.versions] if g.versions else None)
                      for g in s["games"]] for s in lib.systems} | {"hidden": lib.hidden}


class Import(unittest.TestCase):
    def setUp(self):
        self.mesen, self.fbneo = S.sample_library()

    def test_the_same_games_as_retroarchs_playlists(self):
        self.assertEqual(import_retroarch(), 13)                         # 10 NES, 2 arcade, 1 homebrew
        for mode in (True, False):
            self.assertEqual(dump(Library(mode, source=OwnLibrary())), dump(Library(mode, source=RetroArch())))

    def test_stored_as_retroarch_had_it(self):
        import_retroarch()
        doc = S.read(paths.LIBRARY)
        nes = next(s for s in doc["systems"] if s["name"] == S.NES)
        self.assertEqual(nes["default_core"], self.mesen)
        wave = next(g for g in nes["games"] if g["label"] == "Wavebreaker (USA)")
        self.assertEqual(wave["core"], f"{S.CORES}/missing_libretro.so")    # kept, though not installed
        self.assertIsNone(nes["games"][0]["core"])                          # "DETECT": the playlist's default

    def test_cores_are_chosen_when_read(self):
        """A core installed after the import is used, as RetroArch's playlists would."""
        import_retroarch()
        S.core("missing_libretro.so")
        wave = next(g for s in Library(source=OwnLibrary()).systems for g in s["games"] if g.label == "Wavebreaker (USA)")
        self.assertEqual(wave.core, f"{S.CORES}/missing_libretro.so")

    def test_favorites_and_history_still_retroarchs(self):
        import_retroarch()
        lib = Library(source=OwnLibrary())
        g = next(g for s in lib.systems if s["id"] == S.NES for g in s["games"] if g.label == "Wavebreaker (USA)")
        self.assertTrue(lib.toggle_favorite(g))
        self.assertEqual(S.read(RetroArch.FAVORITES)["items"][0]["path"], g.path)
        lib.add_history(g)
        lib.refresh_specials()
        self.assertEqual(next(s for s in lib.systems if s["id"] == "recent")["games"][0].core, self.mesen)


class Choosing(unittest.TestCase):
    def setUp(self):
        S.sample_library()

    def test_retroarch_by_default(self):
        kind, source, note = open_source("retroarch")
        self.assertEqual((kind, note), ("retroarch", None))
        self.assertFalse(os.path.exists(paths.LIBRARY))                      # nothing written

    def test_imported_the_first_time(self):
        kind, source, note = open_source("insertcoin")
        self.assertEqual(kind, "insertcoin")
        self.assertEqual(note, "imported")
        self.assertEqual(open_source("insertcoin")[2], None)                 # the second time: just read

    def test_a_damaged_library_falls_back_to_retroarch(self):
        os.makedirs(os.path.dirname(paths.LIBRARY), exist_ok=True)
        with open(paths.LIBRARY, "w") as f: f.write("{not json")
        kind, source, note = open_source("insertcoin")
        self.assertEqual(kind, "retroarch")
        self.assertIsInstance(source, RetroArch)
        self.assertIn("couldn't be read", note)
        with open(paths.LIBRARY) as f: self.assertEqual(f.read(), "{not json")   # left alone, never overwritten


class MenuSwitch(unittest.TestCase):
    def test_switch_and_back(self):
        S.sample_library()
        import insert_coin as ic
        app = ic.App(shot=f"{S.TMP}/shots")
        before = dump(app.lib)
        app.screen_mode = "quit"; app.quit_sel = app.POWER_MENU.index("Library: RetroArch"); app.accept()
        self.assertEqual(app.lib_kind, "insertcoin")
        self.assertIn("Library: Insert Coin (beta)", app.POWER_MENU)
        self.assertEqual(json.load(open(f"{S.TMP}/config/settings.json"))["library"], "insertcoin")
        self.assertIn("imported", app.toast[0])
        self.assertEqual(dump(app.lib), before)
        shown = sum(len(s["games"]) for s in app.lib.systems if not s["special"])
        self.assertLess(shown, 13)                                           # copies hidden: fewer than imported
        self.assertIn(f" - {shown} games (imported", app.toast[0])           # the games it shows, not the entries
        app.accept()                                                         # and back to RetroArch
        self.assertEqual(app.lib_kind, "retroarch")
        self.assertEqual(json.load(open(f"{S.TMP}/config/settings.json"))["library"], "retroarch")
        app.draw()

    def test_first_switch_in_show_all_counts_entries(self):
        S.sample_library()
        import insert_coin as ic
        app = ic.App(shot=f"{S.TMP}/shots")
        app.screen_mode = "quit"; app.quit_sel = app.POWER_MENU.index("Games: One per game"); app.accept()
        app.quit_sel = app.POWER_MENU.index("Library: RetroArch"); app.accept()
        self.assertIn(" - 13 entries (imported", app.toast[0])


if __name__ == "__main__":
    unittest.main()
