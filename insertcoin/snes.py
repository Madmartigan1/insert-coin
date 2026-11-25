"""Super Nintendo games with an enhancement chip of the DSP or ST01x kind.

Mesen-S needs the chip's own program and data files (dsp1.program.rom ...) in the BIOS folder to run these games;
without them they stop at the start-up logo. Snes9x has these chips built in, so when the files are missing the
built-in player runs those games in Snes9x instead (`insert-coin --cores` installs it). With the files in the BIOS
folder they stay with Mesen-S, like every other Super Nintendo game.

Which chip a game has is read from its cartridge header: the "chipset" byte, and for the custom chips (ST010 /
ST011) the sub-type byte just before the header.

Sources: the SNES cartridge header layout as documented by the community (SNESdev wiki,
https://snes.nesdev.org/wiki/ROM_header, and nocash's fullsnes); the chip file names are the ones
the libretro core info files list. No code was copied."""
import os, shutil, subprocess, zipfile
from paths import CORES_DIR, RA
from insertcoin.cores import core_file
from insertcoin.names import split_archive

MESEN_S, SNES9X = "mesen-s_libretro.so", "snes9x_libretro.so"
CHIP_FILES = {"DSP": [f"{c}.{p}.rom" for c in ("dsp1", "dsp1b", "dsp2", "dsp3", "dsp4") for p in ("data", "program")],
              "ST01x": [f"{c}.{p}.rom" for c in ("st010", "st011") for p in ("data", "program")]}
ROM_TYPES = (".sfc", ".smc", ".swc", ".fig", ".bs")


def header_chip(data):
    """'DSP', 'ST01x' or None, from a Super Nintendo ROM's header."""
    if len(data) % 1024 == 512: data = data[512:]                    # a copier's header in front of the game
    best = None
    for base, hirom in ((0x7FC0, False), (0xFFC0, True)):
        if len(data) < base + 0x20: continue
        h = data[base:base + 0x20]
        checksum, complement = h[0x1E] | h[0x1F] << 8, h[0x1C] | h[0x1D] << 8
        score = (2 if checksum ^ complement == 0xFFFF else 0) + (1 if (h[0x15] & 1) == hirom else 0)
        if best is None or score > best[0]: best = (score, base)
    if not best: return None
    base = best[1]
    chipset, kind = data[base + 0x16] & 0x0F, data[base + 0x16] >> 4
    if chipset < 3: return None                                        # ROM only, + RAM, + battery: no chip
    if kind == 0: return "DSP"
    if kind == 0xF and data[base - 1] == 0x01: return "ST01x"         # custom chip, sub-type 1 = ST010 / ST011
    return None


def rom_data(path):
    """The ROM's bytes: a loose file, 'archive.zip#game.sfc', or the first ROM in an archive. None if unreadable."""
    archive, inner = split_archive(path)
    try:
        if archive.lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                inner = inner or next((n for n in z.namelist() if n.lower().endswith(ROM_TYPES)), "")
                return z.read(inner) if inner else None
        if archive.lower().endswith(".7z"):
            exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
            if not exe or not inner: return None
            r = subprocess.run([exe, "e", "-so", archive, inner], capture_output=True, timeout=60)
            return r.stdout if r.returncode == 0 else None
        with open(archive, "rb") as f: return f.read()
    except Exception:                                                 # damaged archives, missing files...
        return None


def chip_files_there(chip, folder):
    return all(os.path.isfile(f"{folder}/{f}") for f in CHIP_FILES[chip])


def snes9x_path(cores_dir=None, ra_cores=None):
    """Where Snes9x is: Insert Coin's own copy, else RetroArch's; None if neither has it."""
    for d in (cores_dir or CORES_DIR, ra_cores or f"{RA}/cores"):
        if os.path.isfile(f"{d}/{SNES9X}"): return f"{d}/{SNES9X}"
    return None


def chip_core(core, rom, folder=None, cores_dir=None, ra_cores=None):
    """For a game Mesen-S would get stuck on (a DSP or ST01x chip, whose files aren't in the BIOS folder): the
    Snes9x core to run it in instead. Returns (core to use instead or None, the chip or None, a note for the log)."""
    if core_file(core) != MESEN_S: return None, None, ""
    data = rom_data(rom)
    chip = header_chip(data) if data else None
    if not chip: return None, None, ""
    from paths import SYSTEM
    if chip_files_there(chip, folder or SYSTEM): return None, chip, f"{chip} chip: its files are in the BIOS folder"
    instead = snes9x_path(cores_dir, ra_cores)
    if not instead:
        return None, chip, f"{chip} chip, its files aren't in the BIOS folder and Snes9x isn't installed (insert-coin --cores)"
    return instead, chip, f"{chip} chip and its files aren't in the BIOS folder: Snes9x runs it"
