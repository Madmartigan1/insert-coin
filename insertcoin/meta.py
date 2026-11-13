"""Year and publisher, read from RetroArch's databases."""
import json, os, threading
from paths import CACHE, RA
from insertcoin.names import sanitize, split_archive
from insertcoin.web import WebGame


# ---------------------------------------------------------------- metadata (year / publisher) from RetroArch's databases
def _rdb_load(path):
    b = open(path, "rb").read(); out = []

    def rd(i):
        t = b[i]; i += 1
        if t <= 0x7f: return t, i
        if 0x80 <= t <= 0x8f: return rmap(i, t & 15)
        if 0xa0 <= t <= 0xbf: n = t & 31; return b[i:i + n].decode("utf-8", "replace"), i + n
        if t == 0xc0: return None, i
        if t in (0xc2, 0xc3): return t == 0xc3, i
        if t in (0xc4, 0xc5, 0xc6):
            w = {0xc4: 1, 0xc5: 2, 0xc6: 4}[t]; n = int.from_bytes(b[i:i + w], "big"); i += w; return None, i + n
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
            src = f"{RA}/database/rdb/{db}.rdb"; cp = f"{CACHE}/meta/{sanitize(db)}.json"
            if not os.path.exists(src): continue
            try:
                if os.path.exists(cp) and os.path.getmtime(cp) >= os.path.getmtime(src):
                    m = json.load(open(cp))
                else:
                    m = {}
                    for e in _rdb_load(src):
                        yr = e.get("releaseyear"); pub = e.get("publisher") or e.get("developer")
                        if not (yr or pub): continue
                        v = [yr or "", pub or ""]
                        if e.get("name"): m.setdefault("n:" + e["name"], v)
                        if e.get("rom_name"): m.setdefault("r:" + os.path.splitext(e["rom_name"])[0], v)
                    json.dump(m, open(cp, "w"))
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
