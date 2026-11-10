"""A game in the library."""
import os
from paths import RA
from insertcoin.names import clean_title, letter_of, sanitize, sort_key, split_archive, thumb_system


# ---------------------------------------------------------------- data
class Game:
    __slots__ = ("label", "path", "core", "db", "title", "letter", "key", "system", "versions")

    def __init__(self, it, playlist_db, default_core):
        self.label = it.get("label") or os.path.splitext(os.path.basename(split_archive(it["path"])[0]))[0]
        self.path = it["path"]
        c = it.get("core_path") or ""
        self.core = c if c not in ("", "DETECT") and os.path.exists(c) else default_core
        self.db = it.get("db_name") or playlist_db
        self.title = clean_title(self.label)
        self.letter = letter_of(self.label)
        self.key = sort_key(self.label)
        self.system = (self.db or "")[:-4] if (self.db or "").endswith(".lpl") else self.db
        self.versions = None                                        # other regions / translations / dumps of this game

    def thumb(self, kind):
        return f"{RA}/thumbnails/{thumb_system(self.db)}/{kind}/{sanitize(self.label)}.png"
