# Excusing yourself, a kickabout, and a hut

**Date:** 2026-09-03
**Status:** Approved design, not yet planned
**Touches:** `yard.py` (new), `roamer.py`, `test_app.py`, `README.md`

## The problem

Three of them on the taskbar can hold a conversation, watch one, or gang up on
whoever walks into one. Every one of those scenes is the same shape: they meet,
they gesture at each other for a few seconds, they part. There is nothing in
their world except each other, and no scene any of them can leave early.

Four things to add:

1. **One of them peels off mid-conversation.** He waves, says bye, and goes.
   The other two carry on for a few more beats and then part normally.
2. **They kick a ball about.** Sometimes a meeting is a kickabout instead of a
   conversation.
3. **They build a hut.** All three walk off the sides of the screen, come back
   carrying planks, put up a small house, and go inside it.
4. **You knock the hut down.** Right-click it. Whoever is in it comes out
   screaming, along with anyone standing nearby, and they run about for a few
   seconds before settling.

## What you see

**Excusing yourself.** Three of them are talking. Partway through, one who is
not speaking turns to the other two, raises a hand, `bye!` appears over his
head, and he walks away. The two left wave him off, exchange a couple more
gestures, and part the way they always do.

**A kickabout.** A ball drops onto the taskbar between them and bounces. Whoever
is nearest trots at it — faster than he walks — and boots it at one of the
others. It arcs, lands, bounces, rolls. They face it and bob on their heels
while they wait. After about thirteen seconds they get bored and wander off, and
the ball goes with them.

**Building.** All three agree on something, then each one trots off to the
nearer side of the screen and walks straight off the edge. A moment later he
comes back carrying a plank held out in front of him, and stands where they
were. When the last of the three is home, a small hut goes up between them, and
they file in through the door and are gone. Twenty seconds or so later they come
back out one at a time and carry on as normal. The hut stays up.

**Knocking it down.** Right-click the hut and it is gone. Anyone inside comes
out on the spot with their arms over their heads and `!` above them, running
back and forth as fast as they move, and so does anyone who was standing near
enough to see it happen. After three seconds they stop, and a moment after that
their faces come back to normal.

## The yard

The ball and the hut are the first things in this app that exist on the desktop
and are not a note, a mascot or a roamer. They need a window.

Three ways to give them one:

- **One shared full-screen overlay.** A single chroma-keyed `Toplevel`, the size
  of the screen, holding the ball and the hut. On Windows the keyed colour is
  click-through, so a right-click anywhere but on the hut itself falls through
  to whatever is underneath — the same trick that already lets you click a
  roamer without clicking his window. One window, one canvas, one paint.
- **A window per prop, moved to follow it.** `Roamer._place` already documents
  why this is wrong: moving a layered top-level does not take effect until the
  event loop next runs, while the canvas inside it repaints against the new
  origin immediately, so a moving window judders. A ball moves every frame.
- **Drawn onto a roamer's canvas.** Free, but the props belong to whichever
  roamer happens to be hosting them, and he can be sent home at any moment.

The first. It goes in a new module rather than into `roamer.py`, which is
already 1739 lines: **`yard.py` knows nothing about roamers.** It owns a window,
a ball, a hut, and a right-click. Roamers ask it for the ball's position and
tell it to put a hut up. It tells them the hut came down through a callback they
set, so nothing in `yard.py` imports `roamer.py`.

### `yard.py` interface

```
on_knock = None        # set by roamer: called (x, floor) after a hut is
                       # right-clicked and removed

attach(root, key)      # remember the Tk root and the chroma key. Idempotent;
                       # the window itself is built on first use.
kick_off(x, floor)     # a ball drops in above (x, floor)
ball()                 # the ball, or None. x, y, vx, vy, r.
drop_ball()            # the ball is gone
raise_hut(x, floor)    # put a hut up, centred on x, standing on floor
hut()                  # the hut, or None. x, floor, w, h.
knock_down()           # the hut is gone, and on_knock is called
step(now, dt)          # ball physics: gravity, bounce, roll, walls
paint()                # redraw, skipped when nothing has moved
clear()                # ball, hut and window all gone
```

`knock_down` both removes the hut and fires the callback, so the right-click
binding is one call and so is the test. `clear` does neither: quitting the app
is not somebody kicking the hut in.

`step` and `paint` are called from `roamer.tick`, which is the only timer in
either module. The cost rule the app lives by holds: with nobody out there,
`crew` is empty, `shutdown` has called `clear`, and the yard owns no window and
no state.

Ball physics gets its own handful of constants in `yard.py` rather than
reaching into `roamer.py` for the ones a falling body uses. They are four
numbers, and a ball is not a person: it bounces higher, rolls further and does
not squash. Sideways it stops at the edges of the yard's own screen rect.

**Multiple monitors:** the yard covers the screen the hut or ball was created
on, and props do not cross to another. `ponytail:` comment on the ceiling; a
roamer who wanders to a second monitor and starts a kickabout there gets a ball
on the wrong screen. Fixing it means a yard per screen, which is not worth it
until somebody notices.

## Excusing yourself

The scene machinery already moves people in and out of a cast: `_turn_on` adds
one mid-scene and swaps the table underneath them. Leaving is the same move in
reverse, and it is the one thing `_leave_scene` cannot do — that always ends the
scene for everybody.

New module function:

```
_bow_out(scene, guy, now)
```

Takes him out of the cast, re-indexes the roles of the two left, swaps the table
to `FAREWELL` and puts `scene.i` back to zero. `scene.mid` is **not**
recomputed: the two left are already standing where they were, and moving the
midpoint under them would only matter on an `approach` beat, which `FAREWELL`
does not have. He gets `_social_at = now`, a direction away from the middle, and
`_begin("bye")`.

```
FAREWELL = (("wave", 24), ("say0", 40), ("agree", 22), ("part", 30))
```

The `wave` beat is new and belongs to `_talk_beat`: both of them raise a hand
towards where he went. Everything after it is beats `_talk_beat` already knows.

**When it fires.** A new `_advance(scene, now)`, called once per scene from
`tick` just before `scene.i += 1` — one place for anything a scene does between
beats. For a three-handed talk sitting exactly on the frame `say1` begins, with
odds `BOW_ODDS`, it picks one of the two who is not about to speak and bows him
out. The frame is computed from the table rather than written down:

```
def _beat_start(table, name)     # frame index the named beat begins on
BOW_AT = _beat_start(TALK3, "say1")
```

It cannot fire twice: `FAREWELL` is shorter than `BOW_AT` frames, and the cast
is down to two, which the check requires three of.

**New state `bye`.** A hand up, `bye!` over his head, facing the pair, for
`BYE_S`. Then `_begin("walk")` followed by a goal set away from `scene.mid` —
the same two lines `_close` uses, and for the same reason: `_begin("walk")`
picks a destination through `_company`, which would happily aim him straight
back at the conversation he just left.

## Choosing a kickabout

`_cast` currently opens `kind="talk"` every time. It gets a choice:

```
_pick_scene(ready)  ->  (kind, table)
```

`BUILD_ODDS` of the time, with three of them and no hut up, a build. A further
`FOOTY_ODDS` of the time, a kickabout. Otherwise a talk, `TALK3` or `TALK2` as
now.

Football and building are scene kinds, not new states, for the reason `mock` is
one: the scene record already carries the cast, the teardown, the cooldowns and
what happens when somebody is picked up out of it halfway through. They stay in
state `chat` and `_do_chat` dispatches on `scene.kind`, which is exactly what it
does for `mock` today.

```
FOOTY = (("kickabout", 780),)     # one long beat, about 13s at 60fps
```

`_footy_beat(scene, beat, u, now, dt)` — `_do_chat` grows a `dt` it currently
throws away:

- No ball (it was cleared under them) → close the scene.
- Whoever is nearest the ball is the chaser. He moves at `CHASE_SPEED` towards
  it, and within `KICK_R` he boots it: `ball.vy = -KICK_VY`, `ball.vx` towards
  one of the others picked at random, and a small hop and a `strain` face on
  him for the frame.
- Everybody else faces the ball, eyes on it, bobbing.

The ball is created in `_cast` right after the scene opens, at `scene.mid`, a
little above the floor so it drops in, and `drop_ball` is called from `_close`.
`step` runs it once per crew tick from `tick` — never per roamer, or three
roamers would advance the physics three times a frame.

## Wood, and the hut

```
BUILD = (("agree", 30), ("send", 6))
```

`_build_beat` handles both: `agree` is the three of them nodding at each other,
`send` puts each into the new `fetch` state. `guy.scene` stays set through the
whole errand, so picking one of them up still tears the build down the way it
tears down a conversation.

**State `fetch`,** three phases on `self._fetch`:

- `"out"` — trot to the nearer wall at `FETCH_SPEED` and keep going `FETCH_OFF`
  past it. Off the side of the screen he is drawn outside his own window and is
  simply not visible; nothing needs hiding.
- `"back"` — a pause of `FETCH_GONE_S` out there, then back to `self._site_x`
  carrying a plank: `self.carry` set, hands held out in front, and a plank drawn
  across them in `paint` after the figure, the same way `_mark` is.
- `"home"` — stood at the site doing nothing, waiting for the other two.

Two guards. If the scene has gone while he was away — somebody picked a mate up
— he drops the plank and goes back to resting where he stands, which reads as
coming home with the wood to find nobody there. And `FETCH_MAX_S` gives up on
the whole errand, so a fetcher wedged against a wall cannot sit in this state
for good.

**Raising it.** `_advance` on a build scene: every cast member `"home"` → ask
the yard to `raise_hut` at `scene.mid`, put each of them into `enter`, and close
the scene. Any cast member who has left the crew or is in neither `chat` nor
`fetch` → abandon it.

**States `enter` and `inside`.** `enter` walks him to the door at his ordinary
pace; on arrival he is `withdraw()`n and goes `inside` for a random
`INSIDE_S`, then `deiconify()`s and rests. `inside` ticks at `SLEEP_MS` and
`step` returns before `_place` and `paint`, so a roamer in a hut costs one
comparison a tick and no drawing at all. `_cast` already ignores any state it
does not list, so nobody indoors is cast in anything.

## Knocking it down

The yard binds `<ButtonPress-3>`. Inside the hut's rectangle it removes the hut
and calls `on_knock(x, floor)`; anywhere else the click falls through the keyed
colour to the desktop.

Right-click destroys it outright rather than opening a menu. A roamer's own
right-click menu exists because "send him home" and "ask him to leave" are two
different things and one of them is final. There is one thing to do to a hut.

`roamer._hut_down(x, floor)` is registered as `yard.on_knock` at import. It puts
everyone who was inside back on the floor at the wreck, and everyone on that
floor within `WATCH_R` who was resting, walking, dozing or watching, into
`panic`.

**State `panic`.** Running at `PANIC_SPEED`, reversing every `PANIC_TURN`,
`FACES["panic"]`, both arms up, `!` overhead, for `PANIC_S`. Then an ordinary
rest with `_stir_at` reset so he does not doze off straight after. The face
outlasts the running on its own: `_idle` already mixes `cross` back in for
`CROSS_S` after a stomp, and `panic` uses the same trick with its own timer.

## Constants

```
BOW_ODDS = 0.35        # a three-way where one of them has somewhere to be
BYE_S = 0.9

FOOTY_ODDS = 0.25
KICK_R = 26.0          # near enough to boot it
KICK_VX, KICK_VY = 300.0, 620.0
CHASE_SPEED = WALK_SPEED * 2.4

BUILD_ODDS = 0.20      # only with three of them, and no hut already up
FETCH_SPEED = WALK_SPEED * 2.2
FETCH_OFF = 130.0      # how far past the edge before he is out of sight
FETCH_GONE_S = 1.2
FETCH_MAX_S = 60.0     # the errand has gone wrong; come back to your senses
PLANK_W, PLANK_H = 44.0, 7.0
INSIDE_S = (14.0, 26.0)

PANIC_S = 3.2
PANIC_TURN = 0.45
PANIC_SPEED = WALK_SPEED * 2.6
```

...and in `yard.py`, which owns what the props look like and how the ball
falls:

```
BALL_R = 11.0
BALL_G = 2400.0        # a ball is lighter on its feet than he is
BALL_BOUNCE = 0.62
BALL_ROLL = 0.75       # horizontal decay per second once it is down
BALL_STOP = 12.0       # slower than this and it has stopped
HUT_W, HUT_H = 96.0, 74.0
DOOR_W = 26.0
```

A build is a twenty-second errand on a wide screen: a roamer standing in the
middle of 1920 pixels is 960 from the nearer edge, and `FETCH_SPEED` covers that
in about ten seconds each way. That is deliberate — it is ambient, not a cut
scene — but `FETCH_SPEED` is the knob if it drags.

## Testing

Four tests in `test_app.py`, in the existing style: real windows, real event
loop, `roamer.STEP` pinned so the physics repeats exactly, and `park()` to place
them and clear stale scenes.

1. **Bowing out.** Open a `talk3`, step to `BOW_AT`, force the odds. The scene is
   still running with two in the cast, roles are 0 and 1, the table is
   `FAREWELL`, and the third is in `bye` and then walking away from `scene.mid`.
2. **A kickabout.** Open a `footy`. Step. The ball is created, it moves, and its
   horizontal direction reverses at least once — somebody kicked it, rather than
   it simply rolling off under friction.
3. **Building.** Three on a floor, force a build. Step until `yard.hut()` exists,
   with a frame budget rather than forever. All three end up not `winfo_viewable`
   and in state `inside`, and the scene is gone.
4. **Knocking it down.** From the state test 3 leaves behind, call
   `yard.knock_down()` — the same call the right-click binding makes.
   `yard.hut()` is None, all three are viewable again and in `panic`, and after
   `PANIC_S` they are resting.

Plus the standing check that the existing suite already makes and which all of
this must not break: an empty crew owns no timer — and now, no yard either.

## What is deliberately not here

- **The hut does not survive a restart.** No `store.py` field, no schema, no
  rebuilding one at startup with nobody to have built it.
- **The ball is not persistent either**, and there is only ever one. It exists
  for the length of a kickabout.
- **Nobody scores.** There are no goals, no sides, and no count. It is three
  people and a ball.
- **A second monitor gets no yard of its own.** See above.
