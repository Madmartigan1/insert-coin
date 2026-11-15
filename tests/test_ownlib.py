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



def find(lib, label, sid=S.NES):
    return next(g for s in lib.systems if s["id"] == sid for g in s["games"] if g.label == label)


def labels(lib, sid):
    return [g.label for g in next((s for s in lib.systems if s["id"] == sid), {"games": []})["games"]]


class FavoritesAndHistory(unittest.TestCase):
    """Insert Coin's own lists: copied from RetroArch's once, then kept by Insert Coin and written to both."""
    def setUp(self):
        S.sample_library()
        self.star = S.rom("nes/Star Pilot (USA).zip") + "#Star Pilot (USA).nes"
        self.copy = S.rom("nes/best-of/Star Pilot (USA).zip") + "#Star Pilot (USA).nes"
        S.write(RetroArch.FAVORITES, {"version": "1.5", "items": [
            {"path": self.copy, "label": "Star Pilot (USA)", "core_path": "DETECT", "db_name": S.NES + ".lpl"},
            {"path": f"{S.ROMS}/gone.nes", "label": "Gone", "db_name": S.NES + ".lpl"}]})
        S.write(RetroArch.HISTORY, {"version": "1.5", "items": [
            {"path": f"{S.ROMS}/nes/Turbo Tanks II (USA).nes", "label": "Turbo Tanks II (USA)", "core_path": "DETECT",
             "db_name": S.NES + ".lpl"}]})
        import_retroarch()

    def both(self):
        return Library(source=OwnLibrary()), Library(source=RetroArch())

    def test_copied_from_retroarch_the_first_time(self):
        own, ra = self.both()
        self.assertEqual(dump(own), dump(ra))                               # same Favorites and Recently Played
        self.assertEqual(labels(own, "favorites"), ["Star Pilot (USA)"])
        self.assertTrue(own.is_fav(find(own, "Star Pilot (USA)")))         # any copy counts
        self.assertEqual(len(S.read(paths.FAVORITES)["items"]), 2)           # kept as RetroArch had them, gone or not
        self.assertEqual(S.read(paths.HISTORY)["items"][0]["label"], "Turbo Tanks II (USA)")

    def test_star_and_unstar_written_to_both(self):
        own, ra = self.both()
        g = find(own, "Wavebreaker (USA)")
        self.assertTrue(own.toggle_favorite(g))
        self.assertIn(g.path, [it["path"] for it in S.read(paths.FAVORITES)["items"]])
        self.assertIn(g.path, [it["path"] for it in S.read(RetroArch.FAVORITES)["items"]])
        own.refresh_specials(); ra.refresh_specials()
        self.assertEqual(labels(own, "favorites"), ["Star Pilot (USA)", "Wavebreaker (USA)"])
        self.assertEqual(labels(own, "favorites"), labels(ra, "favorites"))
        self.assertFalse(own.toggle_favorite(find(own, "Star Pilot (USA)")))   # unstarring removes every copy
        own.refresh_specials(); ra.refresh_specials()
        self.assertEqual(labels(own, "favorites"), ["Wavebreaker (USA)"])
        self.assertEqual(labels(ra, "favorites"), ["Wavebreaker (USA)"])

    def test_own_list_is_kept_if_retroarchs_goes(self):
        Library(source=OwnLibrary())
        os.remove(RetroArch.FAVORITES); os.remove(RetroArch.HISTORY)
        own = Library(source=OwnLibrary())
        self.assertEqual(labels(own, "favorites"), ["Star Pilot (USA)"])
        self.assertEqual(labels(own, "recent"), ["Turbo Tanks II (USA)"])
        self.assertFalse(own.toggle_favorite(find(own, "Star Pilot (USA)")))   # and RetroArch's is written again
        self.assertEqual(S.read(RetroArch.FAVORITES)["items"], [])

    def test_history_newest_first_kept_to_200_and_written_to_both(self):
        own, _ = self.both()
        S.write(paths.HISTORY, {"version": 1, "items": [{"label": str(i), "path": f"/r/{i}.nes", "core": None, "db": ""}
                                                        for i in range(250)]})
        a, b = find(own, "Wavebreaker (USA)"), find(own, "Turbo Tanks II (USA)")
        for g in (a, b, a): own.add_history(g)
        items = S.read(paths.HISTORY)["items"]
        self.assertEqual(len(items), 200)
        self.assertEqual([it["label"] for it in items[:2]], ["Wavebreaker (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual([it["label"] for it in S.read(RetroArch.HISTORY)["items"]], ["Wavebreaker (USA)", "Turbo Tanks II (USA)"])
        own.refresh_specials()
        self.assertEqual(labels(own, "recent"), ["Wavebreaker (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual(find(own, "Wavebreaker (USA)", "recent").core, self.mesen_core())

    def test_played_in_retroarch(self):
        """RetroArch writes its own history: only Insert Coin's is added to, and the RetroArch source does nothing."""
        own, ra = self.both()
        before = S.read(RetroArch.HISTORY)
        own.played_in_retroarch(find(own, "Wavebreaker (USA)"))
        ra.played_in_retroarch(find(ra, "Wavebreaker (USA)"))
        self.assertEqual(S.read(RetroArch.HISTORY), before)
        self.assertEqual(S.read(paths.HISTORY)["items"][0]["label"], "Wavebreaker (USA)")

    def test_a_damaged_list_falls_back_and_is_left_alone(self):
        Library(source=OwnLibrary())
        with open(paths.FAVORITES, "w") as f: f.write("[broken")
        kind, source, note = open_source("insertcoin")
        self.assertEqual(kind, "retroarch")
        self.assertIn("couldn't be read", note)
        with open(paths.FAVORITES) as f: self.assertEqual(f.read(), "[broken")

    def mesen_core(self):
        return f"{S.CORES}/mesen_libretro.so"


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
        self.assertEqual(S.read(f"{S.TMP}/config/settings.json")["library"], "insertcoin")
        self.assertIn("imported", app.toast[0])
        self.assertEqual(dump(app.lib), before)
        shown = sum(len(s["games"]) for s in app.lib.systems if not s["special"])
        self.assertLess(shown, 13)                                           # copies hidden: fewer than imported
        self.assertIn(f" - {shown} games (imported", app.toast[0])           # the games it shows, not the entries
        app.accept()                                                         # and back to RetroArch
        self.assertEqual(app.lib_kind, "retroarch")
        self.assertEqual(S.read(f"{S.TMP}/config/settings.json")["library"], "retroarch")
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
