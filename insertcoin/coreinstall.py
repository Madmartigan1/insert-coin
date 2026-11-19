"""Insert Coin's own emulator cores (0.6 step 1): `insert-coin --cores` puts a copy of every core the built-in
player runs in ~/.local/share/insert-coin/cores/, and the built-in player uses those copies from then on.

Each core is copied from RetroArch's core folder when RetroArch has it, so the versions already played and tested
stay the same; a core RetroArch doesn't have is downloaded from the libretro buildbot, where RetroArch gets its
cores too. Every copy is test-loaded in a separate process before it is used, and must report the name the core
table expects; a copy that fails is removed again. RetroArch's own folder is never changed, and RetroArch keeps
using its own cores. Cores already in Insert Coin's folder are kept as they are (delete one to replace it).

Insert Coin itself doesn't ship cores: several of them don't allow commercial use, so they come from their own
publisher's server, at the user's request."""
import hashlib, io, json, os, platform, shutil, subprocess, sys, time, urllib.request, zipfile
from paths import CORES_DIR, RA
from insertcoin.cores import CORES, core_file
from insertcoin.logs import log

BUILDBOT = "https://buildbot.libretro.com/nightly/linux/{arch}/latest/{file}.zip"
ARCHES = {"x86_64": "x86_64", "AMD64": "x86_64"}                 # this machine's name -> the buildbot's folder
MANIFEST = f"{CORES_DIR}/cores.json"                              # where each copy came from, its version and hash
TIMEOUT = 120                                                     # seconds for one download

# Loads a core and prints the name and version it reports. Run in its own process: a broken file can't crash us.
_PROBE = r"""
import ctypes as C, sys
class Info(C.Structure):
    _fields_ = [("library_name", C.c_char_p), ("library_version", C.c_char_p), ("valid_extensions", C.c_char_p),
                ("need_fullpath", C.c_bool), ("block_extract", C.c_bool)]
lib = C.CDLL(sys.argv[1]); i = Info(); lib.retro_get_system_info(C.byref(i))
print((i.library_name or b"").decode(errors="replace")); print((i.library_version or b"").decode(errors="replace"))
"""


def own_core(path):
    """The core file to load in the built-in player: Insert Coin's own copy when it has one, else the path given."""
    mine = f"{CORES_DIR}/{core_file(path)}"
    return mine if path and os.path.isfile(mine) else path


def wanted():
    """The cores Insert Coin installs: those the built-in player runs (N64's stays with RetroArch for now)."""
    return [f for f, c in CORES.items() if c.builtin]


def check(path):
    """Load a core in a separate process. Returns (name, version), or None if it can't be loaded."""
    try:
        r = subprocess.run([sys.executable, "-I", "-c", _PROBE, path], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired): return None
    out = r.stdout.splitlines()
    return (out[0], out[1] if len(out) > 1 else "") if r.returncode == 0 and out else None


def fetch(url):
    """Download a file; returns its bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "insert-coin"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r: return r.read()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def install(checker=check, download=fetch, progress=None, ra_cores=None):
    """Put a copy of every wanted core in Insert Coin's folder. Returns [(file, outcome, detail)], where outcome is
    "kept", "copied", "downloaded" or "failed"."""
    ra_cores = ra_cores or f"{RA}/cores"
    os.makedirs(CORES_DIR, exist_ok=True)
    try:
        with open(MANIFEST) as f: manifest = json.load(f)
        if not isinstance(manifest, dict): manifest = {}
    except (OSError, ValueError): manifest = {}
    arch = ARCHES.get(platform.machine())
    results = []
    for n, file in enumerate(wanted(), 1):
        if progress: progress(n, len(wanted()), file)
        name = CORES[file].name
        dest, tmp = f"{CORES_DIR}/{file}", f"{CORES_DIR}/.{file}.part"
        if os.path.isfile(dest):
            got = checker(dest)
            if got and got[0] == name: results.append((file, "kept", got[1])); continue
            results.append((file, "failed", f"the copy in {CORES_DIR} doesn't load as {name}; delete it to replace it"))
            continue
        try:
            if os.path.isfile(f"{ra_cores}/{file}"):
                shutil.copy2(f"{ra_cores}/{file}", tmp); source, outcome = "RetroArch's copy", "copied"
            elif arch:
                url = BUILDBOT.format(arch=arch, file=file)
                with zipfile.ZipFile(io.BytesIO(download(url))) as z, open(tmp, "wb") as f: f.write(z.read(file))
                source, outcome = url, "downloaded"
            else:
                results.append((file, "failed", f"not in RetroArch's folder, and there are no downloads for {platform.machine()}"))
                continue
        except Exception as e:                                        # network, a damaged zip, a full disk...
            if os.path.exists(tmp): os.remove(tmp)
            results.append((file, "failed", f"couldn't get it: {e}")); continue
        got = checker(tmp)
        if not got or got[0] != name:
            os.remove(tmp)
            results.append((file, "failed", f"it doesn't load as {name}" + (f" (it says {got[0]})" if got else ""))); continue
        os.replace(tmp, dest)
        manifest[file] = {"name": name, "version": got[1], "from": source, "sha256": sha256(dest),
                          "installed": time.strftime("%Y-%m-%d %H:%M")}
        results.append((file, outcome, got[1]))
        log.info("Core %s: %s (%s, from %s)", outcome, file, got[1], source)
    with open(MANIFEST + ".tmp", "w") as f: json.dump(manifest, f, indent=1)
    os.replace(MANIFEST + ".tmp", MANIFEST)
    return results


def summary(results):
    lines = []
    for what, title in (("copied", "Copied from RetroArch"), ("downloaded", "Downloaded from the libretro buildbot"),
                        ("kept", "Already there"), ("failed", "Not installed")):
        rows = [r for r in results if r[1] == what]
        if not rows: continue
        lines += ["", f"{title}: {len(rows)}"]
        lines += [f"  {CORES[f].name}" + (f": {d}" if what == "failed" else f" ({d})" if d else "") for f, _, d in rows]
    lines += ["", f"Insert Coin's cores: {CORES_DIR}",
              "The built-in player uses them from now on; RetroArch keeps using its own."]
    return "\n".join(lines).lstrip("\n")
