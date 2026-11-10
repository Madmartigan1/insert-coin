"""Where Insert Coin reads and writes its files, in one place.

Every other module imports these names instead of building its own paths.
Tests point them elsewhere with environment variables:
  INSERT_COIN_CONFIG  settings, controllers, remaps, browser playlists, played.json
  INSERT_COIN_SAVES   the built-in player's saves
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
# BIOS files: Insert Coin's own folder once it has one, else the one RetroArch uses (Neo Geo BIOS lives there)
SYSTEM = f"{APPDIR}/system" if os.path.isdir(f"{APPDIR}/system") else f"{RA}/system"
HERE = os.path.dirname(os.path.abspath(__file__))                    # the folder with insert_coin.py and engine.py
THUMB_SYNC_CACHE = f"{HOME}/.cache/retroarch-thumb-sync"              # sync_thumbnails.py's download cache
