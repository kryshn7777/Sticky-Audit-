# Three of them on the taskbar

**Date:** 2026-09-02
**Status:** Approved design, not yet planned
**Touches:** `roamer.py`, `mascot.py` (one new face), `test_app.py`

## The problem

Two roamers on the taskbar find each other and hold a conversation. Three is
not a designed state. `_pair_up` (`roamer.py:188`) sorts the free ones by x and
claims pairs greedily, left to right, so with three out the nearest eligible
two pair up and the third is never claimed. He carries on walking or dozing
beside a conversation he does not acknowledge, and because nothing in the crew
does separation, he walks straight through it.

`MAX_ROAMERS` is 3 (`roamer.py:60`), enforced at peel-off (`note.py:853`), so
three is also the most there will ever be.

This design gives three of them something to do: a genuine three-way
conversation when they all arrive together, and — when one turns up to a
conversation already in progress — either being quietly left out of it, or
being pointed at, laughed at, and stalking off.

## What you see

**All three together.** They close into a row, and one of them talks at a time
while the other two face him and watch. The speaker works the room, addressing
one and then the other. It ends the way a two-way ends: a nod from everyone and
away in different directions.

**Turning up late, and hanging back.** He stops at the edge, turns, and follows
whoever is speaking. Neither of them ever looks at him. When the conversation
ends they walk off in opposite directions and leave him standing in the middle
of where it was.

**Turning up late, and walking into it.** They break off mid-sentence, turn on
him, point, and laugh. He works out what is happening, stands there and takes
it, then turns and stalks away — faster than his normal walk, in a straight
line, without stopping to look at anything. The anger stays on his face for a
few seconds after he has gone, and he is not in the mood to talk to anybody for
a good while afterwards.

## Choosing a scene

Everyone stands on one line. Three in a row means one of them is always in the
middle, so **position alone cannot separate "three friends talking" from "two
closing in on the one between them".** They are the same arrangement. Timing
separates them:

- **All three free and sociable when the scene starts → `talk3`.** They decided
  together; nobody is an outsider. The cast is built by chaining free roamers by
  adjacency within `CHAT_R`, same floor — the existing `_pair_up` filter,
  clustering instead of claiming pairs.
- **A scene is already running and someone else arrives → he is an outsider.**
  Where he stops decides which scene he gets:
  - outside the scene but within `WATCH_R` (~220px), stopping around 100px out
    → **`watch`**;
  - closer to the participants' midpoint than they are to each other →
    **`mock`**.

Two things put him in the gap, both requiring no new movement code:

1. The user drops him there.
2. He walks into them. Roamers pass through each other today; here that is the
   trigger rather than a defect.

`approach` already moves participants together with `_mix(self.x, want, 0.10)`,
so a pair starting a conversation around someone already standing between them
closes ranks on him without anything being added.

Both passes — building casts from the free roamers, then testing everyone left
over against the running scenes — happen inside `_cast(now)`, once per tick for
the whole crew, exactly as `_pair_up` decides pairings today.

At a cap of 3 this collapses to two shapes and no others: `talk3` is everybody,
so it can never have an outsider, and `watch`/`mock` are always two in a scene
plus one out of it. The rules are written for N so that raising the cap does not
mean rewriting them, not because other shapes are reachable now.

## Beats

`_beat(TABLE, i)` and the `(name, frames)` tuple form are unchanged. Each scene
is one table.

**State names.** Everyone taking part in a scene keeps the state `chat`,
whichever table is running. Dispatch is `getattr(self, "_do_" + self.state)`
(`roamer.py:593`) and `rate()` keys off the same string, so holding the name
steady leaves both untouched and keeps `talk2` byte-identical in behaviour; the
scene record is what says which table and which role. `watch` and `stomp` are
genuinely new states with their own `_do_` methods, and both belong in `rate()`
— `watch` at `TICK_MS`, since his eyes move every frame, and `stomp` likewise.

### `talk3`

```
approach 34 - greet 20 - say(0) 46 - react 22 - say(1) 42 - react 22 -
say(2) 44 - agree 24 - part 30            ~ 284 frames, 4.5s
```

A roamer's role is his index in the cast. `speaking = (beat index == my role)`.

The two lines that carry the existing conversation —

```python
self.facing = _clamp((other.x - self.x) / 70.0, -1.0, 1.0)
self.look = _aim((self.x, self._face_y()), (other.x, other._face_y()))
```

— become "aim at the current speaker" and generalize to any cast size unchanged.
The speaker himself aims at one listener for the first half of his beat and the
other for the second, so he addresses both.

Standing positions are `centroid + (i - 1) * CHAT_GAP` for the cast sorted by x:
the existing `approach` `_mix`, with a different target.

### `watch`

A state on the outsider, not a scene table. Per frame he stands still
(`phase = 0`, no walk goal), aims `facing` and `look` at the current speaker
using the same two lines, and his face drifts between `calm` and `happy`.

His eyes come off the pointer. Only `wtf` does that today, and for the same
reason: something on screen is more interesting than the user.

The participants' code does not change. They never acknowledge him. When the
scene ends he returns to `rest`, standing where they left him.

### `mock`

Pre-empts a running conversation — if they are mid-sentence when he arrives,
they abandon the beat.

```
notice 18 - point 40 - laugh 54 - burn 30 - storm 26      ~ 168 frames, 2.7s
```

Deliberately shorter than a conversation. Cruelty is quick.

- **notice** — both break off, turn to him, face `calm` → `smug`.
- **point** — `_one_hand(side, 30, -4)`, arm out at him, `smug` held. Him:
  turning toward the nearer one, `calm` → `think`.
- **laugh** — mockers take `FACES["laugh"]`, hands up at face height, bobbing on
  `abs(sin(u * pi * 3)) * 5`. This is the existing `react_b` laugh, lifted.
  Him: `calm` → `cross`, looking at each of them in turn, then his gaze drops.
- **burn** — his beat. `cross` at full, a small shudder on `roll` and `squash`,
  standing there taking it while their laughing decays.
- **storm** — he turns away, and the exit takes over.

**No dialogue.** `_mark` can draw a string over a head and `greet` puts up a
`!`, but the conversation is carried entirely by facing and looking, on purpose.
A "ha ha" would be the first real line of dialogue in the app and would cheapen
a scene that is stronger silent.

## The new face

`FACES` has `calm happy panic strain talk laugh think smug wtf dazed plead`.
`smug` is currently unused and is the mockers' face.

Nothing angry exists, so one entry is added to `FACES` in `mascot.py`: `cross`
— narrowed eyes, heavy lids, brows driven down and angled in, mouth set in a
hard frown. Eight numbers, tuned by eye like the rest of the table.

`wtf` is not reused. It is spoken for as the look straight out at the user, and
blurring the two costs that joke.

## The exit

**`stomp`**, roughly 2.5s: `_do_walk`'s body with three differences — speed
x1.35, direction fixed away from the mockers
(`-sign(centroid - self.x)`, toward the far end of his `walk_line`), and no
stopping to look around. He does not doze off in a huff; `stomp` falls through
to normal `rest`/`walk` when it ends.

**Cooling off.** `_idle()` already runs every step for every state. One
`_cross_until` field and about three lines there: while the timer is live, mix
whatever face the current state set toward `cross`, by a weight decaying to
nothing over ~10s. Without it he is fine the instant the stomp ends, which reads
as a bug.

**Cooldown.** `sociable()` gains one clause against a new `_social_until` field.
The victim gets `MOCK_COOLDOWN` ~ 150s against the normal `CHAT_COOLDOWN` of 45.
He is not avoiding those two specifically — there is no per-pair memory anywhere
in the crew, by choice — he is simply not in the mood for anyone. The mockers
part on the normal cooldown.

## Teardown

`_release_partner` generalizes to `_leave_scene(now)`: drop me from the cast,
then decide what is left.

| Event | Result |
|---|---|
| `talk3`, one lifted | Scene ends. The other two to `rest`, normal cooldown. |
| `mock`, victim lifted | Mockers to `rest`. |
| `mock`, a mocker lifted | Scene ends. Victim to `rest`, un-stormed, no cooldown penalty. |
| `watch`, scene ends | Back to `rest`, standing where they left him. |

`talk3` is not degraded to a `talk2` when it loses someone: reindexing roles and
the speaker inside a running beat is fiddly for something nobody would read as
intentional.

Lifting the victim is how the user rescues him — and holding him over the two
who were laughing fires the existing `abandoned_by` check, so both of them get
the look. Rescue and comeuppance, out of code that already shipped.

## Cost

Idle is untouched: an empty crew owns no timer and costs one comparison against
an empty list, and the existing assertion still guards it.

| Scene | Cost |
|---|---|
| `talk3` | Three animating at 16ms for ~4.5s. ~18-30% by the README's per-walker figures. |
| `mock` | The same, for 2.7s. |
| `watch` | One extra animated figure for the length of a scene. His eyes and face move every frame, so the repaint-on-change check does not help him. |

All bursts. No new floor.

**`MAX_ROAMERS` stays at 3.** Each roamer owns a screen-sized overlay window;
four walking is 24-40%, which is rude on a laptop. Everything here is written
for N, so raising it later is one constant — but do that with measurements, not
on the strength of this document.

**Separation is not built.** Walking through each other is the `mock` trigger,
and at a cap of 3 there is nobody spare to walk through a scene. It is the first
thing to revisit if the cap goes up.

**Re-measure before shipping.** The README quotes real figures (0.2-0.5% idle,
6-10% walking, 4.8ms median frame). Scenes change the busy end of that.

## Tests

`test_app.py` has the template: build `Roamer`s directly against note windows,
force `state`/`floor`/`y`, zero `_social_at`, pin `_until`, then `crank(n, stop)`
and assert states. Pinned `roamer.STEP` plus fixed x keeps the cast
deterministic, which matters more now `_pair_up` is greedy over three. A third
roamer needs a third note window; the existing test already uses two.

1. **`talk3` forms and rotates.** Three free and in range: all three in `chat`,
   one cast, distinct roles, every role gets a `say` beat. Ends once. All three
   leave.
2. **`watch`.** Two mid-conversation, third parked outside: not in the cast, his
   `look` retargets when the speaker changes, and the participants' beat index
   is untouched.
3. **`mock`.** Third placed in the gap: the scene pre-empts, the victim ends in
   `stomp`, `(victim._goal - victim.x)` has the opposite sign to
   `(centroid - victim.x)`, and `sociable()` stays false past `CHAT_COOLDOWN`.
4. **Teardown.** Lift the victim mid-`mock`: mockers to `rest`, nothing raises.
   Hold him overhead and both reach `wtf`.
5. **The existing two-roamer test passes unchanged.** The real regression guard
   on generalizing `_do_chat`: if `talk2` behaves exactly as it does today, the
   generalization cost nothing.

## Approach, and what was rejected

**Chosen: generalize the pairwise conversation in place.** `partner` becomes a
shared scene record (cast, beat index, speaker index); `_chat_first` becomes a
role; `CHAT` becomes one table per scene. `_pair_up` clusters instead of
claiming pairs. All within `roamer.py`, which goes from about 1307 lines to
about 1500.

**Rejected: an audience bolted onto the existing pair.** The smallest possible
diff — pairs never change, a third near an active pair enters `watch`, pushing
in flips the pair to a mock beat. It cannot produce a three-way conversation at
all, so it delivers half the feature.

**Rejected: extracting a `scene.py`.** `_do_chat` writes `self.hands`,
`self.face`, `self.y`, `self.facing` and `self.look` directly, every frame. A
scene module either reaches into those internals — a boundary in name only — or
needs a pose interface invented to hold it. Social behaviour is not separable
from pose solving here; it *is* pose solving with a reason. If `roamer.py`
becomes a problem, the pose half is what is worth lifting out, and that is a
different job.
