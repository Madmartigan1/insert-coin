"""Save states in the built-in player: 4 slots per game with a picture, the pause menu's slot screens, the
overwrite question, cores without states, the hidden start-up run some arcade games need first, the Continue
point, and the picture look chosen per system."""
import ctypes as C, json, os, unittest
import support  # noqa: F401  (sets up a throwaway HOME before anything else is imported)
import pygame
import engine
from engine import Player
from insertcoin.cores import has_states, state_warmup

CORE = "/cores/{}_libretro.so".format
engine.log = lambda level, msg: None                          # keep the test output quiet


class FakeCore:
    """Stands in for a libretro core: its whole 'state' is a counter of the frames it has run."""
    def __init__(self, player, takes_from=0):
        self.p, self.frames, self.takes_from, self.inputs = player, 0, takes_from, []
        self.run_at_load = None

    def retro_serialize_size(self): return 8

    def retro_serialize(self, buf, size):
        C.memmove(buf, self.frames.to_bytes(8, "little"), 8); return True

    def retro_unserialize(self, buf, size):
        self.run_at_load = self.frames
        if self.frames < self.takes_from: return True          # like MAME 2003-Plus: "fine", but nothing happens
        self.frames = int.from_bytes(buf.raw[:8], "little"); return True

    def retro_run(self):
        self.frames += 1
        self.inputs.append(self.p.state(0, engine.DEVICE_JOYPAD, 0, engine.START))
        self.p.batch(b"\0" * 4, 1)


class Sound:
    def __init__(self): self.pushed = 0; self.lock = __import__("threading").Lock(); self.buf = bytearray()
    def push(self, data): self.pushed += 1


def player(core="mesen", takes_from=0, system=None):
    p = Player.__new__(Player)
    p.system, p.scan_cache, p.picture = system, {}, "sharp"
    p.core_path, p.name, p.game_name, p.title = CORE(core), core.title(), "Star Pilot (USA)", None
    p.probe, p.shot, p.frames_left, p.audio, p.rotation, p.frame = False, None, None, None, 0, None
    p.av = engine.AVInfo(); p.av.geometry.aspect_ratio = 4 / 3
    p.screen = pygame.display.set_mode((engine.W, engine.H))
    p.font = lambda n, _c={}: _c.setdefault(n, pygame.font.Font(None, n))
    p.paused = p.combo_down = False; p.mode = "pause"; p.menu_sel = 0; p.style = "xbox"
    p.ran = 0; p.ask_sel = 0; p.warming = False; p.slot_sel = 0; p.slot_action = "save"; p.confirm_sel = 1; p.slot_pics = {}
    p.bits = [1 << engine.START]; p.keymap = None
    p.frame = pygame.Surface((256, 240)); p.frame.fill((200, 40, 40))
    p.lib = FakeCore(p, takes_from)
    return p


def choose(p, item):
    p.set_pause(True); p.menu_sel = p.MENU.index(item); p.menu_key("ok")


class Slots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init(); pygame.font.init()

    def run_frames(self, p, n):
        for _ in range(n): p.step()

    def test_save_and_load_give_the_moment_back(self):
        p = player(); self.run_frames(p, 100)
        self.assertTrue(p.save_state(1))
        self.assertTrue(os.path.exists(p.state_path(1)))
        self.assertTrue(os.path.exists(p.state_path(1)[:-6] + ".png"))        # the slot's picture
        self.assertTrue(p.state_path(1).endswith("/Mesen/Star Pilot (USA).slot1.state"))
        self.run_frames(p, 50)
        self.assertTrue(p.load_state(1))
        self.assertEqual(p.lib.frames, 100)
        self.assertFalse(p.load_state(3))                                      # an empty slot: nothing happens
        self.assertEqual(p.lib.frames, 100)

    def test_menu_has_save_and_load(self):
        self.assertEqual(player().MENU, ("Resume", "Save state", "Load state", "Picture", "Quit game"))
        self.assertEqual(player("fbneo").MENU, ("Resume", "Save state", "Load state", "Picture", "Controls", "Quit game"))

    def test_saving_in_an_empty_slot_needs_no_question(self):
        p = player("pcsx_rearmed"); self.run_frames(p, 10)
        choose(p, "Save state"); self.assertEqual(p.mode, "slots")
        p.menu_key("right"); p.menu_key("down")                                # slot 4
        p.menu_key("ok")
        self.assertEqual(p.mode, "pause"); self.assertTrue(p.paused)
        self.assertIsNotNone(p.slot_time(4)); self.assertIn("slot 4", p.osd[0])

    def test_a_used_slot_asks_first_and_keeps_it_by_default(self):
        p = player("stella"); self.run_frames(p, 10); p.save_state(2)
        self.run_frames(p, 10)
        choose(p, "Save state"); p.menu_key("right"); p.menu_key("ok")
        self.assertEqual(p.mode, "confirm"); self.assertEqual(p.confirm_sel, 1)   # "Keep it" chosen first
        p.menu_key("ok")
        self.assertEqual(p.mode, "slots")
        p.load_state(2); self.assertEqual(p.lib.frames, 10)                       # the old state is still there
        self.run_frames(p, 5)
        p.menu_key("ok"); p.menu_key("left"); p.menu_key("ok")                    # now "Replace"
        self.assertEqual(p.mode, "pause")
        p.load_state(2); self.assertEqual(p.lib.frames, 15)

    def test_back_leaves_the_question_and_the_slots(self):
        p = player("vbam"); p.save_state(1)
        choose(p, "Save state"); p.menu_key("ok"); p.menu_key("back")
        self.assertEqual(p.mode, "slots"); p.menu_key("back")
        self.assertEqual(p.mode, "pause"); self.assertTrue(p.paused)

    def test_loading_resumes_the_game(self):
        p = player("blastem"); self.run_frames(p, 30); p.save_state(3); self.run_frames(p, 30)
        choose(p, "Load state"); self.assertEqual(p.slot_action, "load")
        p.menu_key("ok")                                                          # slot 1 is empty
        self.assertTrue(p.paused); self.assertIn("empty", p.osd[0])
        p.menu_key("down"); p.menu_key("ok")                                      # slot 3
        self.assertFalse(p.paused); self.assertEqual(p.lib.frames, 30)

    def test_slot_screen_and_question_draw(self):
        p = player(); p.save_state(1)
        for style in ("xbox", "playstation", "nintendo", "keyboard"):
            p.style = style; choose(p, "Save state"); p.draw_menu()
            p.menu_key("ok"); p.draw_menu(); p.menu_key("back")
        p.style = "playstation"; self.assertEqual(p.menu_buttons(), ("✕", "○"))
        p.style = "nintendo"; self.assertEqual(p.menu_buttons(), ("A", "B"))
        p.style = "xbox"; self.assertEqual(p.menu_buttons(), ("A", "B"))
        p.style = "keyboard"; self.assertEqual(p.menu_buttons(), ("Enter", "Esc"))


class CoresWithoutStates(unittest.TestCase):
    def test_cps3_offers_no_states(self):
        self.assertFalse(has_states(CORE("fbalpha2012_cps3")))
        self.assertTrue(has_states(CORE("mesen")))
        self.assertTrue(has_states(CORE("some_new_core")))                        # not in the table: try
        p = player("fbalpha2012_cps3")
        choose(p, "Save state")
        self.assertEqual(p.mode, "pause"); self.assertIn("aren't available", p.osd[0])
        self.assertFalse(os.path.exists(os.path.dirname(p.state_path(1))))


class StartUpFirst(unittest.TestCase):
    def test_mame_runs_its_start_up_before_a_state_is_loaded(self):
        self.assertEqual(state_warmup(CORE("mame2003_plus")), 1800)
        p = player("mame2003_plus", takes_from=1800)
        p.lib.frames = 2500; p.save_state(1)
        p = player("mame2003_plus", takes_from=1800); p.audio = Sound()          # a new session
        for _ in range(13): p.step()
        self.assertTrue(p.load_state(1))
        self.assertEqual(p.lib.run_at_load, 1800)                                 # ran the rest of the start-up first
        self.assertEqual(p.lib.frames, 2500)                                       # ...so the state took
        self.assertEqual(p.lib.inputs[13:], [0] * (1800 - 13))                      # no buttons while hidden
        self.assertEqual(p.audio.pushed, 13)                                       # and no sound
        self.assertFalse(p.warming)

    def test_no_extra_run_later_in_the_game_or_on_other_cores(self):
        p = player("mame2003_plus", takes_from=1800); p.lib.frames = 2500; p.save_state(2)
        p.ran = 1900; p.load_state(2); self.assertEqual(p.lib.run_at_load, 2500)
        p = player("mesen"); p.save_state(2); p.load_state(2)
        self.assertEqual(p.lib.run_at_load, 0)


class ContinuePoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init(); pygame.font.init()

    def quit_after(self, p, frames):
        p.lib.frames = frames; return p.keep_continue(frames)

    def test_quitting_keeps_a_continue_point(self):
        p = player("picodrive")
        self.assertFalse(self.quit_after(p, 300))                              # a few seconds: nothing kept
        self.assertIsNone(p.slot_time("continue"))
        self.assertTrue(self.quit_after(p, 5000))
        self.assertTrue(p.state_path("continue").endswith("/Star Pilot (USA).continue.state"))
        self.assertTrue(os.path.exists(p.state_path("continue")[:-6] + ".png"))
        self.assertIsNone(p.slot_time(1))                                      # not one of the 4 slots

    def test_test_runs_keep_nothing(self):
        for attr, value in (("probe", True), ("shot", "x.png"), ("frames_left", 1500)):
            p = player("mednafen_ngp"); setattr(p, attr, value)
            self.assertFalse(p.interactive)
            self.assertFalse(self.quit_after(p, 5000))
            self.assertIsNone(p.slot_time("continue"))
        p = player("fbalpha2012_cps3")                                         # a core without states
        self.assertFalse(self.quit_after(p, 5000))

    def asked(self, core="mesen_s"):
        p = player(core); p.lib.frames = 4000; p.keep_continue(4000)
        p = player(core)                                                       # the next start
        p.paused, p.mode = True, "ask"
        return p

    def test_continue_puts_the_game_back(self):
        p = self.asked()
        p.draw_menu()                                                          # the question draws
        self.assertEqual(p.ask_sel, 0)                                         # "Continue" first
        p.menu_key("ok")
        self.assertFalse(p.paused); self.assertEqual(p.lib.frames, 4000)

    def test_start_over_leaves_the_game_fresh(self):
        p = self.asked(); p.menu_key("right"); p.menu_key("ok")
        self.assertFalse(p.paused); self.assertEqual(p.lib.frames, 0)
        p = self.asked(); p.menu_key("back")                                   # B: start over too
        self.assertFalse(p.paused); self.assertEqual(p.lib.frames, 0)
        self.assertIsNotNone(p.slot_time("continue"))                          # kept until the next quit

    def test_mame_continue_runs_the_start_up_first(self):
        p = player("mame2003_plus", takes_from=1800); p.lib.frames = 9000; p.keep_continue(9000)
        p = player("mame2003_plus", takes_from=1800); p.paused, p.mode = True, "ask"
        p.menu_key("ok")
        self.assertEqual(p.lib.run_at_load, 1800); self.assertEqual(p.lib.frames, 9000)


NES = "Nintendo - Nintendo Entertainment System"


class PictureLook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init(); pygame.font.init()

    def setUp(self):
        if os.path.exists(engine.PICTURE): os.remove(engine.PICTURE)

    def started(self, core="mesen", system=NES):
        p = player(core, system=system); p.picture = p.load_picture(); return p

    def test_sharp_until_chosen(self):
        self.assertEqual(self.started().picture, "sharp")

    def test_chosen_in_the_menu_for_the_whole_system(self):
        p = self.started(); p.set_pause(True); p.menu_sel = p.MENU.index("Picture")
        p.menu_key("right"); self.assertEqual(p.picture, "smooth")
        self.assertIn("for every NES game", p.osd[0])          # the system's own name
        p.menu_key("ok"); self.assertEqual(p.picture, "scanlines")
        p.menu_key("right"); self.assertEqual(p.picture, "sharp")                 # round again
        p.menu_key("left"); self.assertEqual(p.picture, "scanlines")
        self.assertTrue(p.paused)                                               # the menu stays open to compare
        self.assertEqual(self.started().picture, "scanlines")                     # another game of that system
        self.assertEqual(self.started("vbam", "Nintendo - Game Boy").picture, "sharp")   # other systems unchanged
        self.assertEqual(json.load(open(engine.PICTURE)), {NES: "scanlines"})

    def test_without_a_system_the_core_name_is_used(self):
        p = self.started("blastem", system=None); p.set_picture("smooth")
        self.assertEqual(json.load(open(engine.PICTURE)), {"Blastem": "smooth"})

    def test_test_runs_and_bad_files_change_nothing(self):
        p = self.started(); p.probe = True; p.set_picture("smooth")
        self.assertFalse(os.path.exists(engine.PICTURE))
        os.makedirs(os.path.dirname(engine.PICTURE), exist_ok=True)
        for bad in ("{not json", "[1, 2]", '{"%s": "neon"}' % NES):
            open(engine.PICTURE, "w").write(bad)
            self.assertEqual(self.started().picture, "sharp")
        self.started().set_picture("smooth")                                     # a broken file is replaced on choosing
        self.assertEqual(json.load(open(engine.PICTURE)), {NES: "smooth"})

    def picture(self, look, rotation=0):
        p = player(); p.picture = look; p.rotation = rotation
        img = pygame.Surface((4, 4), 0, 16); img.fill((255, 255, 255))
        img.fill((0, 0, 0), (0, 0, 2, 4))                                       # left half black
        return p.scaled(img, 40, 40)

    def test_sharp_keeps_hard_edges(self):
        out = self.picture("sharp")
        self.assertEqual({tuple(out.get_at((x, 20)))[:3] for x in range(40)}, {(0, 0, 0), (255, 255, 255)})

    def test_smoothed_blends_the_edges(self):
        out = self.picture("smooth"); self.assertEqual(out.get_size(), (40, 40))
        greys = {out.get_at((x, 20))[0] for x in range(40)}
        self.assertTrue(any(0 < g < 255 for g in greys), greys)

    def test_scanlines_darken_every_line(self):
        out = self.picture("scanlines")
        col = [out.get_at((30, y))[0] for y in range(40)]                       # down the white half
        self.assertEqual(col.count(255) + col.count(140), 40)
        self.assertEqual(col[:10], [255] * 6 + [140] * 4)                       # 4 source lines, 10 px each
        out = self.picture("scanlines", rotation=1)                              # a turned arcade screen
        row = [out.get_at((x, 30))[0] for x in range(20, 40)]                    # across the white half
        self.assertEqual(row[:10], [255] * 6 + [140] * 4)                       # the lines run up and down


if __name__ == "__main__":
    unittest.main()
