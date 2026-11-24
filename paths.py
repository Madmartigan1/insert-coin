"""Where Insert Coin reads and writes its files, in one place.

Every other module imports these names instead of building its own paths.
Tests point them elsewhere with environment variables:
  INSERT_COIN_CONFIG  settings, controllers, remaps, browser playlists, played.json
  INSERT_COIN_SAVES   the built-in player's saves
  INSERT_COIN_STATES  the built-in player's save states
  INSERT_COIN_SYSTEM  the BIOS folder (test starts use a copy, so a core can't change the real one)
  XDG_STATE_HOME      where the logs go (standard XDG variable)
"""
import os

HOME = os.path.expanduser("~")
RA = f"{HOME}/.config/retroarch"                                     # RetroArch: playlists, thumbnails, cores, saves
APPDIR = f"{HOME}/.local/share/insert-coin"                           # launch.cfg, saves, browser profiles, Ruffle
CACHE = f"{HOME}/.cache/insert-coin"                                  # year/publisher parsed from RetroArch's databases
LOGDIR = f"{os.environ.get('XDG_STATE_HOME') or HOME + '/.local/state'}/insert-coin"
CONFDIR = os.environ.get("INSERT_COIN_CONFIG") or f"{HOME}/.config/insert-coin"
SAVES = os.environ.get("INSERT_COIN_SAVES") or f"{APPDIR}/saves"
STATES = os.environ.get("INSERT_COIN_STATES") or f"{APPDIR}/states"   # save states: <core>/<game>.slotN.state + .png
LIBRARY = f"{APPDIR}/library.json"                                    # Insert Coin's own game library (B menu: Library)
FAVORITES = f"{APPDIR}/favorites.json"                                # ...its Favorites
HISTORY = f"{APPDIR}/history.json"                                    # ...and Recently Played
CORES_DIR = f"{APPDIR}/cores"                                         # Insert Coin's own copies of the cores (--cores)
THUMBNAILS = f"{APPDIR}/thumbnails"                                   # Insert Coin's own box art (read before RetroArch's)
RA_THUMBNAILS = f"{RA}/thumbnails"                                    # RetroArch's box art
# BIOS files: Insert Coin's own folder once it has one, else the one RetroArch uses (Neo Geo BIOS lives there)
SYSTEM = os.environ.get("INSERT_COIN_SYSTEM") or (f"{APPDIR}/system" if os.path.isdir(f"{APPDIR}/system") else f"{RA}/system")
HERE = os.path.dirname(os.path.abspath(__file__))                    # the folder with insert_coin.py and engine.py
THUMB_SYNC_CACHE = f"{HOME}/.cache/retroarch-thumb-sync"              # sync_thumbnails.py's download cache
