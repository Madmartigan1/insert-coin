"""Pictures: backgrounds always cover the screen exactly (one pixel short once stopped all art loading)."""
import os, unittest
import support as S
import pygame
from insertcoin.media import Images


class Backgrounds(unittest.TestCase):
    def test_blurred_background_is_exactly_the_screen_size(self):
        os.makedirs(f"{S.TMP}/img", exist_ok=True)
        images = Images(sync=True)
        for iw, ih in [(154, 100), (154, 107), (320, 224), (256, 239), (999, 701), (2000, 90)]:
            path = f"{S.TMP}/img/{iw}x{ih}.png"
            pygame.image.save(pygame.Surface((iw, ih)), path)
            for w, h in [(1280, 720), (1920, 1080), (3840, 2160)]:
                surf = images._make((path, w, h, "blur"))
                self.assertEqual(surf.get_size(), (w, h), f"{iw}x{ih} on {w}x{h}")

    def test_fit_keeps_the_shape(self):
        path = f"{S.TMP}/img/box.png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pygame.image.save(pygame.Surface((200, 100)), path)
        self.assertEqual(Images(sync=True)._make((path, 300, 300, "fit")).get_size(), (300, 150))

    def test_missing_or_broken_files_give_no_image(self):
        images = Images(sync=True)
        self.assertIsNone(images._make((f"{S.TMP}/img/none.png", 10, 10, "fit")))
        bad = f"{S.TMP}/img/bad.png"
        os.makedirs(os.path.dirname(bad), exist_ok=True)
        with open(bad, "w") as f: f.write("not a picture")
        self.assertIsNone(images._make((bad, 10, 10, "fit")))

    def test_a_failing_picture_never_stops_the_loader(self):
        images = Images()                                                   # the real thing: three loader threads
        images._make = lambda key: 1 / 0
        for i in range(5): images.get(f"/nowhere/{i}.png", 10, 10)
        deadline = __import__("time").time() + 5
        while len(images.done) < 5 and __import__("time").time() < deadline: pass
        self.assertEqual(len(images.done), 5)                               # every request answered


if __name__ == "__main__":
    unittest.main()
