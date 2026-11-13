"""The core table: one entry per core, and everything derived from it."""
import unittest
import support  # noqa: F401
from insertcoin.cores import (CORES, DEFAULT_CORE, ENGINE_CORES, core_file, core_short, is_arcade, is_builtin,
                              not_builtin_systems)
from insertcoin.systems import FRIENDLY


class CoreTable(unittest.TestCase):
    def test_built_in_player_cores(self):
        self.assertEqual(len(ENGINE_CORES), 13)
        self.assertIn("mesen_libretro.so", ENGINE_CORES)
        self.assertNotIn("mupen64plus_next_libretro.so", ENGINE_CORES)      # N64 needs the graphics card
        self.assertTrue(is_builtin("/x/cores/fbneo_libretro.so"))
        self.assertFalse(is_builtin(None))

    def test_arcade(self):
        for f in ("fbneo_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so", "fbalpha2012_cps3_libretro.so"):
            self.assertTrue(is_arcade(f"/x/{f}"), f)
        self.assertFalse(is_arcade("/x/mesen_libretro.so", "Mesen"))
        # a core missing from the table is judged by the name it reports
        self.assertTrue(is_arcade("/x/fbalpha2012_cps1_libretro.so", "FB Alpha 2012 CPS-1"))
        self.assertFalse(is_arcade("/x/someother_libretro.so", "Some Console"))

    def test_every_default_system_is_known(self):
        for system, f in DEFAULT_CORE.items():
            self.assertIn(system, FRIENDLY, f)
            self.assertIn(f, CORES)

    def test_one_default_core_per_system(self):
        listed = [s for c in CORES.values() for s in c.systems]
        self.assertEqual(len(listed), len(set(listed)))

    def test_systems_left_to_retroarch(self):
        """What the B menu says when the built-in player is switched on."""
        self.assertEqual(not_builtin_systems(), ["Nintendo 64"])

    def test_names(self):
        self.assertEqual(core_file("/home/me/cores/mesen-s_libretro.so"), "mesen-s_libretro.so")
        self.assertEqual(core_short("/home/me/cores/mesen-s_libretro.so"), "mesen-s")
        self.assertEqual(core_short(None), "")


if __name__ == "__main__":
    unittest.main()
