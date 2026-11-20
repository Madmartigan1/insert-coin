"""Insert Coin's own box-art folder: the menus read it first, then RetroArch's; --copy-art copies RetroArch's
pictures (never replacing one, never changing RetroArch's folder) and proves every file and every game's
pictures are the same in both."""
import support as S
import hashlib, os, unittest
import paths
from insertcoin import artwork
from insertcoin.app import check_options
from insertcoin.retroarch import thumb_path

OWN, RA_ART = paths.THUMBNAILS, paths.RA_THUMBNAILS
BOX, TITLE, SNAP = "Named_Boxarts", "Named_Titles", "Named_Snaps"
MAME = "MAME 2003-Plus"


def picture(root, system, kind, label, data=b"\x89PNG picture"):
    p = f"{root}/{system}/{kind}/{label}.png"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
    return p


def fingerprint(root):
    """Every file and its bytes' hash: to show a folder wasn't changed."""
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            with open(os.path.join(d, f), "rb") as fh: out[os.path.relpath(os.path.join(d, f), root)] = hashlib.sha1(fh.read()).hexdigest()
    return out


class Reading(unittest.TestCase):
    def setUp(self): S.reset()

    def test_own_folder_first(self):
        theirs = picture(RA_ART, S.NES, BOX, "Star Pilot (USA)")
        self.assertEqual(thumb_path(S.NES + ".lpl", "Star Pilot (USA)", BOX), theirs)     # only RetroArch's has it
        ours = picture(OWN, S.NES, BOX, "Star Pilot (USA)")
        self.assertEqual(thumb_path(S.NES + ".lpl", "Star Pilot (USA)", BOX), ours)

    def test_neither_has_it(self):
        self.assertEqual(thumb_path(S.NES + ".lpl", "Comet Run", BOX), f"{RA_ART}/{S.NES}/{BOX}/Comet Run.png")

    def test_mame_playlists_share_one_folder(self):
        ours = picture(OWN, "MAME", SNAP, "Moon Raiders")
        self.assertEqual(thumb_path(MAME + ".lpl", "Moon Raiders", SNAP), ours)

    def test_names_with_unsafe_characters(self):
        ours = picture(OWN, S.NES, BOX, "Pixel Knights_ Part 2")
        self.assertEqual(thumb_path(S.NES + ".lpl", "Pixel Knights: Part 2", BOX), ours)


class Copying(unittest.TestCase):
    def setUp(self):
        S.reset()
        picture(RA_ART, S.NES, BOX, "Star Pilot (USA)", b"star box")
        picture(RA_ART, S.NES, TITLE, "Star Pilot (USA)", b"star title")
        picture(RA_ART, "MAME", SNAP, "Moon Raiders", b"moon snap")
        os.makedirs(f"{RA_ART}/{S.NES}/{SNAP}", exist_ok=True)                        # an empty folder is fine
        self.before = fingerprint(RA_ART)

    def test_copies_everything_and_checks_clean(self):
        copied, kept, failed = artwork.copy()
        self.assertEqual((copied, kept, failed), (3, 0, []))
        self.assertEqual(fingerprint(OWN), self.before)
        self.assertEqual(artwork.verify(), [])
        self.assertEqual(fingerprint(RA_ART), self.before)                            # RetroArch's untouched

    def test_never_replaces_a_picture(self):
        mine = picture(OWN, S.NES, BOX, "Star Pilot (USA)", b"my own box")
        copied, kept, _ = artwork.copy()
        self.assertEqual((copied, kept), (2, 1))
        with open(mine, "rb") as f: self.assertEqual(f.read(), b"my own box")
        self.assertEqual(artwork.verify(), [(f"{S.NES}/{BOX}/Star Pilot (USA).png", "different")])

    def test_second_run_copies_only_whats_new(self):
        artwork.copy()
        picture(RA_ART, S.NES, SNAP, "Turbo Tanks II (USA)")
        self.assertEqual(artwork.copy()[:2], (1, 3))

    def test_check_finds_missing_and_different(self):
        artwork.copy()
        os.remove(f"{OWN}/MAME/{SNAP}/Moon Raiders.png")
        with open(f"{OWN}/{S.NES}/{TITLE}/Star Pilot (USA).png", "wb") as f: f.write(b"star titlX")  # same size
        self.assertEqual(artwork.verify(), [("MAME/Named_Snaps/Moon Raiders.png", "missing"),
                                            (f"{S.NES}/{TITLE}/Star Pilot (USA).png", "different")])

    def test_leftover_part_files_are_not_pictures(self):
        picture(RA_ART, S.NES, BOX, "Comet Run.png.part")
        os.rename(f"{RA_ART}/{S.NES}/{BOX}/Comet Run.png.part.png", f"{RA_ART}/{S.NES}/{BOX}/Comet Run.png.part")
        self.assertEqual(artwork.copy()[0], 3)

    def test_same_folder(self):
        self.assertFalse(artwork.same_folder(RA_ART, OWN))
        os.makedirs(OWN, exist_ok=True)
        link = f"{S.TMP}/linked"
        os.symlink(OWN, link)
        self.assertTrue(artwork.same_folder(link, OWN))


class EveryGame(unittest.TestCase):
    def setUp(self):
        S.sample_library()
        picture(RA_ART, S.NES, BOX, "Star Pilot (USA)")
        picture(RA_ART, S.NES, SNAP, "Star Pilot (USA)")
        picture(RA_ART, S.NES, BOX, "Turbo Tanks II (USA)")
        picture(RA_ART, "FBNeo - Arcade Games", BOX, "Moon Raiders")
        S.write(paths.LIBRARY, {"version": 1, "systems": [{"name": "Nintendo - Super Nintendo Entertainment System",
                "games": [{"label": "Comet Run (USA)", "path": "/x.sfc", "core": None,
                           "db": "Nintendo - Super Nintendo Entertainment System.lpl"}]}]})
        picture(RA_ART, "Nintendo - Super Nintendo Entertainment System", BOX, "Comet Run (USA)")

    def test_games_from_every_list(self):
        games = artwork.library_games()
        self.assertIn((S.NES + ".lpl", "Star Pilot (USA)"), games)
        self.assertIn(("FBNeo - Arcade Games.lpl", "Moon Raiders"), games)
        self.assertIn(("Nintendo - Super Nintendo Entertainment System.lpl", "Comet Run (USA)"), games)

    def test_every_game_covered_after_the_copy(self):
        artwork.copy()
        cover = artwork.coverage(artwork.library_games())
        self.assertEqual(cover[S.NES][BOX][:2], [2, 2])
        self.assertEqual(cover[S.NES][SNAP][:2], [1, 1])
        self.assertEqual(cover[S.NES][TITLE][:2], [0, 0])                    # no title screens anywhere: fine
        text = artwork.summary(4, 0, [], [], cover)
        self.assertIn("All checks passed", text)
        self.assertIn("box art 4", text)

    def test_a_game_missing_its_picture_is_named(self):
        artwork.copy()
        os.remove(f"{OWN}/{S.NES}/{BOX}/Turbo Tanks II (USA).png")
        cover = artwork.coverage(artwork.library_games())
        self.assertEqual(cover[S.NES][BOX][2], ["Turbo Tanks II (USA)"])
        text = artwork.summary(4, 0, [], [], cover)
        self.assertNotIn("All checks passed", text)
        self.assertIn("Turbo Tanks II (USA)", text)


class Options(unittest.TestCase):
    def test_copy_art_is_an_option(self):
        self.assertIsNone(check_options(["--copy-art"]))
        self.assertIn("--copy-art", check_options(["--help"])[0])


if __name__ == "__main__":
    unittest.main()
