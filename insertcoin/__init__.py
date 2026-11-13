"""Insert Coin's code, one module per job. Start it with insert_coin.py; tests are in tests/.

  app          the App: state, navigation, input, main loop (built from the three mixins below)
  pads         controllers: opening, hot-plugging, setting up unrecognised pads
  launch       starting games: RetroArch, the built-in player (engine.py) or a browser
  screens      drawing every screen
  library      the systems' games, Favorites, Recently Played, browser playlists
  retroarch    the games' source: RetroArch's playlists, favorites, history, thumbnails
  games        a game;  names: labels, sorting, versions;  meta: year and publisher
  web          browser and Flash games;  flashinput: optional DevTools input for Flash
  systems      known systems;  cores: every core, its systems, built-in player, arcade
  controllers  controller families, glyphs, set-up steps
  media        images, fonts, sounds;  draw: drawing helpers;  settings;  logs
"""
import os

__version__ = "0.4.5"

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")            # before any module imports pygame
