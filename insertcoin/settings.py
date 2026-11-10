"""Settings saved in settings.json."""
import json, os
from paths import CONFDIR


DEFAULT_SETTINGS = {"sound": True, "engine": False, "one_per_game": True}

def load_settings():
    try:
        with open(f"{CONFDIR}/settings.json") as f: return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception: return dict(DEFAULT_SETTINGS)

def save_settings(s):
    os.makedirs(CONFDIR, exist_ok=True)
    tmp = f"{CONFDIR}/settings.json.tmp"
    with open(tmp, "w") as f: json.dump(s, f, indent=2)
    os.replace(tmp, f"{CONFDIR}/settings.json")
