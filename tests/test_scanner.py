"""The scanner (step 4a): finds games in the folders, recognises them, compares with the library, changes nothing."""
import os, unittest, zipfile, zlib
import support as S
import paths
from insertcoin import scanner
from insertcoin.meta import _rdb_load
from insertcoin.retroarch import RetroArch

NES, MD, SNES = S.NES, "Sega - Mega Drive - Genesis", "Nintendo - Super Nintendo Entertainment System"


def crc(data): return f"{zlib.crc32(data) & 0xffffffff:08x}"


ROOT = f"{S.TMP}/scan-roms"                                             # its own folder: the sample library's stand-ins are empty


def make_zip(rel, members):
    p = f"{ROOT}/{rel}"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with zipfile.ZipFile(p, "w") as z:
        for name, data in members.items(): z.writestr(name, data)
    return p


def put(rel, data):
    p = f"{ROOT}/{rel}"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data)
    return p


STAR = b"NES\x1a" + b"\x01" * 12 + b"star pilot program" * 100           # an NES ROM: 16-byte header, then the game
ODD = b"NES\x1a" + b"\x07" * 12 + STAR[16:]                             # the same game with an odd header
COMET = b"NES\x1a" + b"\x01" * 12 + b"comet run" * 300
PLAIN = bytes(range(256)) * 128                                         # a Mega Drive game, 32 KB in plain order


def to_smd(plain):
    """The same game as an interleaved .smd file: a 512-byte header, then 16 KB blocks (odd bytes, then even)."""
    out = bytearray(b"\0" * 512)
    for b in range(0, len(plain), 16384):
        blk = plain[b:b + 16384]; out += blk[1::2] + blk[0::2]
    return bytes(out)


class Scan(unittest.TestCase):
    def setUp(self):
        S.sample_library()
        import shutil; shutil.rmtree(ROOT, ignore_errors=True)
        self.listed = make_zip("nes/Star Pilot (USA).zip", {"Star Pilot (USA).nes": STAR})
        make_zip("nes/extra/Star Pilot (USA).zip", {"Star Pilot (USA).nes": STAR})            # a copy
        make_zip("nes/odd/Star Pilot (old).zip", {"Star Pilot (old).nes": ODD})               # a copy, odd header
        make_zip("nes/Comet Run (USA).zip", {"Comet Run (USA).nes": COMET})                    # new
        put("nes/Comet Run (Hack).nes", COMET + b"hack")                                       # by file type
        make_zip("md/Turbo Tanks (USA).zip", {"Turbo Tanks (USA).smd": to_smd(PLAIN)})         # new, as .smd
        put("md/0001 Byte Rally.bin", b"byte rally" * 50)                                      # .bin beside MD games
        make_zip("arcade/moonraid.zip", {"mr1.bin": b"chip1", "mr2.bin": b"chip2"})            # listed set
        make_zip("arcade/# FAVES #/moonraid.zip", {"mr1.bin": b"chip1"})                        # the same set again
        make_zip("arcade/galaxy.zip", {"g1.bin": b"chip"})                                     # new arcade set
        make_zip("arcade/nosuch.zip", {"n1.bin": b"chip"})                                     # a set nobody knows
        make_zip("famicom/galaxy.zip", {"Galaxy (J).nes": COMET + b"g"})                      # console, set-like name
        make_zip("snes/DSP9 (World) (Enhancement Chip).zip", {"DSP9 (World) (Enhancement Chip).sfc": b"dsp" * 100})
        put("snes/Pixel Knights (USA) [h].smc", b"\0" * 512 + b"pixel knights" * 1024)        # copier header
        put("notes/README.md", b"# just text")
        put("broken/Wave (USA).zip", b"not really a zip")
        self.md_listed = put("md/Byte Rally (USA).md", b"byte rally md" * 40)
        self.dbs = ({crc(STAR[16:]): [(NES, "Star Pilot (USA)")], crc(COMET): [(NES, "Comet Run (USA)")],
                     crc(PLAIN): [(MD, "Turbo Tanks (USA)")], crc(b"dsp" * 100): [(SNES, "DSP9 (World) (Enhancement Chip)")],
                     crc(b"pixel knights" * 1024): [(SNES, "Pixel Knights (USA)")]},
                    {"moonraid": ("FBNeo - Arcade Games", "Moon Raiders"), "galaxy": ("MAME 2003-Plus", "Galaxy Run")})
        self.listed_games = [(NES, self.listed + "#Star Pilot (USA).nes"), (MD, self.md_listed),
                             ("MAME 2003-Plus", f"{ROOT}/arcade/moonraid.zip")]   # listed in the other arcade playlist

    def run_scan(self):
        return scanner.scan(roots=[ROOT], dbs=self.dbs, listed=self.listed_games)

    def paths(self, r, sy, kind):
        return sorted(os.path.relpath(x["path"], ROOT) for x in r["systems"].get(sy, scanner._empty())[kind])

    def test_what_it_finds(self):
        r = self.run_scan()
        self.assertEqual(r["systems"][NES]["listed"], 1)
        self.assertEqual(self.paths(r, NES, "copies"), ["nes/extra/Star Pilot (USA).zip#Star Pilot (USA).nes",
                                                       "nes/odd/Star Pilot (old).zip#Star Pilot (old).nes"])
        self.assertEqual(self.paths(r, NES, "new"), ["nes/Comet Run (USA).zip#Comet Run (USA).nes"])
        self.assertEqual(self.paths(r, NES, "by_type"), ["famicom/galaxy.zip#Galaxy (J).nes", "nes/Comet Run (Hack).nes"])
        self.assertEqual([x["name"] for x in r["systems"][MD]["new"]], ["Turbo Tanks (USA)"])          # .smd recognised
        self.assertEqual(self.paths(r, MD, "by_type"), ["md/0001 Byte Rally.bin"])                     # by its folder
        self.assertEqual(self.paths(r, "MAME 2003-Plus", "new"), ["arcade/galaxy.zip"])
        self.assertEqual(self.paths(r, "FBNeo - Arcade Games", "copies"), ["arcade/# FAVES #/moonraid.zip"])   # same set
        self.assertEqual(self.paths(r, "FBNeo - Arcade Games", "new"), [])
        self.assertEqual([x["name"] for x in r["systems"][SNES]["new"]], ["Pixel Knights (USA)"])     # copier header
        self.assertEqual([x["name"] for x in r["systems"][SNES]["not_games"]], ["DSP9 (World) (Enhancement Chip)"])
        self.assertEqual([os.path.relpath(u["path"], ROOT) for u in r["unknown"]], ["arcade/nosuch.zip"])
        self.assertEqual([os.path.relpath(u["path"], ROOT) for u in r["unreadable"]], ["broken/Wave (USA).zip"])
        self.assertNotIn("notes/README.md", str(r))                                                   # text, not a game
        self.assertEqual(S.read(scanner.REPORT)["systems"][NES]["listed"], 1)

    def test_changes_nothing_else(self):
        before = {p: os.path.getmtime(p) for p in (f"{S.RA}/playlists/{NES}.lpl", self.listed)}
        self.run_scan()
        self.assertEqual({p: os.path.getmtime(p) for p in before}, before)
        self.assertFalse(os.path.exists(paths.LIBRARY) or os.path.exists(RetroArch.FAVORITES))
        self.assertEqual(sorted(os.listdir(paths.APPDIR)), ["scan-report.json"])

    def test_a_second_scan_reads_only_what_changed(self):
        self.assertGreater(self.run_scan()["files_read"], 10)
        self.assertEqual(self.run_scan()["files_read"], 0)
        put("nes/Comet Run (Hack).nes", COMET + b"hack 2")
        r = self.run_scan()
        self.assertEqual(r["files_read"], 1)
        self.assertEqual(self.paths(r, NES, "by_type"), ["famicom/galaxy.zip#Galaxy (J).nes", "nes/Comet Run (Hack).nes"])

    def test_roots_from_the_library(self):
        self.assertEqual(scanner.default_roots([f"{ROOT}/nes/a.zip#a.nes", f"{ROOT}/md/b.bin"]), [ROOT])
        home = os.path.expanduser("~")
        self.assertEqual(scanner.default_roots([f"{home}/a/x.nes", f"{home}/b/c/y.nes", f"{home}/b/z.nes"]),
                         [f"{home}/a", f"{home}/b"])


class SecondChecksums(unittest.TestCase):
    def test_smd_back_to_plain_order(self):
        self.assertEqual(scanner.second_checksum(".smd", to_smd(PLAIN)), crc(PLAIN))

    def test_nes_without_header_and_snes_without_copier_header(self):
        self.assertEqual(scanner.second_checksum(".nes", ODD), crc(STAR[16:]))
        self.assertEqual(scanner.second_checksum(".smc", b"\0" * 512 + b"x" * 1024), crc(b"x" * 1024))
        self.assertIsNone(scanner.second_checksum(".smc", b"x" * 1024))
        self.assertIsNone(scanner.second_checksum(".gb", b"x" * 1024))


class Database(unittest.TestCase):
    def test_checksums_read_from_retroarchs_database(self):
        """A tiny .rdb: a header, then one record {name: "Star Pilot", crc: <4 bytes>}."""
        rec = bytes([0x82]) + b"\xa4name" + b"\xaaStar Pilot" + b"\xa3crc" + b"\xc4\x04" + bytes.fromhex("1234abcd")
        p = f"{S.TMP}/test.rdb"
        with open(p, "wb") as f: f.write(b"RARCHDB\0" + b"\0" * 8 + rec + b"\xc0")
        self.assertEqual(_rdb_load(p), [{"name": "Star Pilot", "crc": None}])                 # as before: meta.py
        self.assertEqual(_rdb_load(p, binary=True), [{"name": "Star Pilot", "crc": "1234abcd"}])


if __name__ == "__main__":
    unittest.main()
