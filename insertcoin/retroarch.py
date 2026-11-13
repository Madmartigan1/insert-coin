"""RetroArch as a source of games: its playlists, favorites, history, thumbnails and save folder.

This is the only module that knows RetroArch's file formats. The library (library.py) asks it for plain
records - label, path, core, db - and never reads RetroArch's files itself, so another source (Insert Coin's
own library, from 0.5) can take its place."""
import json, os
from typing import NamedTuple
from paths import RA
from insertcoin.cores import core_short
from insertcoin.names import sanitize, split_archive, thumb_system


class Entry(NamedTuple):
    label: str                  # the name shown (RetroArch's label, else the ROM's file name)
    path: str                   # the ROM, "archive.zip#inner.ext" for a file inside an archive
    core: object                # the core's full path, or None when none is set
    db: str                     # the playlist it belongs to ("Nintendo - Game Boy.lpl")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return None


def write_json(path, d):
    """Written whole, then moved into place, so RetroArch never sees half a file."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)
    os.replace(tmp, path)


def entry(it, playlist_db, default_core):
    """A playlist item as an Entry. An item's own core counts only if it's set and installed."""
    label = it.get("label") or os.path.splitext(os.path.basename(split_archive(it["path"])[0]))[0]
    c = it.get("core_path") or ""
    core = c if c not in ("", "DETECT") and os.path.exists(c) else default_core
    return Entry(label, it["path"], core, it.get("db_name") or playlist_db)


def thumb_path(db, label, kind):
    """Where RetroArch keeps a game's picture (kind: Named_Boxarts, Named_Titles, Named_Snaps)."""
    return f"{RA}/thumbnails/{thumb_system(db)}/{kind}/{sanitize(label)}.png"


class RetroArch:
    PLAYLISTS = f"{RA}/playlists"
    FAVORITES = f"{RA}/content_favorites.lpl"
    HISTORY = f"{RA}/content_history.lpl"
    SAVES = f"{RA}/saves"

    def __init__(self):
        self.defaults = {}                                          # "Name.lpl" -> its default core, if installed
        self.fav_doc = {"version": "1.5", "items": []}              # favorites as last read, kept whole for writing

    def playlists(self):
        """Every playlist: [(name, [Entry, ...])], by file name. Items without a path are skipped."""
        pls = {}
        for f in sorted(os.listdir(self.PLAYLISTS) if os.path.isdir(self.PLAYLISTS) else []):
            if f.endswith(".lpl"):
                d = read_json(f"{self.PLAYLISTS}/{f}")
                if d: pls[f[:-4]] = d
        for name, d in pls.items():
            dc = d.get("default_core_path") or ""
            self.defaults[name + ".lpl"] = dc if dc and os.path.exists(dc) else None
        return [(name, [entry(it, name + ".lpl", self.defaults[name + ".lpl"]) for it in d.get("items", []) if it.get("path")])
                for name, d in pls.items()]

    def _entries(self, items):
        """Favorites / history items whose file is still there."""
        out = []
        for it in items:
            if not it.get("path") or not os.path.exists(split_archive(it["path"])[0]): continue
            db = it.get("db_name") or ""
            out.append(entry(it, db, self.defaults.get(db)))
        return out

    # -- favorites: RetroArch's content_favorites.lpl
    def favorites(self):
        """Read the favorites again (RetroArch may have changed them while a game ran): [Entry]."""
        self.fav_doc = read_json(self.FAVORITES) or {"version": "1.5", "items": []}
        return self._entries(self.fav_doc.get("items", []))

    def favorite_marks(self):
        """(paths, (db, label) pairs) of every favorite, found or not: a favorite is any copy with either."""
        items = self.fav_doc.get("items", [])
        return {it.get("path") for it in items}, {(it.get("db_name") or "", it.get("label")) for it in items}

    def set_favorite(self, g, on):
        """Star or unstar a game, then save. Unstarring removes every copy with its path or its (db, label)."""
        items = self.fav_doc.setdefault("items", [])
        same = lambda it: it.get("path") == g.path or ((it.get("db_name") or ""), it.get("label")) == ((g.db or ""), g.label)
        if not on:
            items[:] = [it for it in items if not same(it)]
        else:
            items.append({"path": g.path, "label": g.label, "core_path": g.core or "DETECT",
                          "core_name": "DETECT" if not g.core else core_short(g.core),
                          "crc32": "00000000|crc", "db_name": g.db or ""})
        self.fav_doc.setdefault("version", "1.5")
        write_json(self.FAVORITES, self.fav_doc)

    # -- history: RetroArch's content_history.lpl, newest first
    def history(self):
        return self._entries((read_json(self.HISTORY) or {"items": []}).get("items", []))

    def add_history(self, g):
        """Put a game at the top of the history (kept to 200)."""
        d = read_json(self.HISTORY) or {"version": "1.5", "items": []}
        items = [it for it in d.get("items", []) if it.get("path") != g.path]
        items.insert(0, {"path": g.path, "label": g.label, "core_path": g.core,
                         "core_name": core_short(g.core), "crc32": "DETECT", "db_name": g.db or ""})
        d["items"] = items[:200]; d.setdefault("version", "1.5")
        write_json(self.HISTORY, d)
