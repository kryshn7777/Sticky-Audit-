# Sticky

**Your notes, stuck to your desktop.** Real windows on coloured paper, in a
handwritten face, still there after a reboot - and a small crew who live on
them, wander off along the taskbar, and get up to things while you work.

Pure Python 3 and tkinter. **No dependencies, no build step, no network.**

---

## Install

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Desktop
```

Creates a Start Menu shortcut (and a Desktop one with `-Desktop`) pointing at
`pythonw.exe`, carrying the note icon and the app's AppUserModelID.

Then **pin it yourself**: Start → type *Sticky* → right-click → *Pin to
taskbar*. Windows has blocked apps from pinning themselves since Windows 10
1607; there is no honest way around it. Because the shortcut and the running
process share an AppUserModelID, the app's windows collapse into that one
pinned icon instead of appearing as a stray Python entry.

Clicking the pinned icon afterwards raises the existing overview window. It
never opens a second copy.

Remove everything with `install.ps1 -Uninstall` (your notes are left alone).

## Run without installing

```powershell
pythonw sticky.pyw
```

---

## Using it

| | |
|---|---|
| **New note** | *New note* in the overview. Pick the colour first with the five dots beside it. |
| **Move a note** | Press anywhere on it and drag. The strip along the top always drags, even mid-edit. |
| **Edit a note** | Double-click it. |
| **Finish** | *OK*, or click away. Nothing is ever lost by skipping it. |
| **Recolour** | The five dots on the edit toolbar, or right-click the note. |
| **Format text** | Select some text, then **B** / *I* / U on the toolbar, or `Ctrl+B` / `Ctrl+I` / `Ctrl+U`. With nothing selected it applies to the whole note. |
| **Font size** | `A-` / `A+` on the toolbar, or `Ctrl+-` / `Ctrl+=`. Per note, 8-24 pt. |
| **Delete** | *Move to Trash*, then *Undo* in the popup if you did not mean it. |
| **Checkbox** | *Checkbox* on the right-click menu, or `Ctrl+Shift+K`. Click the `[ ]` to tick it - no need to enter edit mode. |
| **Poke the mascot** | Click his face. Ten different reactions, taken in turn - and sometimes he has something to say. |
| **Pick him up** | Press his face and drag. He comes off the note, thrashing, and falls wherever you drop him. Drop him on any note and he takes hold of it there. |
| **Right-click him** | Once he is off the note: *Send him home*, or *Ask him to leave*. |
| **Pin to an app** | Drag the note so its top edge lands on another window's title bar. A paperclip snaps on while you are still holding the note; let go and it travels with that window from then on. Drag it away, or *Unpin*, to take it off. |
| **Right-click a note** | Edit, checkbox, colour, unpin, always-on-top, show mascot, *Sit with me*, *Earlier versions*, new note, Move to Trash. |
| **Capture anywhere** | `Ctrl+Alt+N` from any application drops a new note under the pointer, ready to type into. |
| **Go back a version** | *Earlier versions* on the right-click menu. The last six saves of that note are there, and putting one back is itself undoable. |
| **Sit with me** | *Sit with me (25 min)* on the right-click menu. He comes off the note, lights a fire under it, and sits there until it burns out. |
| **Resize by hand** | Drag the folded corner, or the right / bottom edge. That note stops auto-sizing from then on, and its content rewraps to the new shape. |

### Keyboard

| Key | |
|---|---|
| `Enter` in the heading | confirm it and drop into the content |
| `Shift+Enter` / `Enter` in the content | new line |
| `Esc` | cancel this edit and put the text back as it was |
| `Ctrl+Z` / `Ctrl+Y` | undo / redo |
| `Ctrl+S` | write to disk now (autosave already does this) |
| `Ctrl+B` / `Ctrl+I` / `Ctrl+U` | bold / italic / underline |
| `Ctrl+-` / `Ctrl+=` | smaller / larger text |
| `Ctrl+Shift+K` | turn this line (or every selected line) into a checkbox |
| `Ctrl+Alt+N` | new note under the pointer, from any application |
| `Tab` | heading → content → OK |

---

## Behaviour worth knowing

**Autosave.** Typing is written to disk 0.7 s after you stop. Moving,
resizing, recolouring, leaving a note, and pressing OK all flush immediately.
*OK* is a way to stop editing, not a way to save — there is nothing to lose by
never pressing it.

**Crash safety.** Every write goes to a temp file, is `fsync`'d, then swapped
in with `os.replace`, which is atomic on NTFS. A crash or a yanked power cord
leaves either the previous file or the new one, never a half-written one. The
exposure is the ≤0.7 s of typing since the last flush.

**Trash.** *Move to Trash* is reversible. Notes wait in the Trash tab until you
*Restore* or *Delete* them, and permanent deletion asks first. A note in the
bin takes its mascot with it: one you had dragged off it goes when it goes,
rather than being left stood on the taskbar with nothing behind him.

**Auto-sizing.** A note grows with what you write, up to 424 × 524 px, then the
content scrolls instead of the note taking over the screen. Resizing by hand
turns that off for that note and is bounded only by the screen — the ceiling
exists to stop growth you did not ask for, not to stop you. Either way the
content rewraps into the new shape.

**Paper.** A vignette darkens the edges the way a sheet does where it meets a
surface, with a sheen along the top-left and a folded bottom-right corner. The
shading stops inside the padding on purpose: Tk text widgets cannot be made
transparent, so anything drawn under them would show their rectangles as a
visible seam - which also means real paper texture is not possible here.

**No drop shadow.** Tk has no per-pixel alpha, and the dithered stand-in it
does have renders as a hard dark band down the right and bottom edges — a
black border, not a shadow. A clean sheet beats a fake shadow.

**Closing.** Closing the overview minimises it; your notes stay on the desktop.
*Quit* in the overview closes everything, and it all comes back next launch.
Tick *Start with Windows* to have it open at login.

**Always on top.** On by default, per the checkbox in the overview.

**Resources.** Measured on this machine with four notes open and the pointer
parked, over 30 s: ~30 MB working set, ~13 MB private, and **under 5 % of one
core**, the same figure with the mascot on as with it off. Almost all of that
is Windows repainting four borderless always-on-top windows; Python's own
share is about 1 %. There is no background thread and no polling loop except
the mascot's single shared timer, which backs off to 1.2 s the moment the
pointer stops.

Until recently that figure was 9 %, and the app rewrote `notes.json` — fsync
and all — about once a second while nobody was touching it. `<FocusOut>` fires
far more often than it looks like it should, because borderless top-level
windows hand focus back and forth between themselves, and every one of those
was a full save plus a rebuild of the overview. It now writes only when there
is actually something unsaved.

**Quick capture.** `Ctrl+Alt+N` anywhere in Windows drops a note under the
pointer with the caret already in it. The key itself costs no timer: a hotkey
registered against the thread never arrives, because Tcl's own notifier drains
that queue first (measured - posted by hand, one `update()`, gone), so Sticky
owns a message-only window and Windows dispatches the key to its procedure
through the loop the app is already running. That procedure sets a flag and
returns - building a note inside a Windows callback inside Tcl's pump takes
the process down with a GIL error - and the flag is read on the pointer
tracker's existing tick, which holds itself to 250 ms while anything is riding
on it. Turn it off in the overview; if another application already owns the
combination, the box goes back to off rather than lying to you.

**Earlier versions.** Every save keeps the text that was there before it, six
deep (`HISTORY_MAX`), in the same JSON you can open in Notepad. *Earlier
versions* on the right-click menu lists them with how long ago they were, and
putting one back is itself just another save - so the version you replaced is
one menu away too. Snapshots rather than diffs: a note is a few hundred bytes,
and a diff you cannot read in Notepad is a diff you cannot trust.

**Offline.** No sockets are opened, not even on loopback. Single-instance
detection uses a named mutex and `FindWindowW`, not a local port.

**Windows integration.** Per-monitor DPI v2, the overview follows the system
light/dark setting including its title bar, and Windows text scaling is
honoured. Data lives in `%APPDATA%\Sticky\notes.json`, not next to the
executable. It was called StickyNote before it was called Sticky, and anybody
who already had notes keeps reading and writing `%APPDATA%\StickyNote` where
they were written - a rename must not hand somebody an empty desk, and moving
the file is the one way it could.

**Handwriting.** Segoe Print: hand-lettered but upright and separated, so
notes still read at a glance. Ink Free and Segoe Script are scrawls at this
size; Segoe UI is not handwriting at all.

**Formatting.** Bold, italic and underline are stored as character ranges in
`marks`, and the bold-italic face is re-derived from the overlap on load, so
text marked both ways renders correctly instead of picking one at random.

**Colours.** The five standard sticky-note papers: yellow, green, pink,
purple, blue. Pick one before creating a note (the dots in the overview), or
change it later from the edit toolbar or the right-click menu.

**Accessibility.** Every paper clears WCAG AA on its ink: yellow 10.44:1,
blue 9.97:1, green 9.92:1, pink 9.31:1, purple 8.57:1 (AA needs 4.5:1).
`test_store.py` fails the build if a new colour drops below that. Everything is
reachable from the keyboard.

---

**The mascot.** A box man holds up every note: a square face with arms and
legs coming straight out of it and shoes on the end - no body, no neck. He
takes one of four poses, picked from the note's own id so a deskful of notes
is not a row of identical figures: on his feet at the bottom-left corner,
leaning out from behind the left edge with one hand hooked round it, sitting
on the top edge propped on one arm with his feet swinging down the front, or
hanging off the bottom one by both hands. In each of them a slice of him goes
behind the paper and his hands close over the edge in front of it, which is
what makes him look like he is holding the note rather than printed on it. Whichever it is, the window only grows on the side
he needs, and the sheet itself never moves. His eyes follow your pointer anywhere on
the desktop, and go wide with a white catchlight when you come near. If a note
has checkboxes you have not ticked, he will occasionally say so - roughly once
a quarter of an hour, never twice about the same note inside fifteen minutes,
and never while you are editing or already looking at it. Right-click any note
and untick *Show mascot* to switch him off everywhere.

**Ticking the last one.** Finish a list - the last empty box on a note goes
from `[ ]` to `[x]` - and he hops, grins and says something about it, and
anybody out on the taskbar within `APPLAUD_R` of that note leaves whatever
they were doing, comes over, and makes a fuss with both hands over his head
before going back to it. The man who came off that note joins in from wherever
he is, because it is his note. It takes two counts rather than one question:
there has to have been something left to do, there has to be nothing left now,
and one more box has to be ticked than was before - without that last part,
deleting the only line you had not done would read as having done it.

He is not only furniture, either. Press his face and drag, and he comes off
the note altogether - see **Picking him up**, below. Nobody guesses that, so on
the very first run - once, ever, and then never again on that machine - he says
so himself.

**Pinning a note to an app.** Drag a note so its own top edge lands on another
application's title bar and it clips itself there: a paperclip snaps onto the
edge while you are still holding the note, so you can see it is going to
attach before you let go. From then on the note moves with that window, hides
when the window is minimised, and comes back when it does. Running a
spreadsheet you keep notes about? Lay the note on its title bar and the two
travel together. Drag the note anywhere else to take the clip off, or use
*Unpin* on the right-click menu.

What decides this is the note's own top edge, not where the pointer happens to
be. Testing the pointer pins to whatever is under your hand, which - when you
drag a note by its middle, as everybody does - is the application's contents,
or some unrelated window a hundred pixels further down. What you lined up is
the note, so the note is what is asked about.

If the note's mascot happens to be the one sitting on the top edge, he drops
down and hangs off the bottom instead - the title bar is now where he was
sitting, and he would be behind it. He climbs back up when you unpin.

What is remembered is the title on the bar and where the note sat on that
window, not a window handle, because handles do not survive a restart. So a
pinned note finds its window again next time you open both, and simply sits
where it is if that application is not running. Closing the pinned-to app
takes the clip off and leaves the note exactly where it was: a note that
disappeared with somebody else's window would look like data loss.

Following a window costs one `GetWindowRect` per tick on the timer the mascot
already owns, and only while something is actually pinned - the tracker takes
the faster of the two rates, so a window being dragged is kept up with every
frame and a still one every 250 ms. A frame is what it takes: at 40 ms the
note trailed a moving window by a visible hand's breadth before catching up,
which reads as a note following a window rather than one attached to it. With
nothing pinned it is one comparison against an empty list.

He is drawn onto the note's own canvas, underneath the paper, which is why the
sheet clips his arm. The few parts that belong in front - legs kicking down
the face of the sheet, fingers curled over an edge - are drawn after it.
Switching him on and off never changes how much room you have to write in: the
note's stored size is the sheet, and the window grows around it.

**Tapping him.** Click his face and he reacts: he hops, waves, winks, rocks
back with an exclamation over his head, goes dizzy, spins on the spot, nods,
shakes, squishes or floats. The ten go in turn, so poking him twice never
looks the same twice, and about a third of the time he says something as well.
Keep poking - four times inside five seconds - and he stops being amused about
it. The cursor turns to a hand over his face so the tap is findable at all.

A press that never moves is a tap. A press that *does* move picks him up off
the note instead - his face is his handle. The note still drags from anywhere
else on the paper and from the strip along the top, which is what those are
for; dragging his face used to move the note, and now moves him.

**Picking him up.** Press his face and drag and he peels off the note into a
window of his own. From that moment he is a character rather than a decoration
on a sheet of paper. Six of them can be out at once (`MAX_ROAMERS`), which is
a cap on windows rather than on the crowd - each of them needs a full-screen
layered window of his own, while the crowd itself handles any number by
breaking into groups. Drag the seventh and the drag moves his note instead,
because a drag that does nothing at all reads as the note being broken.

Take hold of him and he is yanked up off the floor first: for `GRAB_S` he is
stretched along the pull with his arms and legs trailing under him and a face
that has not caught up, and only then does the thrashing start. After that he
does not enjoy it: eyes screwed shut, mouth open, arms thrown up and down
against each other, legs kicking, the whole of him shuddering - and turned
towards the note he came from the entire time, leaning after it. A child being
carried out of a room.

He also trails the hand. How fast you are moving is measured off the same few
frames the throw is measured from, smoothed, and fed into his lean, so he hangs
back the way he came and swings past the hand when it stops. Without it he is
the same pose whether he is carried gently across the desk or swung about,
which is the one thing a dragged body must not look like.

**Poking him.** Click without dragging - inside `TAP_S`, and having gone
nowhere - and he is not thrown anywhere at all. He hops where he stands and
gives you a look (`STARTLE_S`) that wears off the way the fright after the hut
does. A click that flung him across the screen made him feel like a physics
object; this makes him feel like somebody who was standing there.

Let go and he falls, with weight. A flick throws him and sets him spinning;
letting go still drops him straight down. He bounces once - twice reads as a
ball rather than a person - flattens on the landing, springs back past his own
height, and picks himself up. The floor is the top of the taskbar, which is
the bottom of the monitor's work area, so it is right for a bar docked to
either side, hidden, or on a second screen with a bar of its own.

Then he goes for a walk along it: a stretch, a stop to look around, another
stretch. His eyes follow your pointer while he stands there. Leave him alone
for two minutes and he dozes off, until the pointer comes near him again.

**Something full-screen.** A video, a game, a slide deck, somebody's shared
window: whatever is in front covers its whole monitor, and the crew clears off
the bar rather than sitting on top of it. They walk off the nearer edge, their
windows go away, the ball and the hut go with them, and when it is over they
walk back in to where they were standing. The whole monitor rather than the
work area, deliberately - a maximised window stops at the top of the taskbar,
and a maximised window is somebody working rather than somebody presenting.
Asked twice a second (`SHY_EVERY`) off the tick the crew is already running,
because it is one `GetForegroundWindow` and one `GetWindowRect` for a thing
that changes about once an hour.

**Standing about.** A stop is not a freeze. Every few seconds of standing
still (`IDLE_EVERY`) he does one of four things with the two seconds he has:
both arms up in a stretch that takes him off his heels, a yawn behind one hand
with his eyes shut, a scratch at the side of his head, or a look either way
along the bar. They are solved against the same two-bone arms everything else
uses rather than keyframed, which is why each one is four lines. An idle also
buys him the full frame rate for as long as it runs and not a tick longer -
standing about is otherwise 200 ms a frame, which is plenty for a blink and
nowhere near enough for an arm going over his head. He finishes what he is
doing before he walks off anywhere.

**Holding on to a note.** Drop him on a sheet, or beside one, and he takes
hold of it *where you dropped him*. Nothing snaps to a spot of its own: by the
middle of an edge he holds the middle, by a corner he holds the corner, and
anywhere on the paper at all he takes the nearest edge to that rather than
falling straight through it. Which edge decides what he does with it - he
hangs by both hands off the bottom, holds on at the left or the right with his
body outside the sheet, and *stands* on the top one.

He stands on the top edge rather than hanging from it because hanging there
would put his whole body down the face of the sheet and across the writing,
which is the one thing he has never been allowed to do. Standing on it puts
him above the paper, exactly where one of his poses on the note already sits.

He does not snap into the pose either. He leans over, steps in, and reaches -
both arms solved from the shoulder, so the elbows bend where elbows bend, and
if the edge is further than his arms go he strains for it and you can see him
not quite make it.

He holds on for as long as the note is there. Drag the note and he goes with
it - he keeps hold of the same point on that edge, not the same point on the
screen - and the shove sets him swinging on a damped pendulum until he
settles, or staggering and catching his balance if he is stood on the top.
Close the note, or minimise the window it is pinned to, and he is left holding
nothing and falls.

**Two of them.** Put a second one on the taskbar and they will find each other
and hold a conversation - closing to arm's length, a raised hand, one talking
with his mouth moving and a hand going while the other nods along, a laugh,
roles swapped, a nod from both, and away. There is no dialogue and no bubbles:
it is carried entirely by where they are facing and where they are looking,
which are recomputed every frame from where the other one's head actually is.
Then they leave in opposite directions, and will not start again for a good
while - both a cooldown and having actually parted, because a cooldown alone
loops forever if they never move apart.

Pick one of them up and hold him over the other, and the one left behind stops
whatever he was doing, turns square to the front, drops his eyes off your
pointer, throws both hands out and asks you what exactly you think you are
doing. Hold him over two of them and both of them ask.

**They go and find each other.** A walk used to be a random stretch off
wherever he happened to be standing, which is fine for one of them and useless
for three: on a thousand pixels of taskbar they drift apart on the first walk
and never come back within talking distance again. Dropped a screen apart and
left alone for two minutes, nothing below this line ever once happened. So most
walks are now aimed at somebody. Drop three of them anywhere along the bar and
the first conversation starts within about ten seconds.

One who has just been laughed at is the exception - he wants nothing to do with
anybody until the face has worn off, and walks off on his own until it has.

**What his hands do while he talks.** One gesture a sentence, settled on
the frame the sentence begins and held for the whole of it: he waves, lays it
out with both hands, counts it off, chops at it, points at whoever he is
talking to, or shrugs. Each is a point the arm is solved to rather than a set
of keyframes, which is why a sixth one is four lines. Chosen once per beat and
kept on the scene rather than on him, so the listeners are watching the hand he
is actually making - picked per frame it strobes, and picked once per
conversation he makes the same shape three times running.

**Three of them, or four.** Three on the floor at once and they talk as three:
one at a time, the others turned to whoever is speaking, and the speaker
working the room - one of them for the first half of what he is saying and
another for the second. It ends the way a two-way ends, and they go their
separate ways. Four together is the same scene off a longer table (`TALK4`),
and `MAX_CAST` is the ceiling: past four they are a row rather than a group,
the two on the ends are too far apart to be looking at each other, and the
last of them waits half a minute for a turn. A fifth stood nearby watches.

That is when all of them are standing there as it starts. Turn up to one already
running and you are outside it, and where you stop decides what happens next.

Hang back and you watch. You follow whoever is talking, neither of them looks
at you once, and when it ends they walk off in opposite directions and leave
you standing in the middle of where it was.

Some of them cannot leave it there. A conversation is over in about four
seconds and the edge of earshot is a five second walk, so anybody who stops out
there is stuck watching whether he likes it or not - unless he closes the last
of the gap himself. The nosy sort does: he sidles in, slower than he walks,
until he is close enough to be noticed. And then he is noticed.

Walk into the middle of it and they break off mid-sentence, turn round, point,
and laugh at you. You work out what is happening, stand there and take it, and
then stalk away - faster than you walk, in a straight line, not looking at
anything. The face stays on for a good while after you have stopped, and you
are not in the mood to talk to anybody for a long time after that.

Nobody holds a grudge. He is not avoiding those two in particular - nothing in
the crew remembers anybody - he has simply had enough of everyone.

There are three ways to end up in the middle: you put him there, he walks
straight into them, or he watches from the edge and cannot help himself. And
picking him up out of it is how you break it up - so if you hold him over the
two who were laughing, they both get the look.

Which of the three you get is down to who is free to talk when. They do not all
come off a conversation at the same moment - one of them is held back, some of
the time - and that is the whole supply of odd ones out. Everybody free at once
is a three-way; somebody still cooling off is a pair with an audience.

**Personal space.** Nobody stands inside anybody. Two of them closer than
`SPACE_R` on the same floor shuffle apart by `SPACE_PUSH` a frame - half each
when both are standing about, all of it from whichever one is. A man on his way
somewhere is never shoved off his line: he makes the other one make room and
carries on. Both of them giving way deadlocks an errand, because two of them
walking the wood home from the same edge have to pass each other, and every
shove moved the man in front further along until the one behind had chased him
the length of the bar. It is one pass over the crew before they draw, for the
same reason the pairing is decided in one place: each of them backing off on
his own turns a crowd into everybody stepping into the space somebody else has
just left.

**Excusing yourself.** About a third of conversations with three or more in
them (`BOW_ODDS`)
are one of them leaving early. He waits for a gap rather than cutting anybody
off - it fires on the frame the second speaker begins, and never on the man
about to speak, because talking over somebody is what the mocking is for and
this is meant to be the opposite of it. He waves, says bye, turns and goes,
and the two left switch to a shorter table and take it to a close. Their roles
are re-indexed as he goes, or the line the table asks the second of them for
lands on nobody and they stand there in silence. Where they are standing is
deliberately not recalculated: they have not moved, and the only beat that
solves a position against the middle of a conversation is the walking-in one,
which the farewell does not have.

**Football.** A quarter of the time (`FOOTY_ODDS`) what they have met up to do
is kick a ball about. There are no sides, no goals and no score. Whoever is
nearest the ball is whoever chases it, worked out from distance every frame
rather than appointed at the start, so possession turns over the instant
somebody else is closer - and two of them converging on a loose ball is the
whole game. He boots it at one of the others rather than at nowhere, and only
while it is coming down: allowed to kick it on the way up he re-boots the same
ball four frames running and it leaves the screen. The four odds are one roll
cut four ways rather than a roll each, because chaining independent odds makes
whatever is last on the list far rarer than its number reads.

**A fire, and an evening.** A fifth of the time (`FIRE_ODDS`), if there are
three or more of them and nothing already burning, they light a campfire. They
walk to a place round it - sides alternating, so three of them read as a ring
rather than as a queue, and handed out left to right so nobody crosses the
flame to reach one - sit down into it, and talk across it while it burns: hips
on the floor, feet out in front, the two-bone legs folding into the sit rather
than shrinking into it. Then it goes out. They watch it go (`dim`), get up,
all of them wave and say bye, and they walk off in different directions. The
fire is lit with exactly as long in it as the table takes to reach the beat
they stand up on, so it dies under them rather than at some time of its own -
retiming a beat cannot leave them sat in the dark or walking away from a fire
still going. The flame itself is two polygons whose outline moves on two
waves that never come back into step, and the last `EMBER_S` of it is a glow
going down rather than a flame going out in one frame.

**Sit with me.** *Sit with me (25 min)* on a note's right-click menu, and
whoever belongs to that note comes off the paper, walks underneath it, lights a
fire and sits down by it. The fire is the timer: no countdown, no bar, no
notification - you glance at the taskbar and see how much of it is left. When
it burns out he stands up, waves, and goes back to the note. Right-click the
fire for *Put it out* and the same ending happens early.

That fire needed the yard to be told the time as well as the frame. Everything
down there is stepped with the crew's own `dt`, which is clamped by `MAX_STEP`
so a stalled event loop cannot teleport anybody - and a man sitting still ticks
five times a second, so twenty-five minutes of fire burned on clamped frames
would have taken a hundred. `step` takes both now: the frame for the physics,
the real gap for anything with a life on it.

**Wood, and a hut.** A fifth of the time (`BUILD_ODDS`), if there are three or
more of them and nothing built yet, they agree on a hut instead. Each trots off to the
nearer edge of the screen and keeps going until he is out of it - he is not
hidden and nothing is switched off, he has simply walked past the end of his
own window, which is the size of the screen and does not follow him. A moment
later he is back with a plank held out in front of him, and when the last of
them is home the hut goes up between them and they file in through the door -
and so does anybody else left standing on that floor with nothing on, wood or
no wood. One of them outside a hut everybody else is in reads as having been
forgotten. `FETCH_SPEED` is the knob if the errand drags on a very wide screen, and
`FETCH_MAX_S` is the give-up: a man who has been out there a minute has had
something go wrong with the floor and comes to his senses rather than standing
off the edge for ever. The scene stays on him for the whole errand, so a hand
closing on any one of them still tears the build down the way it breaks up
a conversation - and whoever comes home with the wood to find nobody there puts
it down and goes back to what he was doing. Indoors he is a withdrawn window
with a time on it, ticking at the dozing rate and drawing nothing.

**Knocking it down.** Right-click the hut and it asks first: *Knock it down*
or *Leave it standing*. It used to go on the click itself, and it is the one
thing down there that cannot be undone - they spend the best part of a minute
walking off the screen for the wood - so a right-click that pulled it over with
no warning was a right-click nobody dared use twice. What it leaves is a wreck:
`WRECK_N` planks lying where it stood, each with its own few seconds on it
(`WRECK_S`), shrinking away over the last third of that rather than fading,
because the window is keyed transparent and there is no background to fade
into. Everybody who was inside comes out where it stood, and so does anybody within
`WATCH_R` on the same floor who was near enough to have watched it happen -
which is the difference between a hut falling over and a hut being kicked in.
They run back and forth for `PANIC_S` rather than off: away is a stomp, and he
does that when he has been laughed at. The face wears off over `PANIC_FACE_S`
after the running stops, for the same reason the anger does - somebody
perfectly calm the instant he stops running reads as a bug.

**The yard.** The ball and the hut share one window between them, keyed
transparent and covering the whole screen, exactly like a roamer's and for the
same two reasons: a window that follows a moving prop judders, and the keyed
colour is click-through, so the right-click that takes the hut down is the only
click that window ever takes. Nothing in `yard.py` knows what a roamer is - the
one thing it has to say, that somebody has just knocked the hut down, it says
through a callback the crew registers on the way past, which keeps the import
one way and the physics checkable without a display. One yard, on one screen:
start a kickabout on a second monitor and the ball turns up on the first. A
yard per screen is the fix, and it is not worth it until somebody notices.

**Getting him back.** Right-click him and choose *Send him home*, or use
*Send him home* on that note's own right-click menu. Dropping him on his own
note does not do it - his own note is just another note to hold on to, and
being put down on it somewhere he was not asked to stand would be exactly the
snapping the rest of this avoids. He goes home by himself
when the app closes and when the mascot is switched off, and nobody is out
there after a restart. There is also *Ask him to leave*, which is the one that
does not bring him back - he crouches, jumps off the bar, waves on the way
past, and that is the last you see of him.

The note he came from does not change size or move a pixel while he is away.
The room his pose needs is left in place: taking it back would reflow the
writing and pull the sheet out from under the hand that is dragging him.

**Idle life.** Between all that he blinks, glances somewhere new while his
eyes are shut, sways gently while your pointer is near him, and now and then
stretches instead of blinking. None of it owns a timer while it waits: being
due for a blink is one float comparison per note, made on a tick the shared
pointer timer was taking anyway. He also perks up when you start writing, at
most once every few seconds, so it never becomes a twitch while you type.

**Changing colour.** He walks round to the bottom-right corner - the one the
note already draws as curled up off the pad, because that is the corner the
sheet itself says is loose - turns his back to you to face the note, takes
hold of it, and walks the fold across to the far side. The page he is pushing
is drawn as a real fold: a straight crease with the light along it, and a
loose edge that bows out, because paper does not fold flat. Behind the crease
is the new colour, with the writing already on it - the same words in the new
ink, arriving with the crease. What is left of the old sheet keeps showing
them in the old ink, and the fold itself covers the band in between, so the
words are on screen the whole way across rather than vanishing and reappearing
at the end. He changes colour with them, over the same crossing, because he is
standing on the side of the crease that has already turned.

When the fold has crossed the whole sheet the note underneath is repainted,
and that is the only moment it could be seen; then he lets go and the page
drops back under its own weight. About two seconds, and clicking anything ends
it on the spot.

The weight is in the easing rather than the drawing. He sinks before he sets
off, leans forward while he is speeding up and back while he is slowing down,
drops onto each footfall, leans against the page the whole time he is pushing
it, and wobbles once when he gets back to his post. The fold falls faster the
longer it has been falling. His route goes round the note rather than over it
- along the top and down the side from the top edge, down to the floor and
along the bottom from anywhere else - so he never walks across the writing,
and `test_app.py` checks that for all four poses.

The crease is upright and travels with him. A diagonal corner-to-corner fold
is the prettier crease, but the corner you are holding ends up right across
the note from where you are standing, and his arm becomes a washing line.

The animation is cosmetic and nothing waits for it. The new colour is stored
and on disk before the first frame is drawn, so an interrupted flip - clicking
straight through the swatches, closing the note, clicking the note itself -
can never lose the colour you picked. It runs on its own transparent window
above the note, because Tk text widgets are opaque and sit above the note's
canvas: nothing drawn on that canvas could pass over the writing. That window
is also bigger than the note, because the walk goes outside it.

**What the mascot costs.** One shared timer for the whole application - not
one per note - and no thread. While the pointer is parked it reads the pointer
once and returns without touching a canvas, so a 30 s idle measurement with
four notes open comes out the same with him on as with him off - the two
readings sit either side of each other run to run, which is what measurement
noise looks like. He is followed at 200 ms
while the pointer is moving anywhere on screen and 100 ms once it is near a
note, and moving onto a note wakes him through Tk's own `<Motion>` event
rather than a faster poll. The alternative - a low-level Windows mouse hook -
would run our callback on every mouse move system-wide, which is strictly more
work than one `GetCursorPos` a second.

Off the note he costs a second timer, and only then: with nobody picked up
there is no timer at all, `roamer.crew` is empty, and `test_app.py` asserts
both. One timer serves however many are out there - not one each - and it runs
at the slowest rate any of them needs: 500 ms asleep, 200 ms standing about,
60 ms hanging off a note, and a frame every 16 ms only while something is
actually moving. `MAX_ROAMERS` is the ceiling on how many are out at once.

Measured over 15 s of a real event loop with two notes open, reading the
process own CPU time either side: nobody out there, 0.2-0.5% of one core -
the same reading as with the mascot switched off entirely. One of him stood on
the taskbar, 1.4-1.7%. One of him actually walking, at 60 fps, 6-10%, because
every frame is thirty-odd canvas items torn down and rebuilt through Tcl.
Patrolling - what he really does, a stretch and then a few seconds standing -
lands between the two. Standing still with the pointer still, he redraws
nothing at all: the pose is compared against the last one first, the same way
an unmoved pointer costs the mascot on the note nothing.

His overlay does not follow him. It is the size of the screen he is on and it
stays there, because a window that tracks him has to be moved, and moving a
layered top-level window does not take effect until the event loop runs
again - while the canvas inside it is redrawn against its new origin at once.
A move and a repaint in the same frame therefore composite the figure at its
new offset in a window still standing at the old place, and he flicks across
the screen and back. At walking pace that was one move a second. Thrown, it
was a move every other frame, and the whole throw juddered. A screen-sized
canvas costs nothing extra per frame - Tk repaints what changed, not the area
it could have changed in - and measured, it comes out cheaper than the move it
replaced. `test_app.py` throws him and asserts the window never moved.

## Files

| | |
|---|---|
| `sticky.pyw` | entry point: DPI, app identity, single instance, wiring |
| `note.py` | the note window — paper, drag, edit, autosize, checkboxes, undo toast |
| `mascot.py` | the box man, his poses, the colour flip, the pointer tracker, the speech bubble |
| `roamer.py` | the same box man off the note: his own window, the physics, and what he does out there |
| `yard.py` | the ball and the hut they build: one shared overlay, and no idea what a roamer is |
| `board.py` | overview, Trash, settings |
| `store.py` | atomic JSON persistence and the palette |
| `winkit.py` | the Windows calls tkinter does not expose |
| `install.ps1` | shortcut installer / uninstaller |
| `make_icon.py` | build-time icon and Store tile generation (needs Pillow; the app does not) |
| `test_store.py`, `test_app.py` | checks — see below |

## Tests

```powershell
python test_store.py   # persistence, trash, corruption recovery, contrast
python test_app.py     # the real app: windows, typing, drag, restart
```

`test_app.py` drives actual widgets through a real event loop against a
throwaway `%APPDATA%`, so windows will flash on screen for a second. It covers
first-run, autosave-without-OK, `Enter` in the heading, `Esc` cancelling,
undo, grow-then-scroll, click-is-not-a-drag, colour persistence, trash with
Undo, multiple independent notes, closing the overview, and a full restart.
It also covers the mascot: that all four poses draw and none of them moves
or resizes the sheet, that a colour change reaches disk without waiting for
the wipe and leaves no timer behind, that tapping him gives a different
reaction each time and always puts him back where he was while a drag from
his face picks *him* up and leaves the sheet where it was, that his eyes aim
at a pointer far off the note,
that a parked pointer does not make them snap back, that an unmoved pointer
costs no canvas work at all, that switching him off gives the window space
back without moving the sheet, and that checkboxes tick by click and persist
as ordinary text.

Off the note it covers the arm - that it bends both ways and stops at its own
length, while the colour flip's older one-armed call still reaches all the way
to the crease - and then him: that he falls and lands on the taskbar, takes
hold of a second note and travels with it and drops when it goes away, that
two of them hold one conversation and not a loop of them, that lifting one
over the other turns the other square to the front, and that sending everybody
home leaves no timer running and an unmoved pointer still costs nothing. The
physics is stepped at a pinned rate so it repeats exactly; how any of it
actually looks is not something an assertion can tell you, and has to be
watched.

## Data format

```json
{
  "version": 1,
  "notes": [{ "id": "...", "color": "yellow", "x": 140, "y": 140,
              "w": 292, "h": 272, "heading": "", "body": "",
              "topmost": true, "auto_size": true,
              "created": 0, "updated": 0 }],
  "trash": [],
  "settings": { "always_on_top": true, "run_at_startup": false,
                "mascot": true }
}
```

`x`/`y`/`w`/`h` are the sheet you can see. With the mascot on the window
is a little larger than that, and the extra area is transparent.

Plain JSON — copy the file to back it up, copy it back to restore. If it ever
becomes unreadable the app renames it to `notes.json.corrupt-<timestamp>` and
starts fresh rather than deleting anything.

## Not built

Windows toast notifications. Nothing here has a deadline to announce yet;
they become worth adding the day notes get reminders.
