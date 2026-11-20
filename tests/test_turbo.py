"""Turbo buttons in the built-in player: on two-button systems, holding LB / RB fires the bottom / right button
rapidly; games that use LB / RB themselves keep them."""
import unittest
import support  # noqa: F401  (sets up a throwaway HOME before anything else is imported)
import engine
from engine import A_, B_, L_, R_, START, X_, Y_, turbo_bits
from insertcoin.cores import has_face_turbo, has_turbo

CORE = "/cores/{}_libretro.so".format
bit = lambda *ids: sum(1 << i for i in ids)


class TurboButtons(unittest.TestCase):
    def frames(self, bits, six=False, n=8, face=False):
        return [turbo_bits(bits, f, six, face) for f in range(n)]

    def test_lb_fires_the_bottom_button_on_and_off(self):
        self.assertEqual(self.frames(bit(L_)), [bit(B_), bit(B_), 0, 0] * 2)          # 2 frames on, 2 off

    def test_rb_fires_the_right_button(self):
        self.assertEqual(self.frames(bit(R_)), [bit(A_), bit(A_), 0, 0] * 2)

    def test_other_buttons_pass_through(self):
        self.assertEqual(self.frames(bit(L_, START, A_)), [bit(B_, START, A_)] * 2 + [bit(START, A_)] * 2 + [bit(B_, START, A_)] * 2 + [bit(START, A_)] * 2)
        self.assertEqual(self.frames(bit(START, A_)), [bit(START, A_)] * 8)          # no LB / RB: unchanged

    def test_six_button_mode_keeps_lb_and_rb(self):
        self.assertEqual(self.frames(bit(L_, R_), six=True), [bit(L_, R_)] * 8)

    def test_pc_engine_face_buttons_are_turbo_too(self):
        self.assertEqual(self.frames(bit(Y_), face=True), [bit(B_), bit(B_), 0, 0] * 2)   # left face: II
        self.assertEqual(self.frames(bit(X_), face=True), [bit(A_), bit(A_), 0, 0] * 2)   # top face: I
        self.assertEqual(self.frames(bit(X_, Y_), face=True, six=True), [bit(X_, Y_)] * 8)   # 6-button: III / IV
        self.assertEqual(self.frames(bit(X_, Y_)), [bit(X_, Y_)] * 8)                  # other systems: plain X / Y
        self.assertTrue(has_face_turbo(CORE("mednafen_supergrafx")))
        self.assertFalse(has_face_turbo(CORE("mesen")))                                 # Mesen's own turbo A / B

    def test_which_games_get_turbo(self):
        self.assertTrue(has_turbo(CORE("mednafen_supergrafx"), ["Star Pilot (USA).pce"]))
        self.assertTrue(has_turbo(CORE("mesen"), ["Comet Run (USA).nes"]))
        self.assertTrue(has_turbo(CORE("vbam"), ["Pixel Knights (USA).gbc"]))
        self.assertTrue(has_turbo(CORE("mednafen_ngp"), ["Moon Raiders (World).ngc"]))
        self.assertFalse(has_turbo(CORE("mesen"), ["Byte Rally (Japan).FDS"]))          # disk switching on LB / RB
        self.assertFalse(has_turbo(CORE("vbam"), ["Galaxy Run (USA).gba"]))             # L and R
        self.assertFalse(has_turbo(CORE("vbam"), ["Galaxy Run.zip", "Galaxy Run (USA).gba"]))   # inside an archive
        self.assertFalse(has_turbo(CORE("stella"), ["Turbo Tanks.a26"]))               # difficulty switches
        self.assertFalse(has_turbo(CORE("snes9x"), ["Dark Run.sfc"]))                   # not a turbo core

    def test_pc_engine_mode_messages(self):
        p = engine.Player.__new__(engine.Player); p.six_button = set()
        engine.Player.core_message(p, "6-button mode selected for pad 2", 3)
        self.assertEqual(p.six_button, {1})
        engine.Player.core_message(p, "2-button mode selected for pad 2", 3)
        self.assertEqual(p.six_button, set())


if __name__ == "__main__":
    unittest.main()
