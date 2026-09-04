"""Sticky - the little box man holding up the note.

He is a square face with arms and legs and nothing in between - no body, no
neck - and a pair of shoes. Every note gets one of four poses, picked from the
note's own id so a deskful of notes is not a row of identical figures: on his
feet at the bottom-left corner, peering round the left edge, sitting on the
top edge, or hanging off the bottom one by both hands.

He is drawn straight onto the note's own canvas, underneath the paper, so the
sheet clips whatever he has behind it and he reads as holding the note rather
than being printed on it. The few parts that belong in front - legs kicking
down the face of the sheet, fingers curled over an edge - are drawn after the
paper, by draw_front.

What he does:

  * his eyes follow the pointer anywhere on the desktop,
  * they go wide and bright, and he smiles, when you come near,
  * he blinks, glances about and stretches while nothing is happening,
  * he perks up when you start writing,
  * poke him and he reacts - a different one each time, and he has something
    to say if you keep poking,
  * change the colour and he walks round to the corner the sheet is already
    curled at, turns his back on you to face the note, and walks the fold
    across it by hand.

Cost
----
There is no animation loop and no thread. A single shared PointerTracker owns
one Tk timer for the whole application - not one per note - and it does the
cheapest thing available at every step:

  * When no note is on screen it ticks at 1.5s and does nothing else.
  * When the pointer has not moved since the last tick it returns immediately,
    without touching a canvas, and backs the poll off to 1.2s. A parked
    pointer is what a machine does most of the day, so that is the path that
    decides what the mascot actually costs.
  * A moving pointer is followed anywhere on the desktop, at 200ms, and at
    100ms once it is near a note. A parked pointer is not re-read at all -
    the eyes simply hold the aim they already have.
  * Moving the pointer over a note wakes the tracker through Tk's own <Motion>
    event, so tracking is crisp exactly where it is visible and lazy elsewhere.
  * Updating the eyes moves existing canvas ovals. Nothing is recreated, and
    nothing happens at all unless the pupil actually lands somewhere new.
  * Idle life owns no timer while it waits. Being due for a blink is one float
    compare per note on a tick the tracker was making anyway, and only an
    actual blink touches Tk at all.
  * A note clipped to another window is the one thing that raises the rate,
    and only while it is clipped: following a window that is being dragged
    needs about 40ms, so the tracker takes the faster of the two rates. With
    nothing pinned this costs a single comparison against an empty list.

Everything else - reactions, the colour flip, the walk - is a fixed handful of
frames started by something you did, and it cancels its own timer at the end.

A low-level Windows mouse hook was the alternative. It would run our callback
on every mouse move system-wide, on the UI thread - strictly more work than
one GetCursorPos a second - so polling is genuinely the lighter choice here,
not the lazier one.
"""

import collections
import math
import random
import time
import tkinter as tk

from store import blend, shade

# Room the figure needs outside the sheet. He stands beside the bottom-left
# corner, so the note only grows to the left and a little underneath; the top
# and right edges are untouched. The extra area is chroma-keyed away, which
# leaves it transparent and lets clicks pass through to the desktop.
SIDE, BOTTOM = 58, 18
ABOVE = 42            # room over the sheet when he is sitting on the top edge
BELOW = 70            # room under it when he is hanging from the bottom one

# He has no body. The square face is the whole of him: the arms come out of
# its sides and the legs out of its bottom edge, and there are shoes on the
# end of the legs.
HEAD = 30             # the face, and therefore the character
LEG_H = 18            # face to the ground
SHOE_H = 7            # how tall a shoe stands
GROUND_DROP = 8       # how far the shoes fall below the bottom of the sheet
STAND_H = HEAD + LEG_H
# Bone lengths, for the arms and legs that are solved rather than drawn. They
# are shorter than they look: an arm that can reach anywhere never has to bend,
# and the bend is the whole point of solving it.
UPPER_ARM = 8.5
FOREARM = 9.0
THIGH = 10.0
SHIN = 9.0

# Where he holds on, and how much room outside the sheet that needs. Notes get
# one each, so a desk full of notes is not a row of identical figures.
POSES = ("stand", "side", "top", "hang")
POSE_MARGINS = {
    "stand": (SIDE, 0, 0, BOTTOM),     # on his feet at the bottom-left corner
    "side":  (SIDE, 0, 0, 0),          # peering round the left edge
    "top":   (0, ABOVE, 0, 0),         # sitting on the top edge
    "hang":  (0, 0, 0, BELOW),         # hanging off the bottom one
}
# Changing colour: he walks to the corner that is already curled up off the
# pad, takes hold of it, and peels the sheet over. Every pose flips at that
# same corner, because that is the one the note itself says is loose.
FLIP_MS = 16          # ~60 frames a second: anything slower reads as steps
WALK_PX = 5.0         # pixels of ground per frame - his speed, not his timing
STEP_PX = 16.0        # ground covered per half stride, so his feet do not skid
BOB_PX = 2.7          # how far he sinks onto each footfall
LEAN_PX = 5.2         # how far his head runs ahead of his feet under way
WALKED = 0.62         # how far he is turned while walking: a three-quarter view
TURNED = 0.95         # ...and while working on the note: very nearly profile
DRAG_PX = 5.8         # ...and while hauling the page over, which is slower
FOLD_BANDS = 10       # steps in the light along the crease
FOLD_LIGHT = 34.0     # how far that light reaches out across the page
FOLD_BOW = 9.0        # how far the folded edge bulges: paper does not fold flat
FLIP_PAD = (86, 96)   # room to the right of and below the note for the walk

EYE_DX = 6.5          # eye spacing either side of the face's centre
EYE_R = 2.8           # resting eye
EYE_R_WIDE = 5.0      # delighted eye
GLINT_R = 1.8         # the white catchlight that appears with it
PUPIL_TRAVEL = 4.0    # furthest an eye ever slides from its resting spot
LOOK_RANGE = 150.0    # past this the eyes are fully over; only the angle moves

NEAR = 110            # within this of the sheet, his eyes light up
NEAR_OUT = 160        # and settle only out here, so they cannot flicker
GROW_STEPS = 3
GROW_MS = 60

# Tapping him. Ten reactions, taken in turn, so the second poke is never the
# same as the first. Each is a fixed handful of frames and then it is over.
REACTIONS = ("hop", "wave", "wink", "wobble", "dizzy", "spin", "nod", "shake", "squish", "float")
REACT_FRAMES = 18     # more, shorter frames: 26ms a frame reads as steps
REACT_MS = 16
HOP = 11              # how high he jumps
SHAKE = 4             # how far he rocks when startled
TAP_PAD = 5           # slack around his face, so he is easy to hit
TAP_CHANCE = 0.34     # how often a poke also gets a word out of him
TAP_LINES = ("Hi!", "Oof.", "Boop.", "Do that again.", "Careful, I'm holding this.")

# Poke him over and over and he stops being amused about it.
PEST_TAPS = 4         # taps...
PEST_WINDOW = 5.0     # ...inside this many seconds
PEST_LINES = ("Alright, ALRIGHT.", "I am holding a note here.",
              "You are enjoying this.", "Okay, that's enough.")

# Idle life. None of this owns a timer of its own while it waits: the shared
# PointerTracker is already ticking, so being due for a blink is one float
# compare per note per tick, and only an actual blink touches Tk at all.
BLINK_EVERY = (3.5, 9.0)   # seconds between blinks, randomised per note
BLINK_MS = 28
BLINK_FRAMES = 6           # closing, shut, shut, opening, open, open
GLANCE_CHANCE = 0.30       # a blink that also moves his eyes somewhere new
GLANCE_REACH = 0.7         # ...by this much of the full travel
IDLE_STIR = 0.12           # a blink that turns into a stretch instead
IDLE_STIRS = ("nod", "squish", "float")   # quiet ones only: nothing pops up
SWAY = 1.6                 # how far he rocks while you are near him
SWAY_HZ = 1.1
PERK_MS = 20
PERK_FRAMES = 8
PERK_GAP = 3.0             # seconds between perking up at your typing

# Checkboxes are stored as plain text, not as a private mark type: a note is
# still a note when you open notes.json in Notepad, and "[ ]" renders in every
# font on every machine, which a checkbox glyph does not.
BOX_OPEN = "[ ] "
BOX_DONE = "[x] "
BOX_PREFIXES = (BOX_OPEN, BOX_DONE, "[X] ")

# The one thing about him nobody guesses: he comes off the note. Said once,
# on the first run, and never again on that machine.
HELLO_LINE = "Psst - drag me off the note."

# ...and what he says when the last of them is finally ticked.
DONE_LINES = (
    "That's the lot!",
    "All of them. Look at that.",
    "Nothing left on this one.",
    "Done. Every box.",
)

LINES = (
    "Hey, are you forgetting me?",
    "Those boxes are still empty...",
    "Psst. One box. Just one?",
    "Still here. Still unticked.",
)


def pose_for(note_id):
    """Pick a pose from the note's own id.

    Deriving it costs nothing to store, survives restarts for free, and gives
    every note a different figure without a schema field to migrate.
    """
    try:
        return POSES[int(str(note_id)[:8], 16) % len(POSES)]
    except (TypeError, ValueError):
        return POSES[0]


def margins(enabled, pose="stand"):
    """(left, top, right, bottom) padding the note window needs for him."""
    if not enabled:
        return (0, 0, 0, 0)
    return POSE_MARGINS.get(pose, POSE_MARGINS["stand"])


def has_open_box(text):
    return any(line.lstrip().startswith(BOX_OPEN) for line in text.split("\n"))


def box_counts(text):
    """(unticked, ticked) on this note.

    Counted rather than answered yes/no because finishing a list is the
    difference between two counts: the last empty box going, and a ticked one
    arriving in its place. Without the second half, deleting the only line you
    had not done would read as having done it.
    """
    empty = full = 0
    for line in text.split("\n"):
        line = line.lstrip()
        if line.startswith(BOX_OPEN):
            empty += 1
        elif line.startswith(BOX_DONE) or line.startswith("[X] "):
            full += 1
    return empty, full


def strip_box(line):
    """('[x] milk') -> ('[x] ', 'milk'). Returns ('', line) when there is none."""
    for prefix in BOX_PREFIXES:
        if line.startswith(prefix):
            return prefix, line[len(prefix):]
    return "", line


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _rect_distance(px, py, x1, y1, x2, y2):
    dx = max(x1 - px, 0, px - x2)
    dy = max(y1 - py, 0, py - y2)
    return (dx * dx + dy * dy) ** 0.5


class Mascot:
    """One box man, bound to one note window."""

    def __init__(self, window, pose=None):
        self.win = window
        self.cv = window.canvas
        self.pose = pose or pose_for(window.note.get("id"))
        self._limb = "#000000"
        self._skin = "#FFFFFF"
        self._swipe = None
        self._face_box = (0, 0, 0, 0)    # the face where it was drawn
        self._face_item = None
        self._face_scale = (1.0, 1.0)    # squashed, stretched or spinning
        self._arm = None                 # the free arm: ids and its points
        self._offset = (0.0, 0.0)        # where an animation has shoved him
        self._wink = False
        self._blinking = False
        self._hide_eyes = False
        self._reaction = None
        self._react_job = None
        self._react_turn = 0
        self._taps = 0
        self._last_tap = 0.0
        self._blink_job = None
        self._blink_at = time.monotonic() + random.uniform(*BLINK_EVERY)
        self._perked_at = 0.0
        self._eyes = ()
        self._glints = ()
        self._mouth = None
        self._grips = ()
        self._pupil = (0.0, 0.0)
        self._radius = EYE_R
        self._eye_home = ()
        self._head = (0.0, 0.0)
        self._paper_box = (0, 0, 0, 0)   # sheet rect in canvas coordinates
        self._happy = False
        self._grow_job = None
        self._bubble = None
        self._ink = "#000000"
        self.away = False   # picked up off the note; a Roamer has him now

    # ------------------------------------------------------------------ draw

    def draw(self, ox, oy, pw, ph, paper, ink):
        """Paint everything of him that goes BEHIND the sheet.

        Call this before the paper is drawn. The paper covering his hands and
        the back of his face is the whole illusion: he is holding the note, not
        printed on it. Whatever has to be in front - legs dangling over the top
        edge, fingers curled round the bottom one - is drawn by draw_front.
        """
        cv = self.cv
        # Resizing a note repaints it on every mouse move, and each repaint
        # comes through here. He must come back in the mood he was already in:
        # forgetting it would drop his wide eyes and light them up again on the
        # very next tracker tick, ten times a second, which reads as a flicker.
        was_happy, was_radius = self._happy, self._radius
        self.clear()
        self._ink = ink
        self._limb = shade(ink, 1.35)
        self._skin = shade(paper, 1.06)
        self._paper_box = (ox, oy, ox + pw, oy + ph)
        self._happy = was_happy
        self._radius = was_radius if was_happy else EYE_R

        self._grips = ()
        painter = {"stand": self._pose_stand, "side": self._pose_side,
                   "top": self._pose_top, "hang": self._pose_hang}
        painter.get(self.pose, self._pose_stand)(ox, oy, pw, ph)

        # The eyes go on last so nothing is ever painted over them.
        hx, hy = self._head
        self._eye_home = ((hx - EYE_DX, hy), (hx + EYE_DX, hy))
        self._eyes = tuple(cv.create_oval(0, 0, 0, 0, fill=ink, outline="",
                                          tags="mascot")
                           for _ in self._eye_home)
        if was_happy:
            self._add_glints()          # the wipe took them; he is still pleased
        self._apply_eyes()
        if self.away:
            # Somebody is carrying him about. A resize or a colour change still
            # repaints the note, and without this it would put a second copy of
            # him back on it while the first one is in the user's hand.
            self._veil("hidden")

    def draw_front(self, ox, oy, pw, ph):
        """The few parts of him that belong over the paper, not under it.

        Everything here is a hand curled over an edge or a foot resting on
        one. Those are the contact points, and a contact point drawn behind
        the paper is a hand that has gone through the note instead of round
        it - which is the difference between holding the thing and floating
        next to it.
        """
        if not self._eyes:
            return
        for grip in self._grips:
            self._grip(*grip)
        if self.pose == "top":
            # Feet swinging down the front of the sheet, crossed at the ankle
            # and unequal, so he reads as sitting rather than standing on the
            # edge. Both stay inside the glue strip and clear of the heading.
            cx = self._head[0]
            self._bone((cx - 4, oy + 1, cx - 8, oy + 8))
            self._shoe(cx - 8, cx - 12, oy + 13)
            self._bone((cx + 6, oy + 1, cx + 9, oy + 5))
            self._shoe(cx + 9, cx + 13, oy + 10)

    # Every pose is built from these three: a limb, a shoe, and the face.

    def _bone(self, points, width=2):
        """One limb, drawn twice. Returns both item ids.

        He hangs over whatever is behind the note, and a single dark line
        disappears against a dark wallpaper. A thicker pale line underneath
        gives every limb its own outline, so he reads on any desktop.
        """
        return (self.cv.create_line(*points, fill=self._skin, width=width + 3,
                                    capstyle="round", joinstyle="round",
                                    tags="mascot"),
                self.cv.create_line(*points, fill=self._limb, width=width,
                                    capstyle="round", joinstyle="round",
                                    tags="mascot"))

    def _free_arm(self, points):
        """The arm that is not holding the note. It is the one that waves."""
        self._arm = (self._bone(points), tuple(points))

    def _grip(self, x, y, facing, r=5):
        """A hand curled over an edge, drawn on the paper side of it.

        `facing` is the direction the fingers point away from the arm: "down"
        for a hand hooked over a top edge, "up" for one hanging from a bottom
        edge, "right" for one round the left side. Keep r small: a wide arc
        stops reading as a hand and starts reading as an ear.
        """
        start = {"down": 180, "up": 0, "right": 270, "left": 90}[facing]
        self.cv.create_arc(x - r, y - r - 1, x + r + 1, y + r + 1, start=start,
                           extent=180, style="arc", outline=self._limb,
                           width=3, tags="mascot")

    def _shoe(self, heel, toe, sole):
        """The top half of a squat ellipse: a rounded toe on a flat sole."""
        self.cv.create_arc(min(heel, toe) - 5, sole - SHOE_H,
                           max(heel, toe) + 5, sole + SHOE_H,
                           start=0, extent=180, style="pieslice",
                           fill=self._limb, outline=self._limb, tags="mascot")

    def _face(self, cx, cy):
        """The square face. It is the whole character: arms come out of its
        sides and legs out of its bottom, and there is nothing in between."""
        half = HEAD / 2.0
        self._face_item = self.cv.create_rectangle(
            cx - half, cy - half, cx + half, cy + half,
            fill=self._skin, outline=self._limb, width=2, tags="mascot")
        self._head = (cx, cy - HEAD * 0.06)
        self._face_box = (cx - half, cy - half, cx + half, cy + half)

    # --------------------------------------------------------------- the poses

    def _pose_stand(self, ox, oy, pw, ph):
        """On his feet beside the bottom-left corner, one arm reaching in."""
        half = HEAD / 2.0
        ground = oy + ph + GROUND_DROP
        cx = ox - HEAD * 0.95
        cy = ground - LEG_H - half
        arm_y = cy + HEAD * 0.16
        self._bone((cx + half - 2, arm_y, ox - 2, arm_y - 5, ox + 10, arm_y - 9))
        self._free_arm((cx - half + 2, arm_y, cx - half - 6, arm_y + 6,
                        cx - half - 10, arm_y + 13))
        for side in (-1, 1):
            leg_x = cx + side * 7
            self._bone((leg_x, cy + half - 1, leg_x, ground - SHOE_H + 2))
            self._shoe(leg_x, leg_x + side * 4, ground)
        self._face(cx, cy)

    def _pose_side(self, ox, oy, pw, ph):
        """Leaning out from behind the left edge, one hand hooked round it.

        Two things sell this and both are easy to lose. A slice of his face
        has to be behind the paper, or he is standing next to the note rather
        than looking round it; and his weight has to be on the gripping arm,
        which means the far leg braces and the near one hangs - never both the
        same, which is what made him look like a sticker.
        """
        half = HEAD / 2.0
        cx = ox - half + 7                   # 7px of him disappears behind it
        cy = oy + ph * 0.42
        arm_y = cy + HEAD * 0.14
        # the gripping arm, short and pulled in: he is holding his own weight
        self._bone((cx + half - 6, arm_y - 4, ox - 1, arm_y))
        self._grips = ((ox + 1, arm_y, "right"),)
        # the free arm hangs loose and swings away from the note
        self._free_arm((cx - half + 3, arm_y - 3, cx - half - 9, arm_y + 6,
                        cx - half - 13, arm_y + 16))
        # near leg hanging, far leg braced up against the edge
        self._bone((cx - 5, cy + half - 1, cx - 10, cy + half + 12,
                    cx - 7, cy + half + 21))
        self._shoe(cx - 7, cx - 12, cy + half + 24)
        self._bone((cx + 5, cy + half - 1, cx + 9, cy + half + 9,
                    cx + 3, cy + half + 15))
        self._shoe(cx + 3, cx + 8, cy + half + 17)
        self._face(cx, cy)

    def _pose_top(self, ox, oy, pw, ph):
        """Sitting on the top edge, leaning back on one propped arm.

        His chin goes behind the paper so the edge cuts across him and he is
        sitting on it, not hovering over it. The arms do different jobs - one
        planted on the edge taking his weight, one up in the air - because two
        arms held out level is a scarecrow, not a character.
        """
        half = HEAD / 2.0
        cx = ox + min(pw * 0.30, 140.0)
        cy = oy + 5 - half                   # the edge cuts across his chin
        arm_y = cy + HEAD * 0.12
        # the propped arm: down and back, palm flat on the edge beside him
        self._bone((cx + half - 3, arm_y - 2, cx + half + 10, arm_y + 6,
                    cx + half + 14, oy - 2))
        self._grips = ((cx + half + 14, oy + 1, "down"),)
        # the free arm, thrown up: this is the one that waves at you
        self._free_arm((cx - half + 3, arm_y - 1, cx - half - 11, arm_y - 6,
                        cx - half - 16, arm_y - 15))
        self._face(cx, cy)

    def _pose_hang(self, ox, oy, pw, ph):
        """Hanging off the bottom edge by both hands, feet swinging.

        He hangs close to the edge with his elbows bent, the way something
        actually holding on does. Straight arms at full stretch read as
        falling, and the legs swing to one side so the whole figure has a
        direction instead of dangling symmetrically like a plumb line.
        """
        half = HEAD / 2.0
        cx = ox + pw * 0.62
        grip_y = oy + ph - 3
        cy = grip_y + 14 + half
        for side in (-1, 1):
            # elbows out, forearms back in to the edge
            self._bone((cx + side * 8, cy - half + 2, cx + side * 16, cy - half - 4,
                        cx + side * 13, grip_y + 2))
        self._grips = tuple((cx + side * 13, oy + ph, "up", 4) for side in (-1, 1))
        # both legs swung the same way, the trailing one further out
        self._bone((cx - 6, cy + half - 1, cx - 10, cy + half + 9,
                    cx - 6, cy + half + 17))
        self._shoe(cx - 6, cx - 11, cy + half + 20)
        self._bone((cx + 6, cy + half - 1, cx + 13, cy + half + 7,
                    cx + 17, cy + half + 13))
        self._shoe(cx + 17, cx + 22, cy + half + 16)
        self._face(cx, cy)

    def _apply_eyes(self):
        """Move (and size) the eyes and their catchlights. This is the only
        thing that runs while the pointer is moving - no item is recreated.

        Coordinates are absolute, so this agrees with a reaction that has
        shoved the whole figure sideways: the offset is simply added in.
        """
        cv = self.cv
        dx, dy = self._pupil
        ox, oy = self._offset
        fsx, fsy = self._face_scale
        fx0, fy0, fx1, fy1 = self._face_box
        cx, base = (fx0 + fx1) / 2.0, fy1        # the face scales about its foot
        r = 0.01 if self._hide_eyes else self._radius
        try:
            for i, (hx, hy) in enumerate(self._eye_home):
                x = cx + (hx - cx + dx) * fsx + ox
                y = base - (base - hy - dy) * fsy + oy
                ry = 1.0 if (self._blinking or (self._wink and i == 0)) else r
                cv.coords(self._eyes[i], x - r, y - ry, x + r, y + ry)
                if self._glints:
                    gx, gy = x - r * 0.34, y - r * 0.38
                    cv.coords(self._glints[i], gx - GLINT_R, gy - GLINT_R,
                              gx + GLINT_R, gy + GLINT_R)
        except (tk.TclError, IndexError):
            return

    def _apply_face(self):
        """Squash, stretch or spin the face box. The eyes follow through
        _apply_eyes, which scales about the same point."""
        if self._face_item is None:
            return
        fx0, fy0, fx1, fy1 = self._face_box
        cx, base = (fx0 + fx1) / 2.0, fy1
        fsx, fsy = self._face_scale
        ox, oy = self._offset
        hw = (fx1 - fx0) / 2.0 * fsx
        h = (fy1 - fy0) * fsy
        try:
            self.cv.coords(self._face_item, cx - hw + ox, base - h + oy,
                           cx + hw + ox, base + oy)
        except tk.TclError:
            pass

    def _set_arm(self, angle):
        """Swing the free arm about its elbow. 0 leaves it where it was drawn."""
        if not self._arm:
            return
        (ids, pts) = self._arm
        ox, oy = self._offset
        ex, ey, tx, ty = pts[2], pts[3], pts[4], pts[5]
        dx, dy = tx - ex, ty - ey
        ca, sa = math.cos(angle), math.sin(angle)
        nx, ny = ex + dx * ca - dy * sa, ey + dx * sa + dy * ca
        try:
            for item in ids:
                self.cv.coords(item, pts[0] + ox, pts[1] + oy, ex + ox, ey + oy,
                               nx + ox, ny + oy)
        except tk.TclError:
            pass

    # ----------------------------------------------------------------- track

    def _veil(self, state):
        """Hide him, or bring him back. Hiding rather than deleting, because
        the note is not being repainted around it and this is one call to
        undo - the same trick the colour flip uses to get him out of its own
        way."""
        for tag in ("mascot", "mascot_glint", "mascot_pop"):
            try:
                self.cv.itemconfigure(tag, state=state)
            except tk.TclError:
                pass

    def leave(self):
        """He has been picked up off the note."""
        if self.away:
            return
        self.away = True
        self.hush()
        self._cancel_react()
        self._veil("hidden")

    def come_back(self):
        if not self.away:
            return
        self.away = False
        self._veil("normal")

    def visible(self):
        # An absent mascot is not on the note to be looked at, which is what
        # keeps the pointer tracker and the checkbox nag off him for free.
        try:
            return (not self.away and bool(self._eyes)
                    and bool(self.win.winfo_viewable()))
        except tk.TclError:
            return False

    def look_at(self, px, py):
        """Point the eyes at a screen position. Returns True while the pointer
        is close enough to have cheered him up."""
        try:
            rx, ry = self.win.winfo_rootx(), self.win.winfo_rooty()
        except tk.TclError:
            return False
        hx, hy = self._head
        dx, dy = px - (rx + hx), py - (ry + hy)
        dist = (dx * dx + dy * dy) ** 0.5 or 1.0
        reach = min(dist, LOOK_RANGE) / LOOK_RANGE * PUPIL_TRAVEL
        # Half-pixel steps: below that the move is invisible and we skip the
        # canvas call entirely, which is most ticks.
        target = (round(dx / dist * reach * 2) / 2.0,
                  round(dy / dist * reach * 2) / 2.0)
        if target != self._pupil:
            self._pupil = target
            self._apply_eyes()

        x1, y1, x2, y2 = self._paper_box
        edge = _rect_distance(px, py, rx + x1, ry + y1, rx + x2, ry + y2)
        if edge <= NEAR:
            self._set_happy(True)
            self._sway()
        elif edge > NEAR_OUT:
            self._set_happy(False)
        return edge <= NEAR_OUT

    def rest(self):
        if self._pupil != (0.0, 0.0):
            self._pupil = (0.0, 0.0)
            self._apply_eyes()
        self._set_happy(False)

    def near(self):
        """True while the pointer is close enough to have set him off."""
        return self._happy

    def head_at(self):
        """Where his face is, in the note window's own coordinates."""
        return self._head

    # ------------------------------------------------------- the happy eyes

    def _set_happy(self, on):
        if on == self._happy or not self._eyes:
            return
        self._happy = on
        self._cancel_grow()
        if on:
            self._add_glints()
        else:
            self._shift(0.0, 0.0)      # stop swaying, stand up straight
        self._grow_step(1)

    def _add_glints(self):
        try:
            self._glints = tuple(
                self.cv.create_oval(0, 0, 0, 0, fill="#FFFFFF", outline="",
                                    tags="mascot_glint")
                for _ in self._eye_home)
            cx, cy = self._head
            sx, sy = self._offset
            # Both tags on purpose: "mascot" so a hop carries the smile with
            # the face, "mascot_glint" so it goes away with the rest of the
            # delight. Without the first it stays behind in mid air.
            self._mouth = self.cv.create_arc(
                cx - 7 + sx, cy + 3 + sy, cx + 7 + sx, cy + 13 + sy,
                start=200, extent=140, style="arc", outline=self._ink,
                width=1.6, tags=("mascot", "mascot_glint"))
        except tk.TclError:
            self._glints = ()
            self._mouth = None

    def _drop_glints(self):
        try:
            self.cv.delete("mascot_glint")
        except tk.TclError:
            pass
        self._glints = ()
        self._mouth = None

    def _grow_step(self, step):
        """A few short frames wide or narrow, then it stops. No loop is left
        running behind it."""
        self._grow_job = None
        k = step / float(GROW_STEPS)
        if not self._happy:
            k = 1.0 - k
        self._radius = EYE_R + (EYE_R_WIDE - EYE_R) * k
        self._apply_eyes()
        if step < GROW_STEPS:
            try:
                self._grow_job = self.win.after(GROW_MS, self._grow_step, step + 1)
            except tk.TclError:
                self._grow_job = None
        elif not self._happy:
            self._drop_glints()

    def _cancel_grow(self):
        if self._grow_job is not None:
            try:
                self.win.after_cancel(self._grow_job)
            except (tk.TclError, ValueError):
                pass
            self._grow_job = None

    # ------------------------------------------------------------- the line

    def say(self, text=None):
        """A speech bubble over his head, gone again in a few seconds."""
        if not self.visible():
            return False
        self.hush()
        try:
            self._bubble = _Bubble(self.win, text or random.choice(LINES))
        except tk.TclError:
            self._bubble = None
            return False
        return True

    def hush(self):
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None

    # ------------------------------------------------------------- being poked

    def hit(self, x, y):
        """Is this point on his face? In the note window's own coordinates."""
        if self.away or not self._eyes:
            return False
        x0, y0, x1, y1 = self._face_box
        sx, sy = self._offset
        return (x0 + sx - TAP_PAD <= x <= x1 + sx + TAP_PAD
                and y0 + sy - TAP_PAD <= y <= y1 + sy + TAP_PAD)

    def react(self):
        """Someone tapped him. Whichever reaction is next in turn, so poking
        him twice never looks the same twice - unless you keep at it, in which
        case he has something to say about that."""
        if not self._eyes:
            return False
        self._cancel_react()
        now = time.monotonic()
        self._taps = self._taps + 1 if now - self._last_tap < PEST_WINDOW else 1
        self._last_tap = now
        pestered = self._taps >= PEST_TAPS

        if pestered:
            self._reaction = "dizzy"
            self._taps = 0
            self.say(random.choice(PEST_LINES))
        else:
            self._reaction = REACTIONS[self._react_turn % len(REACTIONS)]
            self._react_turn += 1
            if random.random() < TAP_CHANCE:
                self.say(random.choice(TAP_LINES))
        self._set_happy(True)
        self._react_step(0)
        return True

    def cheer(self):
        """Every box on his note is ticked. He does not need to be poked.

        The same reaction machinery a tap uses, minus the tap bookkeeping: a
        second animation system for one moment would be two things to keep
        working and one of them would rot.
        """
        if not self._eyes:
            return False
        self._cancel_react()
        self._reaction = "hop"
        self.say(random.choice(DONE_LINES))
        self._set_happy(True)
        self._react_step(0)
        return True

    def _react_step(self, i):
        self._react_job = None
        t = i / float(REACT_FRAMES)
        kind = self._reaction
        try:
            self.cv.delete("mascot_pop")
            self._wink = False
            self._hide_eyes = False
            self._face_scale = (1.0, 1.0)
            arm = 0.0
            shift = (0.0, 0.0)

            if kind == "hop":
                # Down before up. The dip is the anticipation, and without it
                # he does not jump so much as teleport upwards.
                dip = max(0.0, 1.0 - t / 0.18)
                air = math.sin(math.pi * max(0.0, (t - 0.18) / 0.82))
                shift = (0.0, 3.0 * dip - HOP * air)
                land = max(0.0, (t - 0.88) / 0.12)          # only the last frames
                self._face_scale = (1.0 + 0.18 * dip - 0.16 * air + 0.22 * land,
                                    1.0 - 0.16 * dip + 0.18 * air - 0.20 * land)
                if i == 4:
                    self._pop_marks(3)
            elif kind == "wave":
                arm = 0.85 * math.sin(t * math.pi * 3.0)
                shift = (0.0, -1.5 * abs(math.sin(t * math.pi * 3.0)))
            elif kind == "wink":
                self._wink = 2 <= i <= 7
                shift = (0.0, 1.5 if self._wink else 0.0)
                if self._wink:
                    self._pop_marks(2)
            elif kind == "wobble":
                shift = (SHAKE * math.sin(t * math.pi * 6.0) * (1.0 - t), 0.0)
                self._pop_text("!")
            elif kind == "perk":
                # not a tap: this is him noticing you have started writing
                shift = (0.0, -3.5 * math.sin(math.pi * t))
            elif kind == "dizzy":
                shift = (2.5 * math.sin(t * math.pi * 10.0), 0.0)
                self._pop_marks(3, spin=t * math.pi * 3.0, spread=1.4)
            elif kind == "nod":
                shift = (0.0, 3.0 * math.sin(t * math.pi * 4.0))
            elif kind == "shake":
                shift = (4.0 * math.sin(t * math.pi * 8.0), 0.0)
            elif kind == "squish":
                sq = math.sin(t * math.pi)
                self._face_scale = (1.0 + 0.3 * sq, 1.0 - 0.4 * sq)
            elif kind == "float":
                shift = (0.0, -12.0 * math.sin(t * math.pi))
            else:                                            # spin
                # two flips: the face narrows to an edge and comes back round,
                # and the eyes go with it because they scale about the same point
                turn = abs(math.cos(t * math.pi * 2.0))
                self._face_scale = (max(0.12, turn), 1.0)
                self._hide_eyes = turn < 0.45
                shift = (0.0, -4.0 * math.sin(math.pi * t))

            self._shift(*shift)
            self._apply_face()
            self._apply_eyes()
            if self._arm:
                self._set_arm(arm)
        except tk.TclError:
            return
        if i < REACT_FRAMES:
            try:
                self._react_job = self.win.after(REACT_MS, self._react_step, i + 1)
            except tk.TclError:
                self._react_job = None
            return
        self._end_react()

    def _shift(self, dx, dy):
        """Move every part of him, eyes included, by an absolute offset."""
        ox, oy = self._offset
        if abs(dx - ox) < 0.5 and abs(dy - oy) < 0.5:
            return
        try:
            self.cv.move("mascot", dx - ox, dy - oy)
        except tk.TclError:
            return
        self._offset = (dx, dy)

    def _pop_marks(self, count, spin=0.0, spread=1.0):
        """Little spokes over his head. Gone by the next frame.

        `spin` turns the whole set, which is what makes the dizzy ones circle.
        """
        cx, cy = self._head
        sx, sy = self._offset
        top = cy + sy - HEAD * 0.75
        for k in range(count):
            angle = spin + math.pi * (0.25 + 0.5 * k / max(count - 1, 1)) * spread
            dx, dy = math.cos(angle) * 9, -math.sin(angle) * 9
            self.cv.create_line(cx + sx + dx * 0.55, top + dy * 0.55,
                                cx + sx + dx, top + dy,
                                fill=self._limb, width=2, capstyle="round",
                                tags=("mascot", "mascot_pop"))

    def _pop_text(self, text):
        cx, cy = self._head
        sx, sy = self._offset
        self.cv.create_text(cx + sx, cy + sy - HEAD * 0.85, text=text,
                            fill=self._limb, font=self.win.f_ui,
                            tags=("mascot", "mascot_pop"))

    def _end_react(self):
        self._wink = False
        self._hide_eyes = False
        self._face_scale = (1.0, 1.0)
        # Exactly back, not nearly: _shift ignores sub-pixel moves during the
        # animation, and those leftovers would otherwise accumulate.
        ox, oy = self._offset
        if ox or oy:
            try:
                self.cv.move("mascot", -ox, -oy)
            except tk.TclError:
                pass
            self._offset = (0.0, 0.0)
        try:
            self.cv.delete("mascot_pop")
        except tk.TclError:
            pass
        self._apply_face()
        self._set_arm(0.0)
        self._apply_eyes()
        self._reaction = None

    def _cancel_react(self):
        if self._react_job is not None:
            try:
                self.win.after_cancel(self._react_job)
            except (tk.TclError, ValueError):
                pass
            self._react_job = None
        if self._reaction is not None:
            self._end_react()

    # --------------------------------------------------------------- idle life

    def quiet_down(self, seconds):
        """Hold off the idle beat for a while, and stop any blink in flight.

        The idle beat rides the tracker's tick on purpose, which means it can
        land in the middle of anything - including a measurement of what the
        tracker costs. Anything timing him needs to be able to park it.
        """
        if self._blink_job is not None:
            try:
                self.win.after_cancel(self._blink_job)
            except (tk.TclError, ValueError):
                pass
            self._blink_job = None
        self._blinking = False
        self._blink_at = time.monotonic() + seconds

    def idle_due(self, now):
        """Is he due to blink? One float compare, no Tk.

        The shared tracker calls this for every note on every tick, including
        the cheap parked-pointer tick, so it must stay this cheap: the whole
        point is that idle life costs no timer of its own while it waits.
        """
        return now >= self._blink_at

    def idle(self, now):
        """Blink or play a small animation. Only ever called when idle_due has already said so."""
        self._blink_at = now + random.uniform(*BLINK_EVERY)
        if (self._blink_job is not None or self._reaction is not None
                or not self._eyes or not self.visible()):
            return
        if random.random() < IDLE_STIR:
            # Now and then he stretches instead of blinking. Only the quiet
            # ones: idle life must never pop a mark or a word over a note you
            # are trying to read.
            self._reaction = random.choice(IDLE_STIRS)
            self._react_step(0)
        else:
            self._blink_step(0)

    def _blink_step(self, i):
        self._blink_job = None
        self._blinking = i < BLINK_FRAMES // 2
        if i == BLINK_FRAMES // 2 and random.random() < GLANCE_CHANCE:
            # His eyes move while they are shut, the way real ones do. This
            # costs nothing extra: the pointer puts them back on its next move.
            reach = PUPIL_TRAVEL * GLANCE_REACH
            angle = random.uniform(0.0, 2.0 * math.pi)
            self._pupil = (round(math.cos(angle) * reach * 2) / 2.0,
                           round(math.sin(angle) * reach * 2) / 2.0)
        self._apply_eyes()
        if i < BLINK_FRAMES - 1:
            try:
                self._blink_job = self.win.after(BLINK_MS, self._blink_step, i + 1)
            except tk.TclError:
                self._blink_job = None

    def perk(self):
        """You have started writing, and he noticed. Event driven: no timer
        exists until a keystroke creates one, and it is capped to one bob every
        few seconds so it never becomes a twitch while you type."""
        now = time.monotonic()
        if (not self._eyes or self._reaction is not None
                or now - self._perked_at < PERK_GAP or not self.visible()):
            return False
        self._perked_at = now
        self._reaction = "perk"
        self._react_step(0)
        return True

    def _sway(self):
        """A slow rock while you are near him. Rides the ticks the tracker is
        already making at that moment, so it adds no timer at all."""
        if self._reaction is not None or not self._happy:
            return
        phase = time.monotonic() * SWAY_HZ * 2.0 * math.pi
        self._shift(0.0, round(math.sin(phase) * SWAY, 1))

    # ---------------------------------------------------------- colour change

    def swipe(self, paper, edge, ink, on_covered):
        """Sweep a new colour across the sheet, repainting under the cover.

        Returns False when there is nothing to animate on - no figure drawn,
        note not on screen - and the caller should simply repaint.
        """
        self.finish_swipe()
        if not self._eyes or not self.visible():
            return False
        try:
            self._swipe = _Flip(self, paper, edge, ink, on_covered)
        except tk.TclError:
            self._swipe = None
            return False
        return True

    def finish_swipe(self):
        """End any running swipe at once. Clicking through the swatches must
        never leave two of them running over each other."""
        if self._swipe is not None:
            self._swipe.finish()
            self._swipe = None

    def clear(self):
        """Forget the canvas items, for a caller about to wipe the canvas."""
        self._cancel_grow()
        if self._react_job is not None:
            try:
                self.win.after_cancel(self._react_job)
            except (tk.TclError, ValueError):
                pass
        self._react_job = None
        self._reaction = None
        if self._blink_job is not None:
            try:
                self.win.after_cancel(self._blink_job)
            except (tk.TclError, ValueError):
                pass
        self._blink_job = None
        self._blinking = False
        self._wink = False
        self._hide_eyes = False
        self._face_scale = (1.0, 1.0)
        self._face_item = None
        self._arm = None
        self._offset = (0.0, 0.0)
        self._happy = False
        self._radius = EYE_R
        self._eyes = ()
        self._glints = ()
        self._mouth = None
        self._grips = ()

    def destroy(self):
        self.finish_swipe()
        self.clear()
        self.hush()


# --------------------------------------------------------------- easing
#
# Weight is mostly easing. Something heavy does not start or stop instantly,
# it leans into the direction it is accelerating, and it falls faster the
# longer it has been falling.

def _smooth(u):
    """Ease in and out. The plain workhorse."""
    return u * u * (3.0 - 2.0 * u)


def _accel(u):
    """How hard _smooth is pushing at u, from +1 to -1.

    This is what the lean is made of: forward while he is speeding up, back
    while he is slowing down. It is the difference between a figure sliding
    along and a figure walking.
    """
    return 1.0 - 2.0 * u


def _drop(u):
    """Gravity: slow at the top, quick at the bottom."""
    return u * u


def _swell(u):
    """0 to 1 and back again."""
    return math.sin(math.pi * u)


def _spring(u, swings=2.4, damp=5.0):
    """Overshoot, then wobble down to nothing."""
    return math.cos(u * math.pi * swings) * math.exp(-damp * u)


def _mix(a, b, u):
    return a + (b - a) * u


def _mix2(a, b, u):
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def _aim(here, there, reach=PUPIL_TRAVEL):
    """Where the pupils sit when he is looking at a point. Screen coordinates
    in, a small offset out - the eyes travel a few pixels, not the width of
    the head."""
    dx, dy = there[0] - here[0], there[1] - here[1]
    span = math.hypot(dx, dy)
    if span < 1e-6:
        return (0.0, 0.0)
    k = min(span, LOOK_RANGE) / LOOK_RANGE * reach / span
    return (dx * k, dy * k)


def _rotor(px, py, angle):
    """A function that turns points about (px, py). None when there is no
    turn to do, so the common case pays one comparison instead of a call per
    point."""
    if not angle:
        return None
    c, s = math.cos(angle), math.sin(angle)

    def turn(pts):
        out = []
        for i in range(0, len(pts), 2):
            dx, dy = pts[i] - px, pts[i + 1] - py
            out.append(px + dx * c - dy * s)
            out.append(py + dx * s + dy * c)
        return out
    return turn


def _reach(root, target, upper, fore, bend=1.0):
    """Two bones from root towards target. Returns (elbow, hand).

    The hand is clamped to what the arm can actually reach, so a target out
    past his fingertips reads as straining towards it rather than as an arm
    made of string - and how far short he fell is then a number the caller can
    put into his face. bend decides which side the joint breaks to; getting
    that wrong is an elbow bending backwards, which is the one thing everybody
    notices.
    """
    dx, dy = target[0] - root[0], target[1] - root[1]
    span = math.hypot(dx, dy) or 1e-6
    # Never quite locked straight: a limb with no angle in it has no joint to
    # read, and reads as a stick rather than an arm.
    grasp = min(span, (upper + fore) * 0.995)
    grasp = max(grasp, abs(upper - fore) + 0.001)
    ux, uy = dx / span, dy / span
    hand = (root[0] + ux * grasp, root[1] + uy * grasp)
    along = (grasp * grasp + upper * upper - fore * fore) / (2.0 * grasp)
    off = math.sqrt(max(0.0, upper * upper - along * along))
    side = 1.0 if bend >= 0 else -1.0
    return ((root[0] + ux * along - uy * off * side,
             root[1] + uy * along + ux * off * side), hand)


def _beat(beats, i):
    """Which beat frame i is in, and how far through it.

    The last frame of a beat is u = 1 exactly, not one step short of it. A
    beat that stops at 0.97 never finishes its easing - and in the colour flip
    the drag in particular would leave a sliver of the old colour showing at
    the very moment the note underneath is repainted.
    """
    for name, n in beats:
        if i < n:
            return name, (i / float(n - 1)) if n > 1 else 1.0
        i -= n
    return "done", 1.0


# ---------------------------------------------------------------------- faces
#
# Eight numbers, mixed one field at a time, so any mood can cross-fade into
# any other and a wail can drive its own mouth without touching the rest.
#
#   eye    radius multiplier: 0 shut, 1 ordinary, 1.8 saucers
#   lid    one signed number - positive drops the upper lid (glaring),
#          negative raises the lower one (a contented squint)
#   brow   raised or lowered
#   tilt   inner ends of the brows up (worry, pleading) or down (anger)
#   mouth  width, 0 for none at all
#   curve  frown to smile
#   open   a closed line to an open oval
#   sweat  one drop off the temple
#
# brow and tilt together carry nearly the whole expression. Gaze is not in
# here on purpose: where he is looking is aim, not mood, and during a
# conversation it is driven every frame by where the other one's head is.

Face = collections.namedtuple(
    "Face", "eye lid brow tilt mouth curve open sweat")


def _face_mix(a, b, u):
    return Face(*[_mix(x, y, u) for x, y in zip(a, b)])


FACES = {
    "calm":   Face(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "happy":  Face(1.7, -0.3, 0.2, 0.0, 1.0, 1.0, 0.0, 0.0),
    "panic":  Face(1.9, 0.0, 1.0, 1.0, 1.0, -1.0, 0.7, 0.9),
    "strain": Face(0.5, 0.6, -0.8, -0.4, 0.9, -0.4, 0.35, 1.0),
    "talk":   Face(1.1, 0.0, 0.3, 0.1, 0.8, 0.3, 0.6, 0.0),
    "laugh":  Face(0.15, -1.0, 0.5, 0.0, 1.3, 1.0, 0.9, 0.0),
    "think":  Face(0.9, -0.4, 0.4, 0.5, 0.6, -0.2, 0.0, 0.0),
    "smug":   Face(0.7, -0.8, 0.3, 0.0, 0.9, 0.8, 0.0, 0.0),
    "cross":  Face(0.6, 0.55, -0.85, -0.7, 0.9, -0.9, 0.10, 0.0),
    "wtf":    Face(2.0, 0.9, -1.0, -0.9, 1.2, -0.7, 0.5, 0.0),
    "dazed":  Face(1.3, 0.4, 0.6, 0.3, 0.8, -0.5, 0.4, 0.6),
    "plead":  Face(0.10, 1.0, 0.55, 1.0, 0.85, -1.0, 0.6, 1.0),
}


def _walker(cv, cx, cy, phase, skin, limb, ink, facing=0.0, hand=None,
            lean=0.0, crouch=0.0, tag="walker",
            hands=None, feet=None, face=None, look=(0.0, 0.0),
            squash=1.0, roll=0.0):
    """The box man, drawn anywhere, from any angle, mid-stride.

    His poses on the note are built from the Mascot's own primitives against
    the note's canvas. The colour change happens on a window of its own - the
    note's text widgets are opaque, and the walk goes outside the note
    altogether - so it needs a version of him that holds no state at all. Once
    he could be picked up off the note entirely, that same statelessness is
    what let the roamer reuse him without a second figure existing.

    facing  -1 to 1: which way he is turned. 0 is straight out at you, and +-1
            is full profile. Anything above about 0.75 crowds his far eye
            towards the near one, which is what makes a turn read as a turn.
    phase   the walk cycle in radians, or None to stand still.
    hand    a point his leading arm reaches for instead of swinging.
    lean    how far his head is ahead of his feet. This is the weight.
    crouch  0 to 1, how far he has bent his knees.
    hands   (left, right) points his arms reach for, either may be None to
            leave that arm swinging. Solved with two bones, so the elbow bends
            instead of the arm stretching.
    feet    (left, right) points his feet are planted on, same idea. Used for
            landing and for balancing, not for walking: the swing formula
            below is cheaper and already looks right.
    face    a Face, or None for the plain pair of eyes he has on a note.
    look    where the pupils are aimed, as a small offset.
    squash  vertical scale about his hips, for the weight of a landing.
    roll    body tilt in radians, about his hips.

    Everything after tag defaults to what he did before any of it existed, so
    the colour flip calls this exactly as it always has.
    """
    hh = HEAD / 2.0
    turn = min(1.0, abs(facing))
    way = -1.0 if facing < 0 else 1.0
    # He is a flat square with no depth to foreshorten, so turning him barely
    # narrows the face at all. Squashing it hard reads as a tall rectangle -
    # a different character. The turn is carried by his eyes and his nose.
    hw = hh * (1.0 - 0.14 * turn)
    stride = math.sin(phase) if phase is not None else 0.0
    step = math.cos(phase) if phase is not None else 0.0

    cy += abs(stride) * BOB_PX + crouch * 7.0  # lowest at full stride
    hip_y = cy + hh
    sole = hip_y + LEG_H - crouch * 5.0
    hx = cx + lean                             # the head leads, the feet do not

    # Squash works about the hips, so a landing flattens him onto the floor
    # instead of lifting him off it. He keeps his volume: what he loses in
    # height he gains in width.
    hh_d = hh * squash
    hw_d = hw / max(0.5, squash)
    fy = hip_y - hh_d                          # the middle of his face
    rot = _rotor(hx, hip_y, roll)

    def bone(points, width=2):
        pts = points if rot is None else rot(list(points))
        cv.create_line(*pts, fill=skin, width=width + 3, capstyle="round",
                       joinstyle="round", tags=tag)
        cv.create_line(*pts, fill=limb, width=width, capstyle="round",
                       joinstyle="round", tags=tag)

    def spot(x, y):
        return (x, y) if rot is None else tuple(rot([x, y]))

    # Legs. The far one is drawn first so the near one reads as in front of it.
    spread = 7.0 * (1.0 - 0.30 * turn)
    for lead in ((-1.0, 1.0) if way > 0 else (1.0, -1.0)):
        planted = None
        if feet is not None:
            planted = feet[0] if lead * way < 0 else feet[1]
        hip_x = cx + lean * 0.34 + lead * spread
        if planted is None:
            swing = stride * lead
            foot_x = hip_x + way * swing * 8.0
            foot_y = sole - max(0.0, step * lead) * 3.5  # the swinging foot lifts
            knee_x = (hip_x + foot_x) / 2.0 + way * 2.0
            knee_y = hip_y + (foot_y - hip_y) * 0.55 + crouch * 3.0
        else:
            # Standing on something. The feet stay where they are and the
            # knees take up whatever the hips do, which is what makes a
            # landing look absorbed rather than survived.
            knee, foot = _reach((hip_x, hip_y - 1), planted, THIGH, SHIN,
                                bend=way)
            knee_x, knee_y = knee
            foot_x, foot_y = foot
        bone((hip_x, hip_y - 1, knee_x, knee_y, foot_x, foot_y))
        toe = foot_x + way * 5.0
        sx1, sy1 = spot(min(foot_x, toe) - 5, foot_y - SHOE_H)
        sx2, sy2 = spot(max(foot_x, toe) + 5, foot_y + SHOE_H)
        cv.create_arc(min(sx1, sx2), min(sy1, sy2), max(sx1, sx2), max(sy1, sy2),
                      start=0, extent=180, style="pieslice",
                      fill=limb, outline=limb, tags=tag)

    # Arms, swinging against the legs. The trailing one goes down first.
    arm_y = fy + hh_d * 0.20
    reach = 10.5 * (1.0 - 0.25 * turn)
    for side in (-way, way):
        target, jointed = None, True
        if hands is not None:
            target = hands[0] if side < 0 else hands[1]
        elif hand is not None and (1.0 if hand[0] > hx else -1.0) == side:
            # The old one-armed form. Its arm stretches to whatever it is
            # holding, because in the colour flip he never steps close enough
            # for a real elbow to reach the crease. Left exactly as it was
            # rather than re-tuned: the flip is finished work.
            target, jointed = hand, False
        sx, sy = hx + side * hw_d * 0.75, arm_y
        if target is None:
            swing = stride * side * way
            bone((sx, sy,
                  hx + side * (hw_d + reach * 0.55), arm_y + 4.5 + swing * 4.0,
                  hx + side * (hw_d + reach), arm_y + 10.0 + swing * 6.5))
            continue
        gx, gy = target
        if jointed:
            # Elbows break outward, away from his chest. Reaching across his
            # own body is what makes a figure look like a puppet, and an elbow
            # bending the wrong way is the one thing everybody notices.
            elbow, gripped = _reach((sx, sy), target, UPPER_ARM, FOREARM,
                                    bend=-side)
            bone((sx, sy, elbow[0], elbow[1], gripped[0], gripped[1]))
            gx, gy = gripped
        else:
            bone((sx, sy, (sx + gx) / 2.0 + side * 5.0,
                  (sy + gy) / 2.0 + 5.0, gx, gy))
        hxx, hyy = spot(gx, gy)
        cv.create_oval(hxx - 4, hyy - 4, hxx + 4, hyy + 4, fill=skin,
                       outline=limb, width=2, tags=tag)

    head = [hx - hw_d, fy - hh_d, hx + hw_d, fy - hh_d,
            hx + hw_d, fy + hh_d, hx - hw_d, fy + hh_d]
    cv.create_polygon(*(head if rot is None else rot(head)), fill=skin,
                      outline=limb, width=2, tags=tag)
    if turn > 0.45:                    # the bridge of his nose sells the turn
        nose = 2.2 * (turn - 0.45) / 0.55
        bridge = [hx + way * hw_d, fy - hh_d * 0.06,
                  hx + way * (hw_d + nose), fy + hh_d * 0.16,
                  hx + way * hw_d, fy + hh_d * 0.36]
        cv.create_line(*(bridge if rot is None else rot(bridge)), fill=limb,
                       width=2, capstyle="round", joinstyle="round", tags=tag)
    _walker_face(cv, spot, bone, hx, fy, hw_d, hh_d, way, turn, skin, limb,
                 ink, face, look, tag)


def _walker_face(cv, spot, bone, hx, fy, hw, hh, way, turn, skin, limb,
                 ink, face, look, tag):
    """His eyes, and everything above and below them.

    Both eyes stay whichever way he is turned. Dropping the far one is what a
    drawing does for a hard profile, but at this size it just looks like he
    has lost an eye; letting it shrink and crowd towards the near one says the
    same thing and keeps his face a face.
    """
    eye_c = hx + way * hw * 0.22 * turn
    sep = EYE_DX * (1.0 - 0.40 * turn)
    scale = 1.0 if face is None else face.eye
    # Eyes that go wide have to move apart as well as grow. Turning him also
    # crowds them together, and saucer eyes on a turned head meet in the
    # middle and read as one black smudge rather than as alarm.
    sep = max(sep, EYE_R * scale * 1.25)
    lx, ly = look
    for eye in (-1.0, 1.0):
        near = eye * way > 0
        r = EYE_R * scale * (1.0 if near else 1.0 - 0.50 * turn)
        ex, ey = eye_c + eye * sep, fy
        if face is not None and scale < 0.3:
            # Shut, and which way it curls is the whole difference between a
            # happy squint and eyes screwed shut against something. lid picks,
            # the same way it picks which lid comes down over an open eye.
            #
            # Kept inside its own half of the face: a turned head crowds the
            # eyes together, and two arcs at their full width then overlap into
            # one dark band across his face rather than two shut eyes.
            half = min(EYE_DX * 0.8, sep * 0.82) * (1.0 if near
                                                    else 1.0 - 0.5 * turn)
            ax, ay = spot(ex - half, ey - 2.6)
            bx, by = spot(ex + half, ey + 2.6)
            cv.create_arc(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by),
                          start=20 if face.lid < 0 else 200, extent=140,
                          style="arc", outline=ink, width=2, tags=tag)
            continue
        px, py = spot(ex + lx, ey + ly)
        cv.create_oval(px - r, py - r, px + r, py + r, fill=ink, outline="",
                       tags=tag)
        if face is None or not face.lid:
            continue
        # The lid is drawn as the face closing over the eye rather than as a
        # line across it: there is no alpha here, so the only way to take a
        # bite out of a shape is to paint the skin back over it.
        cut = min(1.0, abs(face.lid)) * r * 1.3
        ox, oy = spot(ex + lx, ey + ly)
        if face.lid > 0:
            cv.create_rectangle(ox - r - 1, oy - r - 1, ox + r + 1,
                                oy - r + cut, fill=skin, outline="", tags=tag)
        else:
            cv.create_rectangle(ox - r - 1, oy + r - cut, ox + r + 1,
                                oy + r + 1, fill=skin, outline="", tags=tag)
    if face is None:
        return

    if face.brow or face.tilt:
        for eye in (-1.0, 1.0):
            ex = eye_c + eye * sep
            # Clear of the eye itself, whatever size it has gone to. Saucer
            # eyes with the brows pinned to a fixed height come out as one
            # black smudge across the middle of his face.
            base = fy - EYE_R * scale - 3.2 - face.brow * 2.4
            inner, outer = eye * -1.6, eye * 4.2   # inner end nearer his nose
            bone((*spot(ex + inner, base - face.tilt * 2.0),
                  *spot(ex + outer, base + face.tilt * 1.4)), width=1)

    if face.mouth > 0.02:
        mw = 7.0 * face.mouth
        # Below the eyes, however big they have gone, and a shut eye is an arc
        # with a height of its own rather than a dot. A fixed height puts the
        # mouth inside a pair of saucer eyes and the whole face becomes soup.
        low = 3.2 if scale < 0.3 else EYE_R * scale
        my = fy + max(hh * 0.40, low + 4.0)
        if face.open > 0.08:
            mh = 1.5 + face.open * 6.0
            ax, ay = spot(hx - mw * 0.6, my - mh * 0.5)
            bx, by = spot(hx + mw * 0.6, my + mh * 0.5)
            cv.create_oval(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by),
                          fill=limb, outline=limb, tags=tag)
        else:
            dip = face.curve * 3.0
            bone((*spot(hx - mw, my - dip * 0.5), *spot(hx, my + dip),
                  *spot(hx + mw, my - dip * 0.5)), width=1)

    if face.sweat > 0.05:
        dx, dy = spot(hx + way * hw * 0.82, fy - hh * 0.42)
        r = 1.6 + face.sweat * 1.4
        cv.create_oval(dx - r, dy - r * 1.3, dx + r, dy + r * 1.3,
                       fill=shade(skin, 0.86), outline=limb, tags=tag)


class _Flip(tk.Toplevel):
    """A colour change: he walks over and folds the sheet across by hand.

    It has to be its own window, and a bigger one than the note. Tk text
    widgets are opaque and sit above the note's own canvas, so nothing drawn
    there can pass over the writing; and the walk goes outside the note.

    The beats, in order: he braces, walks round to the bottom-right corner -
    the one the note already draws as curled up off the pad, because that is
    the corner the sheet itself says is loose - turns his back to you to face
    the note, takes hold of it, and walks the fold across to the far side,
    leaning against the weight of it the whole way. Then he lets go, the page
    drops back flat, and what was under it is the new colour.

    The fold is upright and travels with him, rather than running corner to
    corner. A diagonal is the prettier crease, but the corner you are holding
    ends up right across the note from where you are standing, and his arm
    becomes a washing line. Holding the crease beside him means the work is
    visibly his: he is walking the page over, not pointing at it.

    The moment the fold covers the sheet completely is the moment the note
    underneath is really repainted, so the change itself is never seen.

    Speeds are pixels per frame, not frames per journey: a wide note takes
    longer to cross than a narrow one, because he only walks at one speed.
    """

    def __init__(self, mascot, paper, edge, ink, on_covered):
        window = mascot.win
        tk.Toplevel.__init__(self, window)
        self.mascot = mascot
        self.new_paper, self.new_edge, self.new_ink = paper, edge, ink
        self.on_covered = on_covered
        self.rect = window.paper_rect()
        ox, oy, pw, ph = self.rect
        self.box = (ox, oy, ox + pw, oy + ph)
        self.skin, self.limb, self.ink = mascot._skin, mascot._limb, mascot._ink
        self.key = getattr(window, "chroma_key", None)
        self._job = None
        self._last_at = (0.0, 0.0)     # where he was drawn, for close-ups
        self._did_cover = False
        self._turned = 0.0
        self._done = False

        self.overrideredirect(True)
        key = getattr(window, "chroma_key", None)
        if key is None:
            raise tk.TclError("no chroma key: nothing to animate through")
        try:
            self.attributes("-transparentcolor", key)
            self.attributes("-topmost", True)
        except tk.TclError:
            self.destroy()
            raise
        pad_r, pad_b = FLIP_PAD
        w = window.winfo_width() + pad_r
        h = window.winfo_height() + pad_b
        self.canvas = tk.Canvas(self, bg=key, highlightthickness=0, bd=0,
                                width=w, height=h)
        self.canvas.pack(fill="both", expand=True)
        self.geometry("%dx%d+%d+%d" % (w, h, window.winfo_rootx(),
                                       window.winfo_rooty()))
        self._win_at = (window.winfo_rootx(), window.winfo_rooty())

        self.home = mascot.head_at()
        # He works on the same floor the standing pose uses, so stepping onto
        # it never looks like he changed height.
        self.floor = oy + ph + GROUND_DROP - LEG_H - HEAD / 2.0
        self.corner = (ox + pw + HEAD * 0.62, self.floor)   # where he takes hold
        self.pushed = (ox + HEAD * 0.95, self.floor)        # the end of the push
        self.spot = (ox - HEAD * 0.95, self.floor)          # and a step clear of it
        self.words = self._read_words(window)
        self.out = self._route(self.home, self.corner)
        # Worked out from his post outwards and then walked backwards. Which
        # way round the sheet is safe depends on where he lives, so the rule
        # only knows how to start from there: asking it to set off from the
        # far corner instead sends him up through the middle of the note.
        self.back = self._reverse_route(self._route(self.home, self.spot))
        self.beats = self._plan()

        self._hide_real()
        # It sits over the note for a couple of seconds. A click means the user
        # wants the note, not the show.
        self.canvas.bind("<Button-1>", lambda _e: self.finish())
        self._step(0)

    # ------------------------------------------------------------ the words

    def _read_words(self, window):
        """Every run of writing on the sheet: (x, y, text, font, width, rule).

        Read off the widgets rather than out of the stored strings, so that
        the wrapping, the heading, and any bold or underlined stretch land
        exactly where the user is already looking at them. Their coordinates
        are the note window's own, which is also this canvas's, because the
        overlay is pinned to the window's corner.

        Done once, here. It is a few dozen Tcl calls and the fold redraws
        sixty times a second.
        """
        out = []
        for widget, plain in ((window.head, window.f_head),
                              (window.body, window.f_body)):
            try:
                ox, oy = widget.winfo_x(), widget.winfo_y()
                index = widget.index("@0,0")
                while True:
                    info = widget.dlineinfo(index)
                    if info is None:
                        break
                    x = ox + info[0]
                    y = oy + info[1]
                    stop = widget.index("%s display lineend" % index)
                    live = set()
                    for kind, value, _where in widget.dump(index, stop,
                                                           text=True, tag=True):
                        if kind == "tagon":
                            live.add(value)
                        elif kind == "tagoff":
                            live.discard(value)
                        elif kind == "text" and value.strip():
                            font = self._font_for(window, plain, live)
                            wide = font.measure(value)
                            out.append((x, y, value, font, wide,
                                        "underline" in live))
                            x += wide
                        elif kind == "text":
                            x += self._font_for(window, plain,
                                                live).measure(value)
                    nxt = widget.index("%s +1 display lines" % index)
                    if widget.compare(nxt, "==", index):
                        break
                    index = nxt
            except (tk.TclError, AttributeError):
                continue
        return out

    @staticmethod
    def _font_for(window, plain, tags):
        if "bi" in tags or ("bold" in tags and "italic" in tags):
            return window.f_bolditalic
        if "bold" in tags:
            return window.f_bold
        if "italic" in tags:
            return window.f_italic
        return plain

    # ------------------------------------------------------------ the route

    def _route(self, a, b):
        """Two straight legs from a to b, going round the sheet not across it.

        From above the paper he travels along the top and then down the side;
        from beside or below it he drops to the floor first. Either way he
        never walks over the writing.
        """
        ox, oy = self.rect[0], self.rect[1]
        bend = (b[0], a[1]) if a[1] < oy else (a[0], b[1])
        legs = (a, bend, b)
        lengths = [_dist(p, q) for p, q in zip(legs, legs[1:])]
        return (legs, lengths, sum(lengths) or 1.0)

    @staticmethod
    def _reverse_route(route):
        legs, lengths, span = route
        return (tuple(reversed(legs)), list(reversed(lengths)), span)

    def _plan(self):
        # Capped as well as scaled. Pace is what makes it read as walking, but
        # a colour change on a big note must not become a short film.
        walk = max(10, min(36, int(self.out[2] / WALK_PX)))
        drag = max(16, min(40, int((self.box[2] - self.box[0]) / DRAG_PX)))
        back = max(6, min(30, int(self.back[2] / WALK_PX)))
        return (("brace", 4), ("walk", walk), ("turn", 6), ("reach", 7),
                ("drag", drag), ("hold", 3), ("fall", 16), ("about", 5),
                ("home", back), ("arrive", 6))

    def _at(self, i):
        return _beat(self.beats, i)

    @staticmethod
    def _along(route, s):
        """A point s of the way along a route, and which way he is heading."""
        legs, lengths, span = route
        want = s * span
        for (a, b), length in zip(zip(legs, legs[1:]), lengths):
            if want <= length or length <= 0.0:
                u = (want / length) if length else 1.0
                dx = b[0] - a[0]
                return (_mix2(a, b, u),
                        1.0 if dx > 1.0 else -1.0 if dx < -1.0 else 0.0)
            want -= length
        return legs[-1], 1.0

    # --------------------------------------------------------- the page fold

    def _fold(self, u):
        """Where the crease stands. u = 0 is the loose edge he starts from,
        u = 1 the far side, by which point the fold is over the whole sheet -
        the only moment the note underneath may be repainted."""
        return _mix(self.box[2], self.box[0], u)

    def _covered(self, u):
        """The part of the sheet the fold has lifted clear of, as a polygon.

        This is what hides the repaint: at u = 1 it is the whole sheet.
        """
        x0, y0, x1, y1 = self.box
        c = self._fold(u)
        if c >= x1:
            return []
        return [(c, y0), (x1, y0), (x1, y1), (c, y1)]

    def _paint_words(self, outer, ink):
        """The writing on the face coming into view.

        It is the same note underneath, so the same words are on the far side
        of the crease - in the new ink, on the new paper. Leave them off and
        the sheet turns over blank and the writing pops back at the end, which
        is the one thing the whole fold exists to hide.
        """
        cv = self.canvas
        for x, y, text, font, wide, rule in self.words:
            if x + wide < outer:
                continue                    # about to be painted out anyway
            cv.create_text(x, y, text=text, font=font, fill=ink, anchor="nw")
            if rule:
                # Canvas text has no underline of its own; it is a line.
                base = y + font.metrics("ascent") + 1
                cv.create_line(x, base, x + wide, base, fill=ink, width=1)

    def _grip(self, u):
        """Where his hand is on the crease.

        At his own height rather than down at the corner: an arm reaching
        across its owner's shins is not holding anything, it is in the way.
        """
        return (self._fold(u), min(self.box[3] - 8, self.floor + 6))

    def _paint_fold(self, u, paper, ink):
        """The turned page and what it has uncovered.

        To the far side of the crease is the new colour - the note's next face
        coming into view as the old one lifts off it. On his side of the
        crease lies the page itself, which is that same strip mirrored back
        over the fold, bowed out in the middle because paper does not fold
        flat, and shaded from bright at the crease to dark at the loose edge.
        """
        cv = self.canvas
        x0, y0, x1, y1 = self.box
        c = self._fold(u)
        outer = max(x0, c - (x1 - c))        # the folded edge, clipped to the sheet
        width = c - outer
        if c < x1:
            cv.create_polygon(c, y0, x1, y0, x1, y1, c, y1,
                              fill=paper, outline="")
            self._paint_words(outer, ink)
        if c > x0:
            # Whatever the writing spilled past the crease goes back to the key
            # colour, which is to say back to transparent: underneath is the
            # real note, still showing those same words in their old ink. The
            # leaf covers the rest. A Tk canvas has no clipping of its own.
            cv.create_rectangle(0, y0 - 1, outer, y1 + 1,
                                fill=self.key, outline="")
        if width < 1.0:
            return
        span = float(y1 - y0)
        bow = min(FOLD_BOW, width * 0.16)    # paper bulges a little, not a lot

        def leaf(depth):
            """The page from the crease out to `depth`, its loose edge bowed.

            The crease side stays a straight, sharp corner; only the loose
            edge is curved, which is what a folded sheet actually looks like.
            Enough points along it that no smoothing is needed - smoothing
            would round the crease too, and turn the page into a lozenge.
            """
            left = c - depth
            pts = [(c, y0)]
            for k in range(9):
                t = k / 8.0
                pts.append((left - bow * math.sin(math.pi * t), y0 + span * t))
            pts.append((c, y1))
            return [v for p in pts for v in p]

        # The silhouette comes from one bowed polygon, drawn in the page's own
        # shade. The light on it is a short ramp beside the crease rather than
        # a wash across the whole leaf: paper catches the light where it bends
        # and is flat everywhere else, and a gradient spread over the full
        # width reads as a curtain instead of a fold. Bowing these as well
        # would draw the shading as a set of arcs - a rainbow, not a curve.
        cv.create_polygon(leaf(width), fill=shade(paper, 0.78), outline="")
        ramp = min(width, FOLD_LIGHT)
        for k in range(1, FOLD_BANDS + 1):
            t = k / float(FOLD_BANDS)
            cv.create_rectangle(c - ramp * (1.0 - t) - 1, y0, c, y1,
                                fill=shade(paper, 0.78 + 0.34 * t * t),
                                outline="")
        cv.create_line(c, y0, c, y1, fill=shade(paper, 0.62), width=2)
        cv.create_line(c - 1, y0, c - 1, y1, fill=shade(paper, 1.24), width=1)

    # ---------------------------------------------------------------- frames

    def _follow(self):
        """The note can be dragged out from under a colour change.

        Only the corner has to keep up. Every coordinate in here - the sheet,
        the words, where he stands, where he takes hold - is the note window's
        own, because the overlay is pinned to that window's corner, so moving
        the corner moves all of it and nothing has to be worked out again. One
        frame behind the note, exactly like the hands of a roamer hanging off
        a note somebody is dragging.
        """
        win = self.mascot.win
        at = (win.winfo_rootx(), win.winfo_rooty())
        if at == self._win_at:
            return
        self._win_at = at
        self.geometry("+%d+%d" % at)

    def _step(self, i):
        self._job = None
        beat, u = self._at(i)
        if beat == "done":
            self.finish()
            return
        try:
            self._follow()
            self.canvas.delete("all")
            self._frame(beat, u)
        except tk.TclError:
            return
        if beat == "drag" and u >= 1.0 - 1e-9:
            self._cover()
        try:
            self._job = self.after(FLIP_MS, self._step, i + 1)
        except tk.TclError:
            self._job = None

    def _frame(self, beat, u):
        here, facing, phase = self.corner, -TURNED, None
        lean = crouch = 0.0
        hand = fold = None

        if beat == "brace":
            # He has seen the swatch change and gathers himself. A beat of
            # anticipation is what stops the walk starting out of nothing.
            here = self.home
            facing = _mix(0.0, self._heading(self.out, 0.0) * WALKED, u)
            crouch = _swell(u) * 0.5
        elif beat == "walk":
            s = _smooth(u)
            here, way = self._along(self.out, s)
            facing = way * WALKED
            phase = s * self.out[2] / STEP_PX * math.pi
            lean = LEAN_PX * _accel(u) * (way or 1.0)
            crouch = 0.5 * max(0.0, 1.0 - 4.0 * u)          # pushing off
        elif beat == "turn":
            # He arrives and squares up to the note. From here on he is
            # working, and his back is to you.
            facing = _mix(self._heading(self.out, 1.0) * WALKED, -TURNED,
                          _smooth(u))
            lean = LEAN_PX * 0.5 * _spring(u, 1.6, 4.0)
        elif beat == "reach":
            # Down to the loose corner, and a good hold of it.
            crouch = _smooth(u) * 0.9
            hand = _mix2((self.corner[0], self.box[3] + 4), self._grip(0.0),
                         _smooth(u))
            lean = -2.0 * _smooth(u)
            fold = 0.0
        elif beat == "drag":
            # The work. He stays behind the crease and walks it across, facing
            # it the whole way and leaning into it - hardest at the start,
            # where the page still has to be got moving at all.
            s = _smooth(u)
            fold, hand = s, self._grip(s)
            here = (self._fold(s) + HEAD * 0.95, self.floor)
            facing = -TURNED
            phase = s * (self.box[2] - self.box[0]) / STEP_PX * math.pi
            lean = -LEAN_PX * (0.7 + 0.5 * max(0.0, _accel(u)))
            crouch = 0.9 * (1.0 - _smooth(min(1.0, u * 2.2))) + 0.16
        elif beat == "hold":
            fold, hand = 1.0, self._grip(1.0)
            here = (self._fold(1.0) + HEAD * 0.95, self.floor)
            lean = -LEAN_PX * 0.7
        elif beat == "fall":
            # He lets go and steps back off the sheet. The page drops under
            # its own weight and rocks once as it lands; his arm follows
            # through rather than stopping dead with it.
            fold = 1.0 - _drop(u)
            here = _mix2(self.pushed, self.spot, _smooth(u))
            lean = -LEAN_PX * 0.7 * _spring(u, 2.0, 4.5)
            crouch = 0.16 * _swell(u)
        elif beat == "about":
            here = self.spot
            facing = _mix(-TURNED, self._heading(self.back, 0.0) * WALKED,
                          _smooth(u))
            crouch = 0.3 * _swell(u)
        elif beat == "home":
            s = _smooth(u)
            here, way = self._along(self.back, s)
            facing = way * WALKED
            phase = s * self.back[2] / STEP_PX * math.pi
            lean = LEAN_PX * _accel(u) * (way or 1.0)
        elif beat == "arrive":
            # Back on his spot. The wobble is the last of the weight leaving.
            here = self.home
            facing = _mix(self._heading(self.back, 1.0) * WALKED, 0.0, _smooth(u))
            lean = LEAN_PX * 0.45 * _spring(u)
            crouch = 0.28 * _spring(u, 1.8, 6.0)

        self._last_at = here
        if fold is not None:
            self._paint_fold(fold, self.new_paper, self.new_ink)
        # He is standing on the side of the crease that has already turned, so
        # he turns with it: by the time the fold is across, so is he. Waiting
        # for the end of it and snapping is what read as him being repainted
        # separately from the note he is standing on.
        self._turned = 1.0 if self._did_cover else (fold or 0.0)
        turned = self._turned
        _walker(self.canvas, here[0], here[1], phase,
                blend(self.skin, shade(self.new_paper, 1.06), turned),
                blend(self.limb, shade(self.new_ink, 1.35), turned),
                blend(self.ink, self.new_ink, turned),
                facing=facing, hand=hand, lean=lean, crouch=crouch)

    @staticmethod
    def _heading(route, s):
        return _Flip._along(route, s)[1] or 1.0

    # The real figure has to get out of the way: two of him at once is worse
    # than no animation at all. Hiding beats deleting - the note itself is not
    # being redrawn, so his items have to still be there when this is over.

    def _hide_real(self):
        try:
            self.mascot.cv.itemconfigure("mascot", state="hidden")
            self.mascot.cv.itemconfigure("mascot_glint", state="hidden")
        except tk.TclError:
            pass

    def _show_real(self):
        try:
            self.mascot.cv.itemconfigure("mascot", state="normal")
            self.mascot.cv.itemconfigure("mascot_glint", state="normal")
        except tk.TclError:
            pass

    def _cover(self):
        """The fold is over the whole sheet: repaint it for real, right now."""
        if self._did_cover:
            return
        self._did_cover = True
        try:
            self.on_covered()
        except tk.TclError:
            pass
        self._hide_real()      # that repaint built the real figure again

    def finish(self):
        if self._done:
            return
        self._done = True
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
            self._job = None
        self._cover()
        self._show_real()
        self.mascot._swipe = None
        try:
            self.destroy()
        except tk.TclError:
            pass


class _Bubble(tk.Toplevel):
    """The speech bubble. Borderless and self-dismissing."""

    def __init__(self, note_window, text, ms=4500):
        tk.Toplevel.__init__(self, note_window)
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        colors = note_window._paper()
        paper, ink = colors["paper"], colors["ink"]
        frame = tk.Frame(self, bg=shade(paper, 1.05), highlightthickness=1,
                         highlightbackground=shade(ink, 1.6), padx=10, pady=6)
        frame.pack()
        label = tk.Label(frame, text=text, bg=shade(paper, 1.05), fg=ink,
                         font=note_window.f_ui)
        label.pack()
        for widget in (frame, label):
            widget.bind("<Button-1>", lambda _e: self.close())

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        # over his face, wherever on the note he happens to be holding on
        fx, fy = note_window.mascot.head_at()
        x = int(note_window.winfo_rootx() + fx - w / 2.0)
        y = int(note_window.winfo_rooty() + fy - HEAD - h)
        x = max(0, min(x, self.winfo_screenwidth() - w))
        self.geometry("+%d+%d" % (x, max(0, y)))
        self._timer = self.after(ms, self.close)

    def close(self):
        try:
            self.after_cancel(self._timer)
        except (tk.TclError, ValueError):
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class PointerTracker:
    """One timer for the whole app. See the note at the top of this file."""

    FAST_MS = 100      # pointer near a note: track it properly
    SLOW_MS = 200      # pointer moving anywhere else on the desktop
    IDLE_MS = 1200     # pointer parked: back off, this is the common case
    EMPTY_MS = 1500    # nothing on screen to look at
    REST_MS = 1500     # pointer still this long: stop polling fast
    WAKE_MIN_S = 0.06  # ceiling on how often a <Motion> may force a tick

    # Notes clipped to another application's window have to keep up with it
    # while it is being dragged, which the pointer rates above are far too
    # slow for. These only ever apply while something is actually pinned: with
    # no pins the tracker costs exactly what it did before.
    PIN_MS = 16        # a host window that moved on the last look
    PIN_IDLE_MS = 250  # one that did not

    # Somebody else's business, looked at on the same tick. The app hangs the
    # quick-capture hotkey here rather than owning a timer for it: the key
    # itself arrives without one, but the flag it sets has to be read
    # somewhere, and a second loop is a second thing to cancel at quit.
    ALSO_MS = 250      # ...and the slowest this may tick while one is set
    also = None        # a callable run on every tick, or None

    # 16ms is a frame. A window being dragged moves the whole time, and at
    # 40ms the note trailed it by a visible hand's breadth before catching up
    # - which reads as a note that is following the window rather than one
    # that is attached to it. It is one GetWindowRect and one move per frame,
    # and only while something is actually pinned.

    def __init__(self, root):
        self.root = root
        self.mascots = []
        self.pinned = []
        self._job = None
        self._last = None
        self._moved_at = 0.0
        self._resting = True
        self._last_wake = 0.0

    def register(self, mascot):
        if mascot not in self.mascots:
            self.mascots.append(mascot)
        self._arm(self.FAST_MS)

    def unregister(self, mascot):
        if mascot in self.mascots:
            self.mascots.remove(mascot)
        if not self.mascots and not self.pinned:
            self.stop()

    def follow(self, window):
        """Keep this note stuck to the window it is clipped to.

        The pending tick is thrown away and a fast one put in its place. _arm
        will not shorten a timer that is already set, so without this a note
        pinned while the tracker was dozing at 1.2s would sit there being left
        behind by its window, then jump - which does not look like a note that
        is attached to anything.
        """
        if window not in self.pinned:
            self.pinned.append(window)
        self._cancel()
        self._arm(self.PIN_MS)

    def unfollow(self, window):
        if window in self.pinned:
            self.pinned.remove(window)
        if not self.mascots and not self.pinned:
            self.stop()

    def _follow_pins(self):
        """Returns the delay the pins want, or None when there are none."""
        if not self.pinned:
            return None
        moved = False
        for window in list(self.pinned):
            try:
                moved = window.follow_host() or moved
            except tk.TclError:
                self.pinned.remove(window)
        return self.PIN_MS if moved else self.PIN_IDLE_MS

    def _cancel(self):
        """Drop any pending tick.

        Every path that is about to run or replace a tick goes through here.
        Setting _job to None without cancelling would leave the old timer
        armed, and a timer that outlives its window fires into a destroyed
        interpreter - the classic Tk 'invalid command name' at shutdown.
        """
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except (tk.TclError, ValueError):
                pass
            self._job = None

    def stop(self):
        self._cancel()

    def wake(self, _event=None):
        """Called from Tk's own <Motion>/<Enter> on a note, so the eyes are
        immediate where the pointer can actually see them.

        Motion events arrive at the mouse's report rate, which is far faster
        than we want to redraw, so the throttle here is what stops a hover
        being more expensive than the poll it is short-circuiting.
        """
        now = time.monotonic()
        if now - self._last_wake < self.WAKE_MIN_S:
            return
        self._last_wake = now
        self.tick()

    def _arm(self, delay):
        if self._job is not None:
            return
        if self.also is not None:
            delay = min(delay, self.ALSO_MS)
        try:
            self._job = self.root.after(delay, self.tick)
        except tk.TclError:
            self._job = None

    def tick(self):
        self._cancel()          # safe to call directly, from anywhere
        if self.also is not None:
            try:
                self.also()
            except Exception:
                pass            # never let a passenger stop the pointer
        pin_delay = self._follow_pins()
        if not self.mascots:
            self._arm(pin_delay or self.EMPTY_MS)
            return
        def arm(delay):
            self._arm(delay if pin_delay is None else min(delay, pin_delay))

        try:
            px, py = self.root.winfo_pointerxy()
        except tk.TclError:
            arm(self.SLOW_MS)
            return

        now = time.monotonic()
        for mascot in self.mascots:
            if mascot.idle_due(now):
                mascot.idle(now)

        if (px, py) == self._last:
            # The pointer has not moved. This branch is the whole performance
            # story: one call to read the pointer, then out. No visibility
            # checks, no geometry, no canvas. A parked pointer is what a
            # machine does most of the day, and a parked pointer is still
            # somewhere - so the eyes keep the aim they already have rather
            # than snapping back to centre.
            if not self._resting and (now - self._moved_at) * 1000.0 > self.REST_MS:
                self._resting = True
            arm(self.IDLE_MS if self._resting else self.SLOW_MS)
            return

        self._last = (px, py)
        self._moved_at = now
        self._resting = False

        live = [m for m in self.mascots if m.visible()]
        if not live:
            arm(self.EMPTY_MS)
            return
        near = False
        for mascot in live:
            near = mascot.look_at(px, py) or near
        arm(self.FAST_MS if near else self.SLOW_MS)
