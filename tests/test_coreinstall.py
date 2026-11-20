"""Insert Coin's own cores (0.6 step 1): copied from RetroArch when it has them, downloaded otherwise, test-loaded
before use; RetroArch's folder is never changed, and the built-in player uses Insert Coin's copies."""
import io, os, shutil, unittest, zipfile
from unittest import mock
import support as S
import paths
from insertcoin import adding, coreinstall
from insertcoin.cores import CORES

WANTED = coreinstall.wanted()


def fake_core(path, name, version="1.0"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write(f"{name}\n{version}")


def text(path):
    with open(path) as f: return f.read()


def checker(path):
    """Stands in for loading a core: a fake core file holds the name and version it reports."""
    try: name, version = text(path).split("\n")
    except (OSError, ValueError): return None
    return name, version


class Downloads:
    def __init__(self, broken=()): self.urls, self.broken = [], set(broken)

    def __call__(self, url):
        self.urls.append(url)
        file = url.rsplit("/", 1)[1][:-4]
        if file in self.broken: raise OSError("connection refused")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z: z.writestr(file, f"{CORES[file].name}\nnightly")
        return buf.getvalue()


class CoreInstall(unittest.TestCase):
    def setUp(self):
        S.reset()
        self.have = WANTED[:3]                                          # RetroArch has these three
        for f in self.have: fake_core(f"{S.CORES}/{f}", CORES[f].name, "tested")
        self.ra = {f: text(f"{S.CORES}/{f}") for f in self.have}
        self.ra_stat = {f: os.stat(f"{S.CORES}/{f}").st_mtime for f in self.have}

    def own(self, f): return f"{paths.CORES_DIR}/{f}"

    def test_copies_retroarchs_cores_and_downloads_the_rest(self):
        dl = Downloads()
        with mock.patch("platform.machine", return_value="x86_64"):
            r = coreinstall.install(checker=checker, download=dl)
        out = {f: how for f, how, _ in r}
        for f in self.have:
            self.assertEqual(out[f], "copied")
            self.assertEqual(text(self.own(f)), self.ra[f])                       # the very same version
        self.assertEqual({f for f, how in out.items() if how == "downloaded"}, set(WANTED) - set(self.have))
        self.assertEqual(len(dl.urls), len(WANTED) - 3)
        self.assertTrue(all(u.startswith("https://buildbot.libretro.com/nightly/linux/x86_64/latest/") for u in dl.urls))
        m = S.read(coreinstall.MANIFEST)
        self.assertEqual(m[self.have[0]]["from"], "RetroArch's copy")
        self.assertEqual(m[self.have[0]]["version"], "tested")
        self.assertEqual({f: text(f"{S.CORES}/{f}") for f in self.have}, self.ra)   # RetroArch's: untouched
        self.assertEqual({f: os.stat(f"{S.CORES}/{f}").st_mtime for f in self.have}, self.ra_stat)
        self.assertEqual(sorted(os.listdir(S.CORES)), sorted(self.have))
        self.assertNotIn("mupen64plus_next_libretro.so", os.listdir(paths.CORES_DIR))  # N64 stays with RetroArch

    def test_a_core_that_doesnt_load_as_itself_is_not_installed(self):
        fake_core(f"{S.CORES}/{self.have[0]}", "Something Else")
        with mock.patch("platform.machine", return_value="x86_64"):
            r = coreinstall.install(checker=checker, download=Downloads(broken=WANTED[3:]))
        out = {f: (how, d) for f, how, d in r}
        self.assertEqual(out[self.have[0]][0], "failed")
        self.assertIn("Something Else", out[self.have[0]][1])
        self.assertFalse(os.path.exists(self.own(self.have[0])))
        self.assertEqual(out[WANTED[3]][0], "failed")                                    # download failed
        self.assertIn("connection refused", out[WANTED[3]][1])
        self.assertEqual([f for f in os.listdir(paths.CORES_DIR) if f.startswith(".")], [])   # no half files
        self.assertIn("Not installed:", coreinstall.summary(r))

    def test_cores_already_there_are_kept(self):
        with mock.patch("platform.machine", return_value="x86_64"):
            coreinstall.install(checker=checker, download=Downloads())
            fake_core(f"{S.CORES}/{self.have[0]}", CORES[self.have[0]].name, "newer")    # RetroArch updated its core
            dl = Downloads()
            r = coreinstall.install(checker=checker, download=dl)
        self.assertEqual({how for _, how, _ in r}, {"kept"})
        self.assertEqual(dl.urls, [])
        self.assertEqual(text(self.own(self.have[0])).split("\n")[1], "tested")    # still the tested one

    def test_a_broken_copy_in_insert_coins_folder_is_reported_not_used_as_good(self):
        fake_core(self.own(self.have[0]), "Something Else")
        with mock.patch("platform.machine", return_value="x86_64"):
            r = coreinstall.install(checker=checker, download=Downloads())
        out = {f: (how, d) for f, how, d in r}
        self.assertEqual(out[self.have[0]][0], "failed")
        self.assertIn("delete it to replace it", out[self.have[0]][1])

    def test_a_download_without_the_core_leaves_nothing_behind(self):
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as z: z.writestr("readme.txt", "nothing here")
        with mock.patch("platform.machine", return_value="x86_64"):
            r = coreinstall.install(checker=checker, download=lambda url: empty.getvalue())
        self.assertEqual({how for f, how, _ in r if f not in self.have}, {"failed"})
        self.assertEqual(sorted(os.listdir(paths.CORES_DIR)), sorted(self.have + ["cores.json"]))

    def test_no_downloads_for_other_machines(self):
        dl = Downloads()
        with mock.patch("platform.machine", return_value="riscv64"):
            r = coreinstall.install(checker=checker, download=dl)
        self.assertEqual(dl.urls, [])
        self.assertEqual({f for f, how, _ in r if how == "copied"}, set(self.have))

    def test_the_built_in_player_uses_insert_coins_copy(self):
        ra = f"{S.CORES}/{self.have[0]}"
        self.assertEqual(coreinstall.own_core(ra), ra)                                   # no copy yet: RetroArch's
        with mock.patch("platform.machine", return_value="x86_64"):
            coreinstall.install(checker=checker, download=Downloads())
        self.assertEqual(coreinstall.own_core(ra), self.own(self.have[0]))
        self.assertEqual(coreinstall.own_core(None), None)

    def test_test_starts_use_insert_coins_copy(self):
        S.sample_library()
        os.makedirs(paths.CORES_DIR, exist_ok=True)
        shutil.copy(f"{S.CORES}/mesen_libretro.so", self.own("mesen_libretro.so"))
        used = []
        def starter(core, rom, env): used.append(core); return True, "started"
        rep = {"systems": {S.NES: {"new": [{"path": S.rom("new/Comet Run (USA).nes"), "name": "Comet Run (USA)"}],
                                   "by_type": []}}}
        adding.add_found(rep, starter=starter, workers=1)
        self.assertEqual(used, [self.own("mesen_libretro.so")])
        lib = {g["label"]: g for s in S.read(paths.LIBRARY)["systems"] for g in s["games"]}
        self.assertIsNone(lib["Comet Run (USA)"]["core"])                                # the library keeps the usual core


if __name__ == "__main__":
    unittest.main()
