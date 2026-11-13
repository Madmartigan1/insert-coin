"""Starting games: RetroArch, the built-in player, or a browser."""
import os, pygame, signal, subprocess, sys, time, urllib.parse
from pygame._sdl2 import controller as sdlc
from paths import APPDIR, HERE, LOGDIR
from insertcoin.logs import log
from insertcoin.cores import core_file, is_builtin
from insertcoin.controllers import controller_style, sdl_controller_update
from insertcoin.names import split_archive
from insertcoin.web import FLASH_PAGE, RUFFLE, WebGame, browser_command, close_stale_browsers, find_browser, serve_folder
from insertcoin.flashinput import FLASH_DEVTOOLS_INPUT, FlashPad, PageInput

LAUNCH_CFG = """# Written by Insert Coin: controller shortcuts while a game runs
# Select + Start opens RetroArch's menu (Quick Menu > Resume / Close Content), like the built-in player's pause
# menu; Close Content then returns to Insert Coin (only for games started from the command line, i.e. by us).
input_quit_gamepad_combo = "0"
input_menu_toggle_gamepad_combo = "4"
quit_on_close_content = "2"
quit_press_twice = "false"
video_fullscreen = "true"
"""
# Added for `--windowed` (testing): a window, and nothing of this saved into retroarch.cfg
LAUNCH_CFG_WINDOWED = """video_fullscreen = "false"
config_save_on_exit = "false"
"""


class Launcher:

    def launch(self, g):
        if isinstance(g, WebGame): return self.launch_browser(g)
        if not g.core:
            self.err("No core is set for this game yet - assign one in RetroArch"); return
        if not os.path.exists(split_archive(g.path)[0]):
            self.err("ROM file not found"); return
        engine = self.settings.get("engine") and is_builtin(g.core)
        who = "Built-in player" if engine else "RetroArch"
        self.sfx.play("coin"); self.draw(); self.splash(g, engine)
        self.sfx.finish(); self.sfx.close()                          # hand the audio device to the game
        os.makedirs(APPDIR, exist_ok=True); os.makedirs(LOGDIR, exist_ok=True)
        with open(f"{APPDIR}/launch.cfg", "w") as f:
            f.write(LAUNCH_CFG.replace('video_fullscreen = "true"\n', "") + LAUNCH_CFG_WINDOWED if self.windowed else LAUNCH_CFG)
        pygame.display.quit()
        kind = "engine" if engine else "retroarch"
        t0 = time.time(); ralog = f"{LOGDIR}/{kind}-last.log"; rc = None
        log.info("Launch (%s): %s | %s | %s", who, g.label, core_file(g.core), g.path)
        try:
            if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/{kind}-previous.log")
            if engine:
                with open(ralog, "w") as out:
                    rc = subprocess.run([sys.executable, f"{HERE}/engine.py", g.core, g.path, "--title", g.title] + (["--windowed"] if self.windowed else []),
                                        stdout=out, stderr=subprocess.STDOUT).returncode
                if rc and time.time() - t0 < 10:                     # didn't start: let RetroArch try it instead
                    log.warning("Built-in player could not start it (exit %s), trying RetroArch", rc)
                    try:
                        errs = [ln.rstrip() for ln in open(ralog, errors="replace") if "[ERROR]" in ln]
                        for ln in errs[-5:]: log.warning("  engine: %s", ln)
                    except Exception: pass
                    engine, who, kind = False, "RetroArch", "retroarch"
                    ralog = f"{LOGDIR}/retroarch-last.log"; t0 = time.time()
                    if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/retroarch-previous.log")
            if not engine:
                rc = subprocess.run(["retroarch", "--verbose", f"--log-file={ralog}", "-L", g.core, g.path,
                                     f"--appendconfig={APPDIR}/launch.cfg"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        except Exception as e:
            self.err(f"Could not start {who}: {e}")
        took = time.time() - t0
        how = ("ended normally" if rc == 0 else f"was killed by signal {-rc} (crash)" if rc is not None and rc < 0
               else f"exited with code {rc}" if rc is not None else "did not start")
        (log.info if rc == 0 else log.warning)("%s %s after %d min %02d s (log: %s)", who, how, took // 60, took % 60, ralog)
        if rc:                                                       # keep the clues next to the event
            try:
                errs = [ln.rstrip() for ln in open(ralog, errors="replace") if "[ERROR]" in ln or "[WARN]" in ln]
                for ln in errs[-15:]: log.warning("  %s: %s", kind, ln)
            except Exception: pass
        if engine and rc == 0 and took >= 3:
            try: self.lib.add_history(g)
            except Exception as e: log.warning("Could not update Recently Played: %s", e)
        if rc is not None and took >= 3:
            try: self.lib.note_launch(g, t0)                        # so browser games sort into Recently Played
            except Exception as e: log.warning("Could not note the launch: %s", e)
        self.back_from_game()
        quit_by_user = False
        if engine:
            try: quit_by_user = "Quit chosen from the game menu" in open(ralog, errors="replace").read()
            except OSError: pass
        if took < 3 and not quit_by_user: self.err("The game closed straight away - it may need a different core")

    def back_from_game(self):
        """The game has ended: screen, controllers (they may have changed), sound, and the lists back."""
        pygame.display.init(); self.open_display(); self.rescan_pads(); self.sfx.open()
        self.img.cache.clear(); self.prev_bg = None
        pygame.event.clear(); self.hold.clear()
        sid, gid = self.sys["id"], self.cur_gi()
        self.lib.refresh_specials()
        self.si = next((i for i, s in enumerate(self.lib.systems) if s["id"] == sid), 0); self.gi[sid] = gid

    def launch_browser(self, g):
        """A browser game: serve its folder on 127.0.0.1 (a random port, nothing reachable from outside), open the
        start page full-screen in its own browser profile, and watch the controllers for Select + Start, which
        closes the browser and comes back here. The page itself reads the pad through the Gamepad API."""
        if not os.path.isfile(g.path): self.err("Game file not found"); return
        br = find_browser()
        if not br: self.err("Browser games need Google Chrome, Chromium or Firefox"); return
        if g.flash and not os.path.isfile(f"{RUFFLE}/ruffle.js"):
            self.err("Flash games need Ruffle - see the README (Browser and Flash games)"); return
        self.sfx.play("coin"); self.draw(); self.splash(g, web=True)
        self.sfx.finish(); self.sfx.close()
        os.makedirs(LOGDIR, exist_ok=True)
        ralog = f"{LOGDIR}/browser-last.log"
        if os.path.exists(ralog): os.replace(ralog, f"{LOGDIR}/browser-previous.log")
        server = rc = None; quit_by_user = False; t0 = time.time()
        try:
            flashpad = None                                         # Chrome-family browsers: genuine input via DevTools
            if FLASH_DEVTOOLS_INPUT and g.flash and "firefox" not in os.path.basename(br):
                flashpad = FlashPad(PageInput(), g.buttons)
            server = serve_folder(g.folder, (g.start, g.title, g.buttons, flashpad is not None) if g.flash else None)
            url = f"http://127.0.0.1:{server.server_address[1]}/" + (FLASH_PAGE if g.flash else urllib.parse.quote(g.start))
            close_stale_browsers()
            cmd = browser_command(br, url, self.windowed) + (["--remote-debugging-pipe"] if flashpad else [])
            log.info("Launch (browser, %s): %s | %s", os.path.basename(br), g.label, g.path)
            pygame.display.quit()
            with open(ralog, "w") as out:
                if flashpad:                                        # the pipe goes to the browser as fds 3 and 4
                    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                                            close_fds=False, preexec_fn=flashpad.xin.child_fds)
                    flashpad.xin.connected()
                else:
                    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
                quit_by_user = self.watch_quit_combo(proc, flashpad)
                if quit_by_user:
                    log.info("Select + Start: closing the browser")
                    for sig, wait in ((signal.SIGTERM, 4), (signal.SIGKILL, 2)):
                        try: os.killpg(proc.pid, sig)
                        except ProcessLookupError: break
                        try: proc.wait(wait); break
                        except subprocess.TimeoutExpired: pass
                rc = proc.wait()
        except Exception as e:
            self.err(f"Could not start the browser: {e}"); log.exception("Browser game failed")
        finally:
            if server: server.shutdown(); server.server_close()
            if flashpad:
                log.info("Flash input sent: %s", ", ".join(f"{k} x{n}" for k, n in sorted(flashpad.xin.stats.items())) or "nothing")
                flashpad.xin.close()
        took = time.time() - t0
        log.info("Browser game ended after %d min %02d s (%s, exit %s)", took // 60, took % 60,
                 "Select + Start" if quit_by_user else "browser closed", rc)
        if rc is not None and took >= 3:
            try: self.lib.note_launch(g, t0)
            except Exception as e: log.warning("Could not update Recently Played: %s", e)
        if not pygame.display.get_init(): self.back_from_game()
        else: self.sfx.open()
        if rc is not None and took < 3 and not quit_by_user: self.err("The browser closed straight away - see browser-last.log")

    def watch_quit_combo(self, proc, flash=None):
        """While the browser runs (Insert Coin has no window then, so no events): read the controllers directly,
        and return True when Select + Start (Back + Start, Share + Options...) is held on any of them.
        flash: a FlashPad that turns the pad into keys and a mouse, used only while the game's window is active."""
        update = sdl_controller_update()
        pads = [(c, self.pad_style.get(c.as_joystick().get_instance_id(), "xbox")) for c in self.pads.values()]
        n = sdlc.get_count(); last_check = time.time(); ready = False; ready_at = 0
        BACK, START = pygame.CONTROLLER_BUTTON_BACK, pygame.CONTROLLER_BUTTON_START
        try:
            while proc.poll() is None:
                time.sleep(0.016 if flash else 0.03)
                if not update: continue
                update()
                if time.time() - last_check > 2:                    # a pad plugged in while the game runs
                    last_check = time.time()
                    if sdlc.get_count() != n:
                        n = sdlc.get_count(); pads = []
                        for i in range(n):
                            try:
                                if sdlc.is_controller(i):
                                    c = sdlc.Controller(i); j = c.as_joystick()
                                    pads.append((c, controller_style(c.name, j.get_guid())))
                            except Exception: pass
                for c, _ in pads:
                    try:
                        if c.get_button(BACK) and c.get_button(START): return True
                    except Exception: pass
                if flash:
                    if time.time() - ready_at > (3 if ready else 0.5):  # find the page; then re-check its size
                        ready_at = time.time()
                        was = ready
                        try: ready = flash.xin.measure() if ready else flash.xin.attach()
                        except Exception: ready = False
                        if ready and not was: log.info("Flash: pad controls ready")
                    if ready: flash.tick(pads)
            return False
        finally:
            if flash: flash.release()
