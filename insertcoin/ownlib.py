"""Insert Coin's own game library: library.json, first filled from RetroArch's playlists.

It gives the library (library.py) the same records as the RetroArch source (retroarch.py), so either can be
used: B menu -> "Library". Each game is kept as RetroArch had it - name, file, its own core if it named one,
playlist - with each playlist's default core, and the core is chosen when the library is read, exactly as
RetroArch's playlists are read. Favorites and Recently Played still come from RetroArch for now."""
import json, os, time
from paths import LIBRARY
from insertcoin.logs import log
from insertcoin.names import split_archive
from insertcoin.retroarch import Entry, RetroArch, read_json

VERSION = 1


def raw_entry(it, playlist_db):
    """A RetroArch playlist item as stored here: what it says, before any core is chosen."""
    c = it.get("core_path") or ""
    return {"label": it.get("label") or os.path.splitext(os.path.basename(split_archive(it["path"])[0]))[0],
            "path": it["path"], "core": c if c not in ("", "DETECT") else None, "db": it.get("db_name") or playlist_db}


def import_retroarch(ra=None):
    """Read every RetroArch playlist into library.json; returns the number of games."""
    ra = ra or RetroArch()
    systems = []
    for f in sorted(os.listdir(ra.PLAYLISTS) if os.path.isdir(ra.PLAYLISTS) else []):
        if not f.endswith(".lpl"): continue
        d = read_json(f"{ra.PLAYLISTS}/{f}")
        if not d: continue
        systems.append({"name": f[:-4], "default_core": d.get("default_core_path") or None,
                        "games": [raw_entry(it, f) for it in d.get("items", []) if it.get("path")]})
    doc = {"version": VERSION, "imported_from": "retroarch", "imported": round(time.time()), "systems": systems}
    os.makedirs(os.path.dirname(LIBRARY), exist_ok=True)
    tmp = LIBRARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(doc, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, LIBRARY)
    n = sum(len(s["games"]) for s in systems)
    log.info("Library: imported %d games in %d playlists from RetroArch into %s", n, len(systems), LIBRARY)
    return n


class OwnLibrary:
    """The source behind "Library: Insert Coin". Raises LibraryError if library.json can't be used."""
    SAVES = RetroArch.SAVES                                         # games still save where RetroArch keeps saves

    def __init__(self):
        self.ra = RetroArch()                                       # favorites and history, for now
        self.doc = read_json(LIBRARY)
        if not isinstance(self.doc, dict) or self.doc.get("version") != VERSION or not isinstance(self.doc.get("systems"), list):
            raise LibraryError(f"{LIBRARY} is missing or can't be read")

    def playlists(self):
        """[(name, [Entry, ...])], as RetroArch.playlists() gives them: an entry's own core only if installed."""
        out = []
        for s in self.doc["systems"]:
            dc = s.get("default_core")
            default = dc if dc and os.path.exists(dc) else None
            self.ra.defaults[s["name"] + ".lpl"] = default             # favorites and history use them too
            out.append((s["name"], [Entry(g["label"], g["path"], g["core"] if g.get("core") and os.path.exists(g["core"]) else default,
                                          g["db"]) for g in s["games"]]))
        return out

    def favorites(self): return self.ra.favorites()
    def favorite_marks(self): return self.ra.favorite_marks()
    def set_favorite(self, g, on): return self.ra.set_favorite(g, on)
    def history(self): return self.ra.history()
    def add_history(self, g): return self.ra.add_history(g)


class LibraryError(Exception):
    pass


def open_source(kind):
    """The source for the "library" setting: ("insertcoin" or "retroarch", source, a note for the user or None).
    The note is "imported" the first time (the app words it, counting the games it shows) or a fallback message.
    Insert Coin's own library is imported from RetroArch the first time; if it can't be used, RetroArch is."""
    if kind != "insertcoin": return "retroarch", RetroArch(), None
    note = None
    try:
        if not os.path.exists(LIBRARY):
            import_retroarch(); note = "imported"
        return "insertcoin", OwnLibrary(), note
    except Exception as e:
        log.warning("Insert Coin's own library can't be used (%s): using RetroArch's playlists", e)
        return "retroarch", RetroArch(), "Insert Coin's library couldn't be read - showing RetroArch's playlists"
