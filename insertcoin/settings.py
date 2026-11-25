"""Settings saved in settings.json."""
import json, os, shutil
from paths import CONFDIR, RA


DEFAULT_SETTINGS = {"sound": True, "engine": False, "one_per_game": True, "library": "retroarch"}


def retroarch_installed():
    """Whether RetroArch is on this computer (its program, and its folder with playlists)."""
    return bool(shutil.which("retroarch")) and os.path.isdir(f"{RA}/playlists")


def defaults():
    """The settings before any are saved. Without RetroArch: Insert Coin's own library and the built-in player."""
    d = dict(DEFAULT_SETTINGS)
    if not retroarch_installed(): d.update(engine=True, library="insertcoin")
    return d


def load_settings():
    try:
        with open(f"{CONFDIR}/settings.json") as f: return {**defaults(), **json.load(f)}
    except Exception: return defaults()

def save_settings(s):
    os.makedirs(CONFDIR, exist_ok=True)
    tmp = f"{CONFDIR}/settings.json.tmp"
    with open(tmp, "w") as f: json.dump(s, f, indent=2)
    os.replace(tmp, f"{CONFDIR}/settings.json")
