"""RetroArch's button layouts (.rmp) in the built-in player: which file is used, reading it, what each control
then gives the game, and the N64's stick that is only a stick."""
import os, unittest
import support as S
import pygame
import engine
from insertcoin import raremap
from test_states import player

engine.log = lambda level, msg: None
N64 = "Mupen64Plus-Next"
B, Y, START, UP, DOWN, LEFT, RIGHT, A, L2 = engine.B_, engine.Y_, engine.START, engine.UP, engine.DOWN, engine.LEFT, engine.RIGHT, engine.A_, engine.L2

SWAP_STICKS = """input_libretro_device_p1 = "1"
input_player1_analog_dpad_mode = "0"
input_remap_port_p1 = "0"
input_player1_stk_l_x+ = "20"
input_player1_stk_l_x- = "21"
input_player1_stk_l_y+ = "22"
input_player1_stk_l_y- = "23"
input_player1_stk_r_x+ = "16"
input_player1_stk_r_x- = "17"
input_player1_stk_r_y+ = "18"
input_player1_stk_r_y- = "19"
"""


def write(folder, name, text):
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, name)
    with open(p, "w") as f: f.write(text)
    return p


class Pad:
    """A pretend controller: buttons held and stick positions."""
    def __init__(self, buttons=(), axes=None): self.buttons, self.axes = set(buttons), axes or {}
    def get_button(self, b): return b in self.buttons
    def get_axis(self, a): return self.axes.get(a, 0)


class Reading(unittest.TestCase):
    def setUp(self):
        S.reset(); self.dir = f"{S.RA}/config/remaps"

    def test_the_game_file_comes_first_then_the_folder_then_the_core(self):
        core = write(f"{self.dir}/{N64}", f"{N64}.rmp", "")
        self.assertEqual(raremap.find(self.dir, N64, "Byte Rally (USA)", "/games/n64"), core)
        folder = write(f"{self.dir}/{N64}", "n64.rmp", "")
        self.assertEqual(raremap.find(self.dir, N64, "Byte Rally (USA)", "/games/n64"), folder)
        game = write(f"{self.dir}/{N64}", "Byte Rally (USA).rmp", "")
        self.assertEqual(raremap.find(self.dir, N64, "Byte Rally (USA)", "/games/n64"), game)
        self.assertIsNone(raremap.find(self.dir, "Mesen", "Star Pilot (USA)", "/games/nes"))

    def test_reading_a_layout(self):
        p = write(self.dir, "x.rmp", SWAP_STICKS + 'input_player1_btn_y = "0"\ninput_player2_btn_l2 = "-1"\n'
                  'input_player1_btn_b = "0"\ninput_player9_btn_a = "1"\ninput_player1_stk_l3 = "5"\n')
        m = raremap.read(p)
        self.assertEqual(m[0][Y], B)                                        # Y gives B
        self.assertNotIn(B, m[0])                                           # "b gives b": nothing changed
        self.assertEqual(m[0][16], 20)                                      # left stick right -> right stick right
        self.assertEqual(m[1], {L2: raremap.NOTHING})                       # player 2's LT does nothing
        self.assertEqual(set(m), {0, 1})                                    # only players 1-4
        self.assertEqual(len(m[0]), 9)

    def test_older_notes_without_stk_are_read_too(self):
        p = write(self.dir, "x.rmp", 'input_player1_l_x+ = "20"\n')
        self.assertEqual(raremap.read(p), {0: {16: 20}})

    def test_a_layout_that_changes_nothing(self):
        p = write(self.dir, "x.rmp", 'input_libretro_device_p1 = "1"\ninput_remap_port_p1 = "0"\n')
        self.assertEqual(raremap.read(p), {})
        self.assertEqual(raremap.read(f"{self.dir}/missing.rmp"), {})


class Applying(unittest.TestCase):
    def test_swapped_sticks(self):
        m = raremap.read(write(f"{S.TMP}/r", "x.rmp", SWAP_STICKS))[0]
        bits, sticks = raremap.apply(m, 0, [(30000, -12000), (-5000, 20000)])
        self.assertEqual(sticks, [(-5000, 20000), (30000, -12000)])
        self.assertEqual(bits, 0)

    def test_buttons_move_and_turn_off(self):
        bits, _ = raremap.apply({Y: B, L2: raremap.NOTHING}, 1 << Y | 1 << L2 | 1 << START, [(0, 0), (0, 0)])
        self.assertEqual(bits, 1 << B | 1 << START)

    def test_a_button_can_push_a_stick_and_a_stick_press_a_button(self):
        bits, sticks = raremap.apply({A: 20, 16: L2}, 1 << A, [(30000, 0), (0, 0)])
        self.assertEqual(sticks[1][0], raremap.FULL)                        # A pushes the right stick right
        self.assertEqual(sticks[0][0], 0)                                   # the left stick's right no longer moves it
        self.assertTrue(bits >> L2 & 1)                                     # ...it presses L2 instead
        bits, _ = raremap.apply({16: L2}, 0, [(9000, 0), (0, 0)])
        self.assertFalse(bits >> L2 & 1)                                    # pushed only a little: not pressed


class InThePlayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init(); pygame.font.init()

    def n64(self, layout=None, pad=None):
        p = player("mupen64plus_next"); p.name = N64
        p.pads = [(pad or Pad(), "xbox")]; p.press = []; p.fno = 0; p.turbo = False; p.remap = {}
        p.ra_layout = layout or {}; p.stick_dpad = engine.stick_is_dpad(p.core_path)
        return p

    def test_the_n64_stick_is_only_a_stick(self):
        p = self.n64(pad=Pad(axes={pygame.CONTROLLER_AXIS_LEFTX: 30000}))
        p.poll()
        self.assertEqual(p.state(0, engine.DEVICE_ANALOG, 0, 0), 30000)
        self.assertFalse(p.bits[0] >> RIGHT & 1)                            # the d-pad isn't pressed
        p = player("mesen"); p.pads = [(Pad(axes={pygame.CONTROLLER_AXIS_LEFTX: 30000}), "xbox")]
        p.press, p.fno, p.turbo, p.remap, p.ra_layout, p.stick_dpad = [], 0, False, {}, {}, True
        p.poll()
        self.assertTrue(p.bits[0] >> RIGHT & 1)                             # NES: the stick works as the d-pad, as before

    def test_retroarchs_layout_reaches_the_game(self):
        m = raremap.read(write(f"{S.TMP}/r", "x.rmp", SWAP_STICKS))
        p = self.n64(m, Pad(axes={pygame.CONTROLLER_AXIS_LEFTX: 30000, pygame.CONTROLLER_AXIS_RIGHTY: -20000}))
        p.poll()
        self.assertEqual(p.state(0, engine.DEVICE_ANALOG, 1, 0), 30000)    # left stick -> the game's right stick
        self.assertEqual(p.state(0, engine.DEVICE_ANALOG, 0, 1), -20000)   # right stick -> the game's left stick

    def test_the_layout_file_is_found_for_the_game(self):
        S.reset()
        write(f"{S.RA}/config/remaps/{N64}", "Byte Rally (USA).rmp", SWAP_STICKS)
        p = self.n64(); p.game_name = "Byte Rally (USA)"; p.rom = S.rom("n64/Byte Rally (USA).z64")
        p.remap_path = lambda: f"{S.TMP}/no-own-layout.json"
        p.load_remap()
        self.assertEqual(p.ra_layout[0][16], 20)

    def test_the_games_own_layout_comes_first(self):
        S.reset()
        write(f"{S.RA}/config/remaps/{N64}", "Byte Rally (USA).rmp", SWAP_STICKS)
        own = write(f"{S.TMP}/own", "layout.json", '{"map": {"0": 2}}')
        p = self.n64(); p.game_name = "Byte Rally (USA)"; p.rom = S.rom("n64/Byte Rally (USA).z64")
        p.remap_path = lambda: own
        p.load_remap()
        self.assertEqual(p.ra_layout, {})
