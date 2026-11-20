"""Super Nintendo games with a DSP or ST01x chip: the chip is read from the header, and when the chip's files
aren't in the BIOS folder the built-in player runs the game in Snes9x instead of Mesen-S (where it would get stuck)."""
import support  # noqa: F401  (must come first: points HOME etc. at a temp dir)
import os, tempfile, unittest, zipfile
from insertcoin.snes import CHIP_FILES, chip_core, header_chip, rom_data

MESEN_S = "/ra/cores/mesen-s_libretro.so"


def rom(chipset=0x00, hirom=False, subtype=0x00, copier=False, size=0x20000):
    """A blank ROM with a valid header at the LoROM or HiROM place."""
    d = bytearray(size)
    base = 0xFFC0 if hirom else 0x7FC0
    d[base:base + 21] = b"STAR PILOT           "
    d[base + 0x15] = 0x21 if hirom else 0x20
    d[base + 0x16] = chipset
    d[base - 1] = subtype
    checksum = 0x1234
    d[base + 0x1C:base + 0x1E] = (checksum ^ 0xFFFF).to_bytes(2, "little")
    d[base + 0x1E:base + 0x20] = checksum.to_bytes(2, "little")
    return (bytes(512) if copier else b"") + bytes(d)


class Header(unittest.TestCase):
    def test_chips(self):
        self.assertIsNone(header_chip(rom(0x00)))                    # ROM only
        self.assertIsNone(header_chip(rom(0x02)))                    # ROM + RAM + battery
        for cs in (0x03, 0x04, 0x05): self.assertEqual(header_chip(rom(cs)), "DSP")
        self.assertEqual(header_chip(rom(0x05, hirom=True)), "DSP")
        self.assertEqual(header_chip(rom(0xF6, subtype=0x01)), "ST01x")
        self.assertIsNone(header_chip(rom(0xF5, subtype=0x00)))      # another custom chip (SPC7110)
        self.assertIsNone(header_chip(rom(0x13)))                    # Super FX
        self.assertIsNone(header_chip(rom(0x35)))                    # SA-1

    def test_copier_header(self):
        self.assertEqual(header_chip(rom(0x03, copier=True)), "DSP")

    def test_short_or_empty(self):
        self.assertIsNone(header_chip(b""))
        self.assertIsNone(header_chip(bytes(100)))


class Choice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = self.tmp.name
        self.bios, self.own, self.ra = f"{t}/system", f"{t}/cores", f"{t}/ra-cores"
        for d in (self.bios, self.own, self.ra): os.makedirs(d)
        self.dsp = f"{t}/Comet Run.zip"
        with zipfile.ZipFile(self.dsp, "w") as z: z.writestr("Comet Run (USA).sfc", rom(0x03))
        self.plain = f"{t}/Byte Rally.sfc"
        with open(self.plain, "wb") as f: f.write(rom(0x02))

    def tearDown(self): self.tmp.cleanup()

    def choose(self, core, path):
        return chip_core(core, path, folder=self.bios, cores_dir=self.own, ra_cores=self.ra)

    def put(self, folder, name):
        with open(f"{folder}/{name}", "wb") as f: f.write(b"x")

    def test_reads_archives(self):
        self.assertEqual(header_chip(rom_data(self.dsp + "#Comet Run (USA).sfc")), "DSP")
        self.assertEqual(header_chip(rom_data(self.dsp)), "DSP")       # the first ROM in the archive
        self.assertIsNone(rom_data(self.dsp + "#Missing.sfc"))
        self.assertIsNone(rom_data("/nowhere/Galaxy Run.zip"))

    def test_snes9x_when_the_files_are_missing(self):
        self.put(self.own, "snes9x_libretro.so")
        core, chip, note = self.choose(MESEN_S, self.dsp + "#Comet Run (USA).sfc")
        self.assertEqual(core, f"{self.own}/snes9x_libretro.so")
        self.assertEqual(chip, "DSP")
        self.assertIn("Snes9x runs it", note)

    def test_retroarchs_snes9x_too(self):
        self.put(self.ra, "snes9x_libretro.so")
        self.assertEqual(self.choose(MESEN_S, self.dsp)[0], f"{self.ra}/snes9x_libretro.so")

    def test_mesen_s_when_the_files_are_there(self):
        self.put(self.own, "snes9x_libretro.so")
        for f in CHIP_FILES["DSP"]: self.put(self.bios, f)
        core, chip, note = self.choose(MESEN_S, self.dsp)
        self.assertIsNone(core); self.assertEqual(chip, "DSP"); self.assertIn("in the BIOS folder", note)

    def test_some_files_are_not_enough(self):
        self.put(self.own, "snes9x_libretro.so")
        for f in CHIP_FILES["DSP"][:2]: self.put(self.bios, f)
        self.assertIsNotNone(self.choose(MESEN_S, self.dsp)[0])

    def test_no_snes9x(self):
        core, chip, note = self.choose(MESEN_S, self.dsp)
        self.assertIsNone(core); self.assertEqual(chip, "DSP"); self.assertIn("--cores", note)

    def test_other_games_and_cores_unchanged(self):
        self.put(self.own, "snes9x_libretro.so")
        self.assertEqual(self.choose(MESEN_S, self.plain), (None, None, ""))
        self.assertEqual(self.choose("/ra/cores/mesen_libretro.so", self.dsp), (None, None, ""))
        self.assertEqual(self.choose(MESEN_S, "/nowhere/Galaxy Run.sfc"), (None, None, ""))


class Launch(unittest.TestCase):
    """The built-in player is started with Snes9x for a chip game whose files are missing, Mesen-S otherwise."""
    def run_launch(self, chip_answer, engine_on=True):
        from unittest import mock
        from insertcoin import launch
        from insertcoin.games import Game
        calls = []

        class Stub(launch.Launcher):
            settings = {"engine": engine_on}; windowed = False
            sfx = mock.MagicMock(); lib = mock.MagicMock()
            def draw(self): pass
            def splash(self, *a, **k): pass
            def err(self, msg): pass
            def back_from_game(self): pass

        def fake_run(args, **k):
            calls.append(args); return mock.Mock(returncode=0)
        with tempfile.TemporaryDirectory() as t:
            path = f"{t}/Comet Run.zip"
            with zipfile.ZipFile(path, "w") as z: z.writestr("Comet Run.sfc", rom(0x03))
            with mock.patch.object(launch, "chip_core", return_value=chip_answer), \
                 mock.patch.object(launch.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(launch.pygame.display, "quit"):
                Stub().launch(Game("Comet Run", path + "#Comet Run.sfc", MESEN_S, "Nintendo - Super Nintendo Entertainment System"))
        return calls[0]

    def test_snes9x_given_to_the_engine(self):
        args = self.run_launch(("/own/cores/snes9x_libretro.so", "DSP", "DSP chip: Snes9x runs it"))
        self.assertTrue(args[1].endswith("engine.py"))
        self.assertEqual(args[2], "/own/cores/snes9x_libretro.so")

    def test_mesen_s_otherwise(self):
        args = self.run_launch((None, "DSP", "files there"))
        self.assertEqual(args[2], MESEN_S)

    def test_retroarch_keeps_its_core(self):
        args = self.run_launch(("/own/cores/snes9x_libretro.so", "DSP", ""), engine_on=False)
        self.assertEqual(args[0], "retroarch")
        self.assertIn(MESEN_S, args)


if __name__ == "__main__":
    unittest.main()
