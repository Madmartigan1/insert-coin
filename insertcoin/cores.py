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
    builtin: bool = False       # the built-in player runs it (test-booted)
    arcade: bool = False        # arcade games: the built-in player's pause menu offers Controls
    turbo: bool = False         # two-button systems: holding LB / RB fires the bottom / right button rapidly
    turbo_face: bool = False    # ...and the left / top face buttons too (PC Engine: they're free in 2-button mode)
    states: bool = True         # save states work (FB Alpha 2012 CPS-3 never takes a saved state back)
    warmup: int = 0             # frames a game must have run before it takes a saved state back (MAME 2003-Plus:
                                # many games ignore one loaded during their start-up; Mupen64Plus-Next refuses
                                # one before its first frame)
    stick_dpad: bool = True     # the left stick also works as the d-pad (not where games read the stick itself: N64)


# file name -> Core. Mupen64Plus-Next (N64) draws with the graphics card: the built-in player gives it an OpenGL
# context (insertcoin/glvideo.py).
CORES = {
    "mesen_libretro.so": Core("Mesen", ("Nintendo - Nintendo Entertainment System",), builtin=True, turbo=True),
    "mesen-s_libretro.so": Core("Mesen-S", ("Nintendo - Super Nintendo Entertainment System",), builtin=True),
    "vbam_libretro.so": Core("VBA-M", ("Nintendo - Game Boy", "Nintendo - Game Boy Color",
                                       "Nintendo - Game Boy Advance"), builtin=True, turbo=True),
    "mupen64plus_next_libretro.so": Core("Mupen64Plus-Next", ("Nintendo - Nintendo 64",), builtin=True, stick_dpad=False,
                                         warmup=10),
    "blastem_libretro.so": Core("BlastEm", ("Sega - Mega Drive - Genesis",), builtin=True),
    "picodrive_libretro.so": Core("PicoDrive", ("Sega - 32X",), builtin=True),
    "mednafen_supergrafx_libretro.so": Core("Beetle SuperGrafx", ("NEC - PC Engine - TurboGrafx 16",), builtin=True, turbo=True,
                                            turbo_face=True),
    "mednafen_ngp_libretro.so": Core("Beetle NeoPop", ("SNK - Neo Geo Pocket", "SNK - Neo Geo Pocket Color"),
                                     builtin=True, turbo=True),
    "pcsx_rearmed_libretro.so": Core("PCSX-ReARMed", ("Sony - PlayStation",), builtin=True),
    "stella_libretro.so": Core("Stella", ("Atari - 2600",), builtin=True),
    "fbneo_libretro.so": Core("FinalBurn Neo", ("FBNeo - Arcade Games",), builtin=True, arcade=True),
    "mame2003_plus_libretro.so": Core("MAME 2003-Plus", ("MAME 2003-Plus",), builtin=True, arcade=True, warmup=1800),
    "mame2003_libretro.so": Core("MAME 2003 (0.78)", builtin=True, arcade=True),
    "fbalpha2012_cps3_libretro.so": Core("FB Alpha 2012 CPS-3", builtin=True, arcade=True, states=False),
    "snes9x_libretro.so": Core("Snes9x", builtin=True),     # Super Nintendo games with a DSP / ST01x chip (insertcoin/snes.py)
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


def stick_is_dpad(path):
    """Whether the left stick also presses the d-pad in this core (cores missing from the table: yes, as before)."""
    c = CORES.get(core_file(path))
    return c.stick_dpad if c else True


def is_builtin(path):
    """Whether the built-in player runs this core."""
    return core_file(path) in ENGINE_CORES


# games of a turbo core that use LB / RB themselves: Famicom Disk System (disk switching), Game Boy Advance (L / R)
NO_TURBO = (".fds", ".gba")


def has_turbo(path, files):
    """Whether LB / RB are turbo buttons for this game: its core is a turbo core and none of the game's files
    (the ROM, or the files inside its archive) is a kind that needs LB / RB."""
    c = CORES.get(core_file(path))
    return bool(c and c.turbo) and not any(f.lower().endswith(NO_TURBO) for f in files)


def has_face_turbo(path):
    """Whether the left / top face buttons are turbo buttons too (for a game has_turbo says yes to)."""
    c = CORES.get(core_file(path))
    return bool(c and c.turbo_face)


def is_arcade(path, name=""):
    """Whether this is an arcade core. Cores missing from the table are judged by the name they report."""
    c = CORES.get(core_file(path))
    if c: return c.arcade
    return any(k in name for k in ("FinalBurn", "FB Alpha", "MAME"))


def has_states(path):
    """Whether the built-in player offers save states for this core (cores missing from the table: yes)."""
    c = CORES.get(core_file(path))
    return not c or c.states


def state_warmup(path):
    """How many frames a game must have run before a saved state is loaded into it (0 = straight away)."""
    c = CORES.get(core_file(path))
    return c.warmup if c else 0
