"""Game names: cleaning labels, sorting, versions, file names."""
import os, re


def split_archive(path):
    """RetroArch's 'archive.zip#file.nes' -> ('archive.zip', 'file.nes'). Only a '#' straight after .zip / .7z
    counts: folder names may contain '#' themselves (e.g. '# Translations #')."""
    m = re.search(r"(?i)\.(zip|7z)#", path)
    return (path[:m.end() - 1], path[m.end():]) if m else (path, "")


def sanitize(s):
    return re.sub(r'[&*/:`<>?\\|"]', "_", s)


def clean_title(label):
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", label).strip()
    m = re.match(r"^(.*), (The|A|An)( - .*)?$", t)          # "Legend of Zelda, The - X" -> "The Legend of Zelda - X"
    if m: t = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    return t or label


def tags(label):
    return [x.strip() for x in re.findall(r"[\(\[]([^)\]]*)[\)\]]", label)]


def sort_key(label):
    t = clean_title(label).lower()
    t = re.sub(r"^(the|a|an) ", "", t)
    return re.sub(r"[^a-z0-9 ]", "", t) or t


def letter_of(label):
    c = sort_key(label)[:1].upper()
    return c if c.isalpha() else "#"


def thumb_system(db_name):
    db = (db_name or "")[:-4] if (db_name or "").endswith(".lpl") else (db_name or "")
    return "MAME" if db.startswith("MAME") else db


def rom_stem(path):
    """The game's own file name without extension: 'a.zip#Game (USA).nes' -> 'Game (USA)'. Saves are named after it."""
    return os.path.splitext(os.path.basename(split_archive(path)[1] or path))[0]


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}

def title_key(title):
    """'The Pixel Knights' / 'Pixel Knights, The', 'Star Pilot II' / 'Star Pilot 2', 'Turbo-Tanks' / 'Turbo Tanks'."""
    t = re.sub(r"^the\s+", "", title.lower())
    words = re.findall(r"[a-z0-9]+", t)
    return " ".join(ROMAN.get(w, w) for w in words)

REGION_RANK = [(r"\b(usa|us|u|ue|ju|jp-us|world)\b", 0), (r"\b(europe|eu|e)\b", 1), (r"\b(japan|j|jp)\b", 2)]
