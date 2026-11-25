"""Command-line options: --help prints the usage, and a mistyped option never opens the full-screen app."""
import support  # noqa: F401  (must come first: points HOME etc. at a temp dir)
import unittest
from insertcoin import __version__
from insertcoin.app import check_options, main
from unittest import mock


class Options(unittest.TestCase):
    def test_no_options_open_the_app(self):
        for a in ([], ["--windowed"], ["--scan"], ["--scan", "--add"], ["--scan", "--add", "--retry"],
                  ["--cores"], ["--databases"], ["--bios"], ["--shot", "out"], ["--shot", "out", "--windowed"]):
            self.assertIsNone(check_options(a), a)

    def test_help(self):
        for a in (["--help"], ["-h"], ["--scan", "--help"]):
            text, code = check_options(a)
            self.assertEqual(code, 0)
            self.assertIn(__version__, text)
            for o in ("--scan --add --retry", "--cores", "--databases", "--bios", "--windowed"): self.assertIn(o, text)

    def test_mistakes_are_refused(self):
        for a in (["--hlep"], ["help"], ["--scan", "--ad"], ["--add"], ["--retry"], ["--scan", "--retry"],
                  ["--shot"], ["--windowed", "-x"], ["--database"]):
            got = check_options(a)
            self.assertIsNotNone(got, a)
            self.assertEqual(got[1], 2, a)
            self.assertIn("insert-coin --help", got[0])

    def test_main_does_not_open_the_app_for_a_mistake(self):
        with mock.patch("sys.argv", ["insert-coin", "--hlep"]), mock.patch("insertcoin.app.App") as app, \
             mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as e: main()
        self.assertEqual(e.exception.code, 2)
        app.assert_not_called()

    def test_main_help_does_not_open_the_app(self):
        with mock.patch("sys.argv", ["insert-coin", "--help"]), mock.patch("insertcoin.app.App") as app, \
             mock.patch("sys.stdout"):
            with self.assertRaises(SystemExit) as e: main()
        self.assertEqual(e.exception.code, 0)
        app.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class ProgressLine(unittest.TestCase):
    """The progress line of --cores, --scan, --scan --add and --copy-art leaves nothing behind."""
    @staticmethod
    def screen(text):
        """What a terminal shows for this output: carriage return goes back to the start of the line."""
        lines = []
        for raw in text.split("\n"):
            row = []
            for part in raw.split("\r"):
                row[:len(part)] = part
            lines.append("".join(row).rstrip())
        return lines

    def test_a_shorter_line_after_a_longer_one(self):
        import io
        from insertcoin.app import Progress
        out = io.StringIO(); p = Progress(out)
        p.show("  15 of 15: mupen64plus_next_libretro.so"); p.show("  1 of 2: x.so")
        self.assertEqual(self.screen(out.getvalue()), ["  1 of 2: x.so"])
        p.clear(); print("Copied from RetroArch: 1", end="", file=out)
        self.assertEqual(self.screen(out.getvalue()), ["Copied from RetroArch: 1"])

    def test_keep_leaves_the_last_count_as_a_record(self):
        import io
        from insertcoin.app import Progress
        out = io.StringIO(); p = Progress(out)
        p.show("  copied 9 of 10..."); p.show("  copied 10 of 10..."); p.keep(); print("Checking", file=out, end="")
        self.assertEqual(self.screen(out.getvalue()), ["  copied 10 of 10...", "Checking"])
