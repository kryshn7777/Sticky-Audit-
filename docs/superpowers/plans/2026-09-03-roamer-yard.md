# Excusing yourself, a kickabout, and a hut — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the taskbar crew four things they cannot do today — leave a conversation early, kick a ball about, walk off the screen for wood and build a hut to go into, and come out of it screaming when you right-click it down.

**Architecture:** A new module `yard.py` owns the props (a ball and a hut) on one shared, chroma-keyed, full-screen overlay, and knows nothing about roamers. `roamer.py` gains one new module function for what a scene does between beats (`_advance`), one for taking somebody out of a cast without ending the scene (`_bow_out`), two new scene kinds (`footy`, `build`) that reuse the existing `_Scene` record exactly as `mock` does, and five new states (`bye`, `fetch`, `enter`, `inside`, `panic`). `roamer.tick` is still the only timer in either module and drives the yard as part of the frame it already runs.

**Tech Stack:** Python 2/3-compatible stdlib + Tkinter. No new dependencies. Windows-only chroma-key transparency via `-transparentcolor`, already used by `note.py`, `mascot.py` and `roamer.py`.

**Spec:** `docs/superpowers/specs/2026-09-03-roamer-yard-design.md`

## Global Constraints

- **No new dependencies.** stdlib and Tkinter only.
- **The cost rule.** With nobody picked up off a note, `roamer.crew` is empty, `roamer._job` is `None`, and now also: the yard owns no window, no ball and no hut. `test_app.py` asserts all of it.
- **One timer.** `roamer.tick` is the only `after()` in either module. `yard.py` never schedules anything.
- **The import is one way.** `roamer.py` imports `yard`; `yard.py` must never import `roamer`. What the yard has to tell the crew, it says through the `on_knock` callback the crew sets.
- **Code style.** Match the house style in `roamer.py`: 79-column lines, docstrings that explain *why* a thing is the way it is and what the alternative looked like, `# ponytail:` comments on deliberate ceilings.
- **`MAX_ROAMERS` is 3** (`roamer.py:69`) and is enforced at peel-off in `note.py`. Nothing in this plan changes it.
- **Test style.** `test_app.py` is one linear script of `assert` + `print("ok  ...")` against real windows and a real event loop, with `roamer.STEP` pinned to `1.0 / 60.0`. No pytest, no fixtures.
- **Commit messages.** Lower-case conventional-commit subject, then a body explaining the *why*. Match the existing log (`git log --oneline -9`). Every commit ends with:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
  ```
- **Running the suite.** `test_app.py` puts real windows on screen for a minute or two and steals real keystrokes. Always run it in the background with topmost off:
  ```bash
  STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py
  ```

## File structure

| File | Responsibility |
|---|---|
| `yard.py` **(new, ~230 lines)** | The props: a ball with its own physics, a hut with a rectangle you can right-click, and the one overlay window they share. Knows nothing about roamers. |
| `roamer.py` (modify) | The crew. Gains the two new scene kinds, the five new states, `_advance`, `_bow_out`, `_pick_scene`, `_hut_down`, and the plank he carries. |
| `test_app.py` (modify) | Four new checks in the existing roaming block, plus one line added to the "nothing left running" check. |
| `README.md` (modify) | The behaviour documentation the repo keeps for every roamer feature. |

---

### Task 1: The yard — props, physics and a window

**Files:**
- Create: `yard.py`
- Test: `yard.py` itself (an `assert`-based `__main__` self-check of the ball physics, which is the only non-trivial logic in the module and the only part that runs without a display)

**Interfaces:**
- Consumes: `winkit.screen_area(x, y)` — returns `(left, top, right, bottom)` for the monitor containing that point, or `None`.
- Produces, for Tasks 3–5:
  - `yard.on_knock` — module attribute, `None` or a callable `(x: float, floor: float) -> None`
  - `yard.attach(root: tk.Misc, key: str) -> None`
  - `yard.kick_off(x: float, floor: float) -> _Ball | None`
  - `yard.ball() -> _Ball | None` — has `.x .y .vx .vy .r .spin` (floats)
  - `yard.drop_ball() -> None`
  - `yard.raise_hut(x: float, floor: float) -> _Hut | None`
  - `yard.hut() -> _Hut | None` — has `.x .floor .w .h` (floats) and `.holds(x, y) -> bool`
  - `yard.knock_down() -> _Hut | None` — removes the hut **and** fires `on_knock`
  - `yard.step(dt: float) -> None`
  - `yard.paint() -> None`
  - `yard.clear() -> None` — everything gone, window destroyed, `on_knock` **not** fired
  - Constants used elsewhere: `yard.WOOD` (str), `yard.DOOR_H`, `yard.BALL_R` (floats)

- [ ] **Step 1: Write the failing self-check**

Create `yard.py` containing *only* this, so the check is written before the code it checks:

```python
if __name__ == "__main__":
    _demo()
```

...and at the bottom of the file, above it:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python yard.py`
Expected: FAIL with `NameError: name '_Ball' is not defined`

- [ ] **Step 3: Write the module**

Put this above `_demo()` in `yard.py`:

```python
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

# ----------------------------------------------------------------- the ball
#
# Its own numbers rather than the roamer's. A ball is not a person: it comes
# off the floor much further than he does, it keeps rolling after it has
# stopped bouncing, and nothing about it squashes.
BALL_R = 11.0
BALL_G = 2400.0         # px/s^2
BALL_BOUNCE = 0.62
BALL_ROLL = 0.75        # horizontal decay per second, and only once it is down
BALL_STOP = 12.0        # slower than this and it has stopped
BALL_DROP = 220.0       # how far above the floor it is thrown in from

# ------------------------------------------------------------------ the hut
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
        if self.vy > BALL_STOP:
            self.vy = -self.vy * BALL_BOUNCE
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
    """Where to build, and what colour is not there. Idempotent, and called
    by every roamer as he is created: the window itself waits until there is
    something to put in it."""
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
    """A ball, thrown in above (x, floor). None if there is nowhere to put
    it, and then there is no game."""
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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python yard.py`
Expected: `ok  the ball falls, bounces, rolls to a stop and stays on screen`

- [ ] **Step 5: Commit**

```bash
git add yard.py
git commit -F - <<'EOF'
feat: somewhere for a ball and a hut to be

The first things on the desktop that are not a note, a mascot or one of
them. Both are props - a position and a shape, no states - so they share
one keyed, full-screen window, for the two reasons a roamer's window is
the same shape: a window that follows a moving prop judders, and the
keyed colour is click-through, so the only click this one ever takes is
the right-click that knocks the hut down.

Nothing in here knows what a roamer is, which keeps the import one way
and leaves the ball physics checkable without a display. python yard.py.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

### Task 2: Excusing yourself from a conversation

**Files:**
- Modify: `roamer.py` — constants block (~line 113-150), `_Scene.__slots__` (~219), `_Scene.__init__` (~223), `tick` (~322), `Roamer.__init__` (~570-600), `_begin` (~796), `_talk_beat` (~1459)
- Modify: `test_app.py` — insert after the `"ok  asked to leave, he jumps off the bar and is gone"` block (~line 1197)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces, for Tasks 3–5:
  - `roamer._advance(scene, now) -> None` — one place for what a scene does between beats; called from `tick` for every live scene just before `scene.i += 1`. Tasks 3 and 4 add arms to it.
  - `roamer._beat_start(table, name) -> int | None`
  - `roamer.BOW_AT` (int), `roamer.BOW_ODDS` (float), `roamer.FAREWELL` (beat table)
  - `_Scene.gone_way` (float) — which way the one who bowed out went
  - New roamer state `"bye"`, and `Roamer._do_bye(now, dt)`

- [ ] **Step 1: Write the failing test**

In `test_app.py`, insert this immediately **after** the line
`print("ok  asked to leave, he jumps off the bar and is gone")`
and **before** the `# --- and none of it is left running ---` comment:

```python
        # --- a ball, a hut, and excusing yourself ----------------------------
        # A fresh three off the three notes: a is still in somebody's hand
        # from the check above, and these want everybody on the floor.
        roamer.send_all_home()
        pump(app.root)
        crowd = [roamer.Roamer(app, paper, 0.0, floor)
                 for paper in (window, second, third)]

        def settle(guys, at=None, gap=roamer.CHAT_GAP):
            """Everybody on the floor, in a row, willing, and in nothing."""
            for stale in list(roamer.scenes):
                roamer._close(stale, roamer._time())
            yard.drop_ball()
            middle = (left + right) / 2.0 if at is None else at
            for k, one in enumerate(guys):
                one.x = middle + (k - 1) * gap
                one.state, one.floor, one.y = "rest", floor, floor
                one.vx = one.vy = 0.0
                one.carry = False
                one._until = time.monotonic() + 999.0
                one._social_at = one._social_until = one._cross_until = 0.0

        # one of them excuses himself, and the other two carry on without him
        # (nothing but a talk exists yet, so there is no scene kind to pin)
        was_bow, roamer.BOW_ODDS = roamer.BOW_ODDS, 1.0
        try:
            settle(crowd)
            step(3)
            scene = crowd[0].scene
            assert scene is not None and scene.kind == "talk", scene
            assert len(scene.cast) == 3, len(scene.cast)
            cast_was = list(scene.cast)
            scene.i = roamer.BOW_AT - 1
            step(2)
            assert len(scene.cast) == 2, \
                ("one of them has to have excused himself", len(scene.cast))
            assert scene in roamer.scenes, \
                "and the scene has to carry on without him"
            assert scene.table is roamer.FAREWELL, "on a shorter table"
            assert sorted(one.role for one in scene.cast) == [0, 1], \
                "with the roles re-indexed, or nobody speaks again"
            gone = [one for one in cast_was if one not in scene.cast][0]
            assert gone.state == "bye", gone.state
            assert gone.scene is None, "he is out of it, not still in it"
            assert all(one.state == "chat" for one in scene.cast), \
                [one.state for one in scene.cast]
        finally:
            roamer.BOW_ODDS = was_bow
        step(1)
        assert gone._mark == "bye!", ("he says it", gone._mark)
        step(600, lambda: gone.state == "walk")
        assert gone.state == "walk", gone.state
        assert (gone._goal - scene.mid) * (gone.x - scene.mid) > 0, \
            "and he walks away from them, not back through the middle"
        step(600, lambda: not roamer.scenes)
        assert not roamer.scenes, "the two left have to part in the end"
        print("ok  one of them says bye and the other two finish without him")
```

Add `import yard  # noqa: E402` next to `import roamer  # noqa: E402` near the top of `test_app.py` (~line 53).

- [ ] **Step 2: Run it to verify it fails**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: FAIL with `AttributeError: module 'roamer' has no attribute 'BOW_ODDS'`

- [ ] **Step 3: Add the constants and the table**

In `roamer.py`, immediately after the `MOCK = (...)` tuple (~line 148), add:

```python
# The two left behind pick it up from `wave` and take it to a close. Shorter
# than what it replaces on purpose: they were three sentences into a
# conversation, and this is the end of it, not a fresh one.
FAREWELL = (("wave", 24), ("say0", 40), ("agree", 22), ("part", 30))
```

...and after the `SPEAKS = {...}` line (~line 149), add:

```python
def _beat_start(table, name):
    """The frame a named beat begins on, or None. Written this way rather
    than as a number so that retiming a table cannot quietly move it."""
    i = 0
    for beat, n in table:
        if beat == name:
            return i
        i += n
    return None


# ------------------------------------------------------------ excusing yourself
BOW_ODDS = 0.35         # ...how often a three-way is one of them leaving early
BOW_AT = _beat_start(TALK3, "say1")
BYE_S = 0.9             # the wave, before he turns and goes
```

- [ ] **Step 4: Carry which way he went on the scene**

In `_Scene.__slots__` (~line 219) add `"gone_way"`:

```python
    __slots__ = ("kind", "table", "cast", "i", "mid", "last_speaker",
                 "victim", "gone_way")
```

...and at the end of `_Scene.__init__`, after `self.victim = None`:

```python
        # Which way the one who excused himself went, so the two left wave
        # after him rather than at each other.
        self.gone_way = 0.0
```

- [ ] **Step 5: Write `_bow_out` and `_advance`**

In `roamer.py`, immediately after `_turn_on` and before `_close` (~line 279), add:

```python
def _bow_out(scene, guy, now):
    """One of them has somewhere else to be.

    The scene does not end. He comes out of the cast, the two left keep their
    places and take the roles 0 and 1, and the table goes back to the start of
    a shorter one - so they see him off and then have a last word with each
    other, rather than standing through beats written for three with nobody
    left to speak them.

    `scene.mid` is deliberately not recomputed. The two left are already stood
    where they were; the only beat that solves a position against mid is
    `approach`, which FAREWELL does not have, so moving it would change
    nothing except where somebody watching from outside thinks they are.
    """
    if guy not in scene.cast or len(scene.cast) < 3:
        return
    scene.cast.remove(guy)
    scene.table = FAREWELL
    scene.i = 0
    scene.last_speaker = None
    for i, other in enumerate(scene.cast):
        other.role = i
    guy.scene = None
    guy.role = 0
    guy._social_at = now
    guy._leave_way = 1.0 if guy.x >= scene.mid else -1.0
    scene.gone_way = guy._leave_way
    guy._begin("bye", now)


def _advance(scene, now):
    """Whatever a scene does between beats.

    One place for it, called once per scene per tick from `tick`, for the same
    reason the beat index lives on the scene rather than on each of them:
    decided inside a roamer's own step, whoever stepped first would settle it
    a frame before whoever stepped second.
    """
    if scene.kind == "talk":
        if (len(scene.cast) == 3 and scene.i == BOW_AT
                and random.random() < BOW_ODDS):
            # Never the one about to speak. Cutting somebody off mid-sentence
            # is what the mock does, and this is meant to be the opposite of
            # it: he waits for a gap, the way people do.
            speaker = scene.speaker()
            going = [g for g in scene.cast if g is not speaker]
            if going:
                _bow_out(scene, random.choice(going), now)
```

- [ ] **Step 6: Call it from `tick`**

In `tick()` (~line 344), replace:

```python
    for scene in list(scenes):
        scene.i += 1
```

with:

```python
    for scene in list(scenes):
        _advance(scene, now)
        if scene in scenes:
            scene.i += 1
```

- [ ] **Step 7: Add the `bye` state**

In `_begin` (~line 796), after the `elif state == "leave":` block, add:

```python
        elif state == "bye":
            self._until = now + BYE_S
            self.hands = self.feet = None
```

Add `_do_bye` to `Roamer`, immediately after `_do_stomp` (~line 1038):

```python
    def _do_bye(self, now, _dt):
        """A hand up and a word, and then he is off.

        He waves back at the two he is leaving rather than at where he is
        going: `_leave_way` is the way out, so the wave is the other one. The
        walk that follows is started the way `_close` starts one - state
        first, goal second - because `_begin("walk")` picks its own
        destination through `_company`, and `_company` would cheerfully aim
        him straight back at the conversation he has just left.
        """
        self.squash, self.roll, self.crouch, self.lean = 1.0, 0.0, 0.0, 0.0
        self.feet = None
        self.phase = 0.0
        self.y = self._floor_y()
        self.face = FACES["happy"]
        back = -self._leave_way
        u = _clamp((now - self.since) / BYE_S, 0.0, 1.0)
        self.facing = _clamp(back * 0.7, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (self.x + back * 120.0, self._face_y()))
        self.hands = self._one_hand(back, 22.0,
                                    -18.0 + math.sin(u * 16.0) * 4.0)
        self._say("bye!")
        if now - self.since < BYE_S:
            return
        self._begin("walk", now)
        self._goal = _clamp(self.x + self._leave_way * 200.0, *self.walk_line)
```

- [ ] **Step 8: Teach `_talk_beat` the `wave` beat**

In `_talk_beat` (~line 1481), immediately after the `if beat == "approach":` block and before `elif beat == "greet":`, insert:

```python
        elif beat == "wave":
            # Somebody has just excused himself. They see him off - both of
            # them turning the same way, after him, which is the only beat in
            # any of these tables where they are not looking at each other.
            self.face = FACES["happy"]
            self.facing = _clamp(scene.gone_way * 0.6, -1.0, 1.0)
            self.hands = self._one_hand(
                scene.gone_way, 22.0, -18.0 + math.sin(u * 14.0) * 4.0)
```

- [ ] **Step 9: Add the fields the later tasks need to `Roamer.__init__`**

After `self._lift_since = None` (~line 597), add:

```python
        self.carry = False      # he is holding a plank
        self._fetch = "out"     # which leg of the errand he is on
        self._fetch_way = -1.0
        self._site_x = self.x
        self._turn_at = 0.0
        self._panic_until = 0.0
```

...and immediately **after** the `try: / except tk.TclError: ... raise` block that
sets `-transparentcolor` in `__init__` (~line 545) — after the `raise`, before
`self.canvas = tk.Canvas(...)` — so the yard always has a live root and a key to
build with, and only once the key is known to have worked:

```python
        self.key = key
        # The yard is built on demand, but it is told where and in what colour
        # here: app.root outlives every roamer, where the module's own _root is
        # taken away under the tests to stop tick() arming timers behind them.
        yard.attach(app.root, key)
```

Add `import yard` to the import block at the top (~line 47), after `import winkit`:

```python
import winkit
import yard
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: PASS, including `ok  one of them says bye and the other two finish without him`

- [ ] **Step 11: Commit**

```bash
git add roamer.py test_app.py
git commit -F - <<'EOF'
feat: one of them has somewhere else to be

A three-way where somebody leaves early. He waits for a gap rather than
cutting anyone off - that is what the mock does - waves, says bye and
goes, and the two left pick it up on a shorter table and take it to a
close. Their roles re-index, or the say1 the table asks for lands on
nobody and they stand in silence.

The scene keeps its midpoint. The two left have not moved, and the only
beat that solves a position against mid is approach, which the farewell
table does not have.

_advance is new and is where anything a scene does between beats goes:
decided inside a roamer's own step, whoever stepped first would settle
it a frame ahead of whoever stepped second.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

### Task 3: A kickabout

**Files:**
- Modify: `roamer.py` — constants (~after `BYE_S`), `_cast` (~line 429), `tick` (~line 322), `_do_chat` (~line 1377), new `_footy_beat`, `shutdown` (~460), `vanish` (~746)
- Modify: `test_app.py` — after the Task 2 block

**Interfaces:**
- Consumes: `yard.kick_off`, `yard.ball`, `yard.drop_ball`, `yard.step`, `yard.paint`, `yard.clear` (Task 1); `roamer._advance` (Task 2).
- Produces, for Task 4:
  - `roamer._pick_scene(ready) -> (kind: str, table: tuple)` — Task 4 adds the `build` arm
  - `roamer.FOOTY_ODDS`, `roamer.BUILD_ODDS` (floats; `BUILD_ODDS` is defined here and used here, and Task 4 gives it a scene)
  - `_do_chat(now, dt)` now takes and forwards a real `dt`

- [ ] **Step 1: Write the failing test**

In `test_app.py`, append immediately after
`print("ok  one of them says bye and the other two finish without him")`:

```python
        # they kick a ball about, and it goes when they do
        was_build, was_footy = roamer.BUILD_ODDS, roamer.FOOTY_ODDS
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = 0.0, 1.0
        settle(crowd)
        step(3)
        scene = crowd[0].scene
        assert scene is not None and scene.kind == "footy", scene
        assert yard.ball() is not None, "a kickabout needs a ball"
        assert yard.ball().y < floor - roamer.STAND_H, \
            "and it is thrown in above their heads"
        booted = []

        def kicked():
            live = yard.ball()
            if live is None:
                return True
            # Only a boot can send it up that fast. It comes in falling, and
            # nothing else in the physics ever adds to its speed.
            if live.vy <= -roamer.KICK_VY * 0.9:
                booted.append(live.vy)
            return bool(booted)

        step(60 * 20, kicked)
        assert booted, "somebody has to actually kick it"
        step(60 * 40, lambda: not roamer.scenes)
        assert not roamer.scenes, "and the game has to end"
        assert yard.ball() is None, "and the ball goes with them"
        print("ok  they kick a ball about, and take it with them")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: FAIL on `assert scene is not None and scene.kind == "footy"` — the scene kind is still `"talk"`.

- [ ] **Step 3: Add the constants and the table**

In `roamer.py`, after `BYE_S = 0.9` (added in Task 2), add:

```python
# --------------------------------------------------------------------- a ball
# One long beat rather than a sequence: there is nothing to choreograph. Who
# is chasing is decided from where the ball is, every frame, so possession
# changes hands the moment somebody else is nearer - which is the entire game,
# and enough of one. Two of them converging on a ball and one getting there
# first reads as football without anybody being told the rules.
FOOTY = (("kickabout", 780),)    # about thirteen seconds
FOOTY_ODDS = 0.25
KICK_R = 26.0                    # near enough to get a boot to it
KICK_VX, KICK_VY = 300.0, 620.0
CHASE_SPEED = WALK_SPEED * 2.4   # nobody walks at a loose ball
BUILD_ODDS = 0.20                # ...and see the hut, below
```

- [ ] **Step 4: Let `_cast` choose what kind of scene this is**

In `roamer.py`, immediately before `def _cast(now):` (~line 392), add:

```python
def _pick_scene(ready):
    """Talk, football, or - once there are three of them - a hut.

    One roll cut into three rather than a roll each. A chain of independent
    odds makes whatever is last on the list far rarer than its number reads,
    and these numbers are meant to say how often you see each of them.
    """
    roll = random.random()
    if len(ready) > 2 and yard.hut() is None and roll < BUILD_ODDS:
        return "build", BUILD
    if roll < BUILD_ODDS + FOOTY_ODDS:
        return "footy", FOOTY
    return "talk", TALK3 if len(ready) > 2 else TALK2


def _kick_off(scene, now):
    """A ball, thrown in between them. No ball, no game."""
    first = scene.cast[0]
    if yard.kick_off(scene.mid, first.floor) is None:
        _close(scene, now)
```

In `_cast`, replace:

```python
            if len(ready) >= 2 and not _incoming(band, group, now):
                _open(ready, "talk",
                      TALK3 if len(ready) > 2 else TALK2, now)
```

with:

```python
            if len(ready) >= 2 and not _incoming(band, group, now):
                kind, table = _pick_scene(ready)
                scene = _open(ready, kind, table, now)
                if kind == "footy":
                    _kick_off(scene, now)
```

Note `_pick_scene` references `BUILD` — define the table now, next to `FOOTY`, so this task's code imports cleanly; Task 4 gives it beats to run:

```python
# --------------------------------------------------------------------- a hut
BUILD = (("agree", 30), ("send", 6))
```

- [ ] **Step 5: Drive and clear the ball from the crew's own frame**

In `tick()`, replace:

```python
    if STEP is None:
        _stamp = None
        now = _time()
    else:
        _stamp = (time.monotonic() if _stamp is None else _stamp) + STEP
        now = _stamp
    _cast(now)
```

with:

```python
    if STEP is None:
        _stamp = None
        now = _time()
    else:
        _stamp = (time.monotonic() if _stamp is None else _stamp) + STEP
        now = _stamp
    # The yard has no clock of its own on purpose: one timer serves the crew,
    # and a ball is part of the same frame they are.
    dt = STEP if STEP is not None else min(now - (_last or now), MAX_STEP)
    _last = now
    _cast(now)
```

...and at the end of `tick`, replace `_arm(delay)` with:

```python
    yard.step(dt)
    yard.paint()
    _arm(delay)
```

Add `_last` to the globals declared at the top of `tick`:

```python
    global _stamp, _last
```

...and to the module globals, beside `_stamp = None` (~line 170):

```python
_last = None            # the last frame the yard was stepped on
```

In `_close` (~line 280), immediately after `if scene in scenes: scenes.remove(scene)`, add:

```python
    if scene.kind == "footy":
        yard.drop_ball()
```

In `shutdown()` (~line 460), after `del scenes[:]`, add:

```python
    global _last
    _last = None
    yard.clear()
```

In `vanish()` (~line 746), replace:

```python
        if not crew:
            _cancel()
```

with:

```python
        if not crew:
            _cancel()
            yard.clear()
```

- [ ] **Step 6: Give `_do_chat` a real `dt` and a footy arm**

Replace the signature and the dispatch at the end of `_do_chat` (~line 1377):

```python
    def _do_chat(self, now, dt):
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
        elif scene.kind == "footy":
            self._footy_beat(scene, u, now, dt)
        else:
            self._talk_beat(scene, beat, u, now)
```

- [ ] **Step 7: Write `_footy_beat`**

Add to `Roamer`, immediately after `_mock_beat` (~line 1577):

```python
    def _footy_beat(self, scene, u, now, dt):
        """A ball, and whoever is nearest it.

        No sides, no goals and no score. The chaser is worked out from
        distance every frame rather than being appointed, so possession
        changes hands the instant somebody else is closer - which is what
        makes two of them converging on a loose ball read as a game.

        He kicks it at one of the others rather than at nowhere, and only on
        the way down: without the `vy >= 0` he re-boots the same ball on the
        four frames after the first one, and it goes through the ceiling.
        """
        ball = yard.ball()
        if ball is None:
            _close(scene, now)
            return
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.lean, self.phase = 0.0, 0.0
        self.y = self._floor_y()
        self.face = _face_mix(FACES["calm"], FACES["happy"], 0.5)
        self.facing = _clamp((ball.x - self.x) / 70.0, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()), (ball.x, ball.y))
        here = [g for g in scene.cast if g.state == "chat"]
        if not here or min(here, key=lambda g: abs(g.x - ball.x)) is not self:
            # Up on his toes, waiting for it to come his way.
            self.y = self._floor_y() - abs(math.sin(now * 3.0 * TAU)) * 2.0
            return
        gap = ball.x - self.x
        if abs(gap) > KICK_R:
            way = 1.0 if gap > 0 else -1.0
            x1, x2 = self._walls()
            self.x = _clamp(self.x + way * CHASE_SPEED * dt, x1, x2)
            self.phase += CHASE_SPEED * dt / STEP_PX * math.pi
            self.lean = way * 3.4
            return
        if ball.vy < 0.0 or ball.y < self.floor - STAND_H:
            return                      # over his head, or already on its way
        others = [g for g in scene.cast if g is not self]
        at = random.choice(others) if others else self
        ball.vx = math.copysign(KICK_VX, (at.x - self.x) or 1.0)
        ball.vy = -KICK_VY
        self.face = FACES["strain"]
        self.y = self._floor_y() - 4.0
        self.feet = ((self.x - 6.0, self.y),
                     (self.x + math.copysign(18.0, ball.vx), self.y - 10.0))
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: PASS, including `ok  they kick a ball about, and take it with them`

- [ ] **Step 9: Commit**

```bash
git add roamer.py test_app.py
git commit -F - <<'EOF'
feat: a ball, and whoever is nearest it

Sometimes the two or three who have found each other kick a ball about
instead of talking. It is a scene kind rather than a state, for the same
reason the mock is one: the scene record already carries the cast, the
teardown, the cooldowns, and what happens when somebody is lifted out of
it halfway through.

Nobody is appointed to chase. The nearest man to the ball is worked out
every frame, so possession turns over the moment somebody else is closer,
and two of them converging on a loose ball is the whole game. He kicks
only on the way down, or he re-boots the same ball four frames running
and it leaves the screen.

_pick_scene is one roll cut three ways rather than a roll each: chained
odds make whatever is last on the list far rarer than its number reads.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

### Task 4: Off the screen for wood, and a hut to go into

**Files:**
- Modify: `roamer.py` — constants, `_advance` (Task 2), `_do_chat` dispatch, new `_build_beat`, `_do_fetch`, `_carry_hands`, `_do_enter`, `_do_inside`, `_begin`, `rate`, `step`, `_pose`, `paint`
- Modify: `test_app.py` — after the Task 3 block

**Interfaces:**
- Consumes: `yard.raise_hut`, `yard.hut`, `yard.WOOD`, `yard.DOOR_H` (Task 1); `roamer._advance` (Task 2); `roamer.BUILD`, `roamer.BUILD_ODDS`, `_do_chat(now, dt)` (Task 3).
- Produces, for Task 5: roamer state `"inside"`, and roamers in it are `withdraw()`n with `self._until` holding when they next come out.

- [ ] **Step 1: Write the failing test**

In `test_app.py`, append immediately after
`print("ok  they kick a ball about, and take it with them")`:

```python
        # three of them fetch wood off the sides of the screen and build a hut
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = 1.0, 0.0
        # Near the left edge, so the errand is a few seconds rather than the
        # twenty a walk from the middle of a wide screen would take.
        settle(crowd, at=left + 140.0)
        step(3)
        scene = crowd[0].scene
        assert scene is not None and scene.kind == "build", scene
        step(60 * 5, lambda: all(one.state == "fetch" for one in crowd))
        assert all(one.state == "fetch" for one in crowd), \
            [one.state for one in crowd]
        went = step(60 * 30, lambda: all(one.x < left - 40.0 for one in crowd))
        assert went is not None, \
            "they have to actually leave the screen for it"
        back = step(60 * 30, lambda: yard.hut() is not None)
        assert back is not None and yard.hut() is not None, \
            "three planks home and there has to be a hut"
        assert all(one.carry is False for one in crowd), "the wood is used up"
        step(60 * 30, lambda: all(one.state == "inside" for one in crowd))
        assert all(one.state == "inside" for one in crowd), \
            [one.state for one in crowd]
        pump(app.root)
        assert not any(one.winfo_viewable() for one in crowd), \
            "indoors is indoors"
        assert not roamer.scenes, "and the build is over"
        print("ok  they fetch wood off the screen and build a hut to go into")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: FAIL — the build scene opens (Task 3 added `BUILD` to `_pick_scene`) but nobody ever reaches `"fetch"`, so `assert all(one.state == "fetch" ...)` fails with three `"chat"`s.

- [ ] **Step 3: Add the constants**

In `roamer.py`, replace the `BUILD = (("agree", 30), ("send", 6))` line added in Task 3 with the full block:

```python
# --------------------------------------------------------------------- a hut
# The agreement is a scene; the errand is not. He keeps his scene through the
# whole of it, so a hand closing on any one of the three still tears the
# build down the way it tears down a conversation.
BUILD = (("agree", 30), ("send", 6))
FETCH_SPEED = WALK_SPEED * 2.2   # eager, and it is a long way to the edge
FETCH_OFF = 130.0                # how far past the edge before he is out of it
FETCH_GONE_S = 1.2               # ...and how long he is out there for
FETCH_MAX_S = 60.0               # the errand has gone wrong: come to your senses
PLANK_W, PLANK_H = 44.0, 7.0
INSIDE_S = (14.0, 26.0)
```

- [ ] **Step 4: Add the build arm to `_advance`**

In `_advance` (Task 2), after the `if scene.kind == "talk": ... return` block, add:

```python
    if scene.kind != "build":
        return
    if any(g not in crew or g.state not in ("chat", "fetch")
           for g in scene.cast):
        _close(scene, now)              # somebody was lifted out of it
        return
    if not scene.cast or any(g.state != "fetch" or g._fetch != "home"
                             for g in scene.cast):
        return                          # still nodding, or still out there
    if yard.raise_hut(scene.mid, scene.cast[0].floor) is None:
        _close(scene, now)
        return
    for guy in list(scene.cast):
        guy.carry = False
        guy._begin("enter", now)
    # _close leaves anybody who is not mid-conversation alone, so they keep
    # walking to the door rather than being sent off in three directions.
    _close(scene, now)
```

- [ ] **Step 5: Add the build arm to `_do_chat`**

In `_do_chat`, extend the dispatch:

```python
        if scene.kind == "mock":
            self._mock_beat(scene, beat, u, now)
        elif scene.kind == "footy":
            self._footy_beat(scene, u, now, dt)
        elif scene.kind == "build":
            self._build_beat(scene, beat, u, now)
        else:
            self._talk_beat(scene, beat, u, now)
```

- [ ] **Step 6: Write `_build_beat`**

Add to `Roamer`, immediately after `_footy_beat`:

```python
    def _build_beat(self, scene, beat, u, now):
        """They agree on it, and then they scatter for the wood."""
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.lean, self.phase = 0.0, 0.0
        self.y = self._floor_y()
        if beat == "agree":
            who = self._who_to_watch(scene, u)
            if who is not None:
                self.facing = _clamp((who.x - self.x) / 70.0, -1.0, 1.0)
                self.look = _aim((self.x, self._face_y()),
                                 (who.x, who._face_y()))
            self.face = FACES["happy"]
            self.y = self._floor_y() + math.sin(u * TAU * 2.0) * 2.6
            if self.role == 0 and scene.i == 6:
                self._say("!")
            return
        # send: off to the nearer edge, and the scene holds him until the
        # wood is home again.
        x1, x2 = self._walls()
        self._fetch = "out"
        self._fetch_way = -1.0 if (self.x - x1) < (x2 - self.x) else 1.0
        self._site_x = scene.stand_x(self)
        self.carry = False
        self._begin("fetch", now)
```

- [ ] **Step 7: Write `_do_fetch` and `_carry_hands`**

Add to `Roamer`, immediately after `_do_bye` (Task 2):

```python
    def _do_fetch(self, now, dt):
        """Off the side of the screen for wood, and back with a plank.

        Three legs, on `_fetch`, and the middle one is the joke: he is not
        hidden and nothing has been switched off. He has simply walked far
        enough past the edge that his own window - which is exactly the size
        of the screen and does not follow him - has nowhere left to draw him.
        """
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.feet = None
        self.y = self._floor_y()
        self.face = FACES["calm"]
        self.look = (0.0, 0.0)
        x1, x2 = self._walls()
        if now - self.since > FETCH_MAX_S:
            # Wedged in a corner, or the floor moved out from under the whole
            # errand. Standing out there for good is the one outcome worse
            # than never having gone.
            self.carry = False
            self.x = _clamp(self.x, x1, x2)
            self._begin("rest", now)
            return

        if self._fetch == "out":
            way = self._fetch_way
            self.x += way * FETCH_SPEED * dt
            self.phase += FETCH_SPEED * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.62, way * 3.0
            self.hands = None
            if self.x < x1 - FETCH_OFF or self.x > x2 + FETCH_OFF:
                self._fetch = "back"
                self._until = now + FETCH_GONE_S
            return

        if self._fetch == "back":
            if now < self._until:
                return                  # out of sight, finding a plank
            self.carry = True
            way = 1.0 if self._site_x > self.x else -1.0
            self.x += way * FETCH_SPEED * dt
            self.phase += FETCH_SPEED * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.62, way * 3.0
            self._carry_hands()
            if abs(self.x - self._site_x) < FETCH_SPEED * dt + 0.5:
                self.x = self._site_x
                self._fetch = "home"
            return

        # home: stood at the site with the wood, waiting for the other two.
        self.phase, self.lean = 0.0, 0.0
        self.facing = _mix(self.facing, 0.0, 0.2)
        self._carry_hands()
        self._watch_pointer()
        if self.scene is None or self.scene not in scenes:
            # He has come back with the wood to find nobody there, which is
            # what a hand closing on one of the other two looks like from out
            # at the edge of the screen.
            self.carry = False
            self._begin("rest", now)

    def _carry_hands(self):
        """Both hands out in front, a plank's width apart. `paint` draws the
        plank across them, after the figure, so it is in front of him."""
        fy = self._face_y() + HEAD * 0.35
        self.hands = ((self.x - PLANK_W / 2.0, fy),
                      (self.x + PLANK_W / 2.0, fy))
```

- [ ] **Step 8: Write `_do_enter` and `_do_inside`**

Add to `Roamer`, immediately after `_carry_hands`:

```python
    def _do_enter(self, now, dt):
        """To the door, and in.

        The hut is asked for every frame rather than remembered from the
        moment it went up: it can be knocked down while he is still walking
        to it, and then there is nothing to walk into.
        """
        hut = yard.hut()
        if hut is None:
            self._begin("rest", now)
            return
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.y = self._floor_y()
        self.face = _face_mix(FACES["calm"], FACES["happy"], 0.5)
        way = 1.0 if hut.x > self.x else -1.0
        self.x += way * WALK_SPEED * dt
        self.phase += WALK_SPEED * dt / STEP_PX * math.pi
        self.facing, self.lean = way * 0.62, way * 2.4
        self.look = _aim((self.x, self._face_y()),
                         (hut.x, hut.floor - yard.DOOR_H))
        if abs(self.x - hut.x) < WALK_SPEED * dt + 0.5:
            self._begin("inside", now)

    def _do_inside(self, now, _dt):
        """Indoors: a withdrawn window and a time to come out at.

        `step` returns before `_place` and `paint` for this one state, so a
        man in a hut costs one comparison a tick and no drawing at all. The
        check on the hut still being there is belt and braces - `_hut_down`
        empties it the moment it goes - and catches it disappearing any other
        way.
        """
        if now < self._until and yard.hut() is not None:
            return
        try:
            self.deiconify()
        except tk.TclError:
            pass
        # Not all three out of the same doorway at the same pixel.
        self.x = _clamp(self.x + random.uniform(-34.0, 34.0), *self.walk_line)
        self._stir_at = now
        self._social_at = now
        self._begin("rest", now)
```

- [ ] **Step 9: Wire the states into `_begin`, `rate` and `step`**

In `_begin`, after the `elif state == "bye":` block added in Task 2:

```python
        elif state == "enter":
            self.hands = self.feet = None
            self._mark = None
        elif state == "inside":
            self._until = now + random.uniform(*INSIDE_S)
            self.hands = self.feet = None
            try:
                self.withdraw()
            except tk.TclError:
                pass
```

In `rate` (~line 825), replace:

```python
        return {"grip": GRIP_MS, "rest": REST_MS,
                "sleep": SLEEP_MS}.get(self.state, TICK_MS)
```

with:

```python
        return {"grip": GRIP_MS, "rest": REST_MS, "sleep": SLEEP_MS,
                "inside": SLEEP_MS}.get(self.state, TICK_MS)
```

In `step` (~line 829), after `self._t = now` and before the `_find_floor` line, insert:

```python
        if self.state == "inside":
            # Nothing to place and nothing to draw: he is a withdrawn window
            # with a time on it.
            self._do_inside(now, dt)
            return self.rate()
```

- [ ] **Step 10: Draw the plank**

In `_pose` (~line 1702), add `self.carry` to the tuple, after `self.feet`:

```python
        return (self._win_at, self._mark, self._blinking, self.face, self.look,
                self.hands, self.feet, self.carry,
                round(self.x, 1), round(self.y, 1),
                None if not self.phase else round(self.phase, 3),
                round(self.facing, 3), round(self.lean, 2),
                round(self.crouch, 3), round(self.squash, 3),
                round(self.roll, 3))
```

In `paint` (~line 1712), between the `_walker(...)` call and the `if self._mark:` block, insert:

```python
        if self.carry and self.hands is not None:
            # After the figure, so it is in front of him rather than behind
            # his chest, and in the yard's own wood so a plank and a wall are
            # obviously the same stuff.
            (lx, ly), (rx, ry) = self.hands
            mid = (ly + ry) / 2.0 - dy
            cv.create_rectangle(lx - dx - 4.0, mid - PLANK_H / 2.0,
                                rx - dx + 4.0, mid + PLANK_H / 2.0,
                                fill=yard.WOOD, outline=self.ink,
                                tags="walker")
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: PASS, including `ok  they fetch wood off the screen and build a hut to go into`

- [ ] **Step 12: Commit**

```bash
git add roamer.py test_app.py
git commit -F - <<'EOF'
feat: they go off the screen for wood and come back with a hut

Three of them on a floor, no hut already up, and they agree on it: each
trots to the nearer edge and keeps going until his own window - which is
the size of the screen and does not follow him - has nowhere left to draw
him. A moment later he is back with a plank held out in front, and when
the last of the three is home the hut goes up between them and they file
in.

The errand is a state, not a beat table: a round trip is however long the
screen is, and no count of frames knows that. But the scene stays on him
the whole way, so a hand closing on any one of the three still tears the
build down, and a man who comes home with the wood to find nobody there
puts it down and goes back to what he was doing.

Indoors he is a withdrawn window with a time on it. step() returns before
place and paint for that one state, so he costs a comparison a tick.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

### Task 5: Knocking it down

**Files:**
- Modify: `roamer.py` — constants, new `_hut_down` and the `yard.on_knock` registration, `_do_panic`, `_begin`, `_idle`
- Modify: `test_app.py` — after the Task 4 block, plus one line in the "nothing left running" check

**Interfaces:**
- Consumes: `yard.knock_down`, `yard.on_knock` (Task 1); roamer state `"inside"` (Task 4).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

In `test_app.py`, append immediately after
`print("ok  they fetch wood off the screen and build a hut to go into")`:

```python
        # ...and right-clicking it brings them out screaming
        where = yard.hut().x
        yard.knock_down()
        assert yard.hut() is None, "right-clicking it takes it down"
        pump(app.root)
        assert all(one.winfo_viewable() for one in crowd), \
            "and everybody in it comes straight back out"
        assert all(one.state == "panic" for one in crowd), \
            [one.state for one in crowd]
        assert all(abs(one.x - where) < roamer.WATCH_R for one in crowd), \
            "out where it stood, not where they went in from"
        spots = [one.x for one in crowd]
        step(30)
        assert any(abs(one.x - was) > 1.0 for one, was in zip(crowd, spots)), \
            "they have to actually run"
        step(60 * 10, lambda: all(one.state == "rest" for one in crowd))
        assert all(one.state == "rest" for one in crowd), \
            ("and settle again", [one.state for one in crowd])
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = was_build, was_footy
        print("ok  knock the hut down and they come out screaming")
```

...and in the `# --- and none of it is left running ---` block, after
`assert roamer._job is None, "an empty crew must not own a timer"`, add:

```python
        assert yard.hut() is None and yard.ball() is None, \
            "an empty crew must not leave a yard behind either"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: FAIL on `assert all(one.winfo_viewable() for one in crowd)` — nothing is registered on `yard.on_knock`, so the three stay withdrawn inside a hut that is no longer there.

- [ ] **Step 3: Add the constants**

In `roamer.py`, after the hut block added in Task 4:

```python
# ------------------------------------------------------------ it came down
PANIC_S = 3.2           # how long the running lasts
PANIC_FACE_S = 2.5      # ...and how long it takes his face to come back
PANIC_TURN = 0.45       # he changes his mind about which way this often
PANIC_SPEED = WALK_SPEED * 2.6
HUT_SPILL = 34.0        # how far apart they come out
```

- [ ] **Step 4: Write `_hut_down` and register it**

In `roamer.py`, immediately after `_advance` (Task 2), add:

```python
def _hut_down(x, floor):
    """Somebody has just knocked it down.

    Registered on the yard as a callback rather than called out of it, so the
    yard never has to know what a roamer is. Everybody who was inside comes
    out where it stood - and so does anybody near enough to have watched it
    happen, which is the difference between a hut falling over and a hut
    being kicked in.
    """
    now = _time()
    for guy in list(crew):
        if guy.state == "inside":
            try:
                guy.deiconify()
            except tk.TclError:
                continue
            guy.x = _clamp(x + random.uniform(-HUT_SPILL, HUT_SPILL),
                           *guy.walk_line)
            guy.y = floor
            guy._begin("panic", now)
        elif (guy.floor is not None and abs(guy.floor - floor) < 4.0
              and abs(guy.x - x) < WATCH_R
              and guy.state in ("rest", "walk", "sleep", "watch")):
            guy._leave_scene(now)
            guy._watching = None
            guy._begin("panic", now)
    _cancel()
    _arm(TICK_MS)


yard.on_knock = _hut_down
```

- [ ] **Step 5: Add the `panic` state**

In `_begin`, after the `elif state == "inside":` block (Task 4):

```python
        elif state == "panic":
            self._until = now + PANIC_S
            self._panic_until = now + PANIC_S + PANIC_FACE_S
            self._leave_way = random.choice((-1.0, 1.0))
            self._turn_at = now + PANIC_TURN
            self.hands = self.feet = None
```

Add `_do_panic` to `Roamer`, immediately after `_do_inside` (Task 4):

```python
    def _do_panic(self, now, dt):
        """Out of the wreck, and running.

        Back and forth rather than away. Away is a stomp, and he already does
        that when he has been laughed at; this is somebody with nowhere in
        particular to be and no intention of standing still while he works
        out where.
        """
        if now >= self._turn_at:
            self._leave_way = -self._leave_way
            self._turn_at = now + PANIC_TURN
        way = self._leave_way
        x1, x2 = self._walls()
        self.x += way * PANIC_SPEED * dt
        if self.x <= x1 or self.x >= x2:
            self.x = _clamp(self.x, x1, x2)
            self._leave_way = -way
            self._turn_at = now + PANIC_TURN
        self.phase += PANIC_SPEED * dt / STEP_PX * math.pi
        self.facing, self.lean = way * 0.5, way * 3.4
        self.look = (0.0, 0.0)
        self.face = FACES["panic"]
        fy = self._face_y()
        self.hands = ((self.x - 26.0, fy - 12.0), (self.x + 26.0, fy - 12.0))
        self.feet = None
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y()
        self._say("!" if int((now - self.since) / 0.18) % 2 else "!!")
        if now - self.since >= PANIC_S:
            self._stir_at = now
            self._begin("rest", now)
```

- [ ] **Step 6: Let the fright outlast the running**

In `_idle` (~line 1650), after the `if now < self._cross_until:` block, add:

```python
        # ...and so does the fright, for the same reason: a man who is
        # perfectly calm the instant he stops running reads as a bug rather
        # than as somebody getting his breath back.
        if now < self._panic_until:
            weight = _clamp((self._panic_until - now) / PANIC_FACE_S,
                            0.0, 1.0)
            self.face = _face_mix(self.face, FACES["panic"], weight * 0.6)
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: PASS, including `ok  knock the hut down and they come out screaming`

- [ ] **Step 8: Run the whole suite three times**

The suite has a history of non-determinism around scene timing. Run it three times in a row and confirm all three pass:

```bash
for i in 1 2 3; do STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py || echo "RUN $i FAILED"; done
```

Expected: three clean runs, no `RUN n FAILED`.

- [ ] **Step 9: Commit**

```bash
git add roamer.py test_app.py
git commit -F - <<'EOF'
feat: knock the hut down and they come out screaming

Right-click it and it is gone - no menu. A roamer has one because "send
him home" and "ask him to leave" are two different things and one of them
is final; there is only one thing to do to a hut.

Everybody who was inside comes out where it stood, and so does anybody
near enough to have watched it happen, which is the difference between a
hut falling over and a hut being kicked in. They run back and forth
rather than off: away is a stomp, and he does that when he has been
laughed at. The fright outlasts the running the way the anger outlasts
the stomping, or a man perfectly calm the instant he stops reads as a bug.

The yard says it through a callback the crew registers, so the import
stays one way and nothing in yard.py knows what a roamer is.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

### Task 6: Documentation

**Files:**
- Modify: `roamer.py` — the module docstring (lines 1-41)
- Modify: `README.md` — the roamer behaviour section

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: nothing.

- [ ] **Step 1: Extend the module docstring**

In `roamer.py`, in the "What he does:" bullet list, after the bullet beginning
`* one who gets into the middle of it, by sidling or by being dropped there,`
and before the `* and lifting one of them over the others...` bullet, insert:

```
  * one of three in a conversation sometimes has somewhere else to be, waves,
    says bye and goes, and the two left finish it off without him,
  * some of the time what they have met up to do is kick a ball about, and
    whoever is nearest it is whoever chases it,
  * three of them with nothing built yet walk off the sides of the screen,
    come back carrying planks, put up a hut and go inside it,
  * and right-clicking the hut takes it down, which brings everybody in it
    and everybody near it out screaming,
```

...and add a paragraph at the end of the `Cost` section:

```
The ball and the hut live in `yard.py`, which owns no timer either: `tick`
steps and paints it as part of the frame it is already running, and the last
of them going home takes the yard's window with it.
```

- [ ] **Step 2: Document the behaviour in README.md**

Two edits, both under `## Behaviour worth knowing` (line 75) unless the line
numbers have moved:

**(a)** In the `## Files` table (~line 434), add a row directly under the
`roamer.py` row:

```
| `yard.py` | the ball and the hut they build: one shared overlay, and no idea what a roamer is |
```

**(b)** In the roamer section, insert a new block immediately **after** the
paragraph ending `...somebody still cooling off is a pair with an audience.`
(~line 330) and **before** the `**Getting him back.**` paragraph. Write it in
the voice of the surrounding text — second person, no bullet lists, the
constant named in prose where it explains how often you see something —
covering:

- **Excusing yourself** — `BOW_ODDS` (0.35), fires only in a three-way and only at the frame `say1` begins, never on the one about to speak; the two left switch to `FAREWELL` with roles re-indexed; `scene.mid` is deliberately not recomputed.
- **Football** — `FOOTY_ODDS` (0.25); `_pick_scene` is one roll cut three ways, not a roll each, so the numbers read as frequencies; no sides, no goals, no score; the chaser is recomputed from distance every frame; he kicks only on the way down.
- **Wood and the hut** — `BUILD_ODDS` (0.20), needs three of them and no hut already up; `FETCH_SPEED` is the knob if the errand drags on a wide screen; the scene stays on him through the errand so a pick-up still tears it down; `FETCH_MAX_S` is the give-up; indoors is a withdrawn window at `SLEEP_MS`.
- **Knocking it down** — right-click, no menu, and why; occupants plus anyone within `WATCH_R` on the same floor; `PANIC_S` running and `PANIC_FACE_S` of the face wearing off after.
- **The yard** — one keyed full-screen overlay for both props; the `on_knock` callback keeps the import one way; the `ponytail:` ceiling that a second monitor gets no yard of its own.

- [ ] **Step 3: Verify nothing is broken**

Run: `STICKYNOTE_TEST_NO_TOPMOST=1 python test_app.py`
Expected: PASS (documentation only, but the docstring edit touches `roamer.py`).

Also run: `python yard.py`
Expected: `ok  the ball falls, bounces, rolls to a stop and stays on screen`

- [ ] **Step 4: Commit**

```bash
git add roamer.py README.md
git commit -F - <<'EOF'
docs: what they get up to now there is a ball and a hut

Four behaviours and one new module in the module docstring and the
README, in the same shape as the rest: what you see, which constant
governs how often you see it, and what the alternative looked like when
it was tried.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XKxFss6tXLQZZ9HEKhW6k9
EOF
```

---

## Notes for the implementer

**Two places the design and this plan differ, deliberately:**

1. The spec says `yard.step(now, dt)`. It is `step(dt)` here — `now` was never used, and an unused parameter on a module boundary is a lie about what the function needs.
2. The spec has `_advance` raising the hut by calling `yard.attach(_root, ...)` first. `attach` is called from `Roamer.__init__` instead, with `app.root` directly. The reason is `test_app.py`'s `steps()` helper, which sets `roamer._root = None` for the duration so that `_arm` cannot schedule anything behind the test's back — a yard attached to `roamer._root` at hut-raising time would get `None` and the hut would never go up under test.

**Things that will bite:**

- `_close` only sends somebody off walking `if guy.state == "chat"`. Every new state relies on that: a fetcher whose scene is torn down keeps fetching, and the three walking to a door are not scattered by the `_close` that ends their build.
- `_cast` groups only roamers in `("rest", "walk", "sleep")` and considers watchers only in `("rest", "walk", "sleep", "watch")`. All five new states are outside both lists, which is what keeps somebody mid-errand or indoors from being cast in anything. Do not add them.
- `_say` writes `self._mark`, and `_begin` clears it. A state that wants a mark must set it every frame, which is why `_do_bye` and `_do_panic` both call `_say` unconditionally.
- `_advance` runs *after* every roamer has stepped and *before* `scene.i += 1`, so at `scene.i == BOW_AT` the cast has already drawn one frame of `say1`.
