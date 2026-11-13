"""The emulator cores Insert Coin knows, in one table: what each is called, which systems it plays, whether the
built-in player runs it, and whether it is an arcade core.

Every other module asks this table instead of keeping its own list of file names or matching core names.
RetroArch's playlists still choose which core a game uses; `systems` records the core each playlist normally
starts with, for the day Insert Coin keeps its own library."""
import os
from typing import NamedTuple
from insertcoin.systems import FRIENDLY


class Core(NamedTuple):
    name: str                   # the name the core reports (retro_get_system_info); also its save-folder name
    systems: tuple = ()         # playlists that start this core by default
    builtin: bool = False       # the built-in player runs it (draws in software; test-booted)
    arcade: bool = False        # arcade games: the built-in player's pause menu offers Controls


# file name -> Core. N64 draws with the graphics card, so it stays with RetroArch for now.
CORES = {
    "mesen_libretro.so": Core("Mesen", ("Nintendo - Nintendo Entertainment System",), builtin=True),
    "mesen-s_libretro.so": Core("Mesen-S", ("Nintendo - Super Nintendo Entertainment System",), builtin=True),
    "vbam_libretro.so": Core("VBA-M", ("Nintendo - Game Boy", "Nintendo - Game Boy Color",
                                       "Nintendo - Game Boy Advance"), builtin=True),
    "mupen64plus_next_libretro.so": Core("Mupen64Plus-Next", ("Nintendo - Nintendo 64",)),
    "blastem_libretro.so": Core("BlastEm", ("Sega - Mega Drive - Genesis",), builtin=True),
    "picodrive_libretro.so": Core("PicoDrive", ("Sega - 32X",), builtin=True),
    "mednafen_supergrafx_libretro.so": Core("Beetle SuperGrafx", ("NEC - PC Engine - TurboGrafx 16",), builtin=True),
    "mednafen_ngp_libretro.so": Core("Beetle NeoPop", ("SNK - Neo Geo Pocket", "SNK - Neo Geo Pocket Color"),
                                     builtin=True),
    "pcsx_rearmed_libretro.so": Core("PCSX-ReARMed", ("Sony - PlayStation",), builtin=True),
    "stella_libretro.so": Core("Stella", ("Atari - 2600",), builtin=True),
    "fbneo_libretro.so": Core("FinalBurn Neo", ("FBNeo - Arcade Games",), builtin=True, arcade=True),
    "mame2003_plus_libretro.so": Core("MAME 2003-Plus", ("MAME 2003-Plus",), builtin=True, arcade=True),
    "mame2003_libretro.so": Core("MAME 2003 (0.78)", builtin=True, arcade=True),
    "fbalpha2012_cps3_libretro.so": Core("FB Alpha 2012 CPS-3", builtin=True, arcade=True),
}

ENGINE_CORES = {f for f, c in CORES.items() if c.builtin}                  # the built-in player's cores
DEFAULT_CORE = {s: f for f, c in CORES.items() for s in c.systems}           # playlist -> its usual core


def core_file(path):
    """The core's file name, from a full path ("…/cores/mesen_libretro.so" -> "mesen_libretro.so")."""
    return os.path.basename(path or "")


def core_short(path):
    """The short name RetroArch's playlists use for a core ("mesen"), from its path."""
    return core_file(path).replace("_libretro.so", "")


def not_builtin_systems():
    """Friendly names of the systems whose usual core the built-in player can't run (["Nintendo 64"])."""
    return sorted({FRIENDLY[s][0] for c in CORES.values() if not c.builtin for s in c.systems if s in FRIENDLY})


def is_builtin(path):
    """Whether the built-in player runs this core."""
    return core_file(path) in ENGINE_CORES


def is_arcade(path, name=""):
    """Whether this is an arcade core. Cores missing from the table are judged by the name they report."""
    c = CORES.get(core_file(path))
    if c: return c.arcade
    return any(k in name for k in ("FinalBurn", "FB Alpha", "MAME"))
