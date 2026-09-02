"""The taskbar as a place, rather than as a row of people.

Everything down there that is not one of them: the ball they kick about and
the hut they build. Both are props - a position, a shape, and no opinions -
so they share one window between them, and this module owns no timer at all.
`roamer.tick` steps and paints the yard as part of the frame it is already
running, which is the same bargain every other part of this app makes: one
timer, or none.

Nothing in here knows what a roamer is. The crew asks for a ball, asks for a
hut, and reads back where they are. The one thing the yard has to tell the
crew - that somebody has just right-clicked the hut down - it says through
`on_knock`, a callback the crew sets on the way past. That keeps the import
one way, and it keeps the physics in here checkable without a display.

The window is the whole screen, keyed transparent, exactly like a roamer's
and for the same two reasons: a window that follows a moving prop judders
(see `Roamer._place` for the long version), and the keyed colour is
click-through on Windows, so the right-click that knocks the hut down is the
only click this window ever takes. Everything else falls through to whatever
is underneath.
"""

import math
import tkinter as tk

import winkit

# ------------------------------------------------------------------ the ball
#
# Its own numbers rather than the roamer's. A ball is not a person: it comes
# off the floor much further than he does, it keeps rolling after it has
# stopped bouncing, and nothing about it squashes.
BALL_R = 11.0
BALL_G = 2400.0         # px/s^2
BALL_BOUNCE = 0.62
BALL_ROLL = 0.75        # horizontal decay per second, and only once it is down
BALL_STOP = 12.0        # rolling slower than this and it has stopped
BALL_DROP = 220.0       # how far above the floor it is thrown in from

# ------------------------------------------------------------------- the hut
HUT_W, HUT_H = 96.0, 74.0
ROOF_H = 26.0
ROOF_OUT = 8.0          # the eaves, so the roof reads as a roof
DOOR_W, DOOR_H = 26.0, 40.0

INK = "#3A3226"
WOOD = "#B98A4B"        # the walls, and the plank he carries home
ROOF_C = "#8C5A2B"
DOOR_C = "#2A241C"
BALL_C = "#E8543F"

on_knock = None         # set by the crew: called (x, floor) once the hut has
                        # gone, and only when somebody knocked it down

_root = None
_key = None
_win = None
_ball = None
_hut = None


class _Ball(object):
    """A ball on a floor between two walls. No window, no canvas, no Tk."""

    __slots__ = ("x", "y", "vx", "vy", "r", "spin", "floor", "walls")

    def __init__(self, x, floor, walls):
        self.x = float(x)
        self.y = float(floor) - BALL_DROP
        self.vx = self.vy = self.spin = 0.0
        self.r = BALL_R
        self.floor = float(floor)
        self.walls = walls

    def step(self, dt):
        self.vy += BALL_G * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.spin += self.vx / self.r * dt
        x1, x2 = self.walls
        if self.x - self.r < x1:
            self.x, self.vx = x1 + self.r, abs(self.vx) * BALL_BOUNCE
        elif self.x + self.r > x2:
            self.x, self.vx = x2 - self.r, -abs(self.vx) * BALL_BOUNCE
        rest = self.floor - self.r
        if self.y < rest:
            return
        self.y = rest
        # It bounces only if the bounce would actually get it off the floor
        # and keep it there for the next frame. A plain "slower than this and
        # it has stopped" cannot work here: one frame of gravity at 60fps is
        # already 40px/s, so any threshold small enough to look like a stop is
        # one the ball climbs back over every single frame, and it hums
        # against the taskbar for ever. Measuring the rebound against what
        # gravity is about to take back is exact, and right at any framerate.
        up = self.vy * BALL_BOUNCE
        if up > BALL_G * dt:
            self.vy = -up
            return
        self.vy = 0.0
        # The drag is on the roll, not on the flight: applied in the air it
        # would flatten every kick into a lob before it had gone anywhere.
        self.vx *= math.exp(-BALL_ROLL * dt)
        if abs(self.vx) < BALL_STOP:
            self.vx = 0.0


class _Hut(object):
    """A small house standing on a floor, centred on x."""

    __slots__ = ("x", "floor", "w", "h")

    def __init__(self, x, floor):
        self.x, self.floor = float(x), float(floor)
        self.w, self.h = HUT_W, HUT_H

    def holds(self, x, y):
        """Is that point on the hut? The right-click test, in screen
        coordinates. The eaves are not included: they overhang thin air."""
        return (abs(x - self.x) <= self.w / 2.0
                and self.floor - self.h <= y <= self.floor)


class _Yard(tk.Toplevel):
    """The one window both props are drawn on."""

    def __init__(self, root, key):
        tk.Toplevel.__init__(self, root)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-transparentcolor", key)
        self.attributes("-topmost", True)
        self.canvas = tk.Canvas(self, bg=key, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.at = (0, 0)
        self.rect = None
        self.drawn = None
        self.canvas.bind("<ButtonPress-3>", self._click)
        self.deiconify()

    def cover(self, x, y):
        """Sit over the whole of the screen that point is on.

        ponytail: one yard, on one screen. Two monitors and a kickabout
        started on the second one puts the ball on the first. A yard per
        screen is the fix, and it is not worth it until somebody notices.
        """
        found = winkit.screen_area(x, y)
        if found is None:
            found = (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())
        if found == self.rect:
            return
        self.rect = found
        self.at = (found[0], found[1])
        self.geometry("%dx%d+%d+%d" % (found[2] - found[0], found[3] - found[1],
                                       found[0], found[1]))
        self.drawn = None

    def _click(self, event):
        if _hut is not None and _hut.holds(event.x_root, event.y_root):
            knock_down()
        return "break"


def attach(root, key):
    """Where to build, and what colour is not there.

    Idempotent, and called by every roamer as he is created: the window itself
    waits until there is actually something to put in it.
    """
    global _root, _key
    _root, _key = root, key


def _open(x, y):
    if _root is None or _key is None:
        return None
    global _win
    if _win is None:
        try:
            _win = _Yard(_root, _key)
        except tk.TclError:
            _win = None
            return None
    try:
        _win.cover(x, y)
    except tk.TclError:
        return None
    return _win


def kick_off(x, floor):
    """A ball, thrown in above (x, floor). None if there is nowhere to put it,
    and then there is no game."""
    global _ball
    win = _open(x, floor)
    if win is None or win.rect is None:
        return None
    _ball = _Ball(x, floor, (win.rect[0] + 4.0, win.rect[2] - 4.0))
    return _ball


def ball():
    return _ball


def drop_ball():
    global _ball
    _ball = None
    paint()


def raise_hut(x, floor):
    """Up it goes. None if there is nowhere to put it."""
    global _hut
    if _open(x, floor) is None:
        return None
    _hut = _Hut(x, floor)
    paint()
    return _hut


def hut():
    return _hut


def knock_down():
    """Somebody kicked it in.

    Both halves in one call - the hut goes and the crew is told - so the
    right-click binding is one line and so is the test. `clear` deliberately
    does neither: quitting the app is not somebody knocking the hut down.
    """
    global _hut
    gone, _hut = _hut, None
    paint()
    if gone is not None and on_knock is not None:
        on_knock(gone.x, gone.floor)
    return gone


def step(dt):
    if _ball is not None:
        _ball.step(dt)


def paint():
    """Redraw, and only when something has moved.

    The same bargain the roamer's own paint makes: a hut on its own never
    changes, and comparing four numbers beats rebuilding six canvas items
    sixty times a second for nothing.
    """
    if _win is None:
        return
    pose = (None if _ball is None else (round(_ball.x, 1), round(_ball.y, 1),
                                        round(_ball.spin, 2)),
            None if _hut is None else (_hut.x, _hut.floor),
            _win.at)
    if pose == _win.drawn:
        return
    _win.drawn = pose
    cv = _win.canvas
    cv.delete("prop")
    dx, dy = _win.at
    # The hut first, so a ball rolling past goes in front of it rather than
    # disappearing behind the wall.
    if _hut is not None:
        _draw_hut(cv, _hut.x - dx, _hut.floor - dy)
    if _ball is not None:
        _draw_ball(cv, _ball.x - dx, _ball.y - dy, _ball.spin)


def _draw_hut(cv, x, base):
    half = HUT_W / 2.0
    wall = base - (HUT_H - ROOF_H)
    cv.create_rectangle(x - half, wall, x + half, base,
                        fill=WOOD, outline=INK, width=2, tags="prop")
    cv.create_polygon(x - half - ROOF_OUT, wall, x, base - HUT_H,
                      x + half + ROOF_OUT, wall,
                      fill=ROOF_C, outline=INK, width=2, tags="prop")
    cv.create_rectangle(x - DOOR_W / 2.0, base - DOOR_H,
                        x + DOOR_W / 2.0, base,
                        fill=DOOR_C, outline=INK, width=2, tags="prop")


def _draw_ball(cv, x, y, spin):
    cv.create_oval(x - BALL_R, y - BALL_R, x + BALL_R, y + BALL_R,
                   fill=BALL_C, outline=INK, width=2, tags="prop")
    # One line across it, turning with the roll. Without it a ball rolling
    # along the taskbar reads as a ball sliding along the taskbar.
    ox, oy = math.cos(spin) * BALL_R * 0.7, math.sin(spin) * BALL_R * 0.7
    cv.create_line(x - ox, y - oy, x + ox, y + oy, fill=INK, width=2,
                   tags="prop")


def clear():
    """Everything gone. Called when the last of them goes home, and at quit."""
    global _win, _ball, _hut
    _ball = _hut = None
    if _win is not None:
        try:
            tk.Toplevel.destroy(_win)
        except tk.TclError:
            pass
    _win = None


def _demo():
    """The ball, without a screen. `python yard.py`.

    Everything else in here is a canvas item or a window, and neither can be
    checked without a display. The physics can, and it is the only part with
    a branch in it worth getting wrong.
    """
    ball = _Ball(500.0, 800.0, (0.0, 1000.0))
    assert ball.y < 800.0 - BALL_R, "it comes in from above the floor"
    for _ in range(600):                     # ten seconds
        ball.step(1.0 / 60.0)
    assert abs(ball.y - (800.0 - BALL_R)) < 0.5, ("it has to settle", ball.y)
    assert ball.vy == 0.0 and ball.vx == 0.0, ("...and stop", ball.vx, ball.vy)

    # A bounce gives some of the drop back, and never all of it.
    ball = _Ball(500.0, 800.0, (0.0, 1000.0))
    high = []
    for _ in range(240):
        ball.step(1.0 / 60.0)
        high.append(ball.vy)
    assert min(high) < 0.0, "it has to come back up off the floor"
    assert min(high) > -max(high), "and not higher than it was dropped from"

    # Kicked sideways, it stops at the wall rather than leaving the screen.
    ball = _Ball(500.0, 800.0, (0.0, 1000.0))
    ball.vx = 4000.0
    for _ in range(600):
        ball.step(1.0 / 60.0)
    assert ball.x <= 1000.0 - BALL_R + 0.01, ("inside the wall", ball.x)

    hut = _Hut(500.0, 800.0)
    assert hut.holds(500.0, 780.0), "the middle of it is inside it"
    assert not hut.holds(500.0, 700.0), "and well above the roof is not"
    assert not hut.holds(700.0, 780.0), "nor well off to the side"
    print("ok  the ball falls, bounces, rolls to a stop and stays on screen")


if __name__ == "__main__":
    _demo()
