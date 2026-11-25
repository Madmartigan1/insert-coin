"""Search: words anywhere in a game's name, from every system; the on-screen keyboard and where B goes."""
import os, unittest
from unittest import mock
import support as S
from insertcoin.library import Library, year_range


class Matching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S.sample_library()
        cls.lib = Library(one_per_game=True)

    def labels(self, q): return [g.label for g in self.lib.search(q)]

    def test_a_word_anywhere_in_the_name(self):
        self.assertEqual(self.labels("knights"), ["Pixel Knights, The (Europe)"])
        self.assertEqual(self.labels("raiders"), ["Moon Raiders"])

    def test_the_start_of_a_word_is_enough_while_typing(self):
        self.assertEqual(self.labels("pil"), ["Star Pilot (USA)"])
        self.assertEqual(self.labels("st pi"), ["Star Pilot (USA)"])         # every word must match
        self.assertEqual(self.labels("lot"), [])                              # not the middle of a word

    def test_numbers_and_roman_numerals(self):
        self.assertEqual(self.labels("tanks 2"), ["Turbo Tanks II (USA)"])
        self.assertEqual(self.labels("tanks ii"), ["Turbo Tanks II (USA)"])

    def test_case_and_punctuation_dont_matter(self):
        self.assertEqual(self.labels("TURBO-tanks"), ["Turbo Tanks II (USA)"])

    def test_every_system_a_to_z(self):
        self.assertEqual(self.labels("r"), ["Byte Runner", "Moon Raiders"])    # Homebrew and Arcade, A-Z

    def test_nothing_typed_finds_nothing(self):
        self.assertEqual(self.labels("   "), [])

    def test_versions_stay_together(self):
        star = self.lib.search("star")
        self.assertEqual(len(star), 1)
        self.assertEqual(len(star[0].versions), 4)                           # X still lists them

    def test_show_all_lists_every_rom(self):
        self.assertEqual(len(Library(one_per_game=False).search("star pilot")), 5)


class YearsAndCompanies(unittest.TestCase):
    """A year, a decade or a company typed in the search finds the games released then, or made by it."""
    INFO = {"Star Pilot": [1991, "Fictional Soft", "Comet Works"], "Moon Raiders": [1981, "Arcadia Corp.", ""],
            "Turbo Tanks II": ["1994", "Fictional Soft", ""], "Byte Runner": ["", "", ""]}

    @classmethod
    def setUpClass(cls):
        S.sample_library()
        cls.lib = Library(one_per_game=True)
        cls.lib.info_of = lambda g: cls.INFO.get(g.title)

    def labels(self, q): return [g.label for g in self.lib.search(q)]

    def test_a_year(self):
        self.assertEqual(self.labels("1991"), ["Star Pilot (USA)"])
        self.assertEqual(self.labels("1994"), ["Turbo Tanks II (USA)"])     # years kept as text work too
        self.assertEqual(self.labels("1993"), [])

    def test_a_decade(self):
        self.assertEqual(self.labels("1990s"), ["Star Pilot (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual(self.labels("1980s"), ["Moon Raiders"])

    def test_with_words_of_the_name(self):
        self.assertEqual(self.labels("1991 star"), ["Star Pilot (USA)"])
        self.assertEqual(self.labels("1991 moon"), [])                       # every word must match

    def test_only_whole_years(self):
        self.assertEqual(self.labels("199"), [])                             # still typing: not a year yet
        self.assertEqual(year_range("1991"), (1991, 1991))
        self.assertEqual(year_range("2000s"), (2000, 2009))
        for word in ("199", "19911", "1234", "2"): self.assertIsNone(year_range(word))

    def test_a_publisher_or_a_developer(self):
        self.assertEqual(self.labels("fictional"), ["Star Pilot (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual(self.labels("comet works"), ["Star Pilot (USA)"])    # the developer
        self.assertEqual(self.labels("arcadia"), ["Moon Raiders"])
        self.assertEqual(self.labels("fictional 1994"), ["Turbo Tanks II (USA)"])
        self.assertEqual(self.labels("fictional tanks"), ["Turbo Tanks II (USA)"])

    def test_companies_from_four_letters(self):
        self.assertEqual(self.labels("fic"), [])                             # 3 letters: game names only
        self.assertEqual(self.labels("fict"), ["Star Pilot (USA)", "Turbo Tanks II (USA)"])
        self.assertEqual(self.labels("arcad"), ["Moon Raiders"])
        self.assertEqual(self.labels("ictional"), [])                        # the start of a word, not the middle
        self.assertEqual(self.labels("corp"), ["Moon Raiders"])

    def test_without_anything_known(self):
        self.assertEqual(Library(one_per_game=True).search("1991"), [])
        self.assertEqual(Library(one_per_game=True).search("fictional"), [])

    def test_known_later(self):
        """The databases load in the background: a search before they're read finds them once they are."""
        lib, known = Library(one_per_game=True), {}
        lib.info_of = lambda g: known.get(g.title)
        self.assertEqual(lib.search("fictional"), [])
        known.update(self.INFO)
        self.assertEqual([g.label for g in lib.search("fictional")], ["Star Pilot (USA)", "Turbo Tanks II (USA)"])

class SearchTile(unittest.TestCase):
    def test_kept_on_the_home_screen(self):
        S.sample_library()
        lib = Library(one_per_game=True)
        self.assertEqual(lib.systems[0]["id"], "search")                     # first, before Favorites
        self.assertEqual(lib.systems[0]["games"], [])
        found = lib.set_search("moon")
        self.assertEqual([g.label for g in found], ["Moon Raiders"])
        lib.refresh_specials()                                               # after a game or a favorite
        tile = next(s for s in lib.systems if s["id"] == "search")
        self.assertEqual([g.label for g in tile["games"]], ["Moon Raiders"])
        self.assertEqual(tile["name"], "Search: moon")

    def test_no_tile_without_games(self):
        S.reset()
        self.assertEqual(Library().systems, [])                              # the "no games found" screen stays


class Screen(unittest.TestCase):
    """The search screen driven with pad actions, as the App receives them."""
    def setUp(self):
        S.sample_library()
        import insert_coin as ic
        self.app = ic.App(shot=f"{S.TMP}/shots")
        self.app.style = "xbox"

    def test_years_and_companies_come_from_the_databases(self):
        star = next(g for g in self.app.lib.search("star pilot"))
        with self.app.meta.lock: self.app.meta.data[star.system] = {"n:" + star.label: [1991, "Fictional Soft", "Comet Works"]}
        self.assertEqual([g.label for g in self.app.lib.search("1991")], [star.label])
        self.assertEqual([g.label for g in self.app.lib.search("comet works")], [star.label])
        self.assertEqual(self.app.make_library().info_of, self.app.game_info)     # a new library keeps it

    def press(self, *acts):
        for a in acts: self.app.press(a)

    def test_type_search_play_and_back(self):
        app = self.app
        home = app.si
        self.press("search")                                                 # R3
        self.assertEqual(app.screen_mode, "search")
        app.kpos = (1, 4); self.press("a")                                   # T
        self.press("y", "x", "x")                                            # space, then delete twice
        self.assertEqual(app.q, "")
        for ch in "moon": app.type_key(ch)
        self.assertEqual([g.label for g in app.preview], ["Moon Raiders"])
        self.press("start")
        self.assertEqual((app.screen_mode, app.sys["id"], app.cur_game().label), ("games", "search", "Moon Raiders"))
        self.press("b")                                                      # results -> keyboard, words kept
        self.assertEqual((app.screen_mode, app.q), ("search", "moon"))
        self.press("b")                                                      # keyboard -> home, on the Search tile
        self.assertEqual((app.screen_mode, app.sys["id"]), ("systems", "search"))
        self.assertNotEqual(app.si, home)

    def test_back_returns_where_search_was_opened(self):
        app = self.app
        self.press("a")                                                      # open the first system's games
        sid = app.sys["id"]
        self.press("search", "b")
        self.assertEqual((app.screen_mode, app.sys["id"]), ("games", sid))

    def test_no_match_stays_on_the_keyboard(self):
        app = self.app
        self.press("search")
        for ch in "zzz": app.type_key(ch)
        self.press("start")
        self.assertEqual(app.screen_mode, "search")
        self.assertIn("No games found", app.toast[0])

    def test_keys_wrap_and_rows_line_up(self):
        app = self.app
        self.press("search")
        app.kpos = (1, 0); self.press("left")
        self.assertEqual(app.kpos, (1, 9))                                   # Q -> P
        app.kpos = (1, 9); self.press("down")
        self.assertEqual(app.key_at(*app.kpos), "L")                         # P -> L, the key below
        self.press("down", "down")
        self.assertEqual(app.key_at(*app.kpos), "Search")
        self.press("down")
        self.assertEqual(app.kpos[0], 0)                                     # bottom row -> top row

    def test_browse_the_games_beside_the_keyboard(self):
        app, played = self.app, []
        app.launch = played.append
        self.press("search"); app.type_key("r")                              # Byte Runner, Moon Raiders
        app.kpos = (1, 8); self.press("right")                               # O -> P: still the keyboard
        self.assertFalse(app.in_results)
        self.press("right")                                                  # off the right edge: the games
        self.assertTrue(app.in_results)
        self.assertEqual(app.kpos, (1, 9))                                   # the keyboard keeps its place
        self.press("down")
        self.assertEqual(app.rsel, 1)
        self.press("down", "rb")                                             # stops at the last game
        self.assertEqual(app.rsel, 1)
        self.press("a")
        self.assertEqual([g.label for g in played], ["Moon Raiders"])         # A plays the chosen one
        self.assertEqual((app.screen_mode, app.in_results), ("search", True)) # and comes back to the list
        self.press("lb")
        self.assertEqual(app.rsel, 0)
        self.press("left")                                                   # back to the keyboard, where it was
        self.assertEqual((app.in_results, app.kpos), (False, (1, 9)))
        self.press("right", "b")                                             # B also goes back to the keyboard
        self.assertEqual((app.screen_mode, app.in_results), ("search", False))

    def test_y_stars_a_game_in_the_list(self):
        app = self.app
        self.press("a"); sid = app.sys["id"]                                 # opened from a system's games
        self.press("search"); app.type_key("r")
        app.kpos = (1, 9); self.press("right", "down")                       # Moon Raiders
        g = app.preview[app.rsel]; was = app.lib.is_fav(g)
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):    # RetroArch isn't running
            self.press("y")
            self.assertEqual(app.lib.is_fav(g), not was)
            self.assertEqual((app.screen_mode, app.in_results, app.preview[app.rsel]), ("search", True, g))
            app.draw()                                                       # the star beside it
            self.press("b", "b")                     # keyboard, then where it was opened (the Favorites tile came)
            self.assertEqual((app.screen_mode, app.sys["id"]), ("games", sid))
            self.press("search"); app.type_key("r"); app.kpos = (1, 9); self.press("right", "down")
            self.press("y")
        self.assertEqual(app.lib.is_fav(g), was)

    def test_unstarring_from_a_search_opened_on_favorites(self):
        app = self.app
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1)):
            self.press("search"); app.type_key("r"); app.kpos = (1, 9); self.press("right", "down", "y")
            self.press("b", "b")
            app.si = next(i for i, s in enumerate(app.lib.systems) if s["id"] == "favorites"); app.screen_mode = "systems"
            self.press("search"); app.type_key("r"); app.kpos = (1, 9)
            self.press("right", "down", "y")                                     # the only favorite: the tile goes
        self.assertEqual((app.screen_mode, app.in_results), ("search", True))    # still searching
        self.assertNotIn("favorites", [s["id"] for s in app.lib.systems])
        self.press("b", "b")
        self.assertEqual(app.screen_mode, "systems")
        self.assertLess(app.si, len(app.lib.systems))

    def test_start_opens_the_full_list_at_the_chosen_game(self):
        app = self.app
        self.press("search"); app.type_key("r")
        app.kpos = (2, 8); self.press("right", "down", "start")              # L is the end of its row
        self.assertEqual((app.screen_mode, app.cur_game().label), ("games", "Moon Raiders"))

    def test_typing_starts_the_list_again(self):
        app = self.app
        self.press("search"); app.type_key("r")
        app.kpos = (1, 9); self.press("right", "down")
        app.type_key("a")                                                    # a real keyboard types while on the list
        self.assertEqual((app.in_results, app.rsel), (False, 0))

    def test_no_games_the_keyboard_wraps(self):
        app = self.app
        self.press("search")
        app.kpos = (1, 9); self.press("right")
        self.assertEqual((app.in_results, app.kpos), (False, (1, 0)))        # P -> Q, as before

    def test_drawing_every_state(self):
        app = self.app
        for mode in ("systems", "search"):
            app.screen_mode = mode; app.draw()
        for ch in "moon": app.type_key(ch)
        app.draw(); self.press("start"); app.draw()
        app.style = "keyboard"; self.press("b"); app.draw()
        app.style = "xbox"; app.kpos = (1, 9); self.press("right"); app.draw()   # on the games beside the keyboard
        self.assertTrue(app.in_results)


if __name__ == "__main__":
    unittest.main()
