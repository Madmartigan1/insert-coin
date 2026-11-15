"""Insert Coin's own game library: library.json, first filled from RetroArch's playlists.

It gives the library (library.py) the same records as the RetroArch source (retroarch.py), so either can be
used: B menu -> "Library". Each game is kept as RetroArch had it - name, file, its own core if it named one,
playlist - with each playlist's default core, and the core is chosen when the library is read, exactly as
RetroArch's playlists are read.

Favorites and Recently Played are its own too (favorites.json, history.json), copied from RetroArch's the first
time. Until RetroArch is no longer needed, every change is also written to RetroArch's lists, so switching back
to "Library: RetroArch" shows the same favorites and games."""
import json, os, time
from paths import FAVORITES, HISTORY, LIBRARY
from insertcoin.logs import log
from insertcoin.names import split_archive
from insertcoin.retroarch import Entry, RetroArch, read_json

VERSION = 1


def raw_entry(it, playlist_db):
    """A RetroArch playlist item as stored here: what it says, before any core is chosen."""
    c = it.get("core_path") or ""
    return {"label": it.get("label") or os.path.splitext(os.path.basename(split_archive(it["path"])[0]))[0],
            "path": it["path"], "core": c if c not in ("", "DETECT") else None, "db": it.get("db_name") or playlist_db}


def save(path, doc):
    """Written whole, then moved into place."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh: json.dump(doc, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def import_list(ra_path, path):
    """Copy one of RetroArch's lists (favorites or history) into Insert Coin's own, as stored; returns the count."""
    items = [raw_entry(it, it.get("db_name") or "") for it in (read_json(ra_path) or {}).get("items", []) if it.get("path")]
    save(path, {"version": VERSION, "imported_from": "retroarch", "items": items})
    log.info("Library: imported %d items from %s into %s", len(items), ra_path, path)
    return len(items)


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
    save(LIBRARY, {"version": VERSION, "imported_from": "retroarch", "imported": round(time.time()), "systems": systems})
    n = sum(len(s["games"]) for s in systems)
    log.info("Library: imported %d games in %d playlists from RetroArch into %s", n, len(systems), LIBRARY)
    return n


class OwnLibrary:
    """The source behind "Library: Insert Coin". Raises LibraryError if library.json can't be used."""
    SAVES = RetroArch.SAVES                                         # games still save where RetroArch keeps saves

    def __init__(self):
        self.ra = RetroArch()                                       # RetroArch's lists, kept up to date during 0.5
        self.doc = read_json(LIBRARY)
        if not isinstance(self.doc, dict) or self.doc.get("version") != VERSION or not isinstance(self.doc.get("systems"), list):
            raise LibraryError(f"{LIBRARY} is missing or can't be read")
        for sy in self.doc["systems"]:                              # each playlist's default core, for the lists below
            dc = sy.get("default_core"); self.ra.defaults[sy["name"] + ".lpl"] = dc if dc and os.path.exists(dc) else None
        self.favorites(); self.history()                            # copied from RetroArch's the first time; must be readable

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

    # -- favorites and history: Insert Coin's own lists, also written to RetroArch's while it is still around
    def _list(self, path, ra_path):
        """One of the own lists, copied from RetroArch's the first time; raises LibraryError if it can't be read."""
        if not os.path.exists(path): import_list(ra_path, path)
        d = read_json(path)
        if not isinstance(d, dict) or d.get("version") != VERSION or not isinstance(d.get("items"), list):
            raise LibraryError(f"{path} can't be read")
        return d

    def _entries(self, items):
        """Items whose file is still there, with their core chosen as RetroArch would."""
        out = []
        for g in items:
            if not g.get("path") or not os.path.exists(split_archive(g["path"])[0]): continue
            c = g.get("core")
            out.append(Entry(g["label"], g["path"], c if c and os.path.exists(c) else self.ra.defaults.get(g.get("db") or ""), g.get("db") or ""))
        return out

    @staticmethod
    def _item(g):
        return {"label": g.label, "path": g.path, "core": g.core or None, "db": g.db or ""}

    def _mirror(self, what, fn):
        """Write a change to RetroArch's list too; Insert Coin's own list already has it if this fails."""
        try: fn()
        except Exception as e: log.warning("Could not update RetroArch's %s: %s", what, e)

    def favorites(self):
        self.fav = self._list(FAVORITES, RetroArch.FAVORITES)
        return self._entries(self.fav["items"])

    def favorite_marks(self):
        """(paths, (db, label) pairs) of every favorite, found or not: a favorite is any copy with either."""
        items = self.fav["items"]
        return {g.get("path") for g in items}, {(g.get("db") or "", g.get("label")) for g in items}

    def set_favorite(self, g, on):
        """Star or unstar a game. Unstarring removes every copy with its path or its (db, label)."""
        items = self.fav["items"]
        same = lambda it: it.get("path") == g.path or ((it.get("db") or ""), it.get("label")) == ((g.db or ""), g.label)
        if not on: items[:] = [it for it in items if not same(it)]
        else: items.append(self._item(g))
        save(FAVORITES, self.fav)
        def ra():
            self.ra.favorites()                                     # RetroArch's list as it is now, then the change
            self.ra.set_favorite(g, on)
        self._mirror("favorites", ra)

    def history(self):
        return self._entries(self._list(HISTORY, RetroArch.HISTORY)["items"])

    def _add_own_history(self, g):
        d = self._list(HISTORY, RetroArch.HISTORY)
        d["items"] = ([self._item(g)] + [it for it in d["items"] if it.get("path") != g.path])[:200]
        save(HISTORY, d)

    def add_history(self, g):
        """Put a game at the top of Recently Played (kept to 200), here and in RetroArch's."""
        self._add_own_history(g)
        self._mirror("history", lambda: self.ra.add_history(g))

    def played_in_retroarch(self, g):
        """RetroArch ran the game and put it in its own history: only Insert Coin's needs it."""
        self._add_own_history(g)


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
