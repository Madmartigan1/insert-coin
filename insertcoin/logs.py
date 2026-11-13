"""Logging: insert-coin.log and crash traces."""
import faulthandler, logging, os
from paths import LOGDIR
log = logging.getLogger("insert-coin")


def start_log():
    """insert-coin.log: start-up, every game launch and how it ended, errors and crashes (kept to ~1 MB)."""
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        path = f"{LOGDIR}/insert-coin.log"
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000: os.replace(path, path + ".1")
        h = logging.FileHandler(path, encoding="utf-8")
    except Exception: return                                        # no log is no reason not to run
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(h); log.setLevel(logging.INFO)
    faulthandler.enable(h.stream)                                   # hard crashes (segfaults) too
