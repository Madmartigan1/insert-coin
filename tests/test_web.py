"""Flash games: the pad's buttons become the keys the game expects, pressed by Ruffle itself."""
import json, re, unittest
import support  # noqa: F401
from insertcoin.web import FLASH_BUTTONS, PAD_INDEX, flash_page


def ruffle_mapping(page):
    m = re.search(r"gamepadButtonMapping: NATIVE \? \{\} : (\{.*?\})\}\}", page)
    return json.loads(m.group(1))


class FlashPage(unittest.TestCase):
    def test_default_buttons(self):
        m = ruffle_mapping(flash_page("game.swf", "Comet Dash"))
        self.assertEqual(set(m), set(FLASH_BUTTONS))
        self.assertEqual((m["south"], m["east"], m["west"], m["north"], m["start"]), (32, 13, 90, 88, 13))
        self.assertEqual((m["dpad-up"], m["dpad-left"]), (38, 37))

    def test_a_game_sets_its_own_keys(self):
        m = ruffle_mapping(flash_page("game.swf", "Comet Dash", {"south": "X", "east": "C", "right-trigger": "P"}))
        self.assertEqual((m["south"], m["east"], m["right-trigger"]), (88, 67, 80))
        self.assertEqual(m["west"], 90)                                     # the rest keep the defaults

    def test_one_key_per_button(self):
        """Ruffle presses one key per button: of "X+Space" only X is used."""
        m = ruffle_mapping(flash_page("game.swf", "Comet Dash", {"south": "X+Space", "north": "Nope"}))
        self.assertEqual(m["south"], 88)
        self.assertNotIn("north", m)                                        # an unknown key leaves the button free

    def test_the_page_never_sends_keys(self):
        """Keys made by the page stopped reaching Flash games on a real screen; only Ruffle presses keys."""
        page = flash_page("game.swf", "Comet Dash", {"south": "X+Space"})
        self.assertNotIn("KeyboardEvent", page)

    def test_insert_coin_sending_real_input_turns_the_mapping_off(self):
        self.assertIn('NATIVE = true', flash_page("game.swf", "Comet Dash", native=True))

    def test_titles_are_escaped(self):
        page = flash_page("g.swf", "Comet <Dash> & Co")                    # "<" and "&" are the ones that matter
        self.assertIn("<title>Comet &lt;Dash> &amp; Co</title>", page)
        self.assertNotIn("<Dash>", page)

    def test_triggers_are_the_bumpers(self):
        """Ruffle's "left-trigger" / "right-trigger" are LB / RB (buttons 4 and 5); RT clicks the pointer."""
        self.assertEqual((PAD_INDEX["left-trigger"], PAD_INDEX["right-trigger"]), (4, 5))


if __name__ == "__main__":
    unittest.main()
