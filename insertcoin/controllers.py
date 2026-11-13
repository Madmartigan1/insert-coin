"""Controller families, their button glyphs and labels, and the controller set-up steps."""
import ctypes, re


# ---------------------------------------------------------------- controller styles (for on-screen button hints)
# USB SNES replicas that SDL knows but maps by position, Xbox-style (vendor, product)
SNES_REPLICA_IDS = {("0583", "2060")}                              # iBuffalo Classic USB Gamepad


def controller_style(name, guid=""):
    """'playstation', 'nintendo', 'snes' (a third-party SNES replica) or 'xbox', from the USB vendor and product
    in SDL's GUID, falling back to the name."""
    n = (name or "").lower()
    vendor = guid[10:12] + guid[8:10] if len(guid) >= 12 else ""     # bytes 4-5 of the GUID, little-endian
    product = guid[18:20] + guid[16:18] if len(guid) >= 20 else ""   # bytes 8-9
    if vendor == "054c" or any(k in n for k in ("ps3", "ps4", "ps5", "playstation", "dualshock", "dualsense", "sony")):
        return "playstation"
    if vendor == "057e":                                           # Nintendo's own pads: SDL follows their labels
        return "nintendo"
    if (vendor, product) in SNES_REPLICA_IDS or any(k in n for k in ("snes", "super nintendo", "super famicom")):
        return "snes"
    if any(k in n for k in ("nintendo", "switch", "joy-con", "joycon")):
        return "nintendo"
    return "xbox"


# action -> how its button looks, per style. kinds: letter (round button), shape (PlayStation symbol), pill, key
GLYPHS = {
    "xbox": {"a": ("letter", "A", (90, 190, 90)), "b": ("letter", "B", (220, 80, 70)),
             "y": ("letter", "Y", (230, 190, 50)), "x": ("letter", "X", (70, 130, 230)), "lbrb": ("pill", "LB RB", (120, 130, 150)),
             "r3": ("pill", "R3", (120, 130, 150))},
    "playstation": {"a": ("shape", "cross", (120, 160, 245)), "b": ("shape", "circle", (235, 90, 95)),
                    "y": ("shape", "triangle", (70, 200, 160)), "x": ("shape", "square", (230, 130, 200)), "lbrb": ("pill", "L1 R1", (120, 130, 150)),
                    "r3": ("pill", "R3", (120, 130, 150))},
    "nintendo": {"a": ("letter", "A", (110, 116, 132)), "b": ("letter", "B", (110, 116, 132)),
                 "y": ("letter", "Y", (110, 116, 132)), "x": ("letter", "X", (110, 116, 132)), "lbrb": ("pill", "L R", (120, 130, 150)),
                 "r3": ("pill", "R3", (120, 130, 150))},
    "keyboard": {"a": ("key", "Enter", None), "b": ("key", "Esc", None),
                 "y": ("key", "F", None), "x": ("key", "V", None), "lbrb": ("key", "PgUp PgDn", None),
                 "r3": ("key", "/", None)},
}
GLYPHS["snes"] = dict(GLYPHS["nintendo"])                        # replicas: same printed letters as Nintendo
GLYPHS["generic"] = {"a": ("letter", "A", (110, 116, 132)), "b": ("letter", "B", (110, 116, 132)),   # set-up pads
                     "y": ("letter", "Y", (110, 116, 132)), "x": ("letter", "X", (110, 116, 132)), "lbrb": ("pill", "LB RB", (120, 130, 150))}
QUIT_COMBO = {"xbox": "Back + Start", "playstation": "Share + Options", "nintendo": "Minus + Plus", "keyboard": "Esc",
              "generic": "Select + Start", "snes": "Select + Start"}

# controller set-up for pads SDL doesn't recognise: (action, button shown, what it does, optional)
SETUP_STEPS = [("up", "up", "Up", False), ("down", "down", "Down", False), ("left", "left", "Left", False),
               ("right", "right", "Right", False), ("a", "A", "Select / play", False), ("b", "B", "Back", False),
               ("y", "Y", "Favorite", True), ("x", "X", "Other versions", True),
               ("lb", "LB", "Previous letter", True), ("rb", "RB", "Next letter", True)]


def quit_combo(style, name="", guid=""):
    """The buttons that quit a game, as printed on this controller (PS3: Select/Start, PS5: Create/Options)."""
    product = guid[18:20] + guid[16:18] if len(guid) >= 20 else ""   # bytes 8-9 of the GUID, little-endian
    n = (name or "").lower()
    if style == "playstation" and (product == "0268" or "ps3" in n or "playstation(r)3" in n):
        return "Select + Start"
    if style == "playstation" and (product in ("0ce6", "0df2") or "dualsense" in n or "ps5" in n):
        return "Create + Options"
    return QUIT_COMBO[style]


def sdl_controller_update():
    """SDL_GameControllerUpdate from the SDL library pygame uses: refreshes the controllers' button states while
    Insert Coin has no window (pygame's event functions need one). None if it can't be found."""
    try:
        lib = next((ln.split()[-1] for ln in open("/proc/self/maps") if re.search(r"/libSDL2-2\.0\.so|/libSDL2-2-[0-9a-f]+\.0\.so", ln)), None)
        return ctypes.CDLL(lib or "libSDL2-2.0.so.0").SDL_GameControllerUpdate
    except Exception:
        return None
