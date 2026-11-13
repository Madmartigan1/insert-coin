"""A game in the library."""
from insertcoin.names import clean_title, letter_of, sort_key
from insertcoin.retroarch import thumb_path


# ---------------------------------------------------------------- data
class Game:
    __slots__ = ("label", "path", "core", "db", "title", "letter", "key", "system", "versions")

    def __init__(self, label, path, core, db):
        """label: the name shown; path: the ROM; core: the core's path or None; db: its playlist ("X.lpl")."""
        self.label, self.path, self.core, self.db = label, path, core, db
        self.title = clean_title(self.label)
        self.letter = letter_of(self.label)
        self.key = sort_key(self.label)
        self.system = (self.db or "")[:-4] if (self.db or "").endswith(".lpl") else self.db
        self.versions = None                                        # other regions / translations / dumps of this game

    def thumb(self, kind):
        return thumb_path(self.db, self.label, kind)
