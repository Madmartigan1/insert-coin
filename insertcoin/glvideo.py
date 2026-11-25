"""Pictures drawn on the graphics card, for cores that need it (N64).

Most cores draw each frame in memory and hand it over. Some (Mupen64Plus-Next for the N64) draw with
OpenGL instead. For them the built-in player makes an OpenGL context without a window (EGL "surfaceless",
so it also works with no screen at all, e.g. for test starts), gives the core a framebuffer to draw into,
and after each frame copies the finished picture into an ordinary pygame surface. From there it goes the
same way as every other core's picture: pause menu, save-state pictures, picture looks, screenshots.

Credits and sources:
- The `HWRender` structure and the RETRO_HW_* / environment numbers follow `libretro.h` from the libretro
  API (https://github.com/libretro/libretro-common, MIT License, Copyright (C) 2010-2024 The RetroArch team).
- The EGL and OpenGL function names and constant values are from the Khronos Group's EGL and OpenGL
  registries (https://registry.khronos.org, headers under the Apache 2.0 / MIT-style Khronos licenses).
  EGL_PLATFORM_SURFACELESS_MESA is Mesa's extension (https://mesa3d.org).
No code was copied from those projects; this file only calls the system's own libEGL / OpenGL driver.
"""
import contextlib, ctypes as C

# libretro.h: enum retro_hw_context_type
HW_NONE, HW_OPENGL, HW_OPENGLES2, HW_OPENGL_CORE, HW_OPENGLES3, HW_OPENGLES_VERSION, HW_VULKAN = range(7)
HW_TYPE_NAMES = {HW_OPENGL: "OpenGL", HW_OPENGLES2: "OpenGL ES 2", HW_OPENGL_CORE: "OpenGL core",
                 HW_OPENGLES3: "OpenGL ES 3", HW_OPENGLES_VERSION: "OpenGL ES", HW_VULKAN: "Vulkan"}
SUPPORTED = (HW_OPENGL, HW_OPENGL_CORE)                  # what this module can give a core
HW_FRAME_VALID = C.c_void_p(-1).value                   # RETRO_HW_FRAME_BUFFER_VALID: "the frame is in your framebuffer"


class HWRender(C.Structure):
    """libretro.h: struct retro_hw_render_callback (the core fills in what it wants, we fill in the callbacks)."""
    _fields_ = [("context_type", C.c_uint), ("context_reset", C.c_void_p), ("get_current_framebuffer", C.c_void_p),
                ("get_proc_address", C.c_void_p), ("depth", C.c_bool), ("stencil", C.c_bool),
                ("bottom_left_origin", C.c_bool), ("version_major", C.c_uint), ("version_minor", C.c_uint),
                ("cache_context", C.c_bool), ("context_destroy", C.c_void_p), ("debug_context", C.c_bool)]


FRAMEBUFFER_T = C.CFUNCTYPE(C.c_size_t)                 # retro_hw_get_current_framebuffer_t
PROC_T = C.CFUNCTYPE(C.c_void_p, C.c_char_p)            # retro_hw_get_proc_address_t
RESET_T = C.CFUNCTYPE(None)                             # retro_hw_context_reset_t

# EGL (egl.h / eglext.h)
EGL_PLATFORM_SURFACELESS_MESA = 0x31DD
EGL_OPENGL_API = 0x30A2
EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_SURFACE_TYPE, EGL_NONE = 0x3040, 0x0008, 0x3033, 0x3038
EGL_CONTEXT_MAJOR_VERSION, EGL_CONTEXT_MINOR_VERSION = 0x3098, 0x30FB
EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT, EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT = 0x30FD, 1, 2
# OpenGL (gl.h / glcorearb.h)
GL_FRAMEBUFFER, GL_READ_FRAMEBUFFER, GL_RENDERBUFFER = 0x8D40, 0x8CA8, 0x8D41
GL_TEXTURE_2D, GL_RGBA, GL_RGBA8, GL_UNSIGNED_BYTE = 0x0DE1, 0x1908, 0x8058, 0x1401
GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_NEAREST = 0x2801, 0x2800, 0x2600
GL_COLOR_ATTACHMENT0, GL_DEPTH_ATTACHMENT, GL_DEPTH_STENCIL_ATTACHMENT = 0x8CE0, 0x8D00, 0x821A
GL_DEPTH_COMPONENT24, GL_DEPTH24_STENCIL8 = 0x81A6, 0x88F0
GL_FRAMEBUFFER_COMPLETE, GL_PACK_ALIGNMENT, GL_PACK_ROW_LENGTH = 0x8CD5, 0x0D05, 0x0D02
GL_RENDERER, GL_VERSION = 0x1F01, 0x1F02


class GLError(Exception):
    pass


def _egl():
    try: egl = C.CDLL("libEGL.so.1")
    except OSError as e: raise GLError(f"no EGL library ({e})")
    egl.eglGetProcAddress.restype = C.c_void_p; egl.eglGetProcAddress.argtypes = [C.c_char_p]
    egl.eglGetPlatformDisplay.restype = C.c_void_p
    egl.eglGetPlatformDisplay.argtypes = [C.c_uint, C.c_void_p, C.c_void_p]
    egl.eglInitialize.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
    egl.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]
    egl.eglCreateContext.restype = C.c_void_p
    egl.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
    egl.eglMakeCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    egl.eglDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
    egl.eglTerminate.argtypes = [C.c_void_p]
    for n in ("eglGetCurrentContext", "eglGetCurrentDisplay", "eglGetCurrentSurface"): getattr(egl, n).restype = C.c_void_p
    egl.eglGetCurrentSurface.argtypes = [C.c_int]
    return egl


def _glx():
    """GLX, if this system has it: pygame's own window may draw with a GLX context on X11."""
    try: glx = C.CDLL("libGLX.so.0")
    except OSError:
        try: glx = C.CDLL("libGL.so.1")
        except OSError: return None
    for n in ("glXGetCurrentContext", "glXGetCurrentDisplay", "glXGetCurrentDrawable", "glXGetCurrentReadDrawable"):
        getattr(glx, n).restype = C.c_void_p
    glx.glXMakeContextCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    return glx


EGL_DRAW, EGL_READ = 0x3059, 0x305A


class GLContext:
    """An OpenGL context with no window, plus the framebuffer the core draws into."""

    def __init__(self, major=3, minor=3, core_profile=True):
        self.egl = egl = _egl(); self.glx = _glx()
        self.saved = None; self.depth_in = 0
        self.dpy = egl.eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, None, None)
        if not self.dpy or not egl.eglInitialize(self.dpy, C.byref(C.c_int()), C.byref(C.c_int())):
            raise GLError("the graphics driver has no window-less (surfaceless) EGL display")
        if not egl.eglBindAPI(EGL_OPENGL_API): raise GLError("the graphics driver has no desktop OpenGL")
        cfg, n = C.c_void_p(), C.c_int()
        attrs = (C.c_int * 5)(EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_SURFACE_TYPE, 0, EGL_NONE)
        if not egl.eglChooseConfig(self.dpy, attrs, C.byref(cfg), 1, C.byref(n)) or not n.value:
            raise GLError("no suitable OpenGL configuration")
        profile = EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT if core_profile else EGL_CONTEXT_OPENGL_COMPATIBILITY_PROFILE_BIT
        ca = (C.c_int * 7)(EGL_CONTEXT_MAJOR_VERSION, max(major, 1), EGL_CONTEXT_MINOR_VERSION, minor,
                           EGL_CONTEXT_OPENGL_PROFILE_MASK, profile, EGL_NONE)
        self.ctx = egl.eglCreateContext(self.dpy, cfg, None, ca)
        if not self.ctx: raise GLError(f"the graphics driver can't make an OpenGL {major}.{minor} context")
        self.set_aside()
        if not egl.eglMakeCurrent(self.dpy, None, None, self.ctx):
            self.put_back(); raise GLError(f"could not use the OpenGL context (EGL error {egl.eglGetError():#x})")
        u, i, p, V = C.c_uint, C.c_int, C.c_void_p, None
        f = self.func
        self.GenFramebuffers = f("glGenFramebuffers", V, i, C.POINTER(u))
        self.BindFramebuffer = f("glBindFramebuffer", V, u, u)
        self.GenTextures = f("glGenTextures", V, i, C.POINTER(u))
        self.BindTexture = f("glBindTexture", V, u, u)
        self.TexImage2D = f("glTexImage2D", V, u, i, i, i, i, i, u, u, p)
        self.TexParameteri = f("glTexParameteri", V, u, u, i)
        self.FramebufferTexture2D = f("glFramebufferTexture2D", V, u, u, u, u, i)
        self.GenRenderbuffers = f("glGenRenderbuffers", V, i, C.POINTER(u))
        self.BindRenderbuffer = f("glBindRenderbuffer", V, u, u)
        self.RenderbufferStorage = f("glRenderbufferStorage", V, u, u, i, i)
        self.FramebufferRenderbuffer = f("glFramebufferRenderbuffer", V, u, u, u, u)
        self.CheckFramebufferStatus = f("glCheckFramebufferStatus", u, u)
        self.ReadPixels = f("glReadPixels", V, i, i, i, i, u, u, p)
        self.PixelStorei = f("glPixelStorei", V, u, i)
        self.GetString = f("glGetString", C.c_char_p, u)
        self.fbo = self.tex = self.rbo = 0; self.size = (0, 0); self.depth = self.stencil = False
        self.buf = None
        self.version = (self.GetString(GL_VERSION) or b"?").decode(errors="replace")
        self.renderer = (self.GetString(GL_RENDERER) or b"?").decode(errors="replace")
        egl.eglMakeCurrent(self.dpy, None, None, None); self.put_back()

    # pygame's window may have an OpenGL context of its own (SDL draws the screen with it). A thread can have only
    # one context in use, and the driver refuses to mix a GLX one with ours, so around every call into the core
    # pygame's context is set aside and given back afterwards, exactly as it was (SDL remembers it as current).
    def set_aside(self):
        egl, glx = self.egl, self.glx
        if glx and glx.glXGetCurrentContext():
            d = glx.glXGetCurrentDisplay()
            self.saved = ("glx", d, glx.glXGetCurrentDrawable(), glx.glXGetCurrentReadDrawable(), glx.glXGetCurrentContext())
            glx.glXMakeContextCurrent(d, None, None, None)
        elif egl.eglGetCurrentContext() and egl.eglGetCurrentContext() != self.ctx:
            d = egl.eglGetCurrentDisplay()
            self.saved = ("egl", d, egl.eglGetCurrentSurface(EGL_DRAW), egl.eglGetCurrentSurface(EGL_READ), egl.eglGetCurrentContext())
            egl.eglMakeCurrent(d, None, None, None)
        else: self.saved = None

    def put_back(self):
        if self.saved:
            kind, d, draw, read, ctx = self.saved; self.saved = None
            if kind == "glx": self.glx.glXMakeContextCurrent(d, draw, read, ctx)
            else: self.egl.eglMakeCurrent(d, draw, read, ctx)

    @contextlib.contextmanager
    def active(self):
        """Use our context for a while (a frame, a save state...), then give pygame's back."""
        if not self.ctx or self.depth_in: self.depth_in += 1; yield; self.depth_in -= 1; return   # already in use
        self.set_aside()
        self.egl.eglMakeCurrent(self.dpy, None, None, self.ctx)
        self.depth_in = 1
        try: yield
        finally:
            self.depth_in = 0
            self.egl.eglMakeCurrent(self.dpy, None, None, None)
            self.put_back()

    def proc(self, name):
        """The address of an OpenGL function (what the core's get_proc_address asks for)."""
        return self.egl.eglGetProcAddress(name)

    def func(self, name, res, *args):
        addr = self.proc(name.encode())
        if not addr: raise GLError(f"the graphics driver has no {name}")
        return C.CFUNCTYPE(res, *args)(addr)

    def framebuffer(self, w, h, depth=False, stencil=False):
        """Make (or grow) the framebuffer the core draws into. Its number stays the same when it grows."""
        if self.fbo and w <= self.size[0] and h <= self.size[1]: return self.fbo
        if not self.fbo:
            n = C.c_uint(); self.GenFramebuffers(1, C.byref(n)); self.fbo = n.value
            n = C.c_uint(); self.GenTextures(1, C.byref(n)); self.tex = n.value
            if depth or stencil: n = C.c_uint(); self.GenRenderbuffers(1, C.byref(n)); self.rbo = n.value
            self.depth, self.stencil = depth, stencil
        w, h = max(w, self.size[0], 1), max(h, self.size[1], 1)
        self.BindFramebuffer(GL_FRAMEBUFFER, self.fbo)
        self.BindTexture(GL_TEXTURE_2D, self.tex)
        self.TexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        self.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        self.TexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        self.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.tex, 0)
        self.BindTexture(GL_TEXTURE_2D, 0)
        if self.rbo:
            self.BindRenderbuffer(GL_RENDERBUFFER, self.rbo)
            self.RenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8 if self.stencil else GL_DEPTH_COMPONENT24, w, h)
            self.FramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_STENCIL_ATTACHMENT if self.stencil else GL_DEPTH_ATTACHMENT,
                                         GL_RENDERBUFFER, self.rbo)
            self.BindRenderbuffer(GL_RENDERBUFFER, 0)
        status = self.CheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE: raise GLError(f"the framebuffer is not usable (status {status:#x})")
        self.size = (w, h)
        return self.fbo

    def read(self, w, h):
        """The w x h picture at the framebuffer's lower left corner, as RGBA bytes, bottom row first."""
        w, h = min(w, self.size[0]), min(h, self.size[1])
        if self.buf is None or len(self.buf) < w * h * 4: self.buf = C.create_string_buffer(w * h * 4)
        self.BindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        self.PixelStorei(GL_PACK_ALIGNMENT, 1); self.PixelStorei(GL_PACK_ROW_LENGTH, 0)
        self.ReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, self.buf)
        return w, h, self.buf.raw[:w * h * 4]

    def close(self):
        if self.ctx:
            self.egl.eglDestroyContext(self.dpy, self.ctx); self.ctx = None
            self.egl.eglTerminate(self.dpy)
