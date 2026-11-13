"""Shared set-up for the tests: a throwaway home folder and a small made-up RetroArch library.

Import this before anything from Insert Coin. It points HOME and every Insert Coin folder at a temporary
directory first, so the tests never read or write a real setup. All games here are fictional."""
import atexit, json, logging, os, shutil, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="insert-coin-tests-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
logging.getLogger("insert-coin").addHandler(logging.NullHandler())   # expected warnings stay out of the output
os.environ.update(HOME=TMP, XDG_STATE_HOME=f"{TMP}/state", INSERT_COIN_CONFIG=f"{TMP}/config",
                  INSERT_COIN_SAVES=f"{TMP}/saves", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
if "paths" in sys.modules and sys.modules["paths"].HOME != TMP:
    raise RuntimeError("paths was imported before tests/support.py: the tests would use the real home folder")
if ROOT not in sys.path: sys.path.insert(0, ROOT)

import paths                                                        # noqa: E402  (after HOME is set)

RA = paths.RA
CORES = f"{RA}/cores"
ROMS = f"{TMP}/roms"
NES = "Nintendo - Nintendo Entertainment System"
ARCADE = "FBNeo - Arcade Games"


def core(name):
    """A stand-in core file (only its existence matters to the library)."""
    os.makedirs(CORES, exist_ok=True)
    p = f"{CORES}/{name}"
    open(p, "a").close()
    return p


def rom(rel):
    """An empty stand-in ROM under the roms folder; returns its full path."""
    p = f"{ROMS}/{rel}"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "a").close()
    return p


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)


def read(path):
    with open(path, encoding="utf-8") as f: return json.load(f)


def playlist(name, items, default_core=""):
    """Write a RetroArch playlist: items are (label, path) or (label, path, core_path)."""
    write(f"{RA}/playlists/{name}.lpl", {"version": "1.5", "default_core_path": default_core, "items": [
        {"path": it[1], "label": it[0], "core_path": it[2] if len(it) > 2 else "DETECT", "core_name": "DETECT",
         "crc32": "DETECT", "db_name": name + ".lpl"} for it in items]})


def reset():
    """An empty home folder again (every test class starts from scratch)."""
    for d in os.listdir(TMP): shutil.rmtree(f"{TMP}/{d}", ignore_errors=True)


def sample_library():
    """A small library: an NES playlist with copies and versions, an arcade playlist, an empty one."""
    reset()
    mesen, fbneo = core("mesen_libretro.so"), core("fbneo_libretro.so")
    core("mame2003_plus_libretro.so")
    playlist(NES, [
        ("Star Pilot (USA)", rom("nes/Star Pilot (USA).zip") + "#Star Pilot (USA).nes"),
        ("Star Pilot (USA)", rom("nes/best-of/Star Pilot (USA).zip") + "#Star Pilot (USA).nes"),   # a copy
        ("Star Pilot (Japan)", rom("nes/Star Pilot (Japan).zip") + "#Star Pilot (Japan).nes"),
        ("Star Pilot (Europe)", rom("nes/Star Pilot (Europe).zip") + "#Star Pilot (Europe).nes"),
        ("Star Pilot (USA) [T+Ger]", rom("nes/# Translations #/Star Pilot (USA) [T+Ger].nes")),
        ("Pixel Knights, The (Europe)", rom("nes/Pixel Knights, The (Europe).nes")),
        ("Pixel Knights (Japan)", rom("nes/Pixel Knights (Japan).nes")),
        ("Turbo Tanks II (USA)", rom("nes/Turbo Tanks II (USA).nes")),
        ("Turbo-Tanks 2 (Japan)", rom("nes/Turbo-Tanks 2 (Japan).nes")),
        ("Wavebreaker (USA)", rom("nes/Wavebreaker (USA).nes"), f"{CORES}/missing_libretro.so"),
    ], default_core=mesen)
    playlist(ARCADE, [
        ("Moon Raiders", rom("arcade/moonraid.zip")),
        ("Moon Raiders (set 2)", rom("arcade/moonraid2.zip"), f"{CORES}/mame2003_plus_libretro.so"),
    ], default_core=fbneo)
    playlist("Sega - 32X", [])                                      # empty: not shown
    playlist("Homebrew - Console", [("Byte Runner", rom("home/byte-runner.bin"))])   # unknown system
    return mesen, fbneo
