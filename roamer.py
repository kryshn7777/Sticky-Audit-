"""Sticky off the leash - the box man once you have picked him up.

On a note he is furniture: painted onto the note's own canvas, bounded by the
sheet he is holding. Drag him off it and he becomes a character with a window
of his own, somewhere to fall to, and opinions about being carried around.

What he does:

  * while you carry him he points at the note he came from and thrashes his
    arms and legs, because he does not want to go,
  * let go and he falls under gravity, lands with the weight of however fast
    he was going, and picks himself up,
  * on the floor - the top of the taskbar - he walks a stretch, stops, looks
    about, and eventually dozes off,
  * dropped beside a note he reaches out, takes hold of an edge and hangs
    there, swinging whenever the note is moved,
  * two of them on the floor together stop and hold a conversation entirely in
    gesture,
  * and lifting one of them over the other gets you a look.

Cost
----
The same rule the rest of the app lives by: when nobody has picked him up this
module owns no timer and holds no state, and costs one comparison against an
empty list. `crew` is empty, `_job` is None, and `test_app.py` checks it.

While somebody is out there, one timer serves the whole crew - not one each -
and runs at the slowest rate any of them needs. Standing about is 200ms,
dozing is 500ms, and only actually moving costs a frame every 16ms. A crew
ticker is also what lets two of them find each other: who is standing next to
whom is decided once per tick over the whole list, rather than each of them
hunting for company on his own.
"""

import math
import random
import time
import tkinter as tk

import winkit
from mascot import (FACES, HEAD, LEG_H, _aim, _beat, _clamp, _dist, _face_mix,
                    _mix, _smooth, _spring, _walker)
from store import shade

TAU = math.pi * 2.0

# ------------------------------------------------------------------ his window
#
# One overlay each, the size of the screen he is on, and it does not follow
# him about: see _place. RW/RH are only what the canvas asks for before the
# real size is known.
RW, RH = 260, 220
STAND_H = HEAD // 2 + LEG_H      # his feet, measured down from his face
MARK_FONT = ("Segoe UI", 13, "bold")

TICK_MS = 16                     # while something is actually happening
GRIP_MS = 60                     # hanging on a note
REST_MS = 200                    # stood on the floor
SLEEP_MS = 500                   # asleep on the floor
MAX_ROAMERS = 3

# -------------------------------------------------------------------- physics
FRAME_S = 0.016
MAX_STEP = 0.050        # a stalled event loop must not teleport him
GRAVITY = 2600.0        # px/s^2, tuned by eye. Real gravity at this scale
                        # reads as a dropped stone, and 1200 reads as the moon.
TERMINAL = 2400.0
AIR = 0.6               # horizontal decay per second
SPIN_DRAG = 2.0
THROW_K = 0.55          # a flick must not fire him off the desk
THROW_MAX = 1800.0
THROW_WINDOW = 0.09     # seconds of drag history a throw is measured over
BOUNCE = 0.22
BOUNCE_MIN = 260.0      # slower than this and he simply lands
FLOOR_FRIC = 0.4        # he must not skate
IMPACT_REF = 1400.0     # the speed that buys the whole squash
SQUASH_MIN = 0.62
RECOVER_S = 0.45
FLOOR_RECHECK = 2.0
TRAY_INSET = 180        # room left for the clock, so he is not stood on it
EDGE_INSET = 40

# ---------------------------------------------------------------------- moods
FLAIL_HZ, PULL = 6.5, 6.0
WALK_SPEED = 46.0
STEP_PX = 16.0
LEG_MIN, LEG_MAX = 60.0, 220.0
REST_MIN, REST_MAX = 3.0, 9.0
SLEEP_AFTER = 120.0
WAKE_NEAR = 140.0       # the pointer this close and he stirs
BLINK_EVERY = (3.0, 8.0)
BLINK_S = 0.11

# ---------------------------------------------------------------- taking hold
GRAB_NEAR = 90.0        # how near an edge he has to land to take hold of it
                        # - or anywhere at all on the sheet itself
GRIP_SPAN = 22.0        # his hands go the width of his shoulders apart
GRIP_DROP = 12.0        # how far his face hangs below them
GRIP_SLOP = 2.0
REACH_FRAMES = 22
SWING_K, SWING_D = 42.0, 5.5
SWING_MAX = 7.0

# -------------------------------------------------------------------- company
CHAT_R = 130.0          # near enough to strike up a conversation
CHAT_GAP = 64.0         # ...and how close they end up standing
CHAT_COOLDOWN = 45.0
WATCH_R = 220.0         # near enough to a conversation to turn round for it
TALK2 =(("approach", 34), ("greet", 20), ("say0", 52), ("react", 26),
         ("say1", 46), ("agree", 24), ("part", 30))
TALK3 = (("approach", 34), ("greet", 20), ("say0", 46), ("react", 22),
         ("say1", 42), ("react", 22), ("say2", 44), ("agree", 24),
         ("part", 30))
# Shorter than a conversation on purpose. Cruelty is quick.
MOCK = (("notice", 18), ("point", 40), ("laugh", 54), ("burn", 30),
        ("storm", 26))

# Which role is talking, by beat name. Everything else about a scene - who
# looks at whom, who laughs, who is left standing - falls out of this and the
# cast order, which is why the three scenes differ only by data.
#
# say_a and say_b became say0 and say1 because the speaker is an index now
# rather than a bool. react_b became react because the rule that made it work
# for two - the one who just spoke thinks, everybody else laughs - was already
# the rule for any number of them.
SPEAKS = {"say0": 0, "say1": 1, "say2": 2}

WTF_ABOVE = 46.0        # his head this far over mine before it counts
WTF_NEAR = 200.0        # ...and still near enough that it is about me
WTF_HOLD = 0.22         # held this long, so a flick past does not trip it
WTF_S = 1.6
WTF_TURN = 8.0          # frames to come round and face the front

# ------------------------------------------------------------------- goodbye
CROUCH_S = 0.16         # the wind-up. Without it he teleports upwards
LEAVE_VX = 420.0
LEAVE_VY = 1150.0
LEAVE_MAX_S = 5.0       # he is gone by now whatever the screen says

# ------------------------------------------------------------------- the crew
crew = []
scenes = []
_job = None
_root = None
STEP = None             # tests pin the step so the physics repeats exactly
_stamp = None


def _time():
    """The clock everything in here runs on.

    Real, unless STEP has been set - and then it advances by exactly one step
    per tick and by nothing in between. Half of what he does is timed in
    seconds rather than in frames (how long a reach takes, how long a landing
    absorbs, how long somebody has to be held overhead before it counts), and
    with a pinned step but a real clock those halves disagree: the same test
    passes or fails on how fast the machine got through the loop.
    """
    return time.monotonic() if STEP is None or _stamp is None else _stamp


def _arm(delay):
    global _job
    if _job is not None or _root is None or not crew:
        return
    try:
        _job = _root.after(int(delay), tick)
    except tk.TclError:
        _job = None


def _cancel():
    global _job
    if _job is None:
        return
    try:
        _root.after_cancel(_job)
    except (tk.TclError, ValueError, AttributeError):
        pass
    _job = None


class _Scene:
    """One thing happening between several of them.

    The cast is ordered left to right at the moment it opens and a roamer's
    role is his index in it, so `say0` means whoever was standing furthest
    left. `mid` is frozen at that moment too: the standing positions are
    solved against it every frame, and against a live centroid the target
    would chase the people walking towards it.

    The beat index lives here rather than on each of them. It is advanced
    once per crew tick, after everybody has been drawn - with an index each,
    whoever stepped first would be a beat ahead of whoever stepped second.
    """

    __slots__ = ("kind", "table", "cast", "i", "mid", "last_speaker")

    def __init__(self, kind, table, cast):
        self.kind = kind
        self.table = table
        self.cast = list(cast)
        self.i = 0
        self.mid = sum(g.x for g in self.cast) / float(len(self.cast))
        self.last_speaker = None

    def speaker(self):
        """Whose turn it is, or None on a beat where nobody is talking."""
        beat, _ = _beat(self.table, self.i)
        role = SPEAKS.get(beat)
        if role is None or role >= len(self.cast):
            return None
        return self.cast[role]

    def stand_x(self, guy):
        """Where he ends up standing: a row, CHAT_GAP apart, about `mid`."""
        i = self.cast.index(guy)
        return self.mid + (i - (len(self.cast) - 1) / 2.0) * CHAT_GAP


def _open(group, kind, table, now):
    scene = _Scene(kind, table, group)
    scenes.append(scene)
    for i, guy in enumerate(group):
        guy.scene = scene
        guy.role = i
        guy._stir_at = now
        guy._begin("chat", now)
    return scene


def _turn_on(scene, guy, now):
    """He has walked into the middle of it. They stop and turn on him.

    The scene is not torn down and built again: the same two keep their roles
    and the beat index goes back to nothing, which is what makes them break
    off mid-sentence rather than finish the thought.
    """
    scene.kind = "mock"
    scene.table = MOCK
    scene.i = 0
    scene.last_speaker = None
    scene.cast.append(guy)
    guy.scene = scene
    guy.role = len(scene.cast) - 1
    guy._watching = None
    guy._stir_at = now
    guy._begin("chat", now)


def _close(scene, now):
    """Everybody out, and away in different directions.

    Sent off from here rather than each finding out for himself: the next one
    to step would see his cast already walking and take it for having been
    abandoned mid-sentence.
    """
    if scene in scenes:
        scenes.remove(scene)
    for guy in list(scene.cast):
        guy.scene = None
        guy.role = 0
        guy._social_at = now
        if guy.state != "chat":
            continue
        guy._begin("walk", now)
        away = 140.0 if guy.x > scene.mid else -140.0
        guy._goal = _clamp(guy.x + away, *guy.walk_line)
    # Whoever was stood watching it is left standing where they left him.
    for guy in crew:
        if guy._watching is scene:
            guy._watching = None
            if guy.state == "watch":
                guy._begin("rest", now)


def tick():
    """One step for everybody. Safe to call directly, which is how the tests
    drive it."""
    global _stamp
    _cancel()
    if not crew:
        return
    if STEP is None:
        _stamp = None
        now = _time()
    else:
        _stamp = (time.monotonic() if _stamp is None else _stamp) + STEP
        now = _stamp
    _cast(now)
    delay = SLEEP_MS
    for guy in list(crew):
        try:
            delay = min(delay, guy.step(now))
        except tk.TclError:
            guy.vanish()
    # After the loop, not before it: that keeps the first tick of a scene
    # reading beat zero, which is what the old per-roamer counter did.
    for scene in list(scenes):
        scene.i += 1
    _arm(delay)


def _scene_near(guy):
    """The running scene he has walked in on, if any: the nearest one on his
    own floor that he is not already part of."""
    best, near = None, WATCH_R
    for scene in scenes:
        if not scene.cast or guy in scene.cast:
            continue
        if abs(scene.cast[0].y - guy.y) > 30.0:
            continue
        gap = abs(guy.x - scene.mid)
        if gap < near:
            best, near = scene, gap
    return best


def _cast(now):
    """Who is in a scene with whom, and who is being dangled over whom.

    Decided here, once, for the whole crew, for the same reason pairing was:
    left to each of them separately, A takes up with B while B is already
    taking up with C and the whole thing knots itself.
    """
    # Grouped by floor first and chained along each one separately. Somebody
    # standing on another floor between two of them has to be stepped over
    # rather than stopped at: the pairing this replaced skipped him, and a
    # chain that halts on him quietly stops the two either side from ever
    # talking to each other.
    bands = {}
    for guy in crew:
        if guy.state in ("rest", "walk", "sleep") and guy.floor is not None:
            bands.setdefault(guy.floor, []).append(guy)
    for band in bands.values():
        band.sort(key=lambda g: g.x)
        i = 0
        while i < len(band):
            # A chain of them, each within talking distance of the last.
            group = [band[i]]
            j = i + 1
            while j < len(band) and band[j].x - group[-1].x <= CHAT_R:
                group.append(band[j])
                j += 1
            ready = [g for g in group if g.sociable(now)][:3]
            if len(ready) >= 2:
                _open(ready, "talk",
                      TALK3 if len(ready) > 2 else TALK2, now)
            i = j

    # Anybody left over, against whatever is already running. Watchers are
    # looked at again every tick rather than settled once: one who is shoved
    # into the middle of a conversation he was watching has to be noticed.
    for guy in crew:
        if guy.scene is not None or guy.state not in (
                "rest", "walk", "sleep", "watch"):
            continue
        scene = _scene_near(guy)
        if scene is None:
            if guy.state == "watch":
                guy._watching = None
                guy._begin("rest", now)
            continue
        span = max(abs(g.x - scene.mid) for g in scene.cast)
        if scene.kind == "talk" and abs(guy.x - scene.mid) < max(span, 1.0):
            _turn_on(scene, guy, now)       # he is standing in the gap
        elif abs(guy.x - scene.mid) < WATCH_R:
            guy.watch(scene, now)

    held = [g for g in crew if g.state == "held"]
    if not held:
        for guy in crew:
            guy._lift_since = None
        return
    for guy in crew:
        # Somebody on his way off the screen does not stop to stare. Without
        # "leave" here, one of them asked to go gets caught by the look four
        # frames into his jump and stands there in mid-air instead.
        if guy.state in ("held", "wtf", "leave"):
            continue
        if any(guy.abandoned_by(h) for h in held):
            guy.notice_the_lift(now)
        else:
            guy._lift_since = None


def shutdown():
    """Everyone back on their notes and nothing left running. Called at quit,
    and whenever the mascot is switched off."""
    _cancel()
    for guy in list(crew):
        guy.go_home()
    del crew[:]
    del scenes[:]


send_all_home = shutdown


def for_note(note_id):
    """The one who came off this note, if he is still out there."""
    for guy in crew:
        if guy.home_id == note_id:
            return guy
    return None


def floor_at(x, y):
    """Where a body at (x, y) comes to rest, and how far it may walk:
    (left, right, floor).

    The bottom of the monitor's work area is the top of the taskbar, so this
    is standing on the taskbar without having to ask which edge it is docked
    to. A bar down one side leaves nothing to walk along, and the work area
    has already taken it out, so he stands on the desktop floor instead.
    """
    area = winkit.work_area(x, y)
    if area is None:
        if _root is None:
            return None
        try:
            return (0.0, float(_root.winfo_screenwidth()),
                    float(_root.winfo_screenheight()))
        except tk.TclError:
            return None
    left, _top, right, bottom = area
    return (float(left + EDGE_INSET),
            float(max(left + EDGE_INSET + 40, right - TRAY_INSET)),
            float(bottom))


def _shift(points, dx, dy):
    if points is None:
        return None
    return tuple(None if p is None else (p[0] - dx, p[1] - dy) for p in points)


def _lerp2(a, b, u):
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)


class Roamer(tk.Toplevel):
    """One box man, off his note and out in the world."""

    def __init__(self, app, note_window, x, y):
        global _root
        tk.Toplevel.__init__(self, app.root)
        _root = app.root
        self.app = app
        self.home_id = note_window.note["id"]
        colours = note_window._paper()
        self.ink = colours["ink"]
        self.skin = shade(colours["paper"], 1.06)
        self.limb = shade(colours["ink"], 1.35)

        self.withdraw()
        self.overrideredirect(True)
        key = getattr(note_window, "chroma_key", None)
        if key is None:
            tk.Toplevel.destroy(self)
            raise tk.TclError("no chroma key: he would be a grey box")
        try:
            self.attributes("-transparentcolor", key)
            self.attributes("-topmost", True)
        except tk.TclError:
            tk.Toplevel.destroy(self)
            raise
        self.canvas = tk.Canvas(self, bg=key, highlightthickness=0, bd=0,
                                width=RW, height=RH)
        self.canvas.pack(fill="both", expand=True)

        now = _time()
        self.x, self.y = float(x), float(y)
        self.vx = self.vy = 0.0
        self.spin = self.roll = 0.0
        self.facing = 0.0
        self.look = (0.0, 0.0)
        self.face = FACES["calm"]
        self.phase = 0.0
        self.squash = 1.0
        self.crouch = 0.0
        self.lean = 0.0
        self.hands = None
        self.feet = None

        self.state = "held"
        self.since = now
        self._t = now
        self._trail = []
        self._hold_off = (0.0, STAND_H * 0.5)
        self._mark = None
        self._screen = None
        self._drawn = None
        self._win_at = None
        self._bounced = False
        self._hit = 0.0
        self._hit_at = 0.0
        self.floor = None
        self.walk_line = (0.0, 0.0)
        self._floor_at = 0.0
        self._goal = self.x
        self._until = 0.0
        self._blink_at = now + random.uniform(*BLINK_EVERY)
        self._blink_off = 0.0
        self._blinking = False
        self._stir_at = now

        self.grip_note = None
        self.grip_side = "bottom"
        self.grip_t = 0.5
        self.grip_at = None
        self.sway = self.sway_v = 0.0
        self._reach_from = (self.x, self.y)

        self._popup = None
        self._launched = False
        self._leave_way = 1.0

        self.scene = None
        self.role = 0
        self._watching = None
        self._social_at = 0.0
        self._lift_since = None

        self.canvas.bind("<ButtonPress-3>", self._menu)
        self.canvas.bind("<ButtonPress-1>", self._grab)
        self.canvas.bind("<B1-Motion>", self._haul)
        self.canvas.bind("<ButtonRelease-1>", self._drop)

        crew.append(self)
        self._find_floor(now, force=True)
        self._place(force=True)
        self.deiconify()
        self.paint()
        _cancel()
        _arm(TICK_MS)

    # -------------------------------------------------------------- the mouse

    def _grab(self, event):
        self.pick_up(event.x_root, event.y_root)
        return "break"

    def _haul(self, event):
        self.drag_to(event.x_root, event.y_root)
        return "break"

    def _drop(self, _event=None):
        self.let_go()
        return "break"

    def _menu(self, event):
        """Right-click him, wherever he happens to be.

        Built the first time it is asked for rather than in the constructor:
        most of them are picked up, put down and sent home again without
        anybody ever wanting a menu.
        """
        menu = self._popup
        if menu is None:
            menu = self._popup = tk.Menu(self, tearoff=0)
            # Both of these destroy the window the menu is posted over, so they
            # are queued rather than run inside its own grab.
            menu.add_command(label="Send him home",
                             command=lambda: self.after_idle(self.go_home))
            menu.add_command(label="Ask him to leave",
                             command=lambda: self.after_idle(self.excuse_me))
        menu.entryconfigure(0, state="normal" if self.home() else "disabled")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return "break"

    def excuse_me(self):
        """He has been asked to go, so he goes: a wind-up, a leap off the bar
        towards the nearer edge, a wave on the way past, and that is the last
        anybody sees of him."""
        now = _time()
        self._leave_scene(now)
        self.grip_note = None
        middle = (self.walk_line[0] + self.walk_line[1]) / 2.0
        self._leave_way = 1.0 if self.x >= middle else -1.0
        self._begin("leave", now)
        _cancel()
        _arm(TICK_MS)

    def pick_up(self, x=None, y=None):
        """He is in somebody's hand. Legal from any state at all - including
        halfway through a conversation, which is the funniest time for it."""
        now = _time()
        self._leave_scene(now)
        self._mark = None
        self.grip_note = None
        self.state = "held"
        self.since = self._stir_at = now
        self.squash, self.crouch, self.roll, self.spin = 1.0, 0.0, 0.0, 0.0
        self.sway = self.sway_v = 0.0
        self._bounced = False
        self._trail = []
        if x is not None:
            # Carried from wherever he was taken hold of, rather than snapping
            # his face to the pointer: grab him by a foot and he should hang
            # from that foot, not jump.
            self._hold_off = (self.x - float(x), self.y - float(y))
            self.drag_to(x, y)
        _cancel()
        _arm(TICK_MS)

    def drag_to(self, x, y):
        if self.state != "held":
            self.pick_up()
        now = _time()
        ox, oy = self._hold_off
        self.x, self.y = float(x) + ox, float(y) + oy
        self._trail.append((now, self.x, self.y))
        if len(self._trail) > 6:
            del self._trail[0]

    def let_go(self):
        if self.state != "held":
            return
        now = _time()
        # Measured against the oldest sample still inside the window, not
        # against the last frame: one pixel of jitter at the moment of release,
        # divided by one frame, is several hundred pixels a second of throw.
        recent = ([s for s in self._trail if now - s[0] < THROW_WINDOW]
                  or self._trail[-1:])
        if recent:
            t0, x0, y0 = recent[0]
            dt = max(now - t0, 1e-3)
            self.vx = _clamp((self.x - x0) / dt * THROW_K, -THROW_MAX, THROW_MAX)
            self.vy = _clamp((self.y - y0) / dt * THROW_K, -THROW_MAX, THROW_MAX)
            self.spin = _clamp(-self.vx / 120.0, -6.0, 6.0)
        self._trail = []
        self._find_floor(now, force=True)
        if not self._take_hold(now):
            self._begin("fall", now)
        _cancel()
        _arm(TICK_MS)

    # ------------------------------------------------------------- life cycle

    def home(self):
        window = self.app.windows.get(self.home_id) if self.home_id else None
        try:
            if window is not None and window.winfo_exists():
                return window
        except tk.TclError:
            pass
        return None

    def orphan(self):
        """His note has gone in the bin. He carries on living; he simply has
        nowhere to go back to, and can still take hold of somebody else's."""
        self.home_id = None

    def go_home(self):
        window = self.home()
        if window is not None:
            try:
                window.mascot_home()
            except tk.TclError:
                pass
        self.vanish()

    def vanish(self):
        self._leave_scene(_time())
        if self in crew:
            crew.remove(self)
        try:
            tk.Toplevel.destroy(self)
        except tk.TclError:
            pass
        if not crew:
            _cancel()

    def destroy(self):
        self.vanish()

    # ---------------------------------------------------------------- a floor

    def _find_floor(self, now, force=False):
        if not force and now - self._floor_at < FLOOR_RECHECK:
            return
        self._floor_at = now
        line = floor_at(self.x, self.y)
        if line is None:
            return
        x1, x2, floor = line
        self.walk_line = (x1, x2)
        if (self.floor is not None and abs(floor - self.floor) > 4.0
                and self.state in ("rest", "walk", "sleep", "chat")):
            # The floor moved out from under him - another monitor, or the
            # taskbar changing size. He falls to the new one.
            self.floor = floor
            self._begin("fall", now)
            return
        self.floor = floor

    def _floor_y(self):
        return self.floor if self.floor is not None else self.y

    def _walls(self):
        """Where he stops sideways: the sides of the screen.

        Not the patrol line - that one stops short of the clock, which is the
        right place to turn round on a walk and an invisible wall to bounce
        off in mid air.
        """
        if self._screen is None:
            return self.walk_line
        return (float(self._screen[0]) + 4.0, float(self._screen[2]) - 4.0)

    # ----------------------------------------------------------------- states

    def _begin(self, state, now):
        self.state = state
        self.since = now
        self._mark = None
        if state == "fall":
            self._bounced = False
            self.hands = self.feet = None
        elif state == "rest":
            self._until = now + random.uniform(REST_MIN, REST_MAX)
            self.hands = self.feet = None
            self.phase = 0.0
        elif state == "leave":
            self._launched = False
            self.hands = self.feet = None
            self.vx = self.vy = self.spin = 0.0
        elif state == "walk":
            self._stir_at = now
            x1, x2 = self.walk_line
            span = random.uniform(LEG_MIN, LEG_MAX) * random.choice((-1.0, 1.0))
            self._goal = _clamp(self.x + span, x1, x2)
            if abs(self._goal - self.x) < 20.0:
                self._goal = x2 if self.x < (x1 + x2) / 2.0 else x1
            self.hands = self.feet = None

    def rate(self):
        return {"grip": GRIP_MS, "rest": REST_MS,
                "sleep": SLEEP_MS}.get(self.state, TICK_MS)

    def step(self, now):
        dt = STEP if STEP is not None else min(now - self._t, MAX_STEP)
        self._t = now
        if self.floor is None or self.state in ("fall", "walk"):
            self._find_floor(now, force=self.floor is None)
        getattr(self, "_do_" + self.state)(now, dt)
        self._idle(now)
        self._place()
        self.paint()
        return self.rate()

    # -- being carried ------------------------------------------------------

    def _do_held(self, now, _dt):
        """Put me down.

        None of this is integrated - he is wherever the hand is, and every
        limb is a wave with its own period. The odd multipliers are the whole
        point: limbs moving in step read as a mechanism, and what is wanted is
        a child who has run out of ideas and is now simply thrashing.

        Every target is kept inside what the arms and legs can actually reach,
        so the wave comes out as movement rather than as a straight limb
        pointing at somewhere it cannot get to.
        """
        w = (now - self.since) * FLAIL_HZ * TAU
        fy = self._face_y()
        hw = HEAD / 2.0
        arm_y = fy + hw * 0.20
        # Eyes screwed shut and yelling, both pulsing so his face is never
        # holding one expression while the rest of him is going berserk.
        self.face = FACES["plead"]._replace(
            eye=0.06 + 0.05 * abs(math.sin(w * 0.7)),
            open=0.30 + 0.35 * abs(math.sin(w * 0.55)))
        # ...and the whole of him shuddering along with it.
        self.roll = math.sin(w * 1.9) * 0.14
        self.squash = 1.0 + math.sin(w * 2.3) * 0.04
        self.crouch, self.phase = 0.0, 0.0
        shake = math.sin(w * 2.7) * 2.6
        target = self._home_point()
        if target is None:
            self.facing, self.lean, self.look = 0.0, shake, (0.0, 0.0)
        else:
            # Not the whole way round to a hard profile: at this size that
            # crowds both eyes and his mouth into the same few pixels, and a
            # face pulling itself apart comes out as a smudge instead.
            self.facing = _clamp((target[0] - self.x) / 90.0, -0.75, 0.75)
            self.lean = PULL * self.facing + shake
            self.look = _aim((self.x, fy), target)

        # His head and shoulders lead his feet by the lean, so the arms hang
        # off that and not off the middle of him. Hung off the middle, the
        # leading arm folds back into its own shoulder and reads as missing.
        hx = self.x + self.lean
        # Arms opposite one another: as one goes up over his head the other
        # comes down past his hip. Together they would only be a shrug. Each
        # hand stays outside its own shoulder, for the same reason.
        self.hands = tuple(
            (hx + side * (hw * 0.75 + 7.0 + math.cos(w * 1.31 + k) * 4.0),
             arm_y - 3.0 + math.sin(w + k) * 11.0)
            for k, side in ((0.0, -1.0), (math.pi, 1.0)))
        # Legs kicking out and back as well as up, or it reads as bouncing.
        # They stay on their own sides too: crossed legs read as a tangle, and
        # wide enough apart that his two shoes are not one dark lump.
        self.feet = tuple(
            (self.x + self.lean * 0.34
             + side * (11.0 + math.sin(w * 0.85 + k) * 5.0),
             self.y - 3.0 - max(0.0, math.cos(w * 0.85 + k)) * 8.0)
            for k, side in ((0.0, -1.0), (math.pi * 0.9, 1.0)))

    def _home_point(self):
        window = self.home()
        if window is None:
            return None
        try:
            ox, oy, pw, ph = window.paper_rect()
            return (window.winfo_rootx() + ox + pw / 2.0,
                    window.winfo_rooty() + oy + ph / 2.0)
        except tk.TclError:
            return None

    # -- falling ------------------------------------------------------------

    def _do_fall(self, now, dt):
        self.vy = min(self.vy + GRAVITY * dt, TERMINAL)
        self.vx *= math.exp(-AIR * dt)
        self.spin *= math.exp(-SPIN_DRAG * dt)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.roll += self.spin * dt
        self.hands = self.feet = None
        self.facing = _clamp(self.vx / 200.0, -1.0, 1.0)
        self.lean, self.squash = 0.0, 1.0
        self.crouch = 0.35
        # He braces just before he arrives, which is most of what makes a drop
        # look like a body rather than a prop.
        near = self.floor is not None and (self.floor - self.y) < 90.0
        self.face = FACES["strain"] if near else FACES["panic"]
        x1, x2 = self._walls()
        if self.x < x1:
            self.x, self.vx = x1, abs(self.vx) * 0.4
        elif self.x > x2:
            self.x, self.vx = x2, -abs(self.vx) * 0.4
        if self.floor is None or self.y < self.floor:
            return
        self.y = self.floor
        speed = self.vy
        if speed > BOUNCE_MIN and not self._bounced:
            # One bounce, and only one. Two reads as a ball, not a person.
            self._bounced = True
            self.vy = -speed * BOUNCE
            self.y -= 1.0
            return
        self.vy = 0.0
        self.vx *= FLOOR_FRIC
        self.roll = 0.0
        self._hit, self._hit_at = speed, now
        self._begin("land", now)

    # -- landing ------------------------------------------------------------

    def _do_land(self, now, dt):
        k = min(1.0, self._hit / IMPACT_REF)
        u = min(1.0, (now - self._hit_at) / RECOVER_S)
        # _spring starts at +1 and decays, so he is flattest at the moment of
        # contact, overshoots tall, then settles. The whole squash and stretch
        # is two lines of an easing that already existed for the colour flip.
        self.squash = 1.0 + (SQUASH_MIN - 1.0) * k * _spring(u, 2.2, 6.5)
        self.crouch = 0.9 * k * (1.0 - _smooth(u))
        self.x += self.vx * dt
        self.vx *= math.exp(-4.0 * dt)
        self.x = _clamp(self.x, *self._walls())
        self.feet = ((self.x - 9.0, self.y), (self.x + 9.0, self.y))
        self.hands = None
        self.face = _face_mix(FACES["dazed"], FACES["calm"], _smooth(u))
        self.roll = self.lean = 0.0
        self.phase = 0.0
        if u < 1.0:
            return
        self.squash, self.crouch = 1.0, 0.0
        self.feet = None
        if not self._take_hold(now):
            self._begin("rest", now)

    # -- on the floor -------------------------------------------------------

    def _do_rest(self, now, _dt):
        self.squash, self.crouch, self.roll, self.lean = 1.0, 0.0, 0.0, 0.0
        self.phase = 0.0
        self.face = FACES["calm"]
        self.facing = _mix(self.facing, 0.0, 0.25)
        self.y = self._floor_y()
        self._watch_pointer()
        if now >= self._until:
            if now - self._stir_at > SLEEP_AFTER:
                self._begin("sleep", now)
            else:
                self._begin("walk", now)

    def _do_sleep(self, now, _dt):
        self.face = FACES["calm"]
        self.facing, self.look, self.phase = 0.0, (0.0, 0.0), 0.0
        self.y = self._floor_y()
        # The pointer coming over is what wakes him. Without it dozing is a
        # state he never leaves except by being picked up, and a mascot who has
        # stopped for good does not read as asleep, it reads as broken.
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return
        if math.hypot(px - self.x, py - self._face_y()) < WAKE_NEAR:
            self._stir_at = now
            self._begin("rest", now)

    def _do_walk(self, now, dt):
        way = 1.0 if self._goal > self.x else -1.0
        self.x += way * WALK_SPEED * dt
        self.phase += WALK_SPEED * dt / STEP_PX * math.pi
        self.facing = way * 0.62
        self.lean = way * 2.4
        self.face = FACES["calm"]
        self.y = self._floor_y()
        self._watch_pointer()
        # Bounded by the screen while he walks, not by the patrol line: thrown
        # past the clock he has to be able to walk back out of there, and
        # clamping him to the line would snap him across it instead.
        x1, x2 = self._walls()
        stopped = self.x <= x1 or self.x >= x2
        self.x = _clamp(self.x, x1, x2)
        if stopped or abs(self.x - self._goal) < WALK_SPEED * dt + 0.5:
            self._begin("rest", now)

    def _watch_pointer(self):
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return
        self.look = _aim((self.x, self._face_y()), (px, py))

    # -- taking hold of a note ----------------------------------------------

    def _sheets(self):
        """Every note he could take hold of: (window, x0, y0, pw, ph).

        Screen coordinates, and the paper only - never the transparent margin
        his own poses need around it.
        """
        out = []
        for window in list(self.app.windows.values()):
            try:
                if not window.winfo_viewable():
                    continue
                ox, oy, pw, ph = window.paper_rect()
                out.append((window, window.winfo_rootx() + ox,
                            window.winfo_rooty() + oy, pw, ph))
            except tk.TclError:
                continue
        return out

    @staticmethod
    def _bounds(x0, y0, pw, ph, side):
        """The stretch of one edge he may take hold along: (lo, hi, fixed).

        Which point of it he has is a fraction of this, kept from the moment
        he took hold, so it travels with the note. Working it out from where
        he is standing instead pins him to himself, and a note pulled out
        sideways from under him leaves his hands behind.
        """
        pad = GRIP_SPAN / 2.0 + 4.0
        if side in ("top", "bottom"):
            return (x0 + pad, max(x0 + pad, x0 + pw - pad),
                    y0 if side == "top" else y0 + ph)
        return (y0 + pad, max(y0 + pad, y0 + ph - pad),
                x0 if side == "left" else x0 + pw)

    def _edge_bounds(self, window, side):
        ox, oy, pw, ph = window.paper_rect()
        return self._bounds(window.winfo_rootx() + ox,
                            window.winfo_rooty() + oy, pw, ph, side)

    def _take_hold(self, now):
        """Take hold of whatever he was dropped on, where he was dropped.

        Every edge of every note is a candidate and the point along it is
        wherever he came down, clamped only by the ends of that edge. Nothing
        snaps to a spot of its own: dropped by the middle of an edge he takes
        the middle of it, dropped by a corner he takes the corner, and dropped
        anywhere on the sheet at all he takes the nearest edge to that rather
        than falling straight through the note.

        The top edge is one of them, but he stands on it rather than hanging
        from it. Hanging from the top puts his whole body down the face of the
        sheet and across the writing, which is the one thing he has never been
        allowed to do; standing on it puts him above the paper, exactly where
        one of his poses on the note already sits.
        """
        best, score = None, None
        hx, hy = self.x, self.y - STAND_H
        for window, x0, y0, pw, ph in self._sheets():
            over = x0 <= hx <= x0 + pw and y0 <= hy <= y0 + ph
            for side in ("top", "bottom", "left", "right"):
                lo, hi, fixed = self._bounds(x0, y0, pw, ph, side)
                if side in ("top", "bottom"):
                    at = _clamp(hx, lo, hi)
                    gap = math.hypot(hx - at, hy - fixed)
                else:
                    at = _clamp(hy, lo, hi)
                    gap = math.hypot(hx - fixed, hy - at)
                if gap > GRAB_NEAR and not over:
                    continue
                if score is None or gap < score:
                    score = gap
                    best = (window, side,
                            (at - lo) / (hi - lo) if hi > lo else 0.5)
        if best is None:
            return False
        self.grip_note, self.grip_side, self.grip_t = best
        self.grip_at = None
        self.sway = self.sway_v = 0.0
        self._reach_from = (self.x, self.y)
        self._begin("reach", now)
        return True

    def _grip_points(self):
        """Where his two hands are, worked out fresh every frame from the
        note's own live rectangle, so that they travel with it."""
        window = self.grip_note
        try:
            if window is None or not window.winfo_viewable():
                return None
            lo, hi, fixed = self._edge_bounds(window, self.grip_side)
        except tk.TclError:
            return None
        half = GRIP_SPAN / 2.0
        at = lo + (hi - lo) * self.grip_t
        if self.grip_side in ("top", "bottom"):
            return ((at - half, fixed), (at + half, fixed))
        return ((fixed, at - half), (fixed, at + half))

    def _hang_from(self, grips):
        """His face, given where his two contact points are. Everything else
        follows from it, which is what keeps him hanging rather than posed."""
        ax = (grips[0][0] + grips[1][0]) / 2.0
        ay = (grips[0][1] + grips[1][1]) / 2.0
        if self.grip_side == "top":
            # Standing on the edge, not hanging off it: his feet are the
            # contact, so his face is a body's height above them. The sway
            # only shifts him a little - it is balance, not a pendulum.
            return (ax + self.sway * 0.35, ay - STAND_H)
        if self.grip_side == "left":
            ax -= HEAD * 0.55
        elif self.grip_side == "right":
            ax += HEAD * 0.55
        return (ax + self.sway, ay + GRIP_DROP)

    def _standing(self):
        return self.grip_side == "top"

    def _shoulder(self, side):
        fy = self._face_y()
        return (self.x + side * (HEAD / 2.0) * 0.75, fy + (HEAD / 2.0) * 0.20)

    def _do_reach(self, now, _dt):
        grips = self._grip_points()
        if grips is None:
            self.grip_note = None
            self._begin("fall", now)
            return
        u = min(1.0, (now - self.since) / (REACH_FRAMES * FRAME_S))
        e = _smooth(u)
        fx, fy = self._hang_from(grips)
        sx, sy = self._reach_from
        # He leans over and steps in rather than arriving. Snapping into place
        # is exactly what this was not supposed to look like.
        self.x = _mix(sx, fx, e)
        self.y = _mix(sy, fy + STAND_H, e)
        if self._standing():
            self.hands = None
            self.feet = (_lerp2((self.x - 9.0, self.y), grips[0], e),
                         _lerp2((self.x + 9.0, self.y), grips[1], e))
        else:
            self.hands = (_lerp2(self._shoulder(-1.0), grips[0], e),
                          _lerp2(self._shoulder(1.0), grips[1], e))
            self.feet = None
        self.squash, self.crouch, self.roll = 1.0, 0.25 * (1.0 - e), 0.0
        self.facing = _clamp((fx - sx) / 60.0, -1.0, 1.0) * (1.0 - e)
        self.lean = 3.0 * (1.0 - e)
        self.phase = 0.0
        # How far short of his hold he still is, straight into his face.
        reaching = self.feet if self._standing() else self.hands
        short = max(0.0, _dist(reaching[1], grips[1]) - GRIP_SLOP)
        self.face = _face_mix(FACES["calm"], FACES["strain"],
                              min(1.0, short / 24.0))
        if u < 1.0:
            return
        if self._standing():
            self.feet = grips
        else:
            self.hands = grips
        self.grip_at = grips
        self._begin("grip", now)
        try:
            self.lift()
        except tk.TclError:
            pass

    def _do_grip(self, now, dt):
        grips = self._grip_points()
        if grips is None:
            # The note was closed, or went away with a minimised host. He is
            # left holding nothing, so he falls.
            self.grip_note = None
            self._begin("fall", now)
            return
        moved = self.grip_at is not None and (
            abs(grips[0][0] - self.grip_at[0][0]) > 0.5
            or abs(grips[0][1] - self.grip_at[0][1]) > 0.5)
        if moved:
            # The note went somewhere and he did not, yet. That difference is
            # the shove that sets him swinging.
            self.sway_v -= (grips[0][0] - self.grip_at[0][0]) * 9.0
            try:
                self.lift()     # a click on the note raises it over his hands
            except tk.TclError:
                pass
        self.grip_at = grips
        # A damped pendulum, plus a slow breath so he is never quite still.
        self.sway_v += (-SWING_K * self.sway - SWING_D * self.sway_v) * dt
        self.sway = _clamp(self.sway + self.sway_v * dt, -SWING_MAX, SWING_MAX)
        fx, fy = self._hang_from(grips)
        self.x = fx + math.sin(now * 1.15) * 0.9
        self.y = fy + STAND_H
        self.squash, self.crouch = 1.0, 0.0
        self.face = FACES["happy"]
        if self._standing():
            # Feet planted on the edge, and the shove goes into his balance
            # rather than into a swing: he is stood on the note, not under it.
            self.feet, self.hands = grips, None
            self.roll = self.sway * 0.004
            self.lean = -self.sway * 0.45
            self.facing = _clamp(self.sway / 22.0, -0.4, 0.4)
            self.phase = 0.0
        else:
            self.hands, self.feet = grips, None
            self.roll = self.sway * 0.012
            self.lean = 0.0
            self.facing = _clamp(self.sway / 14.0, -0.5, 0.5)
            self.phase = now * 1.4 if abs(self.sway) > 1.2 else 0.0
        self._watch_pointer()

    def swinging(self):
        return abs(self.sway) > 0.4 or abs(self.sway_v) > 2.0

    # -- going for good ------------------------------------------------------

    def _do_leave(self, now, dt):
        if not self._launched:
            u = min(1.0, (now - self.since) / CROUCH_S)
            self.crouch, self.squash = 0.9 * u, 1.0 - 0.18 * u
            self.face = FACES["strain"]
            self.facing = -self._leave_way * 0.5
            self.hands = self.feet = None
            if u < 1.0:
                return
            self._launched = True
            self.vx = self._leave_way * LEAVE_VX
            self.vy = -LEAVE_VY
            self.spin = -self.vx / 260.0
            return
        self.vy = min(self.vy + GRAVITY * dt, TERMINAL)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.roll += self.spin * dt
        self.crouch, self.squash, self.lean = 0.0, 1.0, 0.0
        self.face = FACES["happy"]
        self.facing = _clamp(self.vx / 300.0, -1.0, 1.0)
        self.look = (0.0, 0.0)
        self.hands = self._one_hand(
            self._leave_way, 20.0 + math.sin((now - self.since) * 14.0) * 7.0,
            -20.0)
        self.feet = None
        self.phase = 0.0
        if now - self.since > LEAVE_MAX_S or self._off_screen():
            self.vanish()

    def _off_screen(self):
        # ponytail: the primary monitor only, so a second screen off to the
        # left keeps him alive a moment longer than it should. LEAVE_MAX_S is
        # the backstop, and this is a goodbye, not a physics engine.
        try:
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
        except tk.TclError:
            return True
        return (self.y - STAND_H > h + 80.0 or self.y < -300.0
                or self.x < -140.0 or self.x > w + 140.0)

    # -- company -------------------------------------------------------------

    @property
    def partner(self):
        """The other one, when there are exactly two of us.

        A conversation between two is still the common case, and reads far
        better than indexing a cast of two.
        """
        scene = self.scene
        if scene is None or len(scene.cast) != 2:
            return None
        return scene.cast[1 - self.role]

    @property
    def mocked(self):
        """Am I the one being laughed at? In a mock the victim is the one who
        walked in, so he is the last into the cast."""
        scene = self.scene
        return (scene is not None and scene.kind == "mock"
                and bool(scene.cast) and scene.cast[-1] is self)

    def sociable(self, now):
        # Both a cooldown and having actually parted. A cooldown on its own
        # loops forever if they never move apart; parting on its own starts
        # again the moment they drift back together.
        return (self.scene is None
                and now - self._social_at > CHAT_COOLDOWN)

    def _leave_scene(self, now):
        """Drop out of whatever I was in, and decide what is left of it."""
        scene, self.scene = self.scene, None
        self.role = 0
        if scene is None:
            return
        self._social_at = now
        if self in scene.cast:
            scene.cast.remove(self)
        _close(scene, now)

    def _do_chat(self, now, _dt):
        scene = self.scene
        if scene is None or scene not in scenes or self not in scene.cast:
            self._social_at = now
            self.scene = None
            self._begin("rest", now)
            return
        beat, u = _beat(scene.table, scene.i)
        if beat == "done":
            _close(scene, now)
            return
        if beat in SPEAKS:
            scene.last_speaker = scene.speaker()
        if scene.kind == "mock":
            self._mock_beat(scene, beat, u, now)
        else:
            self._talk_beat(scene, beat, u, now)

    def watch(self, scene, now):
        if self.state == "watch" and self._watching is scene:
            return
        self._watching = scene
        self._begin("watch", now)

    def _do_watch(self, now, _dt):
        """Stood at the edge of somebody else's conversation.

        His eyes come off the pointer, which nothing but the look out at the
        camera does, and for the same reason: there is something on the screen
        more interesting than the user. Nobody in the scene ever acknowledges
        him. That is the whole of it.
        """
        scene = self._watching
        if scene is None or scene not in scenes or not scene.cast:
            self._watching = None
            self._begin("rest", now)
            return
        who = scene.speaker() or scene.last_speaker or scene.cast[0]
        self.facing = _clamp((who.x - self.x) / 70.0, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (who.x, who._face_y()))
        self.squash, self.roll, self.crouch, self.lean = 1.0, 0.0, 0.0, 0.0
        self.hands = self.feet = None
        self.phase = 0.0
        self.y = self._floor_y()
        self.face = _face_mix(FACES["calm"], FACES["happy"], 0.30)

    def _who_to_watch(self, scene, u):
        """Whose head my eyes are on this frame.

        Whoever is talking; between speeches, whoever spoke last; and before
        anyone has, simply the nearest of them. A speaker cannot watch
        himself, so he works the room instead - one listener for the first
        half of his beat and the other for the second.
        """
        who = scene.speaker() or scene.last_speaker
        others = [g for g in scene.cast if g is not self]
        if not others:
            return None
        if who is None or who is self:
            if who is None:
                return min(others, key=lambda g: abs(g.x - self.x))
            return others[0] if (u < 0.5 or len(others) < 2) else others[1]
        return who

    def _talk_beat(self, scene, beat, u, now):
        who = self._who_to_watch(scene, u)
        if who is None:
            return
        # Attention, every frame and whatever the beat is doing: they square
        # up to whoever is talking and their eyes follow. Two lines, and they
        # are what makes this read as a conversation instead of two toys
        # twitching.
        self.facing = _clamp((who.x - self.x) / 70.0, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (who.x, who._face_y()))
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.lean, self.phase = 0.0, 0.0
        self.y = self._floor_y()
        side = 1.0 if who.x > self.x else -1.0
        speaking = scene.speaker() is self
        listening = scene.speaker() is not None and not speaking

        if beat == "approach":
            want = scene.stand_x(self)
            self.x = _mix(self.x, want, 0.10)
            self.phase = now * 6.0 if abs(self.x - want) > 2.0 else 0.0
            self.face = FACES["calm"]
        elif beat == "greet":
            if self.role == 0:
                self.hands = self._one_hand(side, 22.0, -16.0)
                if scene.i == 35:
                    self._say("!")
            self.face = _face_mix(FACES["calm"], FACES["happy"], _smooth(u))
        elif speaking:
            # The gesture is a moving target rather than keyframes: the arm is
            # solved to wherever the hand ought to be and the elbow sorts
            # itself out. That is what the two-bone solver is for.
            self.hands = self._one_hand(
                side, 24.0 + 10.0 * math.sin(u * math.pi * 3.0),
                -6.0 + 8.0 * math.cos(u * math.pi * 2.0))
            self.face = FACES["talk"]._replace(
                open=0.25 + 0.55 * abs(math.sin(now * 5.0 * TAU)))
        elif listening:
            self.y = self._floor_y() + math.sin(u * TAU * 1.6) * 2.4
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.4)
        elif beat == "react":
            if scene.last_speaker is self:
                self.face = _face_mix(FACES["calm"], FACES["think"], 0.7)
            else:
                self.face = FACES["laugh"]
                fy = self._face_y()
                self.hands = ((self.x - 30.0, fy + 6.0), (self.x + 30.0, fy + 6.0))
                self.y = self._floor_y() - abs(math.sin(u * math.pi * 3.0)) * 5.0
        elif beat == "agree":
            self.face = FACES["happy"]
            self.y = self._floor_y() + math.sin(u * TAU * 2.0) * 2.6
        elif beat == "part":
            self.facing = _mix(self.facing, 0.0, _smooth(u) * 0.6)
            self.face = FACES["happy"]
            if u < 0.5:
                self.hands = self._one_hand(side, 20.0,
                                            -18.0 + math.sin(u * 18.0) * 4.0)

    def _mock_beat(self, scene, beat, u, now):
        """Two of them pointing, and the one they are pointing at.

        Carried the same way the conversation is - by where they are facing
        and what their faces are doing - and with no more dialogue than that
        one has. A written "ha ha" would be the first line anybody in this app
        had spoken, and it would cheapen a scene that is stronger silent.
        """
        victim = scene.cast[-1]
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.lean, self.phase = 0.0, 0.0
        self.y = self._floor_y()

        if self is victim:
            others = [g for g in scene.cast if g is not self]
            # Looking from one of them to the other while it dawns on him,
            # and then his eyes go down and stay down.
            who = others[min(len(others) - 1, int(u * 2.0))] if others else None
            if beat in ("burn", "storm") or who is None:
                self.look = (0.0, 0.6)
                self.facing = _mix(self.facing, 0.0, 0.12)
            else:
                self.facing = _clamp((who.x - self.x) / 70.0, -1.0, 1.0)
                self.look = _aim((self.x, self._face_y()),
                                 (who.x, who._face_y()))
            if beat == "notice":
                self.face = FACES["calm"]
            elif beat == "point":
                self.face = _face_mix(FACES["calm"], FACES["think"], _smooth(u))
            elif beat == "laugh":
                self.face = _face_mix(FACES["think"], FACES["cross"], _smooth(u))
            else:
                # Standing there taking it: not a flinch, a held tension.
                self.face = FACES["cross"]
                self.roll = math.sin(now * 11.0 * TAU) * 0.015
                self.squash = 1.0 + math.sin(now * 9.0 * TAU) * 0.012
            return

        side = 1.0 if victim.x > self.x else -1.0
        self.facing = _clamp((victim.x - self.x) / 70.0, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (victim.x, victim._face_y()))
        if beat == "notice":
            self.face = _face_mix(FACES["calm"], FACES["smug"], _smooth(u))
        elif beat == "point":
            self.face = FACES["smug"]
            self.hands = self._one_hand(side, 30.0, -4.0)
        elif beat == "laugh":
            self.face = FACES["laugh"]
            fy = self._face_y()
            self.hands = ((self.x - 30.0, fy + 6.0), (self.x + 30.0, fy + 6.0))
            self.y = self._floor_y() - abs(math.sin(u * math.pi * 3.0)) * 5.0
        else:
            # Winding down, still pleased with themselves.
            self.face = _face_mix(FACES["laugh"], FACES["happy"], _smooth(u))

    def _one_hand(self, side, out, up):
        point = (self.x + side * out, self._face_y() + up)
        return (point, None) if side < 0 else (None, point)

    def _say(self, text):
        # Kept as a string and drawn over his head every frame, not pinned to
        # a fixed spot on the canvas: the window does not move with him any
        # more, so anything drawn once stays where it was put while he walks
        # away from it.
        self._mark = text

    # -- the look ------------------------------------------------------------

    def abandoned_by(self, other):
        """Is that one of us being dangled over my head?

        Being held is the load-bearing part of this. Somebody bouncing past
        overhead is an accident; somebody hanging up there in the user's hand
        is the user doing it, and that is what he is reacting to.
        """
        return (other is not self and other.state == "held"
                and other.y < self.y - WTF_ABOVE
                and abs(other.x - self.x) < WTF_NEAR)

    def notice_the_lift(self, now):
        if self._lift_since is None:
            self._lift_since = now
            return
        if now - self._lift_since < WTF_HOLD:
            return
        self._leave_scene(now)
        self._begin("wtf", now)
        self._lift_since = None

    def _do_wtf(self, now, _dt):
        frames = (now - self.since) / FRAME_S
        # Turning to camera is the joke, and so is what he stops doing: his
        # eyes follow the pointer every other moment of his life, and here
        # they go dead centre and look straight out instead.
        self.facing = _mix(self.facing, 0.0, min(1.0, frames / WTF_TURN))
        self.look = (0.0, 0.0)
        self.face = FACES["wtf"]
        fy = self._face_y()
        self.hands = ((self.x - 30.0, fy - 2.0), (self.x + 30.0, fy - 2.0))
        self.feet = None
        self.squash, self.crouch, self.roll, self.lean = 1.0, 0.0, 0.0, 0.0
        self.phase = 0.0
        self.y = self._floor_y() - max(0.0, _spring(min(1.0, frames / 6.0),
                                                    1.0, 3.0)) * 4.0
        if frames < 2.0:
            self._say("?!")
        if now - self.since >= WTF_S:
            # Back to whatever he was doing, and his social cooldown is left
            # alone on purpose: he will happily start talking again the moment
            # his friend is put back down, which is funnier than sulking.
            self._begin("rest", now)

    # ----------------------------------------------------------------- idling

    def _idle(self, now):
        if self.state in ("held", "fall", "wtf"):
            self._blinking = False
            return
        if self._blinking:
            if now >= self._blink_off:
                self._blinking = False
        elif now >= self._blink_at:
            self._blink_at = now + random.uniform(*BLINK_EVERY)
            self._blink_off = now + BLINK_S
            self._blinking = True

    # ---------------------------------------------------------------- drawing

    def _face_y(self):
        return self.y - STAND_H

    def _place(self, force=False):
        """Give him a window the size of the screen he is on, and then leave
        it alone.

        A window that follows him has to be moved, and moving a layered
        top-level window does not take effect until the event loop next runs -
        while the canvas inside it is redrawn against the new origin
        immediately. So a move and a repaint in the same frame can composite
        the figure at its new offset inside a window still standing at the old
        place, and he flicks across the screen and back for a frame. At
        walking pace that is one move every second or so. Thrown, it is a move
        every other frame, and the whole throw judders.

        So this does not follow him. The window is the whole screen from the
        moment he exists, and only ever changes when he crosses onto a
        different one. A canvas that size costs nothing extra per frame - Tk
        repaints the part that changed, not the area it could have changed in
        - and measured, it comes out slightly cheaper than the move it
        replaces.
        """
        rect = self._screen
        if rect is not None and not force and                 rect[0] <= self.x <= rect[2] and rect[1] <= self.y <= rect[3]:
            return                      # still on the screen he was given
        found = winkit.screen_area(self.x, self.y)
        if found is None:
            try:
                found = (0, 0, self.winfo_screenwidth(),
                         self.winfo_screenheight())
            except tk.TclError:
                return
        if found == self._screen and not force:
            return
        self._screen = found
        self._win_at = (found[0], found[1])
        try:
            self.geometry("%dx%d+%d+%d" % (found[2] - found[0],
                                           found[3] - found[1],
                                           found[0], found[1]))
        except tk.TclError:
            pass

    def _pose(self):
        """Everything paint() puts on the canvas, as one comparable value."""
        return (self._win_at, self._mark, self._blinking, self.face, self.look,
                self.hands, self.feet,
                round(self.x, 1), round(self.y, 1),
                None if not self.phase else round(self.phase, 3),
                round(self.facing, 3), round(self.lean, 2),
                round(self.crouch, 3), round(self.squash, 3),
                round(self.roll, 3))

    def paint(self):
        if self._win_at is None:
            return
        # Standing still with the pointer still, nothing about him changes -
        # and the note mascot has always made that cost nothing, so neither
        # does this one. Comparing fifteen numbers beats tearing down and
        # rebuilding thirty-odd canvas items five times a second.
        pose = self._pose()
        if pose == self._drawn:
            return
        self._drawn = pose
        cv = self.canvas
        cv.delete("walker")
        dx, dy = self._win_at
        face = self.face
        if self._blinking:
            face = face._replace(eye=0.12)
        _walker(cv, self.x - dx, self.y - dy - STAND_H, self.phase or None,
                self.skin, self.limb, self.ink,
                facing=self.facing, lean=self.lean, crouch=self.crouch,
                hands=_shift(self.hands, dx, dy),
                feet=_shift(self.feet, dx, dy),
                face=face, look=self.look, squash=self.squash, roll=self.roll,
                tag="walker")
        if self._mark:
            cv.create_text(self.x - dx, self.y - dy - STAND_H - HEAD,
                           text=self._mark, fill=self.limb, font=MARK_FONT,
                           tags="walker")
