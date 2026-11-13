"""Search: words anywhere in a game's name, from every system; the on-screen keyboard and where B goes."""
import os, unittest
import support as S
from insertcoin.library import Library


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

    def test_drawing_every_state(self):
        app = self.app
        for mode in ("systems", "search"):
            app.screen_mode = mode; app.draw()
        for ch in "moon": app.type_key(ch)
        app.draw(); self.press("start"); app.draw()
        app.style = "keyboard"; self.press("b"); app.draw()


if __name__ == "__main__":
    unittest.main()
