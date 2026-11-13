"""The library: copies hidden, versions grouped, cores chosen, Favorites and Recently Played kept."""
import os, unittest
import support as S
from insertcoin.games import Game
from insertcoin.library import Library, version_score
from insertcoin.retroarch import RetroArch


def system(lib, sid):
    return next(s for s in lib.systems if s["id"] == sid)


def find(lib, label, sid=S.NES):
    return next(g for g in system(lib, sid)["games"] if g.label == label)


class OnePerGame(unittest.TestCase):
    def setUp(self):
        self.mesen, self.fbneo = S.sample_library()
        self.lib = Library(one_per_game=True)

    def test_systems_in_order_and_empty_ones_hidden(self):
        ids = [s["id"] for s in self.lib.systems]
        self.assertEqual(ids, [S.ARCADE, S.NES, "Homebrew - Console"])     # known systems first, unknown last
        nes = system(self.lib, S.NES)
        self.assertEqual((nes["name"], nes["maker"]), ("NES", "Nintendo"))
        other = system(self.lib, "Homebrew - Console")
        self.assertEqual((other["name"], other["maker"]), ("Console", "Homebrew"))

    def test_copies_hidden_and_versions_grouped(self):
        self.assertEqual(self.lib.hidden, 1)                                 # the "best-of" copy of Star Pilot
        labels = [g.label for g in system(self.lib, S.NES)["games"]]
        self.assertEqual(labels, ["Pixel Knights, The (Europe)", "Star Pilot (USA)", "Turbo Tanks II (USA)", "Wavebreaker (USA)"])
        star = find(self.lib, "Star Pilot (USA)")
        # USA / World first, then Europe, then Japan; translations after the clean dumps
        self.assertEqual([v.label for v in star.versions],
                         ["Star Pilot (USA)", "Star Pilot (Europe)", "Star Pilot (Japan)", "Star Pilot (USA) [T+Ger]"])
        self.assertNotIn("best-of", star.path)                                # the main folder's copy is the one kept
        # the region decides even when the name is longer: Europe before Japan, USA before Europe
        self.assertEqual([v.label for v in find(self.lib, "Pixel Knights, The (Europe)").versions],
                         ["Pixel Knights, The (Europe)", "Pixel Knights (Japan)"])
        rank = lambda label: version_score(Game(label, f"/r/{label}.nes", None, S.NES + ".lpl"), set())
        self.assertLess(rank("Comet Run (USA, Canada)"), rank("Comet Run (Europe)"))
        self.assertLess(rank("Comet Run (Europe) (Rev 1)"), rank("Comet Run (Japan)"))
        self.assertLess(rank("Comet Run (World) (Rev 2)"), rank("Comet Run (USA) [T+Fre]"))   # clean dumps first
        self.assertLess(rank("Comet Run (Japan)"), rank("Comet Run (USA) (Beta)"))
        tanks = find(self.lib, "Turbo Tanks II (USA)")
        self.assertEqual(len(tanks.versions), 2)                             # "Turbo-Tanks 2" is the same game
        self.assertIsNone(find(self.lib, "Wavebreaker (USA)").versions)

    def test_the_version_you_played_comes_first(self):
        os.makedirs(f"{S.RA}/saves/Mesen", exist_ok=True)
        open(f"{S.RA}/saves/Mesen/Star Pilot (Japan).srm", "w").close()
        lib = Library(one_per_game=True)
        star = next(g for g in system(lib, S.NES)["games"] if g.title == "Star Pilot")
        self.assertEqual(star.label, "Star Pilot (Japan)")

    def test_cores(self):
        self.assertEqual(find(self.lib, "Star Pilot (USA)").core, self.mesen)          # the playlist's default
        self.assertEqual(find(self.lib, "Wavebreaker (USA)").core, self.mesen)         # its own core isn't installed
        raiders = find(self.lib, "Moon Raiders", S.ARCADE)
        self.assertEqual([os.path.basename(v.core) for v in raiders.versions],
                         ["fbneo_libretro.so", "mame2003_plus_libretro.so"])          # an entry's own core wins
        self.assertIsNone(find(self.lib, "Byte Runner", "Homebrew - Console").core)    # no core set anywhere

    def test_thumbnail_paths(self):
        g = find(self.lib, "Star Pilot (USA)")
        self.assertEqual(g.thumb("Named_Boxarts"), f"{S.RA}/thumbnails/{S.NES}/Named_Boxarts/Star Pilot (USA).png")


class ShowAll(unittest.TestCase):
    def test_every_rom_as_the_playlists_list_them(self):
        S.sample_library()
        lib = Library(one_per_game=False)
        self.assertEqual(lib.hidden, 0)
        self.assertEqual(len(system(lib, S.NES)["games"]), 10)
        self.assertTrue(all(g.versions is None for g in system(lib, S.NES)["games"]))


class Favorites(unittest.TestCase):
    def setUp(self):
        S.sample_library()
        self.lib = Library(one_per_game=True)

    def test_star_and_unstar(self):
        g = find(self.lib, "Wavebreaker (USA)")
        self.assertFalse(self.lib.is_fav(g))
        self.assertTrue(self.lib.toggle_favorite(g))
        items = S.read(RetroArch.FAVORITES)["items"]
        self.assertEqual(items, [{"path": g.path, "label": "Wavebreaker (USA)", "core_path": g.core, "core_name": "mesen",
                                  "crc32": "00000000|crc", "db_name": S.NES + ".lpl"}])
        self.lib.refresh_specials()
        favs = system(self.lib, "favorites")
        self.assertEqual([x.label for x in favs["games"]], ["Wavebreaker (USA)"])
        self.assertFalse(self.lib.toggle_favorite(g))
        self.assertEqual(S.read(RetroArch.FAVORITES)["items"], [])
        self.lib.refresh_specials()
        self.assertNotIn("favorites", [s["id"] for s in self.lib.systems])

    def test_any_copy_counts(self):
        """Starred in RetroArch on the "best-of" copy: the copy Insert Coin shows is a favorite too."""
        star = find(self.lib, "Star Pilot (USA)")
        copy = S.rom("nes/best-of/Star Pilot (USA).zip") + "#Star Pilot (USA).nes"
        S.write(RetroArch.FAVORITES, {"version": "1.5", "items": [{"path": copy, "label": "Star Pilot (USA)",
                                                                    "db_name": S.NES + ".lpl"}]})
        self.lib.refresh_specials()
        self.assertTrue(self.lib.is_fav(star))
        self.assertFalse(self.lib.toggle_favorite(star))                     # unstarring removes that copy too
        self.assertEqual(S.read(RetroArch.FAVORITES)["items"], [])

    def test_games_whose_file_is_gone_are_left_out(self):
        S.write(RetroArch.FAVORITES, {"version": "1.5", "items": [{"path": f"{S.ROMS}/gone.nes", "label": "Gone"}]})
        self.lib.refresh_specials()
        self.assertNotIn("favorites", [s["id"] for s in self.lib.systems])


class History(unittest.TestCase):
    def test_newest_first_once_each(self):
        S.sample_library()
        lib = Library(one_per_game=True)
        a, b = find(lib, "Wavebreaker (USA)"), find(lib, "Turbo Tanks II (USA)")
        for g in (a, b, a): lib.add_history(g)
        items = S.read(RetroArch.HISTORY)["items"]
        self.assertEqual([it["label"] for it in items], ["Wavebreaker (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual(items[0]["core_name"], "mesen")
        lib.refresh_specials()
        self.assertEqual([g.label for g in system(lib, "recent")["games"]], ["Wavebreaker (USA)", "Turbo Tanks II (USA)"])

    def test_kept_to_200(self):
        S.sample_library()
        lib = Library(one_per_game=True)
        S.write(RetroArch.HISTORY, {"version": "1.5", "items": [{"path": f"/r/{i}.nes", "label": str(i)} for i in range(250)]})
        lib.add_history(find(lib, "Wavebreaker (USA)"))
        items = S.read(RetroArch.HISTORY)["items"]
        self.assertEqual(len(items), 200)
        self.assertEqual(items[0]["label"], "Wavebreaker (USA)")


class BrowserGames(unittest.TestCase):
    def setUp(self):
        S.sample_library()
        folder = f"{S.TMP}/web/comet-dash"
        os.makedirs(folder); open(f"{folder}/index.html", "w").close(); open(f"{folder}/cover.png", "w").close()
        S.write(f"{S.TMP}/config/browser_games.json", {"playlists": [
            {"name": "My Games", "maker": "Made at home", "games": [
                {"title": "Comet Dash", "folder": folder, "boxart": "cover.png", "year": "2026"},
                {"title": "Not There", "folder": f"{S.TMP}/web/missing"}]}]})
        self.lib = Library(one_per_game=True)

    def test_listed_after_the_systems(self):
        self.assertEqual(self.lib.systems[-1]["id"], "web:My Games")
        games = self.lib.systems[-1]["games"]
        self.assertEqual([g.label for g in games], ["Comet Dash"])          # a missing folder is skipped
        g = games[0]
        self.assertEqual(g.thumb("Named_Snaps"), f"{S.TMP}/web/comet-dash/cover.png")   # one image fills in for all
        self.assertEqual(g.info, ["2026", ""])

    def test_favorites_and_recently_played(self):
        web = self.lib.systems[-1]["games"][0]
        self.assertTrue(self.lib.toggle_favorite(web))
        self.assertEqual(S.read(f"{S.TMP}/config/played.json")["favorites"], [web.path])
        a, b = find(self.lib, "Wavebreaker (USA)"), find(self.lib, "Turbo Tanks II (USA)")
        # played: b, then the browser game, then a (RetroArch's history has no times: launches place it)
        self.lib.add_history(b); self.lib.note_launch(b, t=100)
        self.lib.note_launch(web, t=200)
        self.lib.add_history(a); self.lib.note_launch(a, t=300)
        self.lib.refresh_specials()
        self.assertEqual([g.label for g in system(self.lib, "recent")["games"]],
                         ["Wavebreaker (USA)", "Comet Dash", "Turbo Tanks II (USA)"])
        self.assertIn(web, system(self.lib, "favorites")["games"])
        self.assertFalse(os.path.exists(RetroArch.FAVORITES))               # never written into RetroArch's files


if __name__ == "__main__":
    unittest.main()
