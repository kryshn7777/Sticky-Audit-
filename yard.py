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
click-through on Windows, so the right-click on the hut itself is the only
click this window ever takes. Everything else falls through to whatever is
underneath.
"""

import math
import random
import tkinter as tk

import winkit
from mascot import HEAD as _HEAD, LEG_H as _LEG_H, _walker

# The walker is drawn about his face, not his feet - see Roamer.paint,
# which measures the same way.
WALK_H = _HEAD // 2 + _LEG_H

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

# ------------------------------------------------------------------- the fire
# Three or more of them together and they light one, sit round it and talk
# until it burns out. It owns nothing but a position and a clock: how long it
# lasts is the crew's business, because the scene they are playing has to end
# with it rather than beside it.
FIRE_W, FIRE_H = 26.0, 40.0     # the flame at full height
FIRE_LOGS = 46.0                # how far the wood sticks out either side
EMBER_S = 3.0                   # the last of it, glowing rather than burning
FLAME_C = "#F0913A"
FLAME_HOT = "#FFDA6B"
EMBER_C = "#C0452A"


class _Fire:
    """Where it is, how long it has left, and how long it has been going.

    The flicker is solved off `t` rather than stored per flame, the same way
    the ball's roll is: one number in, a shape out, and nothing to keep in
    step across a frame the event loop was late for.
    """

    def __init__(self, x, floor, life):
        self.x, self.floor = float(x), float(floor)
        self.life = self.left = float(life)
        self.t = 0.0

    def step(self, dt, elapsed=None):
        """`dt` is the frame, `elapsed` is the time.

        They are not the same number: the crew clamps its own dt so a stalled
        event loop cannot teleport anybody, and while somebody is just sitting
        here the crew ticks five times a second - so a fire burning on dt
        would take a hundred minutes to get through twenty-five. The flicker
        wants the frame; how much fire is left wants the clock.
        """
        self.t += dt
        self.left -= dt if elapsed is None else elapsed

    @property
    def dying(self):
        """Down to embers: the flame is going out rather than burning."""
        return self.left <= EMBER_S

    @property
    def scale(self):
        """How much flame is left, 1 while it burns and 0 as it dies."""
        if not self.dying:
            return 1.0
        return max(0.0, self.left / EMBER_S)

    def holds(self, x, y):
        """Is this point on the fire? Generous about it: it is smaller than a
        hut and the flame moves, so the box is the wood plus the tallest the
        flame gets."""
        return (abs(x - self.x) <= FIRE_LOGS / 2.0 + 6.0
                and self.floor - FIRE_H - 8.0 <= y <= self.floor + 4.0)


# -------------------------------------------------------------------- a wreck
# What a hut leaves when it comes down: planks lying where it stood, each with
# its own time on it, so the pile goes a piece at a time rather than blinking
# out whole. It is only something to look at - a wreck is not a hut, nothing
# can be built out of it, and the crew never asks it anything.
WRECK_W, WRECK_H = 34.0, 6.0
WRECK_N = 7
WRECK_S = (3.5, 7.0)    # how long a plank lies there before it is gone
WRECK_FADE = 0.35       # the last of its life, spent shrinking away

# -------------------------------------------------------------------- a van
# Somebody has called for help and something turns up for it: an ambulance
# for a man who has been knocked down, a police car for two who are still at
# it. One prop for both - a shape that drives on, does its one thing and
# drives off again - and it knows no more about a roamer than the hut does.
# The crew reads `phase` off it and plays its own half against that: who gets
# carried, who runs, and who goes home afterwards is all decided over there.
# The two of them are different vehicles, not one box in two colours. A type
# III ambulance is about two and a third times as long as it is tall, and the
# patient box behind the cab is the tall part - that step down to the cab roof
# is what makes it read as an ambulance from across the room. A patrol car is
# a saloon: longer, much lower, with the cabin set into the middle of it.
AMB_W, AMB_H = 116.0, 46.0      # the box, floor to roof
AMB_CAB = 13.0                  # how far the cab roof sits below the box
AMB_BOX = 0.60                  # how much of the length the box takes
CAR_W, CAR_H = 126.0, 17.0      # the body, without the cabin on top
CAR_CAB = 15.0                  # ...and the cabin above it. Long and low:
                                # a patrol car that is as tall as it is long
                                # is a van with a light on it
ICE_W, ICE_H = 108.0, 44.0      # the ice cream van: a box with an awning
SERVE_MAX_S = 30.0              # nobody parks it there all afternoon
AWNING_C = "#E86A6A"
SCOOP_C = "#F2B8CB"
CONE_C = "#D9A05B"
WHEEL_R = 9.0
HUB_R = 3.4
VAN_SPEED = 430.0
VAN_OFF = 170.0                 # how far past the edge it starts, and ends
VAN_STAND = 130.0               # how far short of the job it pulls up
MEDIC_SPEED = 130.0
MEDIC_GAP = 40.0                # how far apart the two of them carry it
STRETCHER_H = 26.0              # how high off the floor they hold it
LOAD_S = 0.9                    # how long the lift takes
POLICE_WAIT_S = 1.8             # how long it sits there before giving chase
LAMP_HZ = 3.0
PAPER = "#F4EFE2"
CROSS_C = "#D6453C"
POLICE_C = "#3B4E8C"
LAMP_C = "#5FA8FF"
GLASS_C = "#A8C6D6"
COAT = "#F7F4EC"                # what the two of them are wearing
COAT_LIMB = "#C9C2B2"


class _Van(object):
    """An ambulance or a police car: a position, a phase and a clock.

    The phases are the whole interface. "in" is driving on, "out" is the two
    of them walking to the job, "load" is the lift, "back" is carrying him to
    the doors, "wait" is a police car sitting there while the pair of them
    bolt, and "away" is leaving. A medic van goes in-out-load-back-away and a
    police car goes in-wait-away, so both are the same few lines of step.
    """

    def __init__(self, kind, at_x, floor, way, walls):
        self.kind = kind                # "medic", "police" or "icecream"
        self.w = {"medic": AMB_W, "police": CAR_W}.get(kind, ICE_W)
        self.at_x = float(at_x)         # what it came for
        self.floor = float(floor)
        self.way = float(way)           # +1 driving right
        self.walls = walls
        self.x = (walls[0] if way > 0 else walls[1]) - way * VAN_OFF
        # An ambulance loads through the back, so it pulls up past him and
        # puts its doors where he is; a police car simply stops short.
        want = (self.at_x + way * VAN_STAND if kind == "medic"
                else self.at_x - way * VAN_STAND)
        self.stop_x = min(max(want, walls[0] + self.w / 2.0),
                          walls[1] - self.w / 2.0)
        self.phase = "in"
        self.t = 0.0
        self.reach = 0.0                # how far the pair are from the doors
        self.carry = False              # is there anybody on the stretcher

    @property
    def door(self):
        """The back doors: where they get out, and what he is loaded into."""
        return self.x - self.way * self.w / 2.0

    @property
    def side(self):
        """Which way from the doors the job is.

        Worked out rather than fixed at -way, because a van that ran out of
        room and stopped short of where it meant to has its doors on the
        other side of him, and the two of them still have to walk to him.
        """
        return 1.0 if self.at_x >= self.door else -1.0

    @property
    def walk(self):
        """How far they have to go from the doors to reach him."""
        return max(0.0, abs(self.at_x - self.door))

    def stretcher(self):
        """Where a man being carried is, or None if nobody is on it yet.

        The crew asks this every frame and puts him there. Leaving him a
        roamer rather than drawing a body in here is what makes it him who is
        carried off: his own colours, his own face, his own note to go back
        to afterwards.
        """
        if self.phase not in ("load", "back"):
            return None
        return (self.door + self.side * self.reach, self.floor - STRETCHER_H)

    @property
    def gone(self):
        return (self.phase == "away"
                and (self.x < self.walls[0] - VAN_OFF
                     or self.x > self.walls[1] + VAN_OFF))

    def leave(self):
        """Finished here. Off it goes, from wherever it is in its day."""
        if self.phase != "away":
            self.phase, self.t = "away", 0.0

    def step(self, dt):
        self.t += dt
        if self.phase == "in":
            self.x += self.way * VAN_SPEED * dt
            if (self.x - self.stop_x) * self.way >= 0.0:
                self.x = self.stop_x
                self.phase = {"medic": "out",
                              "icecream": "serve"}.get(self.kind, "wait")
                self.t = 0.0
        elif self.phase == "out":
            self.reach = min(self.reach + MEDIC_SPEED * dt, self.walk)
            if self.reach >= self.walk:
                self.phase, self.t = "load", 0.0
        elif self.phase == "load":
            if self.t >= LOAD_S:
                self.carry = True
                self.phase, self.t = "back", 0.0
        elif self.phase == "back":
            self.reach = max(0.0, self.reach - MEDIC_SPEED * dt)
            if self.reach <= 0.0:
                self.phase, self.t = "away", 0.0
        elif self.phase == "wait":
            if self.t >= POLICE_WAIT_S:
                self.phase, self.t = "away", 0.0
        elif self.phase == "serve":
            # The crew sends it off when the queue is done; the cap is only
            # so a van nobody queued at does not sit there for ever.
            if self.t >= SERVE_MAX_S:
                self.phase, self.t = "away", 0.0
        else:
            self.x += self.way * VAN_SPEED * dt


on_knock = None         # set by the crew: called (x, floor) once the hut has
                        # gone, and only when somebody knocked it down

_root = None
_key = None
_win = None
_ball = None
_hut = None
_fire = None
_van = None
_wreck = []             # [x, y, angle, left, total] a plank


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
        self._menu = None
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
            menu = self.hut_menu()
        elif _fire is not None and _fire.holds(event.x_root, event.y_root):
            menu = self.fire_menu()
        else:
            return "break"
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def fire_menu(self):
        """What a right-click on a fire offers. Built here, posted there, for
        the same reason the hut's is."""
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Put it out", command=douse)
        self._menu.add_command(label="Leave it burning")
        return self._menu

    def hut_menu(self):
        """The menu the right-click puts up - built here, posted there.

        A hut used to come down on the click itself. It is the one thing on
        this window that cannot be undone: they spend the best part of a
        minute walking off the screen for the wood, and a right-click that
        pulls the whole thing over with no warning is a right-click nobody
        dares use twice. So the click asks, and the menu does it.

        Split from the posting for the same reason the note's menu is: a
        popup takes a grab, and a check that has to dismiss a grab is a check
        that hangs the suite the day it fails.
        """
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="Knock it down", command=knock_down)
        self._menu.add_command(label="Leave it standing")
        return self._menu


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


def light_fire(x, floor, life):
    """A fire at (x, floor) with `life` seconds in it. None if there is
    nowhere to put it, and then there is no campfire."""
    global _fire
    win = _open(x, floor)
    if win is None:
        return None
    _fire = _Fire(x, floor, life)
    return _fire


def fire():
    return _fire


def douse():
    """Out, now. Called when whoever was sat round it is not there any more -
    a fire nobody is at is a fire nobody lit."""
    global _fire
    _fire = None


def call_van(kind, x, floor):
    """Something on its way to (x, floor). None if there is nowhere for it.

    One at a time: a second ambulance while the first is still loading is two
    ambulances for one man. Whether it was worth calling is decided by
    whoever calls it - all this does is drive.
    """
    global _van
    if _van is not None:
        return None
    win = _open(x, floor)
    if win is None or win.rect is None:
        return None
    walls = (float(win.rect[0]), float(win.rect[2]))
    # From the nearer edge, so it is on the screen quickly rather than
    # crossing the whole bar to reach somebody lying at one end of it.
    way = 1.0 if (x - walls[0]) < (walls[1] - x) else -1.0
    _van = _Van(kind, x, floor, way, walls)
    return _van


def van():
    return _van


def send_off():
    """Whatever was called for is finished with, now rather than when it has
    driven off. Used when the man it came for is taken out of it."""
    global _van
    _van = None
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
    if gone is not None:
        _wreck.extend(_scatter(gone))
    paint()
    if gone is not None and on_knock is not None:
        on_knock(gone.x, gone.floor)
    return gone


def _scatter(hut):
    """The planks it leaves, spread across where it stood.

    Laid out along its base rather than dropped at random inside it: a pile
    that is narrower than the hut was reads as a hut that shrank, and the
    whole point of leaving anything behind is that the bar remembers what was
    there for a few seconds.
    """
    out = []
    for i in range(WRECK_N):
        u = (i + 0.5) / WRECK_N - 0.5
        life = random.uniform(*WRECK_S)
        out.append([hut.x + u * hut.w * 1.15 + random.uniform(-4.0, 4.0),
                    hut.floor - random.uniform(0.0, WRECK_H * 1.6),
                    random.uniform(-0.45, 0.45), life, life])
    return out


def step(dt, elapsed=None):
    """One frame of the props. `elapsed` is real time, `dt` is the clamped
    frame - see _Fire.step for why anything with a clock on it needs both."""
    global _fire
    gone = dt if elapsed is None else elapsed
    if _ball is not None:
        _ball.step(dt)
    if _fire is not None:
        _fire.step(dt, gone)
        if _fire.left <= 0.0:
            _fire = None
    global _van
    if _van is not None:
        _van.step(dt)
        if _van.gone:
            _van = None
    if _wreck:
        for plank in _wreck:
            plank[3] -= gone
        _wreck[:] = [plank for plank in _wreck if plank[3] > 0.0]


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
            # A tenth of a second of the wreck's clock. Rounded, or a pile
            # that only shrinks over the last third of its life redraws every
            # frame for six seconds to show nothing changing.
            tuple(round(plank[3], 1) for plank in _wreck),
            # A flame that is not redrawn is a picture of a flame, so this one
            # is deliberately in the pose: while there is a fire, every frame
            # is a new one.
            None if _fire is None else round(_fire.t, 3),
            # Same again for the van: while one is on the screen every frame
            # is a new one, because the lamp flashes and the pair of them are
            # walking.
            None if _van is None else (round(_van.x, 1), _van.phase,
                                       round(_van.reach, 1), round(_van.t, 2)),
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
    for plank in _wreck:
        _draw_plank(cv, plank, dx, dy)
    if _fire is not None:
        _draw_fire(cv, _fire, dx, dy)
    if _van is not None:
        _draw_van(cv, _van, dx, dy)
    if _ball is not None:
        _draw_ball(cv, _ball.x - dx, _ball.y - dy, _ball.spin)


def _along(v, u, dx):
    """A point along the vehicle, 0 at the back of it and 1 at the nose.

    Everything below is laid out in these rather than in pixels, so one set
    of numbers draws it driving either way and nothing is written twice with
    the signs flipped.
    """
    return v.x - dx + v.way * (u - 0.5) * v.w


def _wheel(cv, x, axle):
    cv.create_oval(x - WHEEL_R, axle - WHEEL_R, x + WHEEL_R, axle + WHEEL_R,
                   fill=INK, outline=INK, tags="prop")
    cv.create_oval(x - HUB_R, axle - HUB_R, x + HUB_R, axle + HUB_R,
                   fill=GLASS_C, outline=INK, tags="prop")


def _lightbar(cv, x1, x2, top, t, warm):
    """Two lamps, one lit at a time, so it actually flashes.

    `warm` is what the other lamp is: red on an ambulance, red on a police
    car too - the blue one is the pair to it, and a bar where both are the
    same colour reads as a roof rack.
    """
    on = int(t * LAMP_HZ) % 2
    mid = (x1 + x2) / 2.0
    for i, (a, b) in enumerate(((x1, mid), (mid, x2))):
        cv.create_rectangle(a, top - 7.0, b, top,
                            fill=(LAMP_C if i == 0 else warm) if i == on
                            else INK, outline=INK, width=1, tags="prop")


def _draw_ambulance(cv, v, dx, dy):
    """A box van: cab at the front, patient box behind it, stripe down it.

    Drawn in the same flat hand as the hut - two-pixel ink, no gradients -
    because a vehicle rendered better than the man it came for reads as
    somebody else's artwork parked on the bar.
    """
    base = v.floor - dy
    axle = base - WHEEL_R
    box_top = base - AMB_H
    cab_top = box_top + AMB_CAB
    tail, nose = _along(v, 0.0, dx), _along(v, 1.0, dx)
    step = _along(v, AMB_BOX, dx)
    # The box, and the cab in front of it with a sloped nose.
    cv.create_rectangle(tail, box_top, step, axle,
                        fill=PAPER, outline=INK, width=2, tags="prop")
    cv.create_polygon(step, cab_top, _along(v, 0.90, dx), cab_top,
                      nose, cab_top + 9.0, nose, axle, step, axle,
                      fill=PAPER, outline=INK, width=2, tags="prop")
    # The windscreen follows that slope; the door window sits square behind it.
    cv.create_polygon(_along(v, 0.895, dx), cab_top + 3.0,
                      _along(v, 0.985, dx), cab_top + 10.0,
                      _along(v, 0.985, dx), cab_top + 17.0,
                      _along(v, 0.895, dx), cab_top + 17.0,
                      fill=GLASS_C, outline=INK, width=1, tags="prop")
    cv.create_rectangle(_along(v, 0.70, dx), cab_top + 4.0,
                        _along(v, 0.86, dx), cab_top + 16.0,
                        fill=GLASS_C, outline=INK, width=1, tags="prop")
    # The stripe along the box, and the cross on it. Both on the box only:
    # a stripe that runs over the cab door is a stripe nobody paints.
    band = box_top + AMB_H * 0.52
    cv.create_rectangle(tail, band, step, band + 7.0,
                        fill=CROSS_C, outline="", tags="prop")
    arm, mid = 8.0, box_top + AMB_H * 0.28
    cross_x = _along(v, 0.30, dx)
    cv.create_rectangle(cross_x - arm / 3.0, mid - arm,
                        cross_x + arm / 3.0, mid + arm,
                        fill=CROSS_C, outline="", tags="prop")
    cv.create_rectangle(cross_x - arm, mid - arm / 3.0,
                        cross_x + arm, mid + arm / 3.0,
                        fill=CROSS_C, outline="", tags="prop")
    # The back doors he is loaded through, and the wheels under it.
    cv.create_line(_along(v, 0.09, dx), box_top, _along(v, 0.09, dx), axle,
                   fill=INK, width=2, tags="prop")
    for u in (0.20, 0.78):
        _wheel(cv, _along(v, u, dx), axle)
    bar = sorted((_along(v, 0.70, dx), _along(v, 0.92, dx)))
    _lightbar(cv, bar[0], bar[1], cab_top, v.t, CROSS_C)


def _draw_police(cv, v, dx, dy):
    """A saloon in the old livery: white body, black doors, lamps on top."""
    base = v.floor - dy
    axle = base - WHEEL_R
    body_top = base - WHEEL_R - CAR_H
    cab_top = body_top - CAR_CAB
    cv.create_polygon(_along(v, 0.02, dx), body_top,
                      _along(v, 0.98, dx), body_top,
                      _along(v, 1.00, dx), body_top + CAR_H * 0.45,
                      _along(v, 0.98, dx), axle + 4.0,
                      _along(v, 0.02, dx), axle + 4.0,
                      fill=PAPER, outline=INK, width=2, tags="prop")
    # The cabin, raked at both ends, and the glass inside it.
    cv.create_polygon(_along(v, 0.30, dx), body_top,
                      _along(v, 0.41, dx), cab_top,
                      _along(v, 0.66, dx), cab_top,
                      _along(v, 0.77, dx), body_top,
                      fill=PAPER, outline=INK, width=2, tags="prop")
    cv.create_polygon(_along(v, 0.345, dx), body_top - 2.0,
                      _along(v, 0.425, dx), cab_top + 3.0,
                      _along(v, 0.515, dx), cab_top + 3.0,
                      _along(v, 0.515, dx), body_top - 2.0,
                      fill=GLASS_C, outline=INK, width=1, tags="prop")
    cv.create_polygon(_along(v, 0.545, dx), body_top - 1.0,
                      _along(v, 0.545, dx), cab_top + 3.0,
                      _along(v, 0.645, dx), cab_top + 3.0,
                      _along(v, 0.735, dx), body_top - 1.0,
                      fill=GLASS_C, outline=INK, width=1, tags="prop")
    # The doors, which are the whole livery: black doors on a white car, the
    # way a panda car has always been done. Between the arches only - a black
    # panel that runs over the wings is a black car with white ends.
    door = sorted((_along(v, 0.33, dx), _along(v, 0.68, dx)))
    cv.create_rectangle(door[0], body_top, door[1], axle + 1.0,
                        fill=POLICE_C, outline=INK, width=1, tags="prop")
    split = (door[0] + door[1]) / 2.0
    cv.create_line(split, body_top, split, axle + 1.0,
                   fill=INK, width=1, tags="prop")
    mid = (body_top + axle + 1.0) / 2.0
    cv.create_oval(split - 9.0, mid - 4.5, split - 1.0, mid + 4.5,
                   fill=PAPER, outline=INK, width=1, tags="prop")
    for u in (0.22, 0.78):
        _wheel(cv, _along(v, u, dx), axle)
    bar = sorted((_along(v, 0.44, dx), _along(v, 0.63, dx)))
    _lightbar(cv, bar[0], bar[1], cab_top, v.t, CROSS_C)


def _draw_icecream(cv, v, dx, dy):
    """A box van got up for sweeter work: awning over the hatch, cone on
    the roof, and nothing about it in a hurry."""
    base = v.floor - dy
    axle = base - WHEEL_R
    top = base - ICE_H
    tail, nose = _along(v, 0.0, dx), _along(v, 1.0, dx)
    cv.create_rectangle(min(tail, nose), top, max(tail, nose), axle,
                        fill=PAPER, outline=INK, width=2, tags="prop")
    # The hatch they are served through, on the back half, with its awning.
    h1, h2 = sorted((_along(v, 0.06, dx), _along(v, 0.44, dx)))
    cv.create_rectangle(h1, top + 10.0, h2, top + 26.0,
                        fill=GLASS_C, outline=INK, width=1, tags="prop")
    stripes = 5
    for i in range(stripes):
        a = h1 - 3.0 + (h2 - h1 + 6.0) * i / stripes
        b = h1 - 3.0 + (h2 - h1 + 6.0) * (i + 1) / stripes
        cv.create_rectangle(a, top + 2.0, b, top + 9.0,
                            fill=AWNING_C if i % 2 == 0 else PAPER,
                            outline=INK, width=1, tags="prop")
    # The windscreen at the driving end, and the cone up top.
    cv.create_rectangle(min(nose, _along(v, 0.80, dx)) + 3.0, top + 6.0,
                        max(nose, _along(v, 0.80, dx)) - 3.0, top + 20.0,
                        fill=GLASS_C, outline=INK, width=1, tags="prop")
    cone_x = _along(v, 0.62, dx)
    cv.create_polygon(cone_x - 5.0, top - 12.0, cone_x + 5.0, top - 12.0,
                      cone_x, top - 1.0, fill=CONE_C, outline=INK, width=1,
                      tags="prop")
    cv.create_oval(cone_x - 6.0, top - 23.0, cone_x + 6.0, top - 11.0,
                   fill=SCOOP_C, outline=INK, width=1, tags="prop")
    for u in (0.20, 0.80):
        _wheel(cv, _along(v, u, dx), axle)


def _draw_van(cv, v, dx, dy):
    """The vehicle, and the two of them walking about beside it."""
    if v.kind == "medic":
        _draw_ambulance(cv, v, dx, dy)
    elif v.kind == "icecream":
        _draw_icecream(cv, v, dx, dy)
        return
    else:
        _draw_police(cv, v, dx, dy)
        return
    if v.phase in ("in", "away"):
        return
    # The two of them, out and walking, with the stretcher between them.
    mid_x = v.door + v.side * v.reach
    lead = mid_x + v.side * MEDIC_GAP / 2.0
    back = mid_x - v.side * MEDIC_GAP / 2.0
    # Facing the way they are walking: out to him, and back to the doors.
    face = v.side if v.phase in ("out", "load") else -v.side
    hold = v.floor - STRETCHER_H
    if v.carry or v.phase == "load":
        cv.create_rectangle(min(lead, back) - dx, hold - dy - 3.0,
                            max(lead, back) - dx, hold - dy + 3.0,
                            fill=PAPER, outline=INK, width=2, tags="prop")
    step = None if v.phase == "load" else v.reach / 14.0
    for mx in (lead, back):
        hand = (mx - dx + face * 12.0, hold - dy)
        _walker(cv, mx - dx, v.floor - dy - WALK_H, step,
                COAT, COAT_LIMB, INK, facing=0.62 * face,
                hands=(hand, hand) if (v.carry or v.phase == "load") else None,
                tag="prop")


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


def _draw_fire(cv, blaze, dx, dy):
    """Two logs and a flame, or two logs and a glow once it is going out.

    The flame is one polygon inside another rather than a stack of tongues:
    at this size anything more detailed is mud, and the whole read comes from
    the outline moving. Both waves are odd multiples of each other so the tip
    never sits still, which is the difference between a fire and a triangle.
    """
    x, base = blaze.x - dx, blaze.floor - dy
    half = FIRE_LOGS / 2.0
    cv.create_line(x - half, base - 2.0, x + half, base - 7.0,
                   fill=WOOD, width=6, capstyle="round", tags="prop")
    cv.create_line(x - half, base - 7.0, x + half, base - 2.0,
                   fill=WOOD, width=6, capstyle="round", tags="prop")
    scale = blaze.scale
    if scale <= 0.02:
        return
    t = blaze.t
    tall = FIRE_H * scale * (0.86 + 0.14 * math.sin(t * 9.3))
    wide = FIRE_W * scale * (0.9 + 0.1 * math.sin(t * 6.1 + 1.0))
    lean = math.sin(t * 4.7) * wide * 0.16
    hot = EMBER_C if blaze.dying else FLAME_C
    tip = FLAME_HOT if not blaze.dying else FLAME_C
    for shrink, colour in ((1.0, hot), (0.52, tip)):
        w, h = wide * shrink, tall * shrink
        cv.create_polygon(
            x - w / 2.0, base - 4.0,
            x - w * 0.34 + lean * 0.4, base - 4.0 - h * 0.52,
            x + lean, base - 4.0 - h,
            x + w * 0.36 + lean * 0.4, base - 4.0 - h * 0.46,
            x + w / 2.0, base - 4.0,
            fill=colour, outline="", smooth=True, tags="prop")


def _draw_plank(cv, plank, dx, dy):
    """One plank of the wreck, lying at whatever angle it landed at.

    It shrinks about its own middle over the last of its life rather than
    changing colour: the window is keyed transparent, so there is no
    background to fade into - anything but the key is fully there.
    """
    x, y, ang, left, total = plank
    scale = min(1.0, (left / total) / WRECK_FADE)
    half, thick = WRECK_W / 2.0 * scale, WRECK_H / 2.0 * scale
    if half < 1.0:
        return
    cos, sin = math.cos(ang), math.sin(ang)
    points = []
    for ox, oy in ((-half, -thick), (half, -thick), (half, thick),
                   (-half, thick)):
        points.extend((x - dx + ox * cos - oy * sin,
                       y - dy + ox * sin + oy * cos))
    cv.create_polygon(*points, fill=WOOD, outline=INK, width=2, tags="prop")


def _draw_ball(cv, x, y, spin):
    cv.create_oval(x - BALL_R, y - BALL_R, x + BALL_R, y + BALL_R,
                   fill=BALL_C, outline=INK, width=2, tags="prop")
    # One line across it, turning with the roll. Without it a ball rolling
    # along the taskbar reads as a ball sliding along the taskbar.
    ox, oy = math.cos(spin) * BALL_R * 0.7, math.sin(spin) * BALL_R * 0.7
    cv.create_line(x - ox, y - oy, x + ox, y + oy, fill=INK, width=2,
                   tags="prop")


def hide():
    """Out of sight while something is full-screen. The props are still there
    - a hut half way through an evening is not knocked down by somebody
    watching a video - they are simply not drawn over the top of it."""
    if _win is not None:
        try:
            _win.withdraw()
        except tk.TclError:
            pass


def show():
    if _win is not None:
        try:
            _win.deiconify()
        except tk.TclError:
            pass


def clear():
    """Everything gone. Called when the last of them goes home, and at quit."""
    global _win, _ball, _hut, _fire, _van
    _ball = _hut = _fire = _van = None
    del _wreck[:]
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
    planks = _scatter(_Hut(500.0, 800.0))
    assert len(planks) == WRECK_N, len(planks)
    assert all(abs(p[0] - 500.0) <= HUT_W * 0.65 for p in planks), \
        "the pile is about as wide as the hut was"
    assert all(WRECK_S[0] <= p[3] <= WRECK_S[1] for p in planks), \
        "and every plank has its own time on it"

    blaze = _Fire(500.0, 800.0, 5.0)
    blaze.step(1.0)
    assert not blaze.dying and blaze.scale == 1.0, "it burns before it dies"
    blaze.step(3.0)
    assert blaze.dying and 0.0 < blaze.scale < 1.0, "and then it goes down"
    blaze.step(1.1)
    assert blaze.left <= 0.0 and blaze.scale == 0.0, "and then it is out"

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

    # The van, phase by phase. Every branch of it is a clock, so it runs
    # without a screen and it is the one part worth getting wrong.
    def drive(kind, way):
        van = _Van(kind, 900.0, 800.0, way, (0.0, 1600.0))
        legs = []
        for _ in range(4000):
            van.step(1.0 / 60.0)
            if not legs or legs[-1] != van.phase:
                legs.append(van.phase)
            if van.gone:
                break
        return van, legs

    sweet = _Van("icecream", 900.0, 800.0, 1.0, (0.0, 1600.0))
    legs = []
    for i in range(4000):
        sweet.step(1.0 / 60.0)
        if not legs or legs[-1] != sweet.phase:
            legs.append(sweet.phase)
        if sweet.phase == "serve" and sweet.t > 0.5:
            sweet.leave()               # the crew's job, done here by hand
        if sweet.gone:
            break
    assert legs == ["in", "serve", "away"], legs
    assert sweet.gone, "and it goes when it is told"

    van, legs = drive("medic", 1.0)
    assert legs == ["in", "out", "load", "back", "away"], legs
    assert van.carry, "somebody has to end up on the stretcher"
    assert van.gone, "and the whole thing ends with it off the screen"
    law, legs = drive("police", -1.0)
    assert legs == ["in", "wait", "away"], legs
    assert not law.carry, "a police car does not carry anybody off"
    assert law.gone and law.x < 0.0, "and it leaves the way it was pointed"
    print("ok  the van drives on, does its one thing and drives off")


if __name__ == "__main__":
    _demo()
