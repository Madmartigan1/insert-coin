"""The game scanner: finds the games in your folders and recognises them, without changing anything (yet).

Console games are recognised by their checksum (CRC32), read from a zip's index or 7z's list without unpacking,
or computed for a loose file, and looked up in RetroArch's databases. Arcade games are zips named after their
set ("gaiden.zip"), recognised by that name. What the scan finds is compared with the library:

  listed     already in the library
  copy       the same game as one already listed (same checksum, or the same arcade set) - never added twice
  new        recognised, not listed yet
  by_type    not in the database, but its file type says which system it is for (translations, hacks...);
             also arcade zips whose set name no database knows (old set names, split clones): they go to the
             MAME 2003-Plus list under their set name if a test start works
  not_games  BIOS files and enhancement-chip dumps: in the databases, but not games
  unknown    a ROM-like file that couldn't be placed, or an archive that couldn't be read

New games are only reported here; they are test-started before anything is added (the next step).
Results are cached by file size and time, so a scan with nothing changed only lists the folders.

Sources: checksums are looked up in the libretro database (RetroArch's .rdb files,
https://github.com/libretro/libretro-database); the iNES header (NESdev wiki, https://www.nesdev.org/wiki/INES),
the SNES copier header and the Super Magic Drive (.smd) interleave follow public community documentation.
No code was copied."""
import json, os, re, subprocess, time, zipfile, zlib
from collections import Counter
from paths import APPDIR, CACHE, DATABASES, LIBRARY, RA, RA_DATABASES
from insertcoin.logs import log
from insertcoin.meta import _rdb_load
from insertcoin.names import split_archive
from insertcoin.retroarch import RetroArch, read_json

VERSION = 3
REPORT = f"{APPDIR}/scan-report.json"
STORE = f"{CACHE}/scan.json"                                            # file -> size, time, checksums

NES, SNES = "Nintendo - Nintendo Entertainment System", "Nintendo - Super Nintendo Entertainment System"
# file type -> the system it is for (None: used by several systems, so only its checksum can tell)
EXT_SYSTEM = {
    ".nes": NES, ".unf": NES, ".unif": NES, ".sfc": SNES, ".smc": SNES, ".fig": SNES, ".swc": SNES,
    ".n64": "Nintendo - Nintendo 64", ".z64": "Nintendo - Nintendo 64", ".v64": "Nintendo - Nintendo 64",
    ".gb": "Nintendo - Game Boy", ".gbc": "Nintendo - Game Boy Color", ".gba": "Nintendo - Game Boy Advance",
    ".md": "Sega - Mega Drive - Genesis", ".gen": "Sega - Mega Drive - Genesis", ".smd": "Sega - Mega Drive - Genesis",
    ".32x": "Sega - 32X", ".pce": "NEC - PC Engine - TurboGrafx 16", ".ngp": "SNK - Neo Geo Pocket",
    ".ngc": "SNK - Neo Geo Pocket Color", ".a26": "Atari - 2600", ".pbp": "Sony - PlayStation", ".bin": None,
}
NO_CHECKSUM = {".pbp"}                                                  # disc images: hundreds of MB, not matched by CRC
TEXT_TOO = {".md"}                    # also a text file's extension (README.md): a loose one counts only if recognised


def second_checksum(ext, data):
    """The checksum the database knows a dump by when the file's own differs: NES ROMs without their 16-byte
    header (old dumps carry odd headers), Super Nintendo ROMs without a copier's 512-byte header, Mega Drive .smd
    files turned back into plain order (they are stored in interleaved 16 KB blocks after a 512-byte header).
    None for other files."""
    if ext == ".nes" and data[:4] == b"NES\x1a": return f"{zlib.crc32(data[16:]) & 0xffffffff:08x}"
    if ext in SNES_EXTS and len(data) % 1024 == 512: return f"{zlib.crc32(data[512:]) & 0xffffffff:08x}"
    if ext == ".smd":
        raw = data[512:] if len(data) % 16384 == 512 else data
        out = bytearray(raw)
        for b in range(0, len(raw) - len(raw) % 16384, 16384):
            blk = raw[b:b + 16384]; out[b:b + 16384:2] = blk[8192:]; out[b + 1:b + 16384:2] = blk[:8192]
        return f"{zlib.crc32(out) & 0xffffffff:08x}"
    return None
# set names are looked up in these databases, in this order -> the playlist they go to (plain MAME 2003's sets play
# from the MAME 2003-Plus playlist, with that core named per game)
ARCADE = (("MAME 2003-Plus", "MAME 2003-Plus"), ("FBNeo - Arcade Games", "FBNeo - Arcade Games"),
          ("MAME 2003", "MAME 2003-Plus"))
ARCADE_PLAYLISTS = {pl for _, pl in ARCADE}
UNKNOWN_SETS = "MAME 2003-Plus"                 # where arcade sets no database names go (by their set name), if they start


NOT_A_GAME = re.compile(r"\bBIOS\b|\(Enhancement Chip\)", re.I)


def console_systems():
    return sorted({s for s in EXT_SYSTEM.values() if s})


def load_databases(rdb_dir=None):
    """(crc -> [(system, name)], set name -> (arcade playlist, name)) from the game databases: RetroArch's and
    Insert Coin's own copy together (a game known to either is known; RetroArch's names first), or those in rdb_dir."""
    folders = [rdb_dir] if rdb_dir else [RA_DATABASES, DATABASES]     # every RetroArch database before any of ours
    by_crc, sets, known = {}, {}, {}                    # known: system -> checksums an earlier copy gave it
    for folder in folders:
        for sy in console_systems():
            p = f"{folder}/{sy}.rdb"
            if not os.path.isfile(p): continue
            here, before = set(), known.setdefault(sy, set())
            for r in _rdb_load(p, binary=True):
                if r.get("crc") and r.get("name") and r["crc"] not in before:
                    by_crc.setdefault(r["crc"], []).append((sy, r["name"])); here.add(r["crc"])
            before |= here
        for db, playlist in ARCADE:
            p = f"{folder}/{db}.rdb"
            if not os.path.isfile(p): continue
            for r in _rdb_load(p):
                rn = (r.get("rom_name") or "").lower()
                if rn.endswith(".zip") and r.get("name"): sets.setdefault(rn[:-4], (playlist, r["name"]))
    return by_crc, sets


def listed_games():
    """Every game in the library, as (playlist, path): Insert Coin's library if it has one, else RetroArch's."""
    doc = read_json(LIBRARY)
    if isinstance(doc, dict) and isinstance(doc.get("systems"), list):
        return [(s["name"], g["path"]) for s in doc["systems"] for g in s.get("games", [])]
    return [(name, e.path) for name, entries in RetroArch().playlists() for e in entries]


def default_roots(paths):
    """The folder that holds every listed game (the deepest one they share), unless that is the home folder or
    above: then each playlist's own folders."""
    dirs = sorted({os.path.dirname(split_archive(p)[0]) for p in paths})
    if not dirs: return []
    common, home = os.path.commonpath(dirs), os.path.expanduser("~")
    if not (home == common or home.startswith(common.rstrip(os.sep) + os.sep)): return [common]
    out = []
    for d in dirs:
        if not any(d == r or d.startswith(r + os.sep) for r in out): out.append(d)
    return out


def checksum(path):
    crc = 0
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): crc = zlib.crc32(block, crc)
    return f"{crc & 0xffffffff:08x}"


SNES_EXTS = {".sfc", ".smc", ".fig", ".swc"}
NEEDS_DATA = {".nes", ".smd"}                                           # their second checksum needs the data itself


def needs_data(ext, size):
    """Whether a file's second checksum needs its data (SNES: only those with a copier header)."""
    return ext in NEEDS_DATA or (ext in SNES_EXTS and size % 1024 == 512)


def read_file(path):
    """What a file holds: {"members": [[name, crc], ...]} for an archive, {"crc": ...} for a ROM; may raise."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".zip":
        try:
            with zipfile.ZipFile(path) as z:
                return {"members": [[i.filename, f"{i.CRC:08x}",
                                     second_checksum(os.path.splitext(i.filename)[1].lower(), z.read(i))
                                     if needs_data(os.path.splitext(i.filename)[1].lower(), i.file_size) else None]
                                    for i in z.infolist() if not i.is_dir()]}
        except zipfile.BadZipFile:
            pass                                                    # some zips only 7z can read: try it below
    if ext in (".zip", ".7z"):
        out = subprocess.run(["7z", "l", "-slt", "-ba", path], capture_output=True, text=True, timeout=120)
        if out.returncode: raise OSError(f"7z could not list it (exit {out.returncode})")
        members, name = [], None
        for line in out.stdout.splitlines():
            if line.startswith("Path = "): name = line[7:]
            elif line.startswith("CRC = ") and name is not None: members.append([name, line[6:].strip().lower(), None]); name = None
        for m in members:                                               # (rare: .nes / .smd inside a 7z)
            e = os.path.splitext(m[0])[1].lower()
            if e in NEEDS_DATA or e in SNES_EXTS:
                data = subprocess.run(["7z", "e", "-so", path, m[0]], capture_output=True, timeout=120).stdout
                m[2] = second_checksum(e, data)
        return {"members": members}
    if ext in NO_CHECKSUM: return {"crc": None}
    if needs_data(ext, os.path.getsize(path)):
        with open(path, "rb") as f: data = f.read()
        return {"crc": f"{zlib.crc32(data) & 0xffffffff:08x}", "alt": second_checksum(ext, data)}
    return {"crc": checksum(path)}


def walk(roots):
    """Every zip, 7z or ROM-type file under the folders (hidden folders skipped), with its size and time."""
    for root in roots:
        for d, subs, files in os.walk(root):
            subs[:] = sorted(s for s in subs if not s.startswith("."))
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in (".zip", ".7z") or ext in EXT_SYSTEM:
                    p = os.path.join(d, f)
                    try: st = os.stat(p)
                    except OSError: continue
                    yield p, st.st_size, int(st.st_mtime)


def scan(roots=None, dbs=None, listed=None, progress=None):
    """Scan the folders and compare with the library; returns the report (also saved in scan-report.json)."""
    t0 = time.time()
    listed = listed_games() if listed is None else listed
    roots = roots or default_roots([p for _, p in listed])
    by_crc, sets = dbs or load_databases()
    old = read_json(STORE) or {}
    store = old.get("files", {}) if old.get("version") == VERSION else {}
    fresh, read = {}, 0
    listed_arcade = {p: sy for sy, p in listed if sy in ARCADE_PLAYLISTS}

    found = []                                                          # (path, kind, info)
    unknown, unreadable = [], []
    for n, (p, size, mtime) in enumerate(walk(roots)):
        if progress and n % 500 == 0: progress(n)
        c = store.get(p)
        if not c or c.get("size") != size or c.get("mtime") != mtime:
            try: c = dict(read_file(p), size=size, mtime=mtime)
            except Exception as e:
                unreadable.append({"path": p, "error": str(e)[:200]}); continue
            read += 1
        fresh[p] = c
        if "members" in c:
            set_name = os.path.splitext(os.path.basename(p))[0].lower()
            roms = [(m, (crc, alt)) for m, crc, alt in c["members"] if os.path.splitext(m)[1].lower() in EXT_SYSTEM]
            console = any(EXT_SYSTEM[os.path.splitext(m)[1].lower()] or crcs[0] in by_crc for m, crcs in roms)
            # an arcade set: listed as one, or a zip with no console ROM in it (arcade chips are often .bin files).
            # A zip holding just one file of a type several systems use (a Mega Drive .bin) whose name is no arcade
            # set is decided below, by what else is in its folder ("lone")
            lone = (len(c["members"]) == 1 and len(roms) == 1 and EXT_SYSTEM[os.path.splitext(roms[0][0])[1].lower()] is None
                    and set_name not in sets and p not in listed_arcade)
            if lone and not console:
                found.append((p, "lone", roms[0]))
            elif p.lower().endswith(".zip") and (p in listed_arcade or not console):
                found.append((p, "arcade", None))                       # an arcade set (its chips may be .bin files)
            else:
                for m, crc in roms: found.append((f"{p}#{m}", os.path.splitext(m)[1].lower(), crc))
        else:
            ext = os.path.splitext(p)[1].lower()
            if ext in TEXT_TOO and not any(x in by_crc for x in (c.get("crc"), c.get("alt"))): continue
            found.append((p, ext, (c.get("crc"), c.get("alt"))))

    listed_paths = {p: sy for sy, p in listed}
    folder_system = {}                                                  # folder -> the system most games listed in it are for
    for sy, p in listed:
        if sy not in ARCADE_PLAYLISTS: folder_system.setdefault(os.path.dirname(split_archive(p)[0]), Counter())[sy] += 1
    # folders without listed games (a library built from scratch): the system most games recognised there are for
    recognised_in = {}
    arcade_in = Counter(os.path.dirname(p) for p, kind, _ in found if kind == "arcade")
    for p, kind, crcs in found:
        if kind in ("arcade", "lone"): continue
        d = os.path.dirname(split_archive(p)[0])
        if d in folder_system: continue
        hits = next((by_crc[x] for x in crcs if x and x in by_crc), [])
        sy = EXT_SYSTEM.get(kind) or (hits[0][0] if len({h[0] for h in hits}) == 1 else None)
        if sy and hits: recognised_in.setdefault(d, Counter())[sy] += 1
    for d, c in recognised_in.items(): folder_system[d] = c
    def lone_is_console(p):                     # its folder is mostly console games (not an arcade romset folder)
        near = folder_system.get(os.path.dirname(p))
        return bool(near) and sum(near.values()) > arcade_in[os.path.dirname(p)]
    found = [((f"{p}#{info[0]}", os.path.splitext(info[0])[1].lower(), info[1]) if lone_is_console(p) else (p, "arcade", None))
             if kind == "lone" else (p, kind, info) for p, kind, info in found]
    rows = []                                   # (path, kind, its checksums, system, name in the database, set name)
    for p, kind, crcs in found:
        if kind == "arcade":
            set_name = os.path.splitext(os.path.basename(p))[0].lower()
            sy, name = (listed_paths[p], None) if p in listed_paths else sets.get(set_name, (UNKNOWN_SETS, None))
            rows.append((p, kind, (), sy, name, set_name)); continue
        crcs = tuple(x for x in crcs if x)
        hits = next((by_crc[x] for x in crcs if x in by_crc), [])      # the checksum the database knows, if either
        typed = EXT_SYSTEM.get(kind)
        if not typed and kind in EXT_SYSTEM:                            # e.g. ".bin": the system of the games beside it
            near = folder_system.get(os.path.dirname(split_archive(p)[0]))
            typed = near.most_common(1)[0][0] if near else None
        hit = next((h for h in hits if h[0] == typed), hits[0] if hits else None)
        sy = listed_paths.get(p) or (hit[0] if hit else typed)
        rows.append((p, kind, crcs, sy, hit[1] if hit else None, None))

    # the same game twice: the same arcade set, or a checksum in common (either one) on the same system
    first = {}                                                          # (system, set or checksum) -> the path kept
    def keys(sy, kind, crcs, set_name):                                 # a set is one game in either arcade playlist
        return [("arcade", set_name)] if kind == "arcade" else [(sy, c) for c in crcs]
    for p, kind, crcs, sy, name, set_name in rows:                      # listed games first: they are the ones kept
        if p in listed_paths:
            for k in keys(sy, kind, crcs, set_name): first.setdefault(k, p)
    systems = {}
    for p, kind, crcs, sy, name, set_name in rows:
        if p in listed_paths:
            systems.setdefault(sy, _empty())["listed"] += 1; continue
        if not sy:
            unknown.append({"path": p, "why": "not an arcade set Insert Coin knows" if kind == "arcade"
                            else "not in the database, and its file type is used by several systems"}); continue
        s = systems.setdefault(sy, _empty())
        ks = keys(sy, kind, crcs, set_name)
        archive, inner = split_archive(p)
        if NOT_A_GAME.search(name or os.path.basename(inner or archive)):      # its database name, else its file name
            s["not_games"].append({"path": p, "name": name or os.path.basename(inner or archive)}); continue
        same = next((first[k] for k in ks if k in first), None)
        if same:
            s["copies"].append({"path": p, "of": same}); continue
        for k in ks: first[k] = p
        (s["new"] if name else s["by_type"]).append({"path": p, "name": name, "crc": crcs[0] if crcs else None})

    report = {"version": VERSION, "scanned": round(t0), "took": round(time.time() - t0, 1), "roots": roots,
              "files": len(fresh), "files_read": read, "systems": systems, "unknown": unknown, "unreadable": unreadable}
    for path, doc in ((STORE, {"version": VERSION, "files": fresh}), (REPORT, report)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as fh: json.dump(doc, fh, indent=1, ensure_ascii=False)
        os.replace(path + ".tmp", path)
    log.info("Scan: %d files (%d read) in %.1f s; new %d, by file type %d, copies %d, unknown %d, unreadable %d",
             len(fresh), read, report["took"], *(sum(len(s[k]) for s in systems.values()) for k in ("new", "by_type", "copies")),
             len(unknown), len(unreadable))
    return report


def _empty():
    return {"listed": 0, "new": [], "by_type": [], "copies": [], "not_games": []}


def summary(report):
    """The report as a few lines of text, one per system."""
    from insertcoin.systems import FRIENDLY
    w = max([len(FRIENDLY.get(s, (s,))[0]) for s in report["systems"]] + [6])
    lines = [f"Scanned {report['files']:,} files in {', '.join(report['roots'])} "
             f"({report['files_read']:,} read, {report['took']} s). Nothing was changed.", "",
             f"{'System':<{w}}  {'listed':>7}  {'new':>6}  {'by type':>7}  {'copies':>7}"]
    for sy in sorted(report["systems"], key=lambda s: FRIENDLY.get(s, (s,))[0]):
        s = report["systems"][sy]
        lines.append(f"{FRIENDLY.get(sy, (sy,))[0]:<{w}}  {s['listed']:>7,}  {len(s['new']):>6,}  {len(s['by_type']):>7,}  {len(s['copies']):>7,}")
    lines += ["", f"BIOS and chip files (not games): {sum(len(s['not_games']) for s in report['systems'].values()):,}   "
              f"Unknown: {len(report['unknown']):,}   Unreadable: {len(report['unreadable']):,}",
              f"Full list: {REPORT}"]
    return "\n".join(lines)
