"""BIOS files (0.6 step 2): which ones the built-in player's cores can use, whether they're there and the right
ones, and Insert Coin's own BIOS folder.

`insert-coin --bios` copies RetroArch's BIOS folder (system/) to ~/.local/share/insert-coin/system/ the first
time; later runs only add files RetroArch has that Insert Coin's folder lacks, never replacing one. The built-in
player uses Insert Coin's folder as soon as it exists (paths.SYSTEM); RetroArch keeps using its own.

The table lists each core's BIOS and firmware files with the checksums RetroArch's core information gives
(libretro's core info files). Most are optional: the games run without them. A few are needed by some games:
Famicom Disk System games and Neo Geo games whose set doesn't carry the BIOS. Super Nintendo games with a DSP or
ST01x chip need the chip's files in Mesen-S; without them they play in Snes9x (insertcoin/snes.py). CD systems aren't in Insert Coin yet, so their BIOS files aren't
listed."""
import hashlib, os, shutil, zipfile
from typing import NamedTuple
from paths import APPDIR, RA, SYSTEM
from insertcoin.cores import core_file

OWN_SYSTEM = f"{APPDIR}/system"
RA_SYSTEM = f"{RA}/system"


class Bios(NamedTuple):
    file: str                   # path inside the BIOS folder
    system: str                 # shown as a heading
    core: str                   # the core file that reads it
    md5: str = ""               # the checksum of the known good file ("" = none known: presence is checked)
    needed: str = ""            # which games need it ("" = optional: games run without it)
    use: str = ""               # what it does, when optional
    title: str = ""             # its name in messages ("the Famicom Disk System BIOS")


_DSP = [f"{chip}.{part}.rom" for chip in ("dsp1", "dsp1b", "dsp2", "dsp3", "dsp4", "st010", "st011")
        for part in ("data", "program")]
TABLE = [
    Bios("disksys.rom", "NES / Famicom", "mesen_libretro.so", "ca30b50f880eb660a320674ed365ef7a",
         needed="Famicom Disk System games (.fds)", title="the Famicom Disk System BIOS"),
    *[Bios(f, "Super Nintendo", "mesen-s_libretro.so",
           use="Mesen-S runs the few games with a DSP or ST01x chip with them; without them those play in Snes9x")
      for f in _DSP],
    Bios("BS-X.bin", "Super Nintendo", "mesen-s_libretro.so", needed="some Satellaview (BS) games"),
    Bios("gb_bios.bin", "Game Boy", "vbam_libretro.so", "32fbbd84168d3482956eb3c5051637f5",
         use="the start-up logo"),
    Bios("gbc_bios.bin", "Game Boy Color", "vbam_libretro.so", "dbfce9db9deaa2567f6a84fde55f9680",
         use="the start-up logo"),
    Bios("gba_bios.bin", "Game Boy Advance", "vbam_libretro.so", "a860e8c0b6d573d191e4ec7db1b1e4f6",
         use="the start-up logo; a few games run more accurately"),
    Bios("rom.db", "Mega Drive / Genesis", "blastem_libretro.so", "ff4a3572475236e859e3e9ac5c87d1f1",
         use="BlastEm's list of games with special hardware"),
    Bios("scph5500.bin", "PlayStation", "pcsx_rearmed_libretro.so", "8dd7d5296a650fac7319bce665a6a53c",
         use="a real Japanese BIOS; PCSX ReARMed has its own built in"),
    Bios("scph5501.bin", "PlayStation", "pcsx_rearmed_libretro.so", "490f666e1afb15b7362b406ed1cea246",
         use="a real US BIOS; PCSX ReARMed has its own built in"),
    Bios("scph5502.bin", "PlayStation", "pcsx_rearmed_libretro.so", "32736f17079d0b2b7024407c39bd3050",
         use="a real European BIOS; PCSX ReARMed has its own built in"),
    Bios("fbneo/neogeo.zip", "Arcade: Neo Geo", "fbneo_libretro.so",
         needed="Neo Geo games whose zip doesn't carry the BIOS"),
]
# what a Neo Geo BIOS zip must hold for FinalBurn Neo: the fixed parts, plus at least one BIOS program (*.sp1 ...)
NEOGEO_PARTS = {"000-lo.lo", "sfix.sfix", "sm1.sm1"}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def locate(b, folder=None):
    """Where a BIOS file is, or None. FinalBurn Neo also looks in the top of the BIOS folder."""
    folder = folder or SYSTEM
    for p in [f"{folder}/{b.file}"] + ([f"{folder}/{os.path.basename(b.file)}"] if "/" in b.file else []):
        if os.path.isfile(p): return p
    return None


def judge(b, path):
    """(status, note) for a BIOS file: ok / different / incomplete / missing."""
    if not path: return "missing", ""
    if b.file.endswith("neogeo.zip"):
        try:
            with zipfile.ZipFile(path) as z: names = {os.path.basename(n).lower() for n in z.namelist()}
        except (OSError, zipfile.BadZipFile): return "different", "not a readable zip"
        lacks = sorted(NEOGEO_PARTS - names)
        if lacks or not any(n.endswith((".sp1", ".rom", ".bin")) and n.startswith(("sp", "uni-bios", "japan", "vs-bios"))
                            for n in names):
            return "incomplete", "lacks " + (", ".join(lacks) or "a BIOS program")
        return "ok", ""
    if b.md5 and md5(path) != b.md5: return "different", "not the known good dump; it may not work"
    return "ok", "" if b.md5 else "no checksum known; found"


def check(folder=None):
    """[(Bios, status, note, path)] for every file in the table."""
    return [(b, *judge(b, p), p) for b in TABLE for p in [locate(b, folder)]]


def set_up_own(ra=None, own=None):
    """Copy RetroArch's BIOS folder to Insert Coin's the first time; afterwards add only the files Insert Coin's
    folder lacks. Never replaces a file, never changes RetroArch's folder. Returns (files copied, created)."""
    ra, own = ra or RA_SYSTEM, own or OWN_SYSTEM
    created = not os.path.isdir(own)
    os.makedirs(own, exist_ok=True)
    copied = 0
    if os.path.isdir(ra):
        for root, dirs, files in os.walk(ra):
            rel = os.path.relpath(root, ra)
            for d in dirs: os.makedirs(os.path.normpath(os.path.join(own, rel, d)), exist_ok=True)   # empty ones too
            for f in files:
                src, dst = os.path.join(root, f), os.path.normpath(os.path.join(own, rel, f))
                if os.path.lexists(dst): continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst); copied += 1
    return copied, created


def needs_missing(core, rom, folder=None):
    """A BIOS this game certainly needs and that's missing, or None (used to explain a game that won't start)."""
    if core_file(core) == "mesen_libretro.so" and rom.lower().endswith(".fds"):
        b = TABLE[0]
        return None if locate(b, folder) else b
    return None


def neogeo_bios_missing(folder=None):
    """Whether FinalBurn Neo has no usable Neo Geo BIOS in the folder."""
    b = next(x for x in TABLE if x.file.endswith("neogeo.zip"))
    return judge(b, locate(b, folder))[0] != "ok"


def summary(results, folder, copied=0, created=False):
    lines = []
    if created: lines.append(f"Made Insert Coin's own BIOS folder, a copy of RetroArch's ({copied:,} files).")
    elif copied: lines.append(f"Added {copied:,} files RetroArch has that Insert Coin's BIOS folder lacked.")
    lines.append(f"BIOS folder: {folder}")
    shown, rows = None, []
    for b, status, note, path in results:              # files with the same purpose and status share one line
        key = (b.system, b.needed, b.use, status, note)
        if rows and rows[-1][0] == key: rows[-1][1].append(b.file)
        else: rows.append((key, [b.file]))
    for (system, needed, use, status, note), files in rows:
        if system != shown: lines += ["", system]; shown = system
        what = f"needed by {needed}" if needed else f"optional: {use}"
        mark = {"ok": "ok", "different": "DIFFERENT", "incomplete": "INCOMPLETE", "missing": "missing"}[status]
        name = files[0] if len(files) == 1 else f"{len(files)} files"
        lines.append(f"  {name:<22} {mark:<10} {what}" + (f" ({note})" if note else ""))
        if len(files) > 1: lines.append(f"    ({files[0]} ... {files[-1]})")      # below, so the columns stay
    problems = [r for r in results if r[1] in ("different", "incomplete")]
    needed_missing = sorted({r[0].needed for r in results if r[1] == "missing" and r[0].needed})
    lines.append("")
    if problems: lines.append(f"{len(problems)} file(s) are not the known good ones: games that use them may not work.")
    if needed_missing:
        lines.append("Missing files some games need: " + "; ".join(needed_missing) + ".")
        lines.append(f"Put them in {folder} (Insert Coin doesn't download BIOS files: they're copyrighted).")
    if not problems and not needed_missing: lines.append("Everything the games need is there.")
    lines.append("RetroArch's BIOS folder was not changed.")
    return "\n".join(lines)
