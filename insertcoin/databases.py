"""Insert Coin's own copy of the game databases, so it no longer needs RetroArch's.

The databases tell Insert Coin which game a file is (by its checksum, or an arcade set by its name) and give
each game its year and publisher. `insert-coin --databases` downloads them from the libretro buildbot (the same
file RetroArch's "Update Databases" uses) into `~/.local/share/insert-coin/database/rdb/`. Running it again
replaces the copy with the newest one; RetroArch's own folder is never changed.

When RetroArch's databases are there too, both are used, so nothing known before is lost: the scanner knows every
game either copy knows, and a game's year and publisher come from RetroArch's copy first (it holds the names
RetroArch's playlists use; newer databases rename some games, e.g. "(Beta)" -> "(Beta) (1990-09-10)") and from
Insert Coin's for the games RetroArch's doesn't know. Without RetroArch, Insert Coin's copy is all there is.

Credits: the libretro database (https://github.com/libretro/libretro-database) by the libretro team and its
contributors, built as `.rdb` files (libretro-db format, MessagePack values) and served from
https://buildbot.libretro.com. No code was copied.
"""
import hashlib, io, json, os, shutil, time, zipfile
from paths import DATABASES, RA_DATABASES

URL = "https://buildbot.libretro.com/assets/frontend/database-rdb.zip"
MANIFEST = f"{os.path.dirname(DATABASES)}/databases.json"
MAGIC = b"RARCHDB\0"                      # the first bytes of every .rdb file
MIN_FILES = 50                            # fewer than this: not the real database (a broken or wrong download)
MUST_HAVE = ("Nintendo - Nintendo Entertainment System.rdb", "MAME 2003-Plus.rdb")
TIMEOUT = 60


def rdb_paths(name):
    """The copies of the database `name` ("Nintendo - Game Boy") there are: RetroArch's first, then Insert Coin's."""
    return [p for p in (f"{RA_DATABASES}/{name}.rdb", f"{DATABASES}/{name}.rdb") if os.path.isfile(p)]


def fetch(url, progress=None):
    """Download a file in pieces; progress(bytes so far, total or 0) after each one. Returns its bytes."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "insert-coin"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        total = int(r.headers.get("Content-Length") or 0); out = io.BytesIO()
        while True:
            block = r.read(1 << 20)
            if not block: break
            out.write(block)
            if progress: progress(out.tell(), total)
    return out.getvalue()


class DatabaseError(Exception):
    pass


def unpack(data):
    """The .rdb files in the downloaded zip, as {file name: bytes}, after checking it is the real database."""
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: raise DatabaseError("the download is not a zip file")
    files = {}
    for info in z.infolist():
        name = info.filename
        if info.is_dir() or not name.endswith(".rdb"): continue
        base = os.path.basename(name)
        if base != name or base.startswith(".") or "\\" in base: continue      # only plain names: nothing outside the folder
        body = z.read(info)
        if not body.startswith(MAGIC): raise DatabaseError(f"{base} is not a game database")
        files[base] = body
    if len(files) < MIN_FILES or not all(m in files for m in MUST_HAVE):
        raise DatabaseError(f"the download holds only {len(files)} databases")
    return files


def install(download=fetch, progress=None):
    """Download the databases and put them in Insert Coin's folder, replacing an older copy only once the new one is
    complete. Returns a summary dict; raises DatabaseError (the old copy is kept) or OSError."""
    data = download(URL, progress)
    files = unpack(data)
    size = sum(map(len, files.values()))
    parent = os.path.dirname(DATABASES); os.makedirs(parent, exist_ok=True)
    if shutil.disk_usage(parent).free < size + (64 << 20):
        raise DatabaseError(f"not enough free space ({size // 2**20} MB needed)")
    new, old = f"{DATABASES}.new", f"{DATABASES}.old"
    for d in (new, old): shutil.rmtree(d, ignore_errors=True)
    os.makedirs(new)
    for name, body in files.items():
        with open(f"{new}/{name}", "wb") as f: f.write(body)
    if os.path.isdir(DATABASES): os.rename(DATABASES, old)
    os.rename(new, DATABASES)
    shutil.rmtree(old, ignore_errors=True)
    info = {"from": URL, "date": time.strftime("%Y-%m-%d %H:%M"), "files": len(files), "bytes": size,
            "sha256": hashlib.sha256(data).hexdigest()}
    with open(MANIFEST + ".tmp", "w") as f: json.dump(info, f, indent=1)
    os.replace(MANIFEST + ".tmp", MANIFEST)
    return info


def summary(info):
    ra = len([f for f in os.listdir(RA_DATABASES) if f.endswith(".rdb")]) if os.path.isdir(RA_DATABASES) else 0
    return (f"Game databases: {info['files']} downloaded ({info['bytes'] // 2**20} MB) into {DATABASES}\n"
            f"From: {info['from']}\n"
            + (f"RetroArch's {ra} databases are used too, first (they match the names in RetroArch's playlists); "
               "they are not changed." if ra else "Insert Coin can now recognise games without RetroArch."))
