"""Insert Coin's own game databases (--databases): which copy is read, checking and installing a download, keeping
the old copy when a download is bad, and the game info following the copy it was built from."""
import io, json, os, shutil, time, unittest, zipfile
import support as S
import paths
from insertcoin import databases, meta
from insertcoin.games import Game

NES = "Nintendo - Nintendo Entertainment System"


def s(text):
    b = text.encode(); return bytes([0xa0 | len(b)]) + b


def rdb(*games):
    """A small .rdb: one record {name, releaseyear, publisher} per (name, year, publisher)."""
    body = b"".join(bytes([0x83]) + s("name") + s(n) + s("releaseyear") + b"\xcd" + y.to_bytes(2, "big")
                    + s("publisher") + s(p) for n, y, p in games)
    return databases.MAGIC + b"\0" * 8 + body + b"\xc0"


def download_of(files):
    """A fake download: the zip the buildbot would serve, holding these {name: bytes}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items(): z.writestr(name, body)
    return lambda url, progress=None: buf.getvalue()


def full_set(year=1991):
    files = {f"Maker - System {k}.rdb": rdb(("Filler", 1980, "Nobody")) for k in range(60)}
    files[f"{NES}.rdb"] = rdb(("Star Pilot", year, "Pixel Co"))
    files["MAME 2003-Plus.rdb"] = rdb(("Galaxy Run", 1982, "Arcade Co"))
    return files


class WhichCopy(unittest.TestCase):
    def setUp(self):
        S.reset()
        for d in (paths.DATABASES, paths.RA_DATABASES): shutil.rmtree(d, ignore_errors=True)

    def put(self, folder, name, body=b"x"):
        os.makedirs(folder, exist_ok=True)
        with open(f"{folder}/{name}.rdb", "wb") as f: f.write(body)
        return f"{folder}/{name}.rdb"

    def test_both_copies_retroarchs_first(self):
        self.assertEqual(databases.rdb_paths(NES), [])
        own = self.put(paths.DATABASES, NES)
        self.assertEqual(databases.rdb_paths(NES), [own])                                  # no RetroArch: ours alone
        ra = self.put(paths.RA_DATABASES, NES)
        self.assertEqual(databases.rdb_paths(NES), [ra, own])                              # its names come first


class Installing(unittest.TestCase):
    def setUp(self):
        S.reset()
        for d in (paths.DATABASES, paths.RA_DATABASES): shutil.rmtree(d, ignore_errors=True)
        os.makedirs(paths.RA_DATABASES); self.ra_file = f"{paths.RA_DATABASES}/{NES}.rdb"
        with open(self.ra_file, "wb") as f: f.write(rdb(("Star Pilot", 1985, "Old Co")))
        self.ra_before = open(self.ra_file, "rb").read()

    def test_install(self):
        got = []
        info = databases.install(download=lambda url, progress=None: (progress(1, 2), download_of(full_set())(url))[1],
                                 progress=lambda a, b: got.append((a, b)))
        self.assertEqual(got, [(1, 2)])                                                     # progress is passed on
        self.assertEqual(info["files"], 62)
        self.assertEqual(len(os.listdir(paths.DATABASES)), 62)
        self.assertEqual(databases.rdb_paths(NES), [self.ra_file, f"{paths.DATABASES}/{NES}.rdb"])
        with open(databases.MANIFEST) as f: m = json.load(f)
        self.assertEqual(m["from"], databases.URL); self.assertEqual(len(m["sha256"]), 64)
        self.assertEqual(open(self.ra_file, "rb").read(), self.ra_before)                 # RetroArch's: untouched
        self.assertIn("62 downloaded", databases.summary(info))
        self.assertIn("databases are used too, first", databases.summary(info))             # both copies are read
        shutil.rmtree(paths.RA_DATABASES)
        self.assertIn("without RetroArch", databases.summary(info))

    def test_a_second_run_replaces_the_copy(self):
        databases.install(download=download_of(full_set(1991)))
        files = full_set(1992); del files["Maker - System 0.rdb"]
        databases.install(download=download_of(files))
        self.assertFalse(os.path.exists(f"{paths.DATABASES}/Maker - System 0.rdb"))
        self.assertEqual(meta._rdb_load(f"{paths.DATABASES}/{NES}.rdb")[0]["releaseyear"], 1992)
        self.assertFalse(os.path.exists(paths.DATABASES + ".old") or os.path.exists(paths.DATABASES + ".new"))

    def test_bad_downloads_change_nothing(self):
        databases.install(download=download_of(full_set()))
        before = sorted(os.listdir(paths.DATABASES))
        few = {k: v for k, v in list(full_set().items())[:10]}
        not_rdb = dict(full_set()); not_rdb[f"{NES}.rdb"] = b"<html>error page</html>"
        no_nes = dict(full_set()); del no_nes[f"{NES}.rdb"]
        for bad in (lambda url, progress=None: b"<html>not a zip</html>", download_of(few), download_of(not_rdb),
                    download_of(no_nes)):
            with self.assertRaises(databases.DatabaseError): databases.install(download=bad)
            self.assertEqual(sorted(os.listdir(paths.DATABASES)), before)

    def test_only_plain_file_names_are_unpacked(self):
        files = full_set(); files["../escape.rdb"] = rdb(); files["sub/inner.rdb"] = rdb(); files["readme.txt"] = b"hi"
        got = databases.unpack(download_of(files)(""))
        self.assertNotIn("../escape.rdb", got); self.assertNotIn("escape.rdb", got); self.assertNotIn("inner.rdb", got)
        self.assertEqual(len(got), 62)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(paths.DATABASES), "escape.rdb")))


class GameInfo(unittest.TestCase):
    def setUp(self):
        S.reset()
        for d in (paths.DATABASES, paths.RA_DATABASES, f"{paths.CACHE}/meta"): shutil.rmtree(d, ignore_errors=True)
        os.makedirs(paths.RA_DATABASES)
        with open(f"{paths.RA_DATABASES}/{NES}.rdb", "wb") as f: f.write(rdb(("Star Pilot", 1985, "Old Co")))
        self.game = Game("Star Pilot", S.rom("nes/Star Pilot (USA).nes"), "/x/mesen_libretro.so", f"{NES}.lpl")

    def info(self):
        m = meta.Meta([NES])
        for _ in range(200):
            if NES in m.data: break
            time.sleep(0.01)
        return m.get(self.game)

    def test_retroarchs_info_first_ours_fills_the_gaps(self):
        self.assertEqual(self.info()[:2], [1985, "Old Co"])                               # RetroArch's database
        self.assertEqual(self.info()[:2], [1985, "Old Co"])                               # (from the cache)
        files = full_set(1991); files[f"{NES}.rdb"] = rdb(("Star Pilot", 1991, "Pixel Co"), ("Comet Dash", 1987, "Dash Co"))
        databases.install(download=download_of(files))
        self.assertEqual(self.info()[:2], [1985, "Old Co"])                               # nothing known changes
        self.game = Game("Comet Dash", S.rom("nes/Comet Dash (USA).nes"), "/x/mesen_libretro.so", f"{NES}.lpl")
        self.assertEqual(self.info()[:2], [1987, "Dash Co"])                              # a gap filled, at once
        shutil.rmtree(paths.RA_DATABASES)
        self.game = Game("Star Pilot", S.rom("nes/Star Pilot (USA).nes"), "/x/mesen_libretro.so", f"{NES}.lpl")
        self.assertEqual(self.info()[:2], [1991, "Pixel Co"])                             # no RetroArch: ours



class Scanner(unittest.TestCase):
    def test_the_scanner_recognises_games_from_insert_coins_copy(self):
        from insertcoin import scanner
        S.reset()
        for d in (paths.DATABASES, paths.RA_DATABASES): shutil.rmtree(d, ignore_errors=True)
        rec = bytes([0x82]) + s("name") + s("Star Pilot (USA)") + s("crc") + b"\xc4\x04" + bytes.fromhex("1234abcd")
        os.makedirs(paths.DATABASES)
        with open(f"{paths.DATABASES}/{NES}.rdb", "wb") as f: f.write(databases.MAGIC + b"\0" * 8 + rec + b"\xc0")
        by_crc, _ = scanner.load_databases()                                                 # no RetroArch at all
        self.assertEqual(by_crc["1234abcd"], [(NES, "Star Pilot (USA)")])

    def test_both_copies_together(self):
        """A game known to either copy is known; RetroArch's names (all of them) win for one both know."""
        from insertcoin import scanner
        S.reset()
        for d in (paths.DATABASES, paths.RA_DATABASES): shutil.rmtree(d, ignore_errors=True)
        def rec(name, crc): return bytes([0x82]) + s("name") + s(name) + s("crc") + b"\xc4\x04" + bytes.fromhex(crc)
        for d, recs in ((paths.RA_DATABASES, rec("Star Pilot (USA)", "1234abcd") + rec("Star Pilot (USA) (Alt)", "1234abcd")),
                        (paths.DATABASES, rec("Star Pilot (USA) (1990-09-10)", "1234abcd") + rec("Comet Dash (USA)", "0000beef"))):
            os.makedirs(d, exist_ok=True)
            with open(f"{d}/{NES}.rdb", "wb") as f: f.write(databases.MAGIC + b"\0" * 8 + recs + b"\xc0")
        by_crc, _ = scanner.load_databases()
        self.assertEqual(by_crc["1234abcd"], [(NES, "Star Pilot (USA)"), (NES, "Star Pilot (USA) (Alt)")])
        self.assertEqual(by_crc["0000beef"], [(NES, "Comet Dash (USA)")])


if __name__ == "__main__":
    unittest.main()
