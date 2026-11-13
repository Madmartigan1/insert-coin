"""Game names: titles, sorting, A-Z letters, versions' keys, archive paths."""
import unittest
import support  # noqa: F401  (throwaway home first)
from insertcoin.names import (clean_title, letter_of, rom_stem, sanitize, sort_key, split_archive, tags,
                              thumb_system, title_key)


class Names(unittest.TestCase):
    def test_clean_title_drops_tags_and_moves_the_article(self):
        self.assertEqual(clean_title("Star Pilot (USA) [!]"), "Star Pilot")
        self.assertEqual(clean_title("Pixel Knights, The (Europe)"), "The Pixel Knights")
        self.assertEqual(clean_title("Legend of Wavebreaker, The - Part Two (Japan)"), "The Legend of Wavebreaker - Part Two")
        self.assertEqual(clean_title("(Prototype)"), "(Prototype)")          # nothing left: keep the label

    def test_tags(self):
        self.assertEqual(tags("Star Pilot (USA, Europe) [T+Ger] (Rev 1)"), ["USA, Europe", "T+Ger", "Rev 1"])

    def test_sorting_ignores_articles_and_punctuation(self):
        self.assertEqual(sort_key("The Pixel Knights (USA)"), "pixel knights")
        self.assertEqual(sort_key("Pixel Knights, The (USA)"), "pixel knights")
        self.assertEqual(sort_key("Turbo-Tanks!"), "turbotanks")

    def test_letters_for_jumping(self):
        self.assertEqual(letter_of("The Pixel Knights"), "P")
        self.assertEqual(letter_of("3000 Skies"), "#")
        self.assertEqual(letter_of("'Lectric Lemon"), "L")

    def test_title_key_matches_spellings_of_the_same_game(self):
        self.assertEqual(title_key("Star Pilot II"), title_key("Star Pilot 2"))
        self.assertEqual(title_key("Turbo-Tanks"), title_key("Turbo Tanks"))
        self.assertEqual(title_key("The Pixel Knights"), title_key("Pixel Knights"))

    def test_archive_paths(self):
        self.assertEqual(split_archive("/r/Star Pilot.zip#Star Pilot (USA).nes"), ("/r/Star Pilot.zip", "Star Pilot (USA).nes"))
        self.assertEqual(split_archive("/r/b.7z#b.sfc"), ("/r/b.7z", "b.sfc"))
        # a '#' in a folder name is not an archive separator
        self.assertEqual(split_archive("/r/# Translations #/Star Pilot.nes"), ("/r/# Translations #/Star Pilot.nes", ""))
        self.assertEqual(split_archive("/r/# Hacks #/a.zip#a.nes"), ("/r/# Hacks #/a.zip", "a.nes"))

    def test_rom_stem_is_the_save_name(self):
        self.assertEqual(rom_stem("/r/a.zip#Star Pilot (USA).nes"), "Star Pilot (USA)")
        self.assertEqual(rom_stem("/r/moonraid.zip"), "moonraid")

    def test_thumbnail_folders(self):
        self.assertEqual(thumb_system("Nintendo - Game Boy.lpl"), "Nintendo - Game Boy")
        self.assertEqual(thumb_system("MAME 2003-Plus.lpl"), "MAME")         # every MAME playlist shares one folder
        self.assertEqual(sanitize('Star: Pilot / "2"?'), "Star_ Pilot _ _2__")


if __name__ == "__main__":
    unittest.main()
