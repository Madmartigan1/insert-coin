"""Command-line options: --help prints the usage, and a mistyped option never opens the full-screen app."""
import support  # noqa: F401  (must come first: points HOME etc. at a temp dir)
import unittest
from insertcoin import __version__
from insertcoin.app import check_options, main
from unittest import mock


class Options(unittest.TestCase):
    def test_no_options_open_the_app(self):
        for a in ([], ["--windowed"], ["--scan"], ["--scan", "--add"], ["--scan", "--add", "--retry"],
                  ["--cores"], ["--bios"], ["--shot", "out"], ["--shot", "out", "--windowed"]):
            self.assertIsNone(check_options(a), a)

    def test_help(self):
        for a in (["--help"], ["-h"], ["--scan", "--help"]):
            text, code = check_options(a)
            self.assertEqual(code, 0)
            self.assertIn(__version__, text)
            for o in ("--scan --add --retry", "--cores", "--bios", "--windowed"): self.assertIn(o, text)

    def test_mistakes_are_refused(self):
        for a in (["--hlep"], ["help"], ["--scan", "--ad"], ["--add"], ["--retry"], ["--scan", "--retry"],
                  ["--shot"], ["--windowed", "-x"]):
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
