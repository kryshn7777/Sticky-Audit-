# Three Mascots On The Taskbar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give three roamers on the taskbar a three-way conversation, a state for being left out of one, and a scene where two of them mock the one who walks into it.

**Architecture:** The existing pairwise conversation is generalized in place. `partner` becomes a shared `_Scene` record (table, cast, beat index); `_chat_first` becomes a role index into that cast; the single `CHAT` beat tuple becomes one table per scene. `_pair_up` becomes `_cast`, which clusters by adjacency instead of claiming pairs and then tests everyone left over against the running scenes. All of it stays in `roamer.py`; `mascot.py` gains one face.

**Tech Stack:** Python 3, Tkinter, no dependencies. Tests are plain asserts in `test_app.py`, run as a script.

**Spec:** `docs/superpowers/specs/2026-09-02-three-mascots-scenes-design.md`

## Global Constraints

- No new dependencies. The app is stdlib-only and ships as a frozen exe.
- An empty crew owns no timer and costs one comparison against an empty list. `test_app.py` asserts this; it must stay true.
- Scene participants keep the state string `chat`. Dispatch is `getattr(self, "_do_" + self.state)` (`roamer.py:593`) and `rate()` keys off the same string.
- `rate()` needs no entries for `watch` or `stomp`. Its lookup is `.get(self.state, TICK_MS)` (`roamer.py:585`) and `TICK_MS` is what both want. The spec says to add them; it is wrong on that detail, and adding them would be dead code.
- `MAX_ROAMERS` stays at 3. Do not change it in this plan.
- No dialogue. `_mark` stays unused by the new scenes; only the existing `greet` `!` remains.
- Run the suite with `python test_app.py` from the project root. It creates real Tk windows and drives real widgets.
- **Do not type on the keyboard while the suite runs.** It uses real widgets and absorbs live keystrokes into note text, which corrupts unrelated assertions.

---

### Task 1: Put the project under version control

There is no git repository here (`git rev-parse` fails). Every later task ends in a commit, so this has to exist first.

**Files:**
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a repository with a green baseline commit, so later tasks can commit and be reverted individually.

- [ ] **Step 1: Confirm the suite is green before touching anything**

Run: `python test_app.py`
Expected: ends with `all app checks passed`. If it does not, stop and report — the baseline is broken and nothing below is safe to build on.

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
build/
dist/
.playwright-mcp/
```

- [ ] **Step 3: Initialise and commit the baseline**

```bash
git init
git add -A
git commit -m "chore: baseline before three-mascot scene work"
```

- [ ] **Step 4: Confirm the tree is clean**

Run: `git status --porcelain`
Expected: no output.

---

### Task 2: An angry face

`FACES` has no angry entry. The mocked one needs one, and `wtf` cannot be reused — it is the look straight out at the user, and blurring the two costs that joke.

**Files:**
- Modify: `mascot.py:1155-1167` (the `FACES` table)
- Test: `test_app.py` (near the other `mascot_mod` face checks)

**Interfaces:**
- Consumes: `mascot.Face`, the existing namedtuple `(eye, lid, brow, tilt, mouth, curve, open, sweat)`.
- Produces: `FACES["cross"]`, used by Task 6 (`laugh`, `burn`) and Task 7 (`stomp`, the cool-off).

- [ ] **Step 1: Write the failing test**

Add this in `test_app.py` immediately before the line `probe = app_module.tk.Canvas(app.root, width=240, height=240)`:

```python
    # An angry face, and not the same angry as the look out at the camera.
    cross = mascot_mod.FACES["cross"]
    wtf = mascot_mod.FACES["wtf"]
    assert cross.brow < 0 and cross.tilt < 0, "brows down and in, or it is not anger"
    assert cross.curve < 0, "and a frown, not a smile"
    assert cross.eye < 1.0 < wtf.eye, \
        "cross narrows his eyes where wtf makes saucers - that is the difference"
    print("ok  he has a face for being laughed at")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python test_app.py`
Expected: `KeyError: 'cross'`.

- [ ] **Step 3: Add the face**

In `mascot.py`, inside the `FACES` dict, add this line directly after the `"smug"` entry:

```python
    "cross":  Face(0.6, 0.55, -0.85, -0.7, 0.9, -0.9, 0.10, 0.0),
```

- [ ] **Step 4: Run it and watch it pass**

Run: `python test_app.py`
Expected: `ok  he has a face for being laughed at`, and the suite still ends with `all app checks passed`.

- [ ] **Step 5: Commit**

```bash
git add mascot.py test_app.py
git commit -m "feat: add the cross face for a mascot who has been laughed at"
```

---

### Task 3: Scenes, with the two-way conversation running on them unchanged

The refactor. Nothing visible changes: two of them still meet, still talk, still leave in opposite directions, on the same frame counts. The existing two-roamer test is the gate — it must pass **without being edited**.

**Files:**
- Modify: `roamer.py:105-109` (the `CHAT` tuple and company constants)
- Modify: `roamer.py:123-127` (module state)
- Modify: `roamer.py:160-230` (`tick`, `_pair_up`, `shutdown`)
- Modify: `roamer.py:358-364` (the chat fields in `__init__`)
- Modify: `roamer.py:1048-1160` (`sociable`, `start_chat`, `_release_partner`, `_do_chat`)
- Test: `test_app.py:849-866` — **read only, do not modify**

**Interfaces:**
- Consumes: `_beat`, `_face_mix`, `_aim`, `_mix`, `_clamp`, `FACES` from `mascot`.
- Produces, relied on by Tasks 4-7:
  - `_Scene(kind, table, cast)` with attributes `kind` (str), `table` (beat tuple), `cast` (list of `Roamer`, left to right), `i` (int beat index), `mid` (float, frozen at open), `last_speaker` (`Roamer` or `None`), and methods `speaker() -> Roamer | None` and `stand_x(guy) -> float`.
  - module-level `scenes` (list of `_Scene`).
  - `_open(group, kind, table, now) -> _Scene`, `_close(scene, now) -> None`.
  - `Roamer.scene` (`_Scene` or `None`), `Roamer.role` (int index into `scene.cast`).
  - `Roamer.partner` — read-only property, the other one when the cast is exactly two, else `None`.
  - `Roamer._leave_scene(now)`.
  - `TALK2`, `SPEAKS`.

- [ ] **Step 1: Replace the beat table and add the scene constants**

In `roamer.py`, replace the `CHAT` tuple at line 108 with:

```python
TALK2 = (("approach", 34), ("greet", 20), ("say0", 52), ("react", 26),
         ("say1", 46), ("agree", 24), ("part", 30))

# Which role is talking, by beat name. Everything else about a scene - who
# looks at whom, who laughs, who is left standing - falls out of this and the
# cast order, which is why the three scenes differ only by data.
SPEAKS = {"say0": 0, "say1": 1, "say2": 2}
```

Frame counts are the old `CHAT` counts in the same order, so the timing is identical. `say_a` and `say_b` become `say0`/`say1` because the speaker is now an index rather than a bool, and `react_b` becomes `react` because the rule that made it work for two — *the one who just spoke thinks, everybody else laughs* — is already the rule for any number.

- [ ] **Step 2: Add the scene record and the module list**

In `roamer.py`, directly below `crew = []` at line 124, add:

```python
scenes = []


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
```

- [ ] **Step 3: Advance scene beats once per tick**

In `roamer.py`, in `tick()`, replace the line `_pair_up(now)` with `_cast(now)`, and add the beat advance **after** the roamer loop and before `_arm(delay)`:

```python
    _cast(now)
    delay = SLEEP_MS
    for guy in list(crew):
        try:
            delay = min(delay, guy.step(now))
        except tk.TclError:
            guy.vanish()
    for scene in list(scenes):
        scene.i += 1
    _arm(delay)
```

Advancing after the loop rather than before it keeps the first tick reading beat index 0, which is what the old per-roamer `_chat_i` did.

- [ ] **Step 4: Rename `_pair_up` to `_cast` and open scenes instead of pairs**

Replace the whole of `_pair_up` (`roamer.py:188-219`) with:

```python
def _cast(now):
    """Who is in a scene with whom, and who is being dangled over whom.

    Decided here, once, for the whole crew, for the same reason pairing was:
    left to each of them separately, A takes up with B while B is already
    taking up with C and the whole thing knots itself.
    """
    free = sorted((g for g in crew if g.state in ("rest", "walk", "sleep")),
                  key=lambda g: g.x)
    i = 0
    while i < len(free):
        # A chain of them, each within talking distance of the last one and
        # standing on the same floor.
        group = [free[i]]
        j = i + 1
        while (j < len(free) and free[j].x - group[-1].x <= CHAT_R
               and abs(free[j].y - group[-1].y) <= 30.0):
            group.append(free[j])
            j += 1
        ready = [g for g in group if g.sociable(now)][:3]
        if len(ready) >= 2:
            _open(ready, "talk", TALK2, now)
        i = j

    held = [g for g in crew if g.state == "held"]
    if not held:
        for guy in crew:
            guy._lift_since = None
        return
    for guy in crew:
        if guy.state in ("held", "wtf"):
            continue
        if any(guy.abandoned_by(h) for h in held):
            guy.notice_the_lift(now)
        else:
            guy._lift_since = None
```

Task 4 replaces the `_open(ready, "talk", TALK2, now)` line to pick a table by cast size. Task 5 adds the outsider pass below the chain loop.

- [ ] **Step 5: Clear scenes on shutdown**

In `shutdown()` (`roamer.py:222`), add `del scenes[:]` immediately after `del crew[:]`.

- [ ] **Step 6: Swap the chat fields on the Roamer**

In `__init__` (`roamer.py:358-364`), replace these four lines —

```python
        self.partner = None
        self._chat_i = 0
        self._chat_first = True
        self._social_at = 0.0
```

— with:

```python
        self.scene = None
        self.role = 0
        self._social_at = 0.0
```

Leave `self._lift_since = None` on the line below exactly as it is.

- [ ] **Step 7: Replace the company methods**

Replace `sociable`, `start_chat`, `_release_partner` and `_do_chat` (`roamer.py:1048` through the end of `_do_chat`) with:

```python
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
        self._talk_beat(scene, beat, u, now)

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
        # are what makes this read as a conversation instead of toys
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
```

Note on `greet`: the old code fired `!` on `self._chat_i == 2`, a per-roamer counter that started at 0 when the scene opened. The scene index is now shared and absolute, and `greet` starts at frame 34, so `scene.i == 35` is the same moment.

- [ ] **Step 8: Point the remaining callers at `_leave_scene`**

Three call sites still say `_release_partner`. Replace each with `self._leave_scene(now)`:

- `excuse_me` (`roamer.py:423`)
- `pick_up` (`roamer.py:435`)
- `vanish` (`roamer.py:511`)

Then in `vanish`, the existing `if self in crew: crew.remove(self)` stays as it is.

Also `notice_the_lift` (`roamer.py:1176` area) calls `self._release_partner(now)` before `self._begin("wtf", now)` — replace that with `self._leave_scene(now)` too.

- [ ] **Step 9: Run the suite. The unmodified two-roamer test is the gate**

Run: `python test_app.py`
Expected: `ok  two of them talk, and only the once` and `ok  one of them lifted over the other gets a look` both still print, and the suite ends with `all app checks passed`. `test_app.py` must not have been edited in this task — if it needed editing, the generalization changed behaviour and is wrong.

- [ ] **Step 10: Commit**

```bash
git add roamer.py
git commit -m "refactor: run the two-way conversation on a shared scene record"
```

---

### Task 4: The three-way conversation

**Files:**
- Modify: `roamer.py` — the `TALK2` block (add `TALK3`), and the `_open(...)` line inside `_cast`
- Test: `test_app.py`, after the `ok  two of them talk, and only the once` block

**Interfaces:**
- Consumes: `_Scene`, `_open`, `_close`, `SPEAKS`, `scenes`, `Roamer.role` from Task 3.
- Produces: `TALK3` (beat tuple), and a cast of three whose roles are `0`, `1`, `2` left to right.

- [ ] **Step 1: Write the failing test**

In `test_app.py`, add this directly after the line `print("ok  two of them talk, and only the once")`:

```python
        # three of them together talk as three, and everybody gets a turn
        third = app.new_note("green")
        pump(app.root)
        trio = [a, b, roamer.Roamer(app, third, 0.0, floor)]
        for k, one in enumerate(trio):
            one.x = right - 460.0 + k * roamer.CHAT_R * 0.6
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
        crank(5)
        assert all(one.state == "chat" for one in trio), \
            [one.state for one in trio]
        scene = trio[0].scene
        assert scene is not None and len(scene.cast) == 3, "one cast of three"
        assert all(one.scene is scene for one in trio), "and all in the same one"
        assert sorted(one.role for one in trio) == [0, 1, 2], "distinct roles"
        assert [one.x for one in scene.cast] == sorted(one.x for one in trio), \
            "the cast is ordered left to right"
        spoke = set()
        for _ in range(600):
            if trio[0].scene is None:
                break
            who = trio[0].scene.speaker()
            if who is not None:
                spoke.add(who.role)
            roamer.tick()
            pump(app.root, 1)
        assert spoke == {0, 1, 2}, ("everybody gets a turn", spoke)
        assert all(one.state == "walk" for one in trio), \
            [one.state for one in trio]
        crank(600)
        assert all(one.state != "chat" for one in trio), "once, not on a loop"
        for one in trio:
            one.vanish()
        print("ok  three of them talk, and everybody gets a turn")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python test_app.py`
Expected: fails on `assert spoke == {0, 1, 2}` with `{0, 1}` — three of them form a cast, but `TALK2` only ever gives role 2 silence.

- [ ] **Step 3: Add the three-way table**

In `roamer.py`, directly below the `TALK2` tuple, add:

```python
TALK3 = (("approach", 34), ("greet", 20), ("say0", 46), ("react", 22),
         ("say1", 42), ("react", 22), ("say2", 44), ("agree", 24),
         ("part", 30))
```

- [ ] **Step 4: Pick the table by cast size**

In `_cast`, replace:

```python
        if len(ready) >= 2:
            _open(ready, "talk", TALK2, now)
```

with:

```python
        if len(ready) >= 2:
            _open(ready, "talk", TALK3 if len(ready) > 2 else TALK2, now)
```

- [ ] **Step 5: Run it and watch it pass**

Run: `python test_app.py`
Expected: `ok  three of them talk, and everybody gets a turn`, with the two-roamer check above it still passing.

- [ ] **Step 6: Commit**

```bash
git add roamer.py test_app.py
git commit -m "feat: three of them on the floor hold a three-way conversation"
```

---

### Task 5: Watching from the edge

**Files:**
- Modify: `roamer.py` — company constants, the outsider pass in `_cast`, a `_do_watch` method, `_leave_scene`
- Test: `test_app.py`, after the three-way block

**Interfaces:**
- Consumes: `_Scene`, `scenes`, `Roamer.scene` from Task 3.
- Produces: `WATCH_R`; `Roamer.watch(scene, now)`; `Roamer._watching` (`_Scene` or `None`); the state string `"watch"`.

**Correction to the spec.** The spec says he stops "around 100px out". He does not walk toward the scene at all — entering `watch` stops him wherever he already is, and there is no drift target. That is why the two ways into the gap are the user dropping him there and him walking through on a goal he already had; a watcher who drifted inward would eventually be mocked every single time. No `WATCH_STAND` constant exists.

- [ ] **Step 1: Write the failing test**

Add this in `test_app.py` directly after `print("ok  three of them talk, and everybody gets a turn")`:

```python
        # two of them talking, and a third who turns up and hangs back
        onlooker = roamer.Roamer(app, third, 0.0, floor)
        pair = [a, b]
        for k, one in enumerate(pair):
            one.x = right - 460.0 + k * roamer.CHAT_R * 0.6
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
        onlooker.state, onlooker.floor, onlooker.y = "rest", floor, floor
        onlooker.vx = onlooker.vy = 0.0
        onlooker.scene = None
        onlooker._until = time.monotonic() + 999.0
        onlooker._social_at = 0.0
        # Out of talking distance of either of them, but inside watching
        # distance of the pair - so he can never be cast, only an audience.
        onlooker.x = (pair[0].x + pair[1].x) / 2.0 + roamer.CHAT_R + 40.0
        crank(8)
        scene = a.scene
        assert scene is not None and len(scene.cast) == 2, "the two of them"
        assert onlooker not in scene.cast, "he is not in it"
        assert onlooker.state == "watch", onlooker.state
        assert scene.i > 0, "and the conversation is running normally"

        # his eyes are on whoever is talking, and move when the speaker does
        seen = {}
        for _ in range(600):
            if a.scene is None:
                break
            who = a.scene.speaker()
            if who is not None:
                seen[who.role] = onlooker.look
            roamer.tick()
            pump(app.root, 1)
        assert set(seen) == {0, 1}, ("he saw both of them speak", set(seen))
        assert seen[0] != seen[1], "and his eyes went from one to the other"
        assert onlooker.state == "rest", onlooker.state
        onlooker.vanish()
        print("ok  one who turns up late hangs back and watches")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python test_app.py`
Expected: fails on `assert onlooker.state == "watch"` with `rest` — nothing puts him in that state yet.

- [ ] **Step 3: Add the constants**

In `roamer.py`, below `CHAT_COOLDOWN`, add:

```python
WATCH_R = 220.0         # near enough to be worth turning round for
```

- [ ] **Step 4: Add the outsider pass to `_cast`**

In `_cast`, directly after the `while i < len(free):` loop and before the `held = [...]` line, add:

```python
    # Anybody left over, against whatever is already running. Watchers are
    # looked at again every tick, not just once: one who is shoved into the
    # middle of a conversation he was watching has to be noticed.
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
        guy.watch(scene, now)
```

And directly above `_cast`, add:

```python
def _scene_near(guy):
    """The running scene he has walked in on, if any: the nearest one on his
    own floor that he is not part of."""
    best, near = None, WATCH_R
    for scene in scenes:
        if guy in scene.cast or not scene.cast:
            continue
        if abs(scene.cast[0].y - guy.y) > 30.0:
            continue
        gap = abs(guy.x - scene.mid)
        if gap < near:
            best, near = scene, gap
    return best
```

- [ ] **Step 5: Add `_watching`, `watch()` and `_do_watch`**

In `__init__`, beside `self.scene = None`, add:

```python
        self._watching = None
```

Then add these two methods next to `_do_chat`:

```python
    def watch(self, scene, now):
        if self.state == "watch" and self._watching is scene:
            return
        self._watching = scene
        self._begin("watch", now)

    def _do_watch(self, now, _dt):
        """Stood at the edge of somebody else's conversation.

        His eyes come off the pointer, which nothing but the look out at the
        camera does, and for the same reason: there is something on the
        screen more interesting than the user. Nobody in the scene ever
        acknowledges him - that is the whole of it.
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
```

- [ ] **Step 6: Send watchers back to rest when the scene ends**

In `_close`, inside the `for guy in list(scene.cast)` loop is not enough — the watcher is not in the cast. Add this at the end of `_close`, after that loop:

```python
    for guy in crew:
        if guy._watching is scene:
            guy._watching = None
            if guy.state == "watch":
                guy._begin("rest", now)
```

- [ ] **Step 7: Run it and watch it pass**

Run: `python test_app.py`
Expected: `ok  one who turns up late hangs back and watches`, and every check above it still passing.

- [ ] **Step 8: Commit**

```bash
git add roamer.py test_app.py
git commit -m "feat: a latecomer hangs back and watches a conversation he is not in"
```

---

### Task 6: Being pointed at and laughed at

**Files:**
- Modify: `roamer.py` — the `MOCK` table, the intrusion branch in `_cast`, `_turn_on`, `_mock_beat`, the `_do_chat` dispatch
- Test: `test_app.py`, after the watching block

**Interfaces:**
- Consumes: `FACES["cross"]` (Task 2), `_Scene`/`_open`/`_close` (Task 3), `_scene_near` (Task 5).
- Produces: `MOCK` (beat tuple); the convention that in a `kind == "mock"` scene **`cast[-1]` is the victim**; `_turn_on(scene, guy, now)`; `Roamer.mocked` (bool property).

- [ ] **Step 1: Write the failing test**

Add this in `test_app.py` directly after `print("ok  one who turns up late hangs back and watches")`:

```python
        # ...and one who walks right into the middle of it gets what he asked for
        victim = roamer.Roamer(app, third, 0.0, floor)
        for k, one in enumerate(pair):
            one.x = right - 460.0 + k * roamer.CHAT_GAP
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
        crank(40)                       # let them get talking first
        scene = a.scene
        assert scene is not None and scene.kind == "talk", "a conversation"
        was = scene.i
        victim.state, victim.floor, victim.y = "rest", floor, floor
        victim.vx = victim.vy = 0.0
        victim.scene = None
        victim._until = time.monotonic() + 999.0
        victim._social_at = 0.0
        victim.x = scene.mid                    # straight into the gap
        crank(3)
        assert victim.scene is scene, "he is in it now, whether he likes it or not"
        assert scene.kind == "mock", scene.kind
        assert scene.i < was, "and they break off mid-sentence to do it"
        assert scene.cast[-1] is victim, "the last one in the cast is the victim"
        assert victim.mocked and not a.mocked, "and only him"
        crank(400, lambda: victim.scene is None)
        assert victim.scene is None and a.scene is None, "it ends"
        print("ok  walk into a conversation and the two of them turn on you")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python test_app.py`
Expected: fails on `assert victim.scene is scene` — standing in the gap currently only makes him a watcher.

- [ ] **Step 3: Add the mock table**

In `roamer.py`, below `TALK3`, add:

```python
# Shorter than a conversation on purpose. Cruelty is quick.
MOCK = (("notice", 18), ("point", 40), ("laugh", 54), ("burn", 30),
        ("storm", 26))
```

- [ ] **Step 4: Turn the watch branch into a fork**

In `_cast`, replace the line `guy.watch(scene, now)` with:

```python
        span = max(abs(g.x - scene.mid) for g in scene.cast)
        if scene.kind == "talk" and abs(guy.x - scene.mid) < max(span, 1.0):
            _turn_on(scene, guy, now)       # he is standing in the gap
        elif abs(guy.x - scene.mid) < WATCH_R:
            guy.watch(scene, now)
```

And add `_turn_on` beside `_open`:

```python
def _turn_on(scene, guy, now):
    """He has walked into the middle of it. They stop and turn on him.

    The scene is not torn down and rebuilt: the same two keep their roles and
    the beat index goes back to nothing, which is what makes them break off
    mid-sentence rather than finish the thought.
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
```

`_Scene.__slots__` lists `kind` and `table` already, so both are assignable.

- [ ] **Step 5: Add the `mocked` property and the beat dispatch**

Beside the `partner` property, add:

```python
    @property
    def mocked(self):
        """Am I the one being laughed at? In a mock the victim is the one who
        walked in, so he is the last into the cast."""
        scene = self.scene
        return (scene is not None and scene.kind == "mock"
                and scene.cast and scene.cast[-1] is self)
```

Then in `_do_chat`, replace the final line `self._talk_beat(scene, beat, u, now)` with:

```python
        if scene.kind == "mock":
            self._mock_beat(scene, beat, u, now)
        else:
            self._talk_beat(scene, beat, u, now)
```

- [ ] **Step 6: Write the mock beats**

Add this method directly below `_talk_beat`:

```python
    def _mock_beat(self, scene, beat, u, now):
        """Two of them pointing, and the one they are pointing at.

        Carried the same way the conversation is - by where they are facing
        and what their faces are doing - and with no more dialogue than that
        one has. A written "ha ha" would be the first line anybody in this app
        has spoken, and it would cheapen a scene that is stronger silent.
        """
        victim = scene.cast[-1]
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.lean, self.phase = 0.0, 0.0
        self.y = self._floor_y()
        mine = self is victim

        if mine:
            others = [g for g in scene.cast if g is not self]
            # Looking from one to the other while it dawns on him, and then
            # his eyes go down and stay down.
            who = others[min(len(others) - 1, int(u * 2.0))] if others else None
            if beat in ("burn", "storm") or who is None:
                self.look = (0.0, 0.6)
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
                self.face = FACES["cross"]
                # Standing there taking it: not a flinch, a held tension.
                self.roll = math.sin(now * 11.0 * TAU) * 0.015
                self.squash = 1.0 + math.sin(now * 9.0 * TAU) * 0.012
                self.facing = _mix(self.facing, 0.0, 0.12)
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
```

- [ ] **Step 7: Run it and watch it pass**

Run: `python test_app.py`
Expected: `ok  walk into a conversation and the two of them turn on you`, everything above still passing.

- [ ] **Step 8: Commit**

```bash
git add roamer.py test_app.py
git commit -m "feat: two of them turn on whoever walks into their conversation"
```

---

### Task 7: Storming off, and cooling down

**Files:**
- Modify: `roamer.py` — the goodbye constants, `_close`, `_do_stomp`, `sociable`, `_idle`
- Test: `test_app.py`, after the mock block

**Interfaces:**
- Consumes: `FACES["cross"]` (Task 2), `Roamer.mocked` and `MOCK` (Task 6).
- Produces: the state string `"stomp"`; `STOMP_S`, `STOMP_SPEED`, `CROSS_S`, `MOCK_COOLDOWN`; `Roamer._cross_until`, `Roamer._social_until`.

- [ ] **Step 1: Write the failing test**

Add this in `test_app.py` directly after `print("ok  walk into a conversation and the two of them turn on you")`:

```python
        # he does not take it well, and he is off in the other direction
        for k, one in enumerate(pair):
            one.x = right - 460.0 + k * roamer.CHAT_GAP
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
        crank(40)
        scene = a.scene
        victim.state, victim.floor, victim.y = "rest", floor, floor
        victim.vx = victim.vy = 0.0
        victim.scene = None
        victim._until = time.monotonic() + 999.0
        victim._social_at = 0.0
        victim.x = scene.mid
        crank(3)
        assert victim.mocked, "the setup has to have taken"
        mid = scene.mid
        crank(400, lambda: victim.state == "stomp")
        assert victim.state == "stomp", victim.state
        assert (victim.x - mid) * victim._leave_way > 0 or victim.x == mid, \
            "he walks away from them, not back through them"
        here = victim.x
        crank(20)
        assert abs(victim.x - here) > abs(roamer.WALK_SPEED * 20 * roamer.STEP), \
            "and faster than his ordinary walk"
        assert not victim.sociable(roamer._time()), \
            "he is not in the mood for anybody"
        crank(400, lambda: victim.state != "stomp")
        assert victim.state in ("rest", "walk"), victim.state
        assert victim._cross_until > 0.0, "the anger outlives the stomping"
        victim.vanish()
        print("ok  the one they laughed at storms off and stays cross")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python test_app.py`
Expected: fails on `assert victim.state == "stomp"` with `rest` — `_close` currently sends everybody to `walk`.

- [ ] **Step 3: Add the constants**

In `roamer.py`, below the `LEAVE_MAX_S` line in the goodbye block, add:

```python
# ------------------------------------------------------- not taking it well
STOMP_S = 2.5           # how long he keeps it up
STOMP_SPEED = WALK_SPEED * 1.35
CROSS_S = 10.0          # ...and how long the face lasts after he stops
MOCK_COOLDOWN = 150.0
```

- [ ] **Step 4: Send the victim off differently in `_close`**

In `_close`, replace the body of the cast loop with:

```python
    for guy in list(scene.cast):
        was_mocked = (scene.kind == "mock" and scene.cast
                      and scene.cast[-1] is guy)
        guy.scene = None
        guy.role = 0
        guy._social_at = now
        if guy.state != "chat":
            continue
        if was_mocked:
            guy._cross_until = now + CROSS_S
            guy._social_until = now + MOCK_COOLDOWN
            guy._leave_way = 1.0 if guy.x > scene.mid else -1.0
            guy._begin("stomp", now)
            continue
        guy._begin("walk", now)
        away = 140.0 if guy.x > scene.mid else -140.0
        guy._goal = _clamp(guy.x + away, *guy.walk_line)
```

`_leave_way` is reused rather than given a twin: it already means "which way he is heading off", and `leave` sets its own before entering that state.

- [ ] **Step 5: Add the two new fields**

In `__init__`, beside `self._social_at = 0.0`, add:

```python
        self._social_until = 0.0
        self._cross_until = 0.0
```

- [ ] **Step 6: Add `_do_stomp`**

Add this directly below `_do_walk`:

```python
    def _do_stomp(self, now, dt):
        """Off, in a straight line, faster than he walks and not looking at
        anything. He does not get to doze off in a huff either - this falls
        through to an ordinary rest."""
        way = self._leave_way
        self.phase += STOMP_SPEED * dt / STEP_PX * math.pi
        x1, x2 = self._walls()
        self.x = _clamp(self.x + way * STOMP_SPEED * dt, x1, x2)
        self.facing = way * 0.62
        self.lean = way * 3.2
        self.face = FACES["cross"]
        self.look = (0.0, 0.0)
        self.hands = self.feet = None
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y()
        if now - self.since >= STOMP_S or self.x <= x1 or self.x >= x2:
            self._stir_at = now
            self._begin("rest", now)
```

- [ ] **Step 7: Hold the cooldown, and let the face decay**

In `sociable`, add the second clause:

```python
    def sociable(self, now):
        # Both a cooldown and having actually parted. A cooldown on its own
        # loops forever if they never move apart; parting on its own starts
        # again the moment they drift back together.
        return (self.scene is None
                and now >= self._social_until
                and now - self._social_at > CHAT_COOLDOWN)
```

And in `_idle`, directly after the blink block and before the method ends, add:

```python
        # The anger outlives the stomping off. Without this he is fine the
        # instant he stops walking, which reads as a bug rather than as a man
        # getting over it.
        if now < self._cross_until:
            weight = _clamp((self._cross_until - now) / CROSS_S, 0.0, 1.0)
            self.face = _face_mix(self.face, FACES["cross"], weight)
```

- [ ] **Step 8: Run it and watch it pass**

Run: `python test_app.py`
Expected: `ok  the one they laughed at storms off and stays cross`, and every check above still passing.

- [ ] **Step 9: Commit**

```bash
git add roamer.py test_app.py
git commit -m "feat: the mocked one storms off and stays cross for a while"
```

---

### Task 8: Interrupting a scene, and the documentation

The teardown matrix from the spec, plus the README. Folded together because the README paragraph is only truthful once the teardown behaves.

**Files:**
- Modify: `roamer.py` — the module docstring
- Modify: `README.md:270` area (the **Two of them** section)
- Test: `test_app.py`, after the stomping block

**Interfaces:**
- Consumes: everything from Tasks 3-7.
- Produces: no new interface. This task pins behaviour and documents it.

- [ ] **Step 1: Write the failing test**

Add this in `test_app.py` directly after `print("ok  the one they laughed at storms off and stays cross")`:

```python
        # lift the one they are laughing at and the scene comes apart cleanly
        rescued = roamer.Roamer(app, third, 0.0, floor)
        for k, one in enumerate(pair):
            one.x = right - 460.0 + k * roamer.CHAT_GAP
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
            one._social_until = 0.0
        crank(40)
        scene = a.scene
        rescued.state, rescued.floor, rescued.y = "rest", floor, floor
        rescued.vx = rescued.vy = 0.0
        rescued.scene = None
        rescued._until = time.monotonic() + 999.0
        rescued._social_at = 0.0
        rescued.x = scene.mid
        crank(3)
        assert rescued.mocked, "the setup has to have taken"
        rescued.pick_up()
        crank(2)
        assert rescued.scene is None, "he is out of it"
        assert scene not in roamer.scenes, "and it is over for the other two"
        assert all(one.state in ("rest", "walk") for one in pair), \
            [one.state for one in pair]

        # a three-way that loses one of them ends for the other two as well,
        # rather than carrying on as a two-way with the roles shuffled
        rescued.let_go()
        for k, one in enumerate(pair + [rescued]):
            one.x = right - 460.0 + k * roamer.CHAT_R * 0.6
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one.scene = None
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
            one._social_until = 0.0
        crank(5)
        big = rescued.scene
        assert big is not None and len(big.cast) == 3, "a cast of three"
        rescued.pick_up()
        crank(2)
        assert big not in roamer.scenes, "lifting one ends it for all of them"
        assert all(one.scene is None for one in pair), "nobody left in a scene"

        # and holding him over them gets the pair of them turning round
        for one in pair:
            one.state, one.floor, one.y = "rest", floor, floor
            one._until = time.monotonic() + 999.0
            one.facing = 0.9
        rescued.x = (pair[0].x + pair[1].x) / 2.0
        rescued.y = floor - roamer.STAND_H - 120.0
        crank(40, lambda: all(one.state == "wtf" for one in pair))
        assert all(one.state == "wtf" for one in pair), \
            ("both of them", [one.state for one in pair])
        rescued.vanish()
        for one in pair:
            one.vanish()
        print("ok  rescuing him ends it, and both of them get the look")
```

- [ ] **Step 2: Run it and see where it stands**

Run: `python test_app.py`
Expected: this may already pass — `pick_up` calls `_leave_scene`, which calls `_close`. If it passes, that is the correct outcome and the test is doing its job as a pin. If it fails, fix it in Step 3.

- [ ] **Step 3: Fix whatever the test caught**

The one case with a real hole: `_close` sends cast members to `walk` only `if guy.state != "chat": continue`, and a roamer who was just picked up is in state `held`, so he is skipped — correct. If the assertion that fails is `scene not in roamer.scenes`, check that `_leave_scene` calls `_close` **after** removing itself from the cast, so `_close` cannot put a held roamer back to walking.

If everything passes, make no code change and move to Step 4.

- [ ] **Step 4: Update the module docstring**

In `roamer.py`, in the bullet list at the top, replace the line

```
  * two of them on the floor together stop and hold a conversation entirely in
    gesture,
```

with

```
  * two or three of them on the floor together stop and hold a conversation
    entirely in gesture, one talking at a time and the rest watching him,
  * one who turns up to a conversation already running stands at the edge of
    it and is never once acknowledged,
  * one who walks into the middle of it is pointed at and laughed at, and
    stalks off with a face on him that takes a while to wear off,
```

- [ ] **Step 5: Update the README**

In `README.md`, at the end of the **Two of them** section (after the paragraph ending `...asks you what exactly you think you are doing.`), add:

```markdown
**Three of them.** Three on the floor at once and they talk as three: one at a
time, the other two turned to whoever is speaking, and the speaker working the
room - one of them for the first half of what he is saying and the other for
the second. It ends the way a two-way ends, and they go three different ways.

That is when all three are standing there as it starts. Turn up to one already
running and you are outside it. Hang back and you watch: you follow whoever is
talking, and neither of them looks at you once, and when it ends they walk off
in opposite directions and leave you standing in the middle of where it was.

Walk into the middle of it and they break off mid-sentence, turn round, point,
and laugh at you. You work out what is happening, stand there and take it, and
then stalk away - faster than you walk, in a straight line, not looking at
anything. The face stays on for a good while after you have stopped, and you
are not in the mood to talk to anybody for a long time after that.

Nobody holds a grudge. He is not avoiding those two in particular - there is no
memory between any of them anywhere - he has simply had enough of everyone.

Picking him up out of it is how you break it up. And if you hold him over the
two who were laughing, they both get the look.
```

- [ ] **Step 6: Run the whole suite one last time**

Run: `python test_app.py`
Expected: `all app checks passed`, with all five new `ok` lines printed.

- [ ] **Step 7: Commit**

```bash
git add roamer.py test_app.py README.md
git commit -m "feat: pin scene teardown and document three of them on the taskbar"
```

---

## After the plan

Two things the spec asks for that are deliberately **not** tasks here, because neither is code:

- **Re-measure the CPU figures.** `README.md` quotes 0.2-0.5% idle, 1.4-1.7% standing, 6-10% walking and a 4.8ms median animation frame. A `talk3` runs three figures at 16ms at once, so the busy end of that needs re-taking by hand before release. The numbers in the README are real measurements and should not be guessed at.
- **`MAX_ROAMERS` stays 3.** Everything above is written for N. Raising it is one constant plus a fresh set of measurements, and the first thing that will need building afterwards is separation between walkers — which this plan deliberately does not add, because walking into people is the mock trigger and at a cap of three there is nobody spare to walk through a scene.
