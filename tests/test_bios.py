"""BIOS files (0.6 step 2): the check, Insert Coin's own BIOS folder (a copy of RetroArch's, which is never
changed), and the plain-words message when a game needs a BIOS that's missing."""
import hashlib, os, unittest, zipfile
from unittest import mock
import support as S
import paths
from insertcoin import bios
from insertcoin.games import Game
from insertcoin.launch import after_game

RA_SYS, OWN = f"{S.RA}/system", f"{paths.APPDIR}/system"
GOOD = b"a stand-in BIOS"                                   # its checksum is put in the table for these tests


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f: f.write(data)


def neogeo(path, names):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n in names: z.writestr(n, b"x")


def entry(file): return next(b for b in bios.TABLE if b.file == file)


class Bios(unittest.TestCase):
    def setUp(self):
        S.reset()
        good = hashlib.md5(GOOD).hexdigest()
        self.table = [b._replace(md5=good) if b.md5 else b for b in bios.TABLE]
        p = mock.patch.object(bios, "TABLE", self.table); p.start(); self.addCleanup(p.stop)

    def status(self, folder=RA_SYS):
        return {b.file: (st, note) for b, st, note, _ in bios.check(folder)}

    def test_good_different_and_missing_files(self):
        put(f"{RA_SYS}/gba_bios.bin", GOOD)
        put(f"{RA_SYS}/gb_bios.bin", b"a bad dump")
        put(f"{RA_SYS}/BS-X.bin", b"no checksum known")
        st = self.status()
        self.assertEqual(st["gba_bios.bin"][0], "ok")
        self.assertEqual(st["gb_bios.bin"][0], "different")
        self.assertEqual(st["BS-X.bin"][0], "ok")
        self.assertEqual(st["disksys.rom"][0], "missing")

    def test_the_neo_geo_bios_zip_is_looked_inside(self):
        neogeo(f"{RA_SYS}/fbneo/neogeo.zip", ["000-lo.lo", "sfix.sfix", "sm1.sm1", "sp-s2.sp1"])
        self.assertEqual(self.status()["fbneo/neogeo.zip"][0], "ok")
        neogeo(f"{RA_SYS}/fbneo/neogeo.zip", ["000-lo.lo", "sp-s2.sp1"])
        self.assertEqual(self.status()["fbneo/neogeo.zip"], ("incomplete", "lacks sfix.sfix, sm1.sm1"))
        put(f"{RA_SYS}/fbneo/neogeo.zip", b"not a zip")
        self.assertEqual(self.status()["fbneo/neogeo.zip"][0], "different")
        os.remove(f"{RA_SYS}/fbneo/neogeo.zip")
        neogeo(f"{RA_SYS}/neogeo.zip", ["000-lo.lo", "sfix.sfix", "sm1.sm1", "uni-bios_3_3.rom"])   # top of the folder
        self.assertEqual(self.status()["fbneo/neogeo.zip"][0], "ok")

    def test_own_folder_is_a_copy_and_retroarchs_is_untouched(self):
        put(f"{RA_SYS}/gba_bios.bin", GOOD)
        neogeo(f"{RA_SYS}/fbneo/neogeo.zip", ["000-lo.lo"])
        before = {p: os.stat(p).st_mtime for p in (f"{RA_SYS}/gba_bios.bin", f"{RA_SYS}/fbneo/neogeo.zip")}
        self.assertEqual(bios.set_up_own(RA_SYS, OWN), (2, True))
        with open(f"{OWN}/gba_bios.bin", "rb") as f: self.assertEqual(f.read(), GOOD)
        self.assertTrue(os.path.isfile(f"{OWN}/fbneo/neogeo.zip"))
        put(f"{OWN}/gba_bios.bin", b"the user's own choice")              # Insert Coin's copy changed by the user
        put(f"{RA_SYS}/disksys.rom", GOOD)                                 # RetroArch gets a new file
        self.assertEqual(bios.set_up_own(RA_SYS, OWN), (1, False))         # only the new one
        with open(f"{OWN}/gba_bios.bin", "rb") as f: self.assertEqual(f.read(), b"the user's own choice")
        self.assertTrue(os.path.isfile(f"{OWN}/disksys.rom"))
        self.assertEqual({p: os.stat(p).st_mtime for p in before}, before)
        self.assertEqual(sorted(os.listdir(RA_SYS)), ["disksys.rom", "fbneo", "gba_bios.bin"])

    def test_empty_folders_are_copied_too(self):
        os.makedirs(f"{RA_SYS}/arcade/samples")
        bios.set_up_own(RA_SYS, OWN)
        self.assertTrue(os.path.isdir(f"{OWN}/arcade/samples"))

    def test_summary(self):
        put(f"{RA_SYS}/gb_bios.bin", b"a bad dump")
        text = bios.summary(bios.check(RA_SYS), RA_SYS, 3, True)
        self.assertIn("a copy of RetroArch's (3 files)", text)
        self.assertIn("1 file(s) are not the known good ones", text)
        self.assertIn("Famicom Disk System games (.fds)", text)
        self.assertIn("doesn't download BIOS files", text)
        self.assertIn("  14 files               missing", text)                      # one row for the chip files,
        self.assertIn("\n    (dsp1.data.rom ... st011.program.rom)\n", text)          # their names below it
        for f in ("disksys.rom", "gba_bios.bin", "scph5501.bin"): put(f"{RA_SYS}/{f}", GOOD)
        for b in self.table:
            if b.needed and not b.file.endswith(".zip"): put(f"{RA_SYS}/{b.file}", GOOD)
        put(f"{RA_SYS}/gb_bios.bin", GOOD)
        neogeo(f"{RA_SYS}/fbneo/neogeo.zip", ["000-lo.lo", "sfix.sfix", "sm1.sm1", "sp-s2.sp1"])
        self.assertIn("Everything the games need is there.", bios.summary(bios.check(RA_SYS), RA_SYS))


class AfterGame(unittest.TestCase):
    def setUp(self):
        S.reset()
        self.fds = Game("Moon Raiders", S.rom("fds/Moon Raiders (Japan).zip") + "#Moon Raiders (Japan).fds",
                        f"{S.CORES}/mesen_libretro.so", "x.lpl")
        self.nes = Game("Comet Run", S.rom("nes/Comet Run (USA).nes"), f"{S.CORES}/mesen_libretro.so", "x.lpl")

    def test_a_disk_system_game_without_its_bios(self):
        with mock.patch.object(bios, "SYSTEM", RA_SYS):
            self.assertEqual(after_game(1, False, False, self.fds),
                             "This game needs the Famicom Disk System BIOS (disksys.rom) - see insert-coin --bios")
            put(f"{RA_SYS}/disksys.rom", GOOD)
            self.assertEqual(after_game(1, False, False, self.fds), "The game closed straight away - it may need a different core")
            self.assertEqual(after_game(1, True, False, self.fds), None)               # quit from the menu
            self.assertEqual(after_game(60, False, False, self.nes), None)              # played normally

    def test_finalburn_neo_missing_files(self):
        with mock.patch.object(bios, "SYSTEM", RA_SYS):
            self.assertIn("so is the Neo Geo BIOS", after_game(60, False, True, self.nes))
            neogeo(f"{RA_SYS}/fbneo/neogeo.zip", ["000-lo.lo", "sfix.sfix", "sm1.sm1", "sp-s2.sp1"])
            self.assertEqual(after_game(60, False, True, self.nes), "FinalBurn Neo says some of this game's files are missing")


if __name__ == "__main__":
    unittest.main()
