"""The systems Insert Coin knows: friendly names, makers, colours, and the cores the built-in player runs."""


# ---------------------------------------------------------------- systems
# playlist name -> (friendly name, maker, accent colour)
SYSTEMS = [
    ("FBNeo - Arcade Games", "Arcade", "Neo Geo, Capcom & more", (226, 64, 64)),
    ("MAME 2003-Plus", "MAME", "Classic arcade", (232, 140, 40)),
    ("Nintendo - Nintendo Entertainment System", "NES", "Nintendo", (200, 40, 50)),
    ("Nintendo - Super Nintendo Entertainment System", "Super Nintendo", "Nintendo", (110, 90, 200)),
    ("Nintendo - Nintendo 64", "Nintendo 64", "Nintendo", (40, 150, 70)),
    ("Nintendo - Game Boy", "Game Boy", "Nintendo", (140, 160, 60)),
    ("Nintendo - Game Boy Color", "Game Boy Color", "Nintendo", (150, 70, 190)),
    ("Nintendo - Game Boy Advance", "Game Boy Advance", "Nintendo", (70, 80, 200)),
    ("Sega - Mega Drive - Genesis", "Mega Drive", "Sega", (30, 110, 210)),
    ("Sega - 32X", "Sega 32X", "Sega", (200, 60, 60)),
    ("NEC - PC Engine - TurboGrafx 16", "PC Engine", "NEC", (240, 120, 40)),
    ("Sony - PlayStation", "PlayStation", "Sony", (110, 120, 140)),
    ("SNK - Neo Geo Pocket", "Neo Geo Pocket", "SNK", (90, 90, 110)),
    ("SNK - Neo Geo Pocket Color", "Neo Geo Pocket Color", "SNK", (40, 160, 170)),
    ("Atari - 2600", "Atari 2600", "Atari", (170, 110, 60)),
]
FRIENDLY = {k: (n, m, c) for k, n, m, c in SYSTEMS}
ORDER = {k: i for i, (k, *_ ) in enumerate(SYSTEMS)}

# cores the built-in player runs (all draw in software; each was test-booted). N64 needs the graphics card: RetroArch.
ENGINE_CORES = {"mesen_libretro.so", "fbneo_libretro.so", "mame2003_plus_libretro.so", "mame2003_libretro.so",
                "fbalpha2012_cps3_libretro.so", "mesen-s_libretro.so", "vbam_libretro.so", "blastem_libretro.so",
                "picodrive_libretro.so", "mednafen_supergrafx_libretro.so", "mednafen_ngp_libretro.so",
                "pcsx_rearmed_libretro.so", "stella_libretro.so"}
