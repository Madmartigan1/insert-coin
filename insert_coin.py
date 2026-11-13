#!/usr/bin/env python3
"""Insert Coin - a controller-driven, console-style front end for RetroArch.

It reads RetroArch's own playlists, thumbnails, favorites and history, and
launches games with each game's assigned core: through RetroArch, or in its own
built-in player (engine.py, beta; B menu > Player). Nothing is duplicated:
whatever works in RetroArch works here.

Controls (Xbox-style pad; keyboard in brackets)
  D-pad / left stick  move            [arrows]
  A                   open / play     [Enter]
  B                   back            [Backspace / Esc]
  Y                   toggle favorite [F]
  X                   versions of a game [V]
  LB / RB             previous / next letter   [PageUp / PageDown]
  Menu sounds can be switched off in the B menu (saved in ~/.config/insert-coin/settings.json).
  In a game: Select+Start opens the game menu (Resume / Quit game, or RetroArch's Quick Menu).
  Browser and Flash games (~/.config/insert-coin/browser_games.json): Select+Start returns here.

Options: --windowed   run in a window (for testing)
         --shot DIR   render sample screens to PNG files and exit (no display needed)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)                    # also when loaded with runpy (docs/make_screenshots.py)

from insertcoin import __version__
# Every name the app defines stays reachable as insert_coin.<name>, as before the code moved into insertcoin/
from insertcoin.logs import *  # noqa: F401,F403
from insertcoin.systems import *  # noqa: F401,F403
from insertcoin.cores import *  # noqa: F401,F403
from insertcoin.controllers import *  # noqa: F401,F403
from insertcoin.names import *  # noqa: F401,F403
from insertcoin.retroarch import *  # noqa: F401,F403
from insertcoin.games import *  # noqa: F401,F403
from insertcoin.web import *  # noqa: F401,F403
from insertcoin.flashinput import *  # noqa: F401,F403
from insertcoin.library import *  # noqa: F401,F403
from insertcoin.meta import *  # noqa: F401,F403
from insertcoin.media import *  # noqa: F401,F403
from insertcoin.settings import *  # noqa: F401,F403
from insertcoin.draw import *  # noqa: F401,F403
from insertcoin.pads import *  # noqa: F401,F403
from insertcoin.launch import *  # noqa: F401,F403
from insertcoin.screens import *  # noqa: F401,F403
from insertcoin.meta import _rdb_load  # noqa: F401
from insertcoin.app import App, main  # noqa: F401

if __name__ == "__main__":
    main()
