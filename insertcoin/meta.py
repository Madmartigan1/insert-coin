"""Year, publisher and developer, read from RetroArch's databases.

Source: the libretro database (https://github.com/libretro/libretro-database); its .rdb files are
libretro-db files (MessagePack values, https://msgpack.org), read here with our own small reader. RetroArch's copy
and Insert Coin's own (insertcoin/databases.py) are both read, RetroArch's first."""
import json, os, threading
from paths import CACHE, RA
from insertcoin.names import sanitize, split_archive
from insertcoin.databases import rdb_paths
from insertcoin.web import WebGame


# ---------------------------------------------------------------- metadata (year / publisher) from RetroArch's databases
def _rdb_load(path, binary=False):
    """Every record of a RetroArch database (.rdb). Binary fields (crc, md5, sha1) come back as None, or as
    lowercase hex with binary=True."""
    with open(path, "rb") as f: b = f.read()
    out = []

    def rd(i):
        t = b[i]; i += 1
        if t <= 0x7f: return t, i
        if 0x80 <= t <= 0x8f: return rmap(i, t & 15)
        if 0xa0 <= t <= 0xbf: n = t & 31; return b[i:i + n].decode("utf-8", "replace"), i + n
        if t == 0xc0: return None, i
        if t in (0xc2, 0xc3): return t == 0xc3, i
        if t in (0xc4, 0xc5, 0xc6):
            w = {0xc4: 1, 0xc5: 2, 0xc6: 4}[t]; n = int.from_bytes(b[i:i + w], "big"); i += w
            return (b[i:i + n].hex() if binary else None), i + n
        if t in (0xcc, 0xcd, 0xce, 0xcf):
            w = {0xcc: 1, 0xcd: 2, 0xce: 4, 0xcf: 8}[t]; return int.from_bytes(b[i:i + w], "big"), i + w
        if t in (0xd9, 0xda, 0xdb):
            w = {0xd9: 1, 0xda: 2, 0xdb: 4}[t]; n = int.from_bytes(b[i:i + w], "big"); i += w
            return b[i:i + n].decode("utf-8", "replace"), i + n
        if t in (0xde, 0xdf):
            w = 2 if t == 0xde else 4; return rmap(i + w, int.from_bytes(b[i:i + w], "big"))
        raise ValueError(t)

    def rmap(i, n):
        d = {}
        for _ in range(n):
            k, i = rd(i); v, i = rd(i); d[k] = v
        return d, i
    i = 16
    while i < len(b) and b[i] != 0xc0:
        r, i = rd(i)
        if isinstance(r, dict): out.append(r)
    return out


class Meta:
    def __init__(self, dbs):
        self.data = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._load, args=(list(dbs),), daemon=True).start()

    def _load(self, dbs):
        os.makedirs(f"{CACHE}/meta", exist_ok=True)
        for db in dbs:
            srcs = rdb_paths(db); cp = f"{CACHE}/meta/{sanitize(db)}.v2.json"   # v2: + developer
            if not srcs: continue
            key = " | ".join(srcs)                    # which copies it was built from (RetroArch's first)
            try:
                m = None
                if os.path.exists(cp) and os.path.getmtime(cp) >= max(map(os.path.getmtime, srcs)):
                    with open(cp) as f: m = json.load(f)
                    if m.get("_src", f"{RA}/database/rdb/{db}.rdb") != key: m = None   # other copies now
                if m is None:
                    m = {"_src": key}
                    for src in srcs:                  # the first copy that knows a game gives its info
                        for e in _rdb_load(src):
                            yr = e.get("releaseyear"); pub = e.get("publisher") or e.get("developer")
                            if not (yr or pub): continue
                            dev = e.get("developer") or ""
                            v = [yr or "", pub or "", dev if dev != pub else ""]   # shown: year, publisher
                            if e.get("name"): m.setdefault("n:" + e["name"], v)
                            if e.get("rom_name"): m.setdefault("r:" + os.path.splitext(e["rom_name"])[0], v)
                    with open(cp, "w") as f: json.dump(m, f)
                    old = f"{CACHE}/meta/{sanitize(db)}.json"                   # the cache before v2
                    if os.path.exists(old): os.remove(old)
                with self.lock: self.data[db] = m
            except Exception:
                pass

    def get(self, g):
        if isinstance(g, WebGame): return g.info                     # year / publisher from browser_games.json
        db = g.system or ""
        with self.lock: m = self.data.get(db)
        if not m: return None
        rom = os.path.splitext(os.path.basename(split_archive(g.path)[0]))[0]
        return m.get("n:" + g.label) or m.get("r:" + rom)
