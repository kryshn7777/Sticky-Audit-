"""Thin ctypes shims over the Windows bits tkinter does not expose.

Everything here degrades to a sane default off Windows or when a call is
unavailable, so the app still runs if any of it fails.
"""

import ctypes
import os
import sys

APP_ID = "Claude.StickyNote"          # AppUserModelID: ties windows to the pinned icon
BOARD_TITLE = "Sticky Notes"          # also the handle the second instance looks for

_IS_WINDOWS = sys.platform == "win32"
_mutex = None                         # kept alive for the life of the process

FROZEN = getattr(sys, "frozen", False)


def packaged():
    """True when running from an installed MSIX package.

    A packaged app lives under a different set of rules: Windows assigns its
    taskbar identity, and its registry writes are virtualised into a private
    hive. Both matter below.
    """
    if not _IS_WINDOWS:
        return False
    APPMODEL_ERROR_NO_PACKAGE = 15700
    length = ctypes.c_uint32(0)
    try:
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(
            ctypes.byref(length), None)
    except (AttributeError, OSError):
        return False           # pre-Windows 8: packaging did not exist
    return rc != APPMODEL_ERROR_NO_PACKAGE


def resource_path(*parts):
    """Locate a bundled file whether we run from source or from a build.

    PyInstaller unpacks bundled data somewhere else entirely and points
    sys._MEIPASS at it, so __file__ is the wrong answer inside a build.
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def app_command():
    """The command line that launches this app, quoted and ready to store.

    A build is its own executable; from source it needs pythonw so no console
    window flashes up behind the notes.
    """
    if FROZEN:
        return '"%s"' % sys.executable
    launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stickynote.pyw")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return '"%s" "%s"' % (pythonw, launcher)


def _user32():
    return ctypes.windll.user32


# ------------------------------------------------------------------ display

def set_dpi_awareness():
    """Per-monitor DPI v2. Must run before the first Tk() call."""
    if not _IS_WINDOWS:
        return
    try:
        # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def set_app_id(app_id=APP_ID):
    """Give the process its own taskbar identity so windows group under the
    pinned shortcut instead of under a generic Python icon.

    Never do this in a packaged build: Windows derives the identity from the
    package, and overriding it breaks taskbar grouping and pinning.
    """
    if not _IS_WINDOWS or packaged():
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def _read_reg(path, name, default):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def dark_mode():
    """True when Windows apps are set to the dark theme."""
    return _read_reg(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                     "AppsUseLightTheme", 1) == 0


def text_scale():
    """Windows accessibility text scaling, as a multiplier. 1.0 when unset."""
    value = _read_reg(r"Software\Microsoft\Accessibility", "TextScaleFactor", 100)
    try:
        return max(1.0, min(2.25, int(value) / 100.0))
    except (TypeError, ValueError):
        return 1.0


def hwnd_of(widget):
    """Native window handle for a Tk window (its real toplevel, not the frame)."""
    try:
        return ctypes.windll.user32.GetParent(widget.winfo_id()) or widget.winfo_id()
    except (AttributeError, OSError):
        return 0


def dark_titlebar(widget, enabled=True):
    """Paint a normal window's title bar dark to match the system theme."""
    if not _IS_WINDOWS:
        return
    hwnd = hwnd_of(widget)
    if not hwnd:
        return
    flag = ctypes.c_int(1 if enabled else 0)
    for attribute in (20, 19):        # 20 on current Windows, 19 on older builds
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_int(attribute),
                ctypes.byref(flag), ctypes.sizeof(flag))
            return
        except (AttributeError, OSError):
            continue


# ----------------------------------------------------------- single instance

def claim_single_instance(title=BOARD_TITLE):
    """True if we are the first instance.

    If another instance already owns the app, raise its board window and
    return False so the caller can exit quietly. No sockets, no polling.
    """
    global _mutex
    if not _IS_WINDOWS:
        return True
    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, "Local\\" + APP_ID)
    if kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
        return True
    raise_existing(title)
    return False


def raise_existing(title=BOARD_TITLE):
    user32 = _user32()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, 5)        # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    return True


# --------------------------------------------------------------- run at login

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "StickyNote"


def startup_command():
    """The exact command Windows should run at login."""
    return app_command()


def get_run_at_startup():
    if packaged():
        # The Run key is virtualised inside a package, so what we wrote there
        # is not what Windows reads. The manifest declares a startup task and
        # the user turns it on in Settings; we cannot read that state here.
        return False
    return _read_reg(_RUN_KEY, _RUN_NAME, None) is not None


def open_startup_settings():
    """Open Settings > Apps > Startup, where a packaged app's startup lives."""
    try:
        os.startfile("ms-settings:startupapps")
        return True
    except OSError:
        return False


def set_run_at_startup(enabled):
    """Add or remove the login entry. Returns True on success.

    Refuses in a packaged build: writing the Run key there succeeds but does
    nothing, because the write is redirected into the package's private hive.
    """
    if not _IS_WINDOWS or packaged():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# ------------------------------------------------------- pinning to a window
#
# A note can be clipped to another application's title bar: drop it there and
# it follows that window around, and hides when the window does.
#
# Finding what is underneath means walking the desktop's z-order rather than
# calling WindowFromPoint, because the note being dragged is itself under the
# pointer. Skipping our own process is the whole trick.

TITLE_BAND = 42          # how far down from a window's top edge counts as its
                         # title bar. Real ones vary; this is generous on
                         # purpose, because the user is aiming while dragging.
_GA_ROOT = 2
_GW_HWNDFIRST, _GW_HWNDNEXT = 0, 2
_SW_SHOWMINIMIZED = 2


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", ctypes.c_uint32)]


_MONITOR_NEAREST = 2


_typed = False


def _pin_api():
    """user32, with the handle-returning calls typed.

    ctypes defaults every return value to c_int, which silently chops the top
    half off a 64-bit window handle. Everything here would then look at the
    wrong window, or at none at all.
    """
    global _typed
    user32 = _user32()
    if not _typed:
        user32.GetTopWindow.restype = ctypes.c_void_p
        user32.GetTopWindow.argtypes = [ctypes.c_void_p]
        user32.GetWindow.restype = ctypes.c_void_p
        user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        # MonitorFromPoint hands back a monitor handle and takes its POINT by
        # value, not by pointer. Both have to be spelled out or it comes back
        # truncated and every answer is about the wrong screen.
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [_Point, ctypes.c_uint]
        user32.GetMonitorInfoW.restype = ctypes.c_int
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(_MonitorInfo)]
        _typed = True
    return user32


def _own_pid():
    return os.getpid()


def _monitor(x, y):
    """The MONITORINFO for the monitor this point is on, or None."""
    if not _IS_WINDOWS:
        return None
    try:
        user32 = _pin_api()
        monitor = user32.MonitorFromPoint(_Point(int(x), int(y)),
                                          _MONITOR_NEAREST)
        if not monitor:
            return None
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not user32.GetMonitorInfoW(ctypes.c_void_p(monitor),
                                      ctypes.byref(info)):
            return None
    except (OSError, AttributeError):
        return None
    return info


def screen_area(x, y):
    """The whole rectangle of the monitor this point is on: (l, t, r, b).

    work_area() without the taskbar taken out of it. What this is for is
    sizing an overlay to a screen, where the bar is part of what may be drawn
    over rather than something to keep off.
    """
    info = _monitor(x, y)
    if info is None:
        return None
    r = info.rcMonitor
    if r.right - r.left < 200 or r.bottom - r.top < 200:
        return None
    return (r.left, r.top, r.right, r.bottom)


def work_area(x, y):
    """The usable rectangle of the monitor this point is on: (l, t, r, b).

    The screen minus whatever the shell has reserved, which in practice means
    the taskbar - so the bottom of this rectangle is the top of a bottom
    docked bar, and something standing on that line is standing on the
    taskbar.

    Asking the taskbar window itself would answer for the primary monitor
    only, would need a second question about which edge it is docked to, and
    would still be wrong while it is auto-hiding. One call covers all of that,
    and covers a second monitor with its own bar as well.

    None if the call is not available, which includes not being on Windows.
    """
    info = _monitor(x, y)
    if info is None:
        return None
    r = info.rcWork
    if r.right - r.left < 200 or r.bottom - r.top < 200:
        return None                      # nonsense: better to say we do not know
    return (r.left, r.top, r.right, r.bottom)


def window_rect(hwnd):
    """(left, top, right, bottom) on screen, or None if the window is gone."""
    if not _IS_WINDOWS or not hwnd:
        return None
    rect = _Rect()
    try:
        if not _user32().GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
            return None
    except OSError:
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def window_title(hwnd):
    if not _IS_WINDOWS or not hwnd:
        return ""
    user32 = _user32()
    try:
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
        return buf.value
    except OSError:
        return ""


def window_alive(hwnd):
    """True while the window still exists. A closed app must not keep a note
    stuck to where it used to be."""
    if not _IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32().IsWindow(ctypes.c_void_p(hwnd)))
    except OSError:
        return False


def window_showing(hwnd):
    """True when the window is on screen: not minimised, not hidden."""
    if not window_alive(hwnd):
        return False
    user32 = _user32()
    try:
        if not user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            return False
        return not user32.IsIconic(ctypes.c_void_p(hwnd))
    except OSError:
        return False


def _own_window(hwnd):
    """Is this one of ours? Notes must not clip to each other."""
    pid = ctypes.c_ulong(0)
    try:
        _user32().GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    except OSError:
        return True
    return pid.value == _own_pid()


def window_under(x, y):
    """The topmost window from another app at this screen point.

    Returns (hwnd, title, rect) or None. Walks the desktop in z-order and
    takes the first visible, non-minimised window from another process whose
    rectangle contains the point - which is what the user is looking at, and
    which WindowFromPoint would not give us while our own note is in the way.
    """
    if not _IS_WINDOWS:
        return None
    user32 = _pin_api()
    try:
        hwnd = user32.GetTopWindow(None)
    except OSError:
        return None
    guard = 0
    while hwnd and guard < 400:
        guard += 1
        if not _own_window(hwnd) and window_showing(hwnd) and window_title(hwnd):
            rect = window_rect(hwnd)
            if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                # A tool window with no width is not something to clip to.
                if rect[2] - rect[0] > 80 and rect[3] - rect[1] > 60:
                    return (hwnd, window_title(hwnd), rect)
        try:
            hwnd = user32.GetWindow(ctypes.c_void_p(hwnd), _GW_HWNDNEXT)
        except OSError:
            return None
    return None


def title_bar_target(x, y):
    """What the user is dropping a note onto, if it is a title bar.

    Returns (hwnd, title, rect) when the point is in the top band of another
    application's window, and None anywhere else - including over that window's
    contents, where a note has no business attaching itself.
    """
    return title_bar_under(((x, y),))


def title_bar_under(points):
    """The first foreign window whose title bar any of these points is on.

    One walk of the desktop for the whole set. A note is aimed by its top
    edge, and several points along that edge have to be tried because it may
    be hanging off one end of the bar - but doing that as several calls would
    walk the z-order once per point, and this runs while the mouse is moving.
    """
    if not _IS_WINDOWS or not points:
        return None
    user32 = _pin_api()
    try:
        hwnd = user32.GetTopWindow(None)
    except OSError:
        return None
    guard = 0
    while hwnd and guard < 400:
        guard += 1
        if not _own_window(hwnd) and window_showing(hwnd) and window_title(hwnd):
            rect = window_rect(hwnd)
            if rect and rect[2] - rect[0] > 80 and rect[3] - rect[1] > 60:
                for x, y in points:
                    if (rect[0] <= x < rect[2] and rect[1] <= y < rect[3]
                            and y - rect[1] <= TITLE_BAND):
                        return (hwnd, window_title(hwnd), rect)
                    if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                        return None      # over its contents: nothing to clip to
        try:
            hwnd = user32.GetWindow(ctypes.c_void_p(hwnd), _GW_HWNDNEXT)
        except OSError:
            return None
    return None


def find_window(title):
    """The first visible window from another app with exactly this title.

    Used to pick a pin back up after a restart: window handles do not survive
    one, but the title on the bar usually does.
    """
    if not _IS_WINDOWS or not title:
        return None
    user32 = _pin_api()
    try:
        hwnd = user32.GetTopWindow(None)
    except OSError:
        return None
    guard = 0
    while hwnd and guard < 400:
        guard += 1
        if (not _own_window(hwnd) and window_showing(hwnd)
                and window_title(hwnd) == title):
            rect = window_rect(hwnd)
            if rect:
                return (hwnd, title, rect)
        try:
            hwnd = user32.GetWindow(ctypes.c_void_p(hwnd), _GW_HWNDNEXT)
        except OSError:
            return None
    return None
