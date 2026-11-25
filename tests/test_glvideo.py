"""Cores that draw on the graphics card (N64): the window-less OpenGL context, the framebuffer the core draws
into, copying each frame back the right way up, and handing the context back and forth with pygame's own.

These need a working OpenGL driver (any Mesa, even the software one); without one they are skipped."""
import ctypes as C, unittest
import support  # noqa: F401  (sets up a throwaway HOME before anything else is imported)
import pygame
import engine
from insertcoin import glvideo
from test_states import player

engine.log = lambda level, msg: None

try:
    glvideo.GLContext().close(); HAVE_GL = True
except Exception as e:                                          # no EGL / OpenGL here: nothing to test
    HAVE_GL, WHY = False, str(e)

GL_SCISSOR_TEST, GL_COLOR_BUFFER_BIT = 0x0C11, 0x4000
RED, BLUE = (220, 30, 30), (30, 30, 220)


def paint(ctx, w, h):
    """Draw like a core would: the lower half (in OpenGL's terms) blue, the upper half red."""
    f = ctx.func; u, i, fl = C.c_uint, C.c_int, C.c_float
    ClearColor = f("glClearColor", None, fl, fl, fl, fl); Clear = f("glClear", None, u)
    Enable, Disable = f("glEnable", None, u), f("glDisable", None, u); Scissor = f("glScissor", None, i, i, i, i)
    ctx.BindFramebuffer(glvideo.GL_FRAMEBUFFER, ctx.fbo); Enable(GL_SCISSOR_TEST)
    for (r, g, b), y in ((BLUE, 0), (RED, h // 2)):
        Scissor(0, y, w, h // 2); ClearColor(r / 255, g / 255, b / 255, 1); Clear(GL_COLOR_BUFFER_BIT)
    Disable(GL_SCISSOR_TEST)


def hw_request(kind=glvideo.HW_OPENGL_CORE, bottom_left=True):
    hw = glvideo.HWRender(); hw.context_type = kind; hw.version_major, hw.version_minor = 3, 3
    hw.depth = True; hw.bottom_left_origin = bottom_left
    return hw


class GLCore:
    """A stand-in core that draws each frame with OpenGL and hands it over as 'in your framebuffer'."""
    def __init__(self, p, w=320, h=240): self.p, self.w, self.h, self.frames = p, w, h, 0

    def retro_run(self):
        paint(self.p.gl, self.w, self.h); self.frames += 1
        self.p.video(glvideo.HW_FRAME_VALID, self.w, self.h, 0)


@unittest.skipUnless(HAVE_GL, "no OpenGL here" if HAVE_GL else f"no OpenGL here: {WHY}")
class GraphicsCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init(); pygame.font.init()

    def gl_player(self, **kw):
        p = player(); hw = hw_request(**kw)
        self.assertTrue(p.set_hw_render(C.addressof(hw)))
        p.av.geometry.max_width, p.av.geometry.max_height = 640, 480
        p.start_gl(); p.lib = GLCore(p)
        self.addCleanup(p.gl.close)
        return p, hw

    def test_the_core_gets_its_callbacks(self):
        p, hw = self.gl_player()
        self.assertEqual(glvideo.FRAMEBUFFER_T(hw.get_current_framebuffer)(), p.gl.fbo)
        self.assertNotEqual(p.gl.fbo, 0)
        self.assertTrue(glvideo.PROC_T(hw.get_proc_address)(b"glClear"))
        self.assertEqual(p.gl.size, (640, 480))                           # the largest picture the core can make

    def test_frames_come_back_the_right_way_up(self):
        p, _ = self.gl_player()
        p.step()
        self.assertEqual(p.frame.get_size(), (320, 240))
        self.assertEqual(p.frame.get_at((10, 10))[:3], RED)                # OpenGL's upper half is the top
        self.assertEqual(p.frame.get_at((10, 230))[:3], BLUE)

    def test_a_core_drawing_top_down_is_not_flipped(self):
        p, _ = self.gl_player(bottom_left=False)
        p.step()
        self.assertEqual(p.frame.get_at((10, 10))[:3], BLUE)

    def test_frames_have_no_see_through_layer(self):
        """A frame with alpha makes every blit to the screen a slow blend (25 ms a frame at 1080p)."""
        p, _ = self.gl_player(); p.step()
        self.assertFalse(p.frame.get_flags() & pygame.SRCALPHA)

    def test_frames_go_through_the_normal_picture_path(self):
        p, _ = self.gl_player(); p.step(); p.present()
        mid = p.screen.get_at((engine.W // 2, engine.H // 4))[:3]
        self.assertEqual(mid, RED)

    def test_vulkan_is_turned_down(self):
        p = player(); hw = hw_request(glvideo.HW_VULKAN)
        self.assertFalse(p.set_hw_render(C.addressof(hw)))
        self.assertIsNone(p.gl)

    def test_the_framebuffer_grows_and_keeps_its_number(self):
        p, _ = self.gl_player(); fbo = p.gl.fbo
        p.av.geometry.max_width, p.av.geometry.max_height = 1280, 960
        p.grow_gl()
        self.assertEqual(p.gl.fbo, fbo); self.assertEqual(p.gl.size, (1280, 960))
        p.lib.w, p.lib.h = 1280, 960; p.step()
        self.assertEqual(p.frame.get_size(), (1280, 960))

    def test_another_context_is_given_back(self):
        """pygame's window may have its own context in use: set aside for each frame, then given back."""
        other = glvideo.GLContext(); self.addCleanup(other.close)
        p, _ = self.gl_player()
        egl = other.egl
        egl.eglMakeCurrent(other.dpy, None, None, other.ctx)
        p.step()                                                           # draws in its own context...
        self.assertEqual(p.frame.get_at((10, 10))[:3], RED)
        self.assertEqual(egl.eglGetCurrentContext(), other.ctx)            # ...and the other one is back
        with p.gl.active():
            self.assertEqual(egl.eglGetCurrentContext(), p.gl.ctx)
            with p.gl.active(): pass                                       # nested (the core asks to grow mid-frame)
            self.assertEqual(egl.eglGetCurrentContext(), p.gl.ctx)
        self.assertEqual(egl.eglGetCurrentContext(), other.ctx)
        egl.eglMakeCurrent(other.dpy, None, None, None)

    def test_states_and_closing_run_in_the_core_context(self):
        p, _ = self.gl_player(); seen = []
        class Core(GLCore):
            def retro_serialize_size(self): return 4
            def retro_serialize(self, buf, size): seen.append(p.gl.egl.eglGetCurrentContext()); return True
        p.lib = Core(p); p.step()
        self.assertTrue(p.save_state(1))
        self.assertEqual(seen, [p.gl.ctx])


class SoftwareCoresUnchanged(unittest.TestCase):
    def test_no_context_for_cores_that_draw_in_memory(self):
        p = player(); p.step()
        self.assertIsNone(p.gl)
        with p.in_gl(): pass                                               # nothing to switch
