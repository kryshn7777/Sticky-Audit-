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
  * most of those stretches are walked at somebody rather than at nowhere in
    particular, which is the only reason any of the rest of this ever happens
    - given a random leg each they drift apart and stay apart,
  * dropped beside a note he reaches out, takes hold of an edge and hangs
    there, swinging whenever the note is moved,
  * held, he is yanked up off the floor, trails the hand he is being carried
    by, and hops with a face on him if he is poked rather than picked up,
  * stood still with nothing on he stretches, yawns, scratches his head or
    has a look either way along the bar,
  * two, three or four of them on the floor together stop and hold a
    conversation entirely in gesture, one talking at a time - waving, counting
    it off, chopping at it, pointing or shrugging - and the rest watching him,
  * and none of them stands inside anybody: whoever is going somewhere makes
    the others make room,
  * one who turns up to a conversation already running stands at the edge of
    it and is never once acknowledged - unless he is the nosy sort, and then
    he sidles in until he is,
  * one who gets into the middle of it, by sidling or by being dropped there,
    is pointed at and laughed at, and stalks off with a face on him that takes
    a while to wear off,
  * one of three or more in a conversation sometimes has somewhere else to
    be, waves, says bye and goes, and those left finish it off without him,
  * some of the time what they have met up to do is kick a ball about, and
    whoever is nearest it is whoever chases it,
  * three or more of them light a fire, sit round it and talk until it burns
    out, and then stand up, say goodbye and walk off,
  * three or more of them with nothing built yet walk off the sides of the
    screen, come back carrying planks, put up a hut, and everybody on that
    floor files into it - wood carried or not,
  * right-clicking that hut offers to knock it down, and knocking it down
    brings everybody in it and everybody near it out screaming over a wreck
    that lies there a few seconds,
  * tick the last box on a note and whoever is near enough comes over to make
    something of it,
  * asked to sit with a note, he lights a fire under it and stays until it
    burns out, then waves and goes back to the paper,
  * and anything full-screen clears the lot of them off the bar until it is
    over - and lifting one of them over the others gets you a look from all
    of them.

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

The ball and the hut live in `yard.py`, which owns no timer either: `tick`
steps and paints it as part of the frame it is already running, and the last
of them going home takes the yard's window with it.
"""

import math
import random
import re
import time
import tkinter as tk

import winkit
import yard
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
# Each of them is a full-screen layered window of his own, which is what
# this is a cap on - not the crowd, which handles any number by breaking into
# groups. Three was too few to get four notes' worth of them out at once.
MAX_ROAMERS = 6

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

# ------------------------------------------------------------ standing about
# What he does with his hands when he has stopped somewhere and has nothing
# else on. Short on purpose: an idle that outlasts about two seconds stops
# reading as a man standing about and starts reading as a loop.
IDLE_EVERY = (2.5, 6.0)          # how long he stands still before one of these
IDLE_ACTS = ("stretch", "yawn", "scratch", "look")
IDLE_S = {"stretch": 1.5, "yawn": 1.7, "scratch": 1.4, "look": 2.0}

# ---------------------------------------------------------------- in the hand
GRAB_S = 0.22           # the yank up off the floor, before the thrashing
DRAG_SWING = 90.0       # px/s of hand for one unit of trailing lean
SWING_MAX_LEAN = 9.0
TAP_S = 0.30            # picked up and put down again inside this is a poke
TAP_SLOP = 6.0          # ...and he has to not have been carried anywhere
STARTLE_S = 0.9         # how long the face he gives you for it lasts
STARTLE_VY = 300.0      # ...and the hop that goes with it

# ----------------------------------------------------------- personal space
# A body is HEAD wide and this is a shade under it: two of them any closer
# than this and one is standing in the other. Deliberately less than half of
# CHAT_GAP, because the man who walks into the middle of a conversation stands
# exactly there - shove him out of that gap and the scene he is meant to
# interrupt never happens.
SPACE_R = 28.0
SPACE_PUSH = 1.0        # px a frame of shuffling, so it reads as making room
# Everybody stood on the floor takes part in this. What is left out is as
# deliberate: "held" and "fall" are somebody's hand and the physics, "grip"
# and "reach" are on a note rather than on the floor, "inside" is a withdrawn
# window, "leave" is a jump off the bar, and "enter" is a queue at one door -
# shoving them apart there stops them ever reaching it.
SPACE_STATES = ("rest", "walk", "sleep", "chat", "watch", "panic", "stomp",
                "bye", "wtf", "fetch", "cheer", "vigil", "sing", "phone",
                "beaten")
# ...but only these are moved by it. A man on his way somewhere is not shoved
# off his line: he makes the other one make room and carries on. Both of them
# giving way deadlocks an errand - two of them walking the wood home from the
# same edge have to pass each other, and every shove moved the man in front
# further along, so the one behind chased him the length of the bar and the
# hut never went up.
# A man sitting with a note is not moved off his fire either: he is where he
# is for twenty-five minutes, and the others can walk round him.
SPACE_SHUFFLE = ("rest", "sleep", "chat", "watch", "wtf", "cheer", "sing",
                 "phone", "beaten")

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
CHAT_STAGGER = 30.0     # ...one of them held back this much, sometimes
LATE_ODDS = 0.35        # how often somebody is the one held back
RALLY_R = CHAT_R * 3.0  # how far off they will wait for one more to arrive
WATCH_R = 220.0         # near enough to a conversation to turn round for it
SEEK_ODDS = 0.75        # how much of a walk is aimed at somebody
NOSY_ODDS = 0.35        # ...and how much of the watching turns into barging in
CREEP_SPEED = WALK_SPEED * 0.8   # sidling in is slower than walking, but
                                 # not so slow he never arrives: a talk is
                                 # over in four seconds
TALK2 = (("approach", 34), ("greet", 20), ("say0", 52), ("react", 26),
         ("say1", 46), ("agree", 24), ("part", 30))
TALK3 = (("approach", 34), ("greet", 20), ("say0", 46), ("react", 22),
         ("say1", 42), ("react", 22), ("say2", 44), ("agree", 24),
         ("part", 30))
TALK4 = (("approach", 34), ("greet", 20), ("say0", 44), ("react", 20),
         ("say1", 40), ("react", 20), ("say2", 40), ("react", 20),
         ("say3", 42), ("agree", 24), ("part", 30))
# By how many of them are in it. Four is the ceiling: past that they are a row
# rather than a group, the ones on the ends are too far apart to be looking at
# each other, and the last of them waits half a minute for a turn.
TALK = {2: TALK2, 3: TALK3, 4: TALK4}
MAX_CAST = 4
# Shorter than a conversation on purpose. Cruelty is quick.
MOCK = (("notice", 18), ("point", 40), ("laugh", 54), ("burn", 30),
        ("storm", 26))
# The two left behind pick it up from `wave` and take it to a close. Shorter
# than what it replaces on purpose: they were three sentences into a
# conversation, and this is the end of one, not the start of another.
FAREWELL = (("wave", 24), ("say0", 40), ("agree", 22), ("part", 30))

# Which role is talking, by beat name. Everything else about a scene - who
# looks at whom, who laughs, who is left standing - falls out of this and the
# cast order, which is why the three scenes differ only by data.
#
# say_a and say_b became say0 and say1 because the speaker is an index now
# rather than a bool. react_b became react because the rule that made it work
# for two - the one who just spoke thinks, everybody else laughs - was already
# the rule for any number of them.
SPEAKS = {"say0": 0, "say1": 1, "say2": 2, "say3": 3}

# What his hands do while he has the floor. One of these a sentence, picked on
# the frame the sentence starts: picked per frame it strobes, and picked once
# for the whole scene he makes the same shape three times running, which reads
# as a loop rather than as a man talking.
TALK_GESTURES = ("wave", "both", "count", "chop", "point", "shrug")


def _beat_start(table, name):
    """The frame a named beat begins on, or None.

    Worked out rather than written down: retiming a table by a frame would
    otherwise quietly move something that is meant to land on the start of a
    sentence to somewhere in the middle of the one before it.
    """
    i = 0
    for beat, n in table:
        if beat == name:
            return i
        i += n
    return None


# ---------------------------------------------------------- excusing yourself
BOW_ODDS = 0.35         # how often a group of three or more is one of them
                        # leaving early
BYE_S = 0.9             # the wave, before he turns and goes

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

# ----------------------------------------------------------------- a campfire
# Longer than anything else they do, and meant to be: a fire is the one scene
# where the point is that nobody is going anywhere. They walk to a place round
# it, sit down, talk while it burns, watch it go out, get up, say goodbye and
# leave - and every one of those is a beat rather than a state, because the
# only thing that has to be true is that the fire dies before they stand.
FIRE = (("gather", 140), ("sit", 40), ("say0", 118), ("react", 46),
        ("say1", 112), ("react", 46), ("say2", 118), ("react", 46),
        ("say3", 112), ("dim", 74), ("stand", 40), ("part", 54))
FIRE_ODDS = 0.20
FIRE_SEAT = 46.0        # how far out from the flame the nearest of them sits
FIRE_ROW = 34.0         # ...and how much further out the pair behind them are
SIT_DROP = 13.0         # how far his hips come down when he sits
FIRE_LOOK = 14.0        # the flame is looked at a little above the wood
# The fire has exactly as long in it as the table takes to reach the beat they
# stand up on. Worked out rather than written down twice: retiming a beat by a
# frame would otherwise leave them sitting in the dark, or standing up in the
# firelight and walking off from a fire that is still going.
FIRE_S = _beat_start(FIRE, "stand") * FRAME_S

# ...and the one you ask for. A fire that burns for as long as you meant to
# work: no countdown, no bar, no notification - the taskbar shows how much of
# it is left, and when it is out he says goodbye and goes back to the note.
FOCUS_S = 25.0 * 60.0
VIGIL_WAVE_S = 1.1      # the goodbye at the end of it

# ---------------------------------------------------------------------- a hut
# The agreement is a scene; the errand is not. He keeps his scene through the
# whole of it, so a hand closing on any one of the three still tears the
# build down the way it tears down a conversation.
BUILD = (("agree", 30), ("send", 6))
BUILD_ODDS = 0.20
FETCH_SPEED = WALK_SPEED * 2.2   # eager, and it is a long way to the edge
FETCH_OFF = 130.0                # how far past the edge before he is out of it
FETCH_GONE_S = 1.2               # ...and how long he is out there for
FETCH_MAX_S = 60.0               # the errand has gone wrong: come to your senses
PLANK_W, PLANK_H = 44.0, 7.0
INSIDE_S = (14.0, 26.0)

# -------------------------------------------------------------- it came down
PANIC_S = 3.2           # how long the running lasts
PANIC_FACE_S = 2.5      # ...and how long it takes his face to come back
PANIC_TURN = 0.45       # he changes his mind about which way this often
PANIC_SPEED = WALK_SPEED * 2.6
HUT_SPILL = 34.0        # how far apart they come out

# ------------------------------------------------------------- a bit of a run
# Running: on his own, or after somebody who is running from him. One set of
# numbers for both, because they are the same legs - all that changes is who
# picks the direction. He turns at the walls rather than stopping at them, so
# a chase that reaches the end of the bar comes back down it instead of
# ending in a corner.
RUN_S = 6.0
RUN_SPEED = WALK_SPEED * 2.4
RUN_LEAN = 5.0          # further over than a stomp: he is leaning into it
RUN_BOB = 3.0           # ...and how far each stride throws him off the floor
CHASE_GAP = 34.0        # the one behind holds off rather than standing on him

WTF_ABOVE = 46.0        # his head this far over mine before it counts
WTF_NEAR = 200.0        # ...and still near enough that it is about me
WTF_HOLD = 0.22         # held this long, so a flick past does not trip it
WTF_S = 1.6
WTF_TURN = 8.0          # frames to come round and face the front

# ---------------------------------------------------------------- how he feels
# A mood is a face held over whatever else he is doing, the way the anger
# after being laughed at already outlives the stomping off. Four of them, by
# name, because that is what the rest of the app wants to say: he is happy,
# sad, angry, sleepy. Anything that wants him to look a particular way asks
# for a mood rather than reaching into FACES.
MOOD_FACE = {"happy": "happy", "sad": "sad", "angry": "cross", "sleepy": "dozy"}
MOODS = tuple(MOOD_FACE)
MOOD_S = 25.0           # how long one colours him for
MOOD_MIX = 0.75         # ...and how much of his face it takes over

# --------------------------------------------------------------- what he can do
# Everything any of them can be asked to perform, and how long it lasts. The
# names are the app's vocabulary: act(guy, "sing"). "sleep" and "celebrate"
# are here too even though they were already states, so that a caller never
# has to know which of these existed first.
ACTS = {
    "sleep": None,          # until something wakes him
    "celebrate": None,      # CHEER_S, from the state itself
    "sing": 7.0,
    "fight": 4.5,
    "beaten": 5.0,
    "phone": 9.0,           # typing on it
    "call": 9.0,            # ...and talking into it
    "run": RUN_S,           # on his own; chase() is two of them
    "clap": None,           # both of these run as long as the song does
    "dance": None,
}
SING_LINES = ("\u266a", "\u266b")     # what floats over his head while he sings

# ------------------------------------------------------------- and the rest
# Nobody sings at nobody. Whoever is near enough to hear it joins in - some
# of them clap along and some of them dance, and both last exactly as long as
# the song does, so it ends the way it started rather than trailing off one
# man at a time.
SONG_EVERY = (70.0, 160.0)      # how often one of them starts one
SONG_NEAR = 300.0               # how far off it is worth listening to
CLAP_ODDS = 0.55                # ...and how many of them clap rather than dance
CLAP_HZ = 2.2                   # the beat, and everything is on it
CLAP_REACH = 15.0               # how far apart his hands get between claps
DANCE_HZ = 1.1
DANCE_STEP = 15.0               # how far the dance takes him either way
DANCE_HOP = 5.0                 # ...and how far off the floor
PHONE_W, PHONE_H = 9.0, 15.0
PHONE_C = "#2A241C"
SWING_HZ = 5.5          # how fast a scrap goes
DUST_R = 9.0            # ...and how far the scuffle throws him about

# ------------------------------------------------------ starting on somebody
# One of them takes against another for no reason either of them could name.
# He comes over, squares up and jabs at the air in front of the other man's
# face - all threat and no contact, the same cartoon rules a scrap runs on.
# What comes back is the other man's business: he is baffled first, and then
# he either walks off wondering what that was about or he has had enough of
# it and there is a scrap after all.
PROVOKE_NEAR = 46.0             # how close he comes before he starts
PROVOKE_SPEED = WALK_SPEED * 1.6
PROVOKE_MAX_S = 12.0            # ...and how long he follows before giving up
SHOVE_S = 2.4                   # how long the squaring up lasts once he is there
SHOVE_HZ = 3.5                  # ...and how often a fist goes out
BAFFLED_S = SHOVE_S + PROVOKE_MAX_S + 2.0   # the other man is never stuck
FIGHT_BACK = 0.5                # how often being started on gets an answer
FIGHT_BACK_STEP = 90.0          # how far off he walks when it does not

# ------------------------------------------------------------------ the fun
# None of it asked for and none of it load-bearing, which is the point.
POUNCE_EVERY = (50.0, 130.0)    # how often one of them stalks the pointer
STALK_R = 420.0                 # how far off the pointer catches his eye
POUNCE_NEAR = 34.0              # close enough: down, wiggle, and go
STALK_SPEED = WALK_SPEED * 0.55
WIGGLE_S = 0.6                  # the wind-up before the leap
RACE_EVERY = (140.0, 300.0)     # how often somebody suggests a race
RACE_MIN = 3                    # fewer than this is just two men running
RACE_SET_S = 2.4                # the three-two-one
RACE_TRIP = 0.5                 # how often somebody goes over mid-race
PILE_EVERY = (8.0, 15.0)        # how often the sleepy look for each other
PILE_R = 46.0                   # how wide a heap of them is
ICE_EVERY = (160.0, 340.0)      # how often the van finds this street
SWEET_HASTE = 0.45              # happy notes bring it round sooner
QUEUE_GAP = 34.0                # a place each in the queue
SERVE_S = 1.2                   # one cone's worth of serving
LICK_S = 6.0                    # how long a cone lasts
PARTY_S = 20.0                  # how long the hats stay on
HAT_H = 12.0
HAT_C, POM_C = "#E8B33C", "#D6453C"
CONE_C, SCOOP_C = "#D9A05B", "#F2B8CB"
BDAY_WORDS = ("birthday", "bday")

# ------------------------------------------------------- what he reads
# The note colours the man who lives on it. Type anger onto a sheet and
# whoever came off it walks about with a bold grin looking for a scrap; type
# sadness and he wants nothing to do with one and runs when one starts. The
# temper is one of the four moods the app already speaks, worked out from
# the words, and it stays on him for as long as the words say so - a mood
# wears off, a temper is re-read from the page.
TEMPER_WORDS = {
    "angry": ("angry", "anger", "mad", "furious", "fury", "rage", "raging",
              "hate", "hatred", "annoyed", "annoying", "pissed", "livid",
              "fuming", "grr", "argh"),
    "sad": ("sad", "sadness", "unhappy", "depressed", "depressing", "down",
            "miserable", "crying", "cried", "tears", "heartbroken", "lonely",
            "gloomy", "grief", "sorrow", "sorry"),
    "happy": ("happy", "happiness", "joy", "joyful", "yay", "excited",
              "exciting", "great", "awesome", "wonderful", "love", "loved",
              "lovely", "glad", "hooray", "woohoo"),
    "sleepy": ("sleepy", "sleep", "tired", "exhausted", "drowsy", "yawn",
               "zzz", "nap", "snooze", "knackered"),
}
SCARE_R = 260.0         # how close a scrap has to be before a sad man runs
KEEN_HASTE = 0.25       # how much sooner trouble comes with an angry man idle
DOZY_HASTE = 0.3        # ...and how much sooner a sleepy one nods off
GRUMP_ODDS = 0.75       # how often an angry note wants no part of the fun
GRUMP_S = 25.0          # how long a "no" stays a no
PIZZA_WORDS = ("pizza", "hungry", "starving")
PICNIC_S = 14.0         # how long the box lasts once it is open
SEAT_GAP = 26.0         # a place each around the box
BITE_HZ = 0.55          # how fast a slice goes up and down
BOX_W, BOX_H = 22.0, 7.0
BOX_C = "#D9B36C"       # cardboard
CRUST_C = "#E8B33C"
PEP_C = "#C24A42"
# The bold grin: his own anger face, but pleased about it. Brows still down,
# mouth turned all the way up.
GRIN = FACES["cross"]._replace(curve=0.9, mouth=0.9, eye=0.85, open=0.0)


def temper_of(text):
    """What the words on a note do to whoever lives on it. None for nothing.

    Whole words only - a man does not come off a note about things he has
    made in a rage - and the feeling named most wins.
    """
    low = text.lower()
    best, count = None, 0
    for mood in MOODS:
        hits = sum(len(re.findall(r"\b%s\b" % word, low))
                   for word in TEMPER_WORDS[mood])
        if hits > count:
            best, count = mood, hits
    return best


def _has_bday(text):
    low = text.lower()
    return any(re.search(r"\b%s\b" % word, low) for word in BDAY_WORDS)


def _has_pizza(text):
    low = text.lower()
    return any(re.search(r"\b%s\b" % word, low) for word in PIZZA_WORDS)


def _order_pizza(guy, now):
    """The note says pizza, and somebody has to go and get one.

    The man whose note it is goes himself - it is his stomach - and the
    sharing happens when he is back: see _serve_picnic. Busy men skip the
    errand; the word already counted, so it is not retried every keystroke.
    """
    if guy.state not in ("rest", "walk", "chat", "watch") or guy.floor is None:
        return
    x1, x2 = guy._walls()
    guy._leave_scene(now)
    guy._watching = None
    guy._site_x = _clamp(guy.x, x1 + 60.0, x2 - 60.0)
    guy._begin("errand", now)


def _serve_picnic(host, now):
    """He is back with the box. Everybody peckish sits down to it.

    Seats alternate either side of the box, nearest first, so a crowd rings
    it rather than queueing off one end - and an angry note mostly stays
    stood where he is, the same as with every other bit of fun.
    """
    eaters = [host]
    for one in crew:
        if (one is not host and one.floor is not None
                and one.state in ("rest", "walk", "chat", "watch")
                and abs(one.x - host.x) <= SONG_NEAR
                and _game(one, now)):
            eaters.append(one)
    for i, one in enumerate(eaters):
        one._leave_scene(now)
        one._watching = None
        one._begin("picnic", now)
        one._queue_i = i
        one._site_x = host._site_x
        side = -1.0 if i % 2 else 1.0
        one._lick_x = host._site_x + side * SEAT_GAP * (i // 2 + 1)
    host.prop = "pizza_open"
    host.feel("happy")


def _party(guy, now):
    """Somebody's note says birthday, and that is worth a fuss.

    Hats for everybody near enough to count as at the party, the man himself
    up celebrating, the rest brought over the way a finished list brings
    them - and one of them starts a song, which the sing-along machinery
    turns into the whole room clapping by itself.
    """
    for one in crew:
        if one is guy or (abs(one.x - guy.x) <= APPLAUD_R
                          and _game(one, now)):
            one._hat_until = now + PARTY_S
    others = [one for one in crew if one is not guy
              and one.state in ("rest", "walk", "chat", "watch")
              and _game(one, now)]
    if others:
        random.choice(others).perform("sing")
    guy.feel("happy")
    guy.perform("celebrate")
    applaud(guy.x, guy.home_id)


def _game(guy, now):
    """Whether he can be talked into the fun. An angry note mostly cannot.

    One roll per invitation, remembered: a man who has said no to a song is
    not asked again every frame until he caves, he is left alone to scowl.
    Everybody else always says yes - the roll is only for the angry.
    """
    if guy._grump_until > now:
        return False
    if guy.temper != "angry" or random.random() >= GRUMP_ODDS:
        return True
    guy._grump_until = now + GRUMP_S
    guy._say("hmph")
    guy.feel("angry")
    return False


def retune(note_id, text):
    """The note has been retyped; whoever came off it reads the room.

    Called from the note's _capture, which every change to the body funnels
    through, so the temper always matches what the sheet currently says.
    A birthday is the exception to "matches": it is a one-shot party when
    the word arrives, not a state held for as long as it stays.
    """
    guy = for_note(note_id)
    if guy is None:
        return None
    bday = _has_bday(text)
    if bday and not guy._bday_done:
        guy._bday_done = True
        _party(guy, _time())
    elif not bday:
        guy._bday_done = False
    pizza = _has_pizza(text)
    if pizza and not guy._pizza_done:
        guy._pizza_done = True
        _order_pizza(guy, _time())
    elif not pizza:
        guy._pizza_done = False
    guy.temper = temper_of(text)
    if guy.temper is not None:
        guy.feel(guy.temper)
    return guy.temper


# --------------------------------------------------------- calling it in
# What happens after a scrap, and sometimes in the middle of one. A man who
# is still sat down when the fighting is over gets noticed by whoever is
# nearest: he comes over, phones for an ambulance and stands out of the way
# while the pair of them carry his mate off. A scrap that is still going gets
# called in the other way about one time in three, and then two men who were
# swinging at each other suddenly have somewhere else to be.
#
# The vehicle itself is a prop and lives in the yard. Everything here is the
# half of it that is people: who calls, who gets carried, who runs.
ANGER_EVERY = (75.0, 180.0)     # how often one of them takes against another
ANGER_NEAR = 220.0              # ...and how near the other has to be for it
HELP_NEAR = 320.0               # how far off a man on the floor is noticed
HELP_STAND = 78.0               # how close whoever phones it in stands
HELP_WALK = WALK_SPEED * 1.7    # he does not amble over to an emergency
HELP_MAX_S = 8.0                # ...and gives up walking over after this
CALL_S = 2.4                    # how long he is on the phone
POLICE_ODDS = 0.35              # how often a scrap gets called in
CASUALTY_S = 14.0               # how long a man lies there waiting to be got
FLEE_SPEED = RUN_SPEED * 1.3    # ...and how fast they go once it turns up
FLEE_OFF = 150.0                # how far past the edge before they are gone
VAN_PATIENCE = 20.0             # the whole pick-up, however it goes

# ------------------------------------------------------------ a finished list
# The last box on a note has just been ticked. Whoever is near enough to have
# seen it comes over and makes something of it; the man who came off that note
# joins in from wherever he is, because it is his note.
APPLAUD_R = 340.0       # how far off he notices
CHEER_S = 2.6           # how long the fuss lasts
CHEER_NEAR = 60.0       # ...and how close to the note he does it
CHEER_GAP = 52.0        # a place each, so two of them are not one shape

# ------------------------------------------------------------------ off screen
# Something has gone full-screen: a video, a game, a slide deck, somebody's
# shared window. They clear off the bar rather than sitting on top of it, and
# they come back to where they were standing once it is over. Checked twice a
# second off the tick the crew is already running - the call is one
# GetForegroundWindow and one GetWindowRect, and asking every frame would be
# sixty of each for a thing that changes about once an hour.
SHY_EVERY = 0.5
SHY_SPEED = WALK_SPEED * 2.4    # he does not amble off while you are waiting
SHY_OFF = 120.0                 # how far past the edge before he is out of it

# ------------------------------------------------------------------- goodbye
CROUCH_S = 0.16         # the wind-up. Without it he teleports upwards
LEAVE_VX = 420.0
LEAVE_VY = 1150.0
LEAVE_MAX_S = 5.0       # he is gone by now whatever the screen says

# ------------------------------------------------------- not taking it well
STOMP_S = 2.5           # how long he keeps it up
STOMP_SPEED = WALK_SPEED * 1.35
CROSS_S = 10.0          # ...and how long the face lasts after he stops
MOCK_COOLDOWN = 150.0

# ------------------------------------------------------------------- the crew
crew = []
scenes = []
shy = False             # something full-screen is up and they are off the bar
_anger_at = 0.0         # when one of them next takes against another
_pounce_at = 0.0        # when the pointer next gets stalked
_race_at = 0.0          # when somebody next suggests a race
_ice_at = 0.0           # when the van next comes round
_pile_at = 0.0          # when the sleepy next look for each other
_scoop_at = 0.0         # when the next cone comes over the counter
_racers = []            # everybody in the current race
_race_order = []        # ...and the order they came home in
_race_t0 = None         # when the gun goes
_race_tripped = None    # whoever went over, owed a sit-down
_song_at = 0.0          # ...and when one of them next starts singing
_scrap_seen = None      # the scrap the law has already been offered
_shy_at = 0.0
_job = None
_root = None
STEP = None             # tests pin the step so the physics repeats exactly
SPONTANEOUS = True      # ...and everything they start themselves: scraps,
                        # ambulances, songs. Pinned off by the suite.
_stamp = None
_last = None            # the last frame the yard was stepped on


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

    __slots__ = ("kind", "table", "cast", "i", "mid", "last_speaker",
                 "victim", "gone_way", "gesture", "beat_was")

    def __init__(self, kind, table, cast):
        self.kind = kind
        self.table = table
        self.cast = list(cast)
        self.i = 0
        self.mid = sum(g.x for g in self.cast) / float(len(self.cast))
        self.last_speaker = None
        # Held by name rather than read off the end of the cast: somebody
        # lifted out of a scene is taken out of the cast before it is closed,
        # and then the last one left in it is a mocker.
        self.victim = None
        # Which way the one who excused himself went, so the two left wave
        # after him rather than at each other.
        self.gone_way = 0.0
        # What the speaker is doing with his hands, and the beat it was chosen
        # for. Held on the scene rather than on him because the listeners have
        # to see the same one he is making.
        self.gesture = TALK_GESTURES[0]
        self.beat_was = None

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

    def seat_x(self, guy):
        """Where he sits round a fire: either side of it, nearest pair first.

        Not the conversation's row, which would sit all of them in a line with
        the flame at one end. Sides alternate so that three of them read as a
        ring rather than as a queue, and the second man on a side sits further
        out so nobody is behind anybody.

        Handed out left to right rather than by cast order: the places are the
        same either way, but this way nobody walks past the fire and the other
        two to reach one on the far side.
        """
        places = sorted(self.mid + (-1.0 if k % 2 == 0 else 1.0)
                        * (FIRE_SEAT + (k // 2) * FIRE_ROW)
                        for k in range(len(self.cast)))
        return places[self.cast.index(guy)]


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
    scene.victim = guy
    guy.scene = scene
    guy.role = len(scene.cast) - 1
    guy._watching = None
    guy._stir_at = now
    guy._begin("chat", now)


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
        # Worked out off the table he is actually in rather than off one
        # table's numbers: a cast of four runs a longer one, and its second
        # speaker does not begin on the frame a three's does.
        if (len(scene.cast) >= 3 and scene.i == _beat_start(scene.table, "say1")
                and random.random() < BOW_ODDS):
            # Never the one about to speak. Cutting somebody off mid-sentence
            # is what the mock does, and this is meant to be the opposite of
            # it: he waits for a gap, the way people do.
            speaker = scene.speaker()
            going = [g for g in scene.cast if g is not speaker]
            if going:
                _bow_out(scene, random.choice(going), now)
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
    # And anybody else stood on the same floor with nothing on. A hut with one
    # of them left outside it reads as him having been forgotten rather than
    # as him not fancying it - he did not carry a plank, but he is not going
    # to be the only man on the bar with nowhere to be.
    floor = scene.cast[0].floor
    for guy in crew:
        if (guy.scene is None and guy.floor is not None
                and abs(guy.floor - floor) < 4.0
                and guy.state in ("rest", "walk", "sleep", "watch")):
            guy._watching = None
            guy._begin("enter", now)
    # _close leaves anybody who is not mid-conversation alone, so they keep
    # walking to the door rather than being sent off in three directions.
    _close(scene, now)


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


def _close(scene, now):
    """Everybody out, and away in different directions.

    Sent off from here rather than each finding out for himself: the next one
    to step would see his cast already walking and take it for having been
    abandoned mid-sentence.
    """
    if scene in scenes:
        scenes.remove(scene)
    if scene.kind == "footy":
        yard.drop_ball()
    if scene.kind == "fire":
        # Out with them. A fire still burning after everybody who lit it has
        # been lifted off the bar is a fire nobody is at.
        yard.douse()
    # Sometimes one of them is held back off the cooldown. All of them coming
    # free together is a group that always reforms whole, and there is never
    # an odd one out to be left watching or walked in on; all of them held
    # back by a different amount is the opposite, and a three-way never
    # happens at all. So it is one of them, some of the time. An empty cast
    # is a scene everybody has already been lifted out of, and there is
    # nobody left to hold back.
    late = (random.choice(scene.cast)
            if scene.cast and random.random() < LATE_ODDS else None)
    for guy in list(scene.cast):
        was_mocked = scene.kind == "mock" and scene.victim is guy
        guy.scene = None
        guy.role = 0
        guy._social_at = now + (CHAT_STAGGER if guy is late else 0.0)
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
    # Whoever was stood watching it is left standing where they left him.
    for guy in crew:
        if guy._watching is scene:
            guy._watching = None
            if guy.state == "watch":
                guy._begin("rest", now)


def tick():
    """One step for everybody. Safe to call directly, which is how the tests
    drive it."""
    global _stamp, _last
    _cancel()
    if not crew:
        return
    if STEP is None:
        _stamp = None
        now = _time()
    else:
        _stamp = (time.monotonic() if _stamp is None else _stamp) + STEP
        now = _stamp
    # The yard has no clock of its own on purpose: one timer serves the crew,
    # and a ball is part of the same frame they are.
    last = _last
    dt = STEP if STEP is not None else min(now - (_last or now), MAX_STEP)
    _last = now
    _watch_the_screen(now)
    _cast(now)
    _trouble(now)
    # The referee runs outside the spontaneous gate: a race somebody started
    # by hand still finishes with the switch off.
    _run_race(now)
    # Before they step, not after: a position fixed after the frame is drawn
    # is a frame of them overlapping, every frame.
    _space_out()
    delay = SLEEP_MS
    for guy in list(crew):
        try:
            delay = min(delay, guy.step(now))
        except tk.TclError:
            guy.vanish()
    # After the loop, not before it: that keeps the first tick of a scene
    # reading beat zero, which is what the old per-roamer counter did.
    for scene in list(scenes):
        _advance(scene, now)
        if scene in scenes:
            scene.i += 1
    # Both clocks: the frame for the physics, the real gap for anything with
    # a life on it. See _Fire.step.
    yard.step(dt, min(now - (last or now), 3600.0))
    yard.paint()
    _arm(delay)


def _due(name, every, now, scale=1.0):
    """One recurring clock, by module-global name.

    The first look only winds it - a crew four frames old has not had time
    to want anything - and every firing winds the next.
    """
    at = globals()[name]
    if at == 0.0 or now >= at:
        globals()[name] = now + random.uniform(*every) * scale
        return at != 0.0
    return False


def _fun(now):
    """Everything that happens for no reason except that it is funny."""
    if _due("_pounce_at", POUNCE_EVERY, now):
        spot = _pointer()
        if spot is not None and not any(g.state == "held" for g in crew):
            px, py = spot
            cats = [guy for guy in crew if guy.state in ("rest", "walk")
                    and guy.floor is not None
                    and abs(py - guy.floor) < 90.0
                    and POUNCE_NEAR < abs(px - guy.x) < STALK_R]
            if cats:
                cat = min(cats, key=lambda guy: abs(guy.x - px))
                cat._leave_scene(now)
                cat._watching = None
                cat._begin("stalk", now)
    if _due("_race_at", RACE_EVERY, now):
        race(now)
    sweet = any(guy.temper == "happy" for guy in crew)
    if _due("_ice_at", ICE_EVERY, now, SWEET_HASTE if sweet else 1.0):
        idle = [guy for guy in crew
                if guy.state in ("rest", "walk", "chat", "watch")
                and guy.floor is not None]
        if len(idle) >= 2 and yard.van() is None and not _racers:
            mid = sum(guy.x for guy in idle) / len(idle)
            yard.call_van("icecream", mid, idle[0]._floor_y())
    if _due("_pile_at", PILE_EVERY, now):
        # A conversation is no protection here either: a sleepy man mid-chat
        # is a man about to fall asleep mid-chat.
        dozy = [guy for guy in crew if guy.temper == "sleepy"
                and guy.state in ("rest", "walk", "chat")
                and guy.floor is not None]
        if len(dozy) >= 2:
            # The sleepy find each other and go down in a heap.
            mid = sum(guy.x for guy in dozy) / len(dozy)
            dozy.sort(key=lambda guy: guy.x)
            for i, guy in enumerate(dozy):
                spot = mid + (i - (len(dozy) - 1) / 2.0) * (PILE_R * 0.8)
                if abs(guy.x - spot) <= 12.0:
                    guy._leave_scene(now)
                    guy._begin("sleep", now)
                else:
                    guy._leave_scene(now)
                    guy._begin("walk", now)
                    x1, x2 = guy.walk_line
                    guy._goal = _clamp(spot, x1, x2)


def _trouble(now):
    """Scraps nobody asked for, and whatever turns up because of one.

    Decided here for the whole crew rather than by each of them, for the same
    reason the pairing is: two men who each phone for an ambulance have
    called two ambulances, and the second one has nobody to pick up.
    """
    global _anger_at, _scrap_seen, _song_at
    if not SPONTANEOUS:
        return
    _join_in(now)
    _fun(now)
    van = yard.van()
    if van is not None:
        _mind_the_van(van, now)
        return
    if any(guy.state == "help" for guy in crew):
        return                      # somebody is already on the phone
    hurt = [guy for guy in crew if guy.state == "beaten"]
    if hurt and _send_for(hurt[0], "medic", hurt[0].x, now):
        return
    # A scrap gets called in once, when it starts, or not at all. Rolling
    # every frame is a police car every scrap and a certainty dressed up as
    # a chance.
    fighting = [guy for guy in crew if guy.state == "fight"]
    if len(fighting) >= 2:
        # Anybody sad enough is not staying to watch it.
        mid = sum(guy.x for guy in fighting) / len(fighting)
        for guy in crew:
            if (guy.temper == "sad" and guy.floor is not None
                    and guy.state in ("rest", "walk", "watch", "chat")
                    and abs(guy.x - mid) < SCARE_R):
                guy._leave_scene(now)
                guy._watching = None
                guy._begin("run", now)
                guy._run_way = 1.0 if guy.x >= mid else -1.0
                guy._until = now + 3.0
        mark = round(min(guy.since for guy in fighting), 3)
        if mark != _scrap_seen:
            _scrap_seen = mark
            if random.random() < POLICE_ODDS:
                mid = sum(guy.x for guy in fighting) / len(fighting)
                _send_for(fighting[0], "police", mid, now)
        return
    # ...and every so often, one of them takes against another for no reason
    # anybody could name. The first tick only sets the clock: a crew that has
    # been up for four frames has not had time to fall out yet.
    # A song, every so often, from whoever is stood about. The first tick
    # only winds the clocks: a crew that has been up for four frames has had
    # no time to fall out with anybody or to burst into song.
    if _song_at == 0.0:
        _song_at = now + random.uniform(*SONG_EVERY)
    elif now >= _song_at:
        _song_at = now + random.uniform(*SONG_EVERY)
        idle = [guy for guy in crew if guy.state in ("rest", "walk")
                and _game(guy, now)]
        sunny = [guy for guy in idle if guy.temper == "happy"]
        if idle:
            random.choice(sunny or idle).perform("sing")
            return
    if _anger_at == 0.0:
        _anger_at = now + random.uniform(*ANGER_EVERY)
        return
    if now < _anger_at:
        return
    # A conversation is no protection: half the point of it is that it comes
    # out of nowhere, and being talked at is a reason as good as any.
    idle = [guy for guy in crew
            if guy.state in ("rest", "walk", "chat") and guy.floor is not None]
    keen = [guy for guy in idle if guy.temper == "angry"]
    # An angry note on the desk keeps the peace short.
    _anger_at = now + random.uniform(*ANGER_EVERY) * (KEEN_HASTE if keen
                                                      else 1.0)
    if len(idle) < 2:
        return
    calm = [guy for guy in idle if guy.temper != "sad"]
    if not calm:
        return                  # a bar full of sad men starts nothing
    bully = random.choice(keen or calm)
    near = [guy for guy in idle
            if guy is not bully and abs(guy.x - bully.x) <= ANGER_NEAR
            and abs(guy.floor - bully.floor) <= 4.0]
    if not near:
        return
    bully.feel("angry")
    provoke(bully, min(near, key=lambda guy: abs(guy.x - bully.x)))


def _join_in(now):
    """Somebody is singing. Anybody near enough joins in, one way or another.

    Checked every tick rather than settled when the song starts: a man who
    wanders into earshot halfway through a song is a man who joins in
    halfway through it, and one who is picked up out of it does not leave a
    seat in the audience behind him.
    """
    singers = [guy for guy in crew if guy.state == "sing"]
    if not singers:
        return
    stage = singers[0]
    for guy in crew:
        # A conversation is not a reason to miss it: they break off, which
        # is what `_leave_scene` below is for.
        if guy is stage or guy.state not in ("rest", "walk", "sleep",
                                             "watch", "chat"):
            continue
        if guy.floor is None or stage.floor is None:
            continue
        if (abs(guy.floor - stage.floor) > 4.0
                or abs(guy.x - stage.x) > SONG_NEAR):
            continue
        if not _game(guy, now):
            continue
        guy._leave_scene(now)
        guy._watching = None
        guy._begin("clap" if random.random() < CLAP_ODDS else "dance", now)
        guy._song_x = stage.x
        # They stop when he does, so it ends as one thing rather than three
        # men winding down separately.
        guy._until = stage._until


def _send_for(hurt, kind, at_x, now):
    """Whoever is nearest and free goes and phones it in. False if nobody is.

    Nearest rather than everybody: a whole crew ringing for one ambulance is
    a crowd, and the man who is actually hurt is behind it.
    """
    best = None
    for guy in crew:
        if guy is hurt or guy.state not in ("rest", "walk", "watch", "sleep"):
            continue
        if guy.floor is None or hurt.floor is None:
            continue
        if abs(guy.floor - hurt.floor) > 4.0 or abs(guy.x - at_x) > HELP_NEAR:
            continue
        if best is None or abs(guy.x - at_x) < abs(best.x - at_x):
            best = guy
    if best is None:
        return False
    best._leave_scene(now)
    best._watching = None
    best._begin("help", now)
    best._help_kind = kind
    best._help_at = at_x
    x1, x2 = best._walls()
    # He stands off to his own side of it rather than on top of it, so the
    # stretcher has somewhere to be put down.
    best._help_x = _clamp(at_x + HELP_STAND * (-1.0 if at_x > best.x else 1.0),
                          x1, x2)
    if kind == "medic":
        # He is not getting up and walking it off while an ambulance is on
        # its way to him.
        hurt._until = now + CASUALTY_S
    return True


def _mind_the_van(van, now):
    """The half of an emergency that is people rather than paint."""
    if van.kind == "medic":
        if van.phase == "load":
            for guy in crew:
                if (guy.state == "beaten"
                        and abs(guy.x - van.at_x) <= HELP_STAND):
                    guy._leave_scene(now)
                    guy._begin("carted", now)
        return
    if van.kind == "icecream":
        global _scoop_at
        if van.phase != "serve":
            return
        line = [guy for guy in crew if guy.state == "queue"]
        if not line:
            if van.carry:
                van.leave()             # everybody has had his
                return
            fresh = [guy for guy in crew
                     if guy.state in ("rest", "walk", "chat", "watch")
                     and guy.floor is not None
                     and abs(guy.x - van.at_x) < HELP_NEAR
                     and _game(guy, now)]
            if not fresh:
                van.leave()
                return
            # One queue, formed once - `carry` marks it, so the men walking
            # off with cones are not recruited straight back onto the end.
            van.carry = True
            fresh.sort(key=lambda guy: abs(guy.x - van.door))
            for i, guy in enumerate(fresh):
                guy._leave_scene(now)
                guy._watching = None
                guy._begin("queue", now)
                guy._queue_i = i
            _scoop_at = now + SERVE_S
            return
        front = min(line, key=lambda guy: guy._queue_i)
        spot = van.door + van.side * 16.0
        if now >= _scoop_at and abs(front.x - spot) < 14.0:
            _scoop_at = now + SERVE_S
            front.prop = "cone"
            front.feel("happy")
            front._begin("lick", now)
            for guy in line:
                if guy is not front:
                    guy._queue_i -= 1
        return
    # A police car, and two men with a reason to be somewhere else. They go
    # opposite ways round it if they can, and it leaves after whichever of
    # them it ended up behind.
    running = [guy for guy in crew if guy.state in ("fight", "provoke")]
    for guy in running:
        guy._leave_scene(now)
        guy._foe = None
        guy._begin("run", now)
        guy._run_leg = "off"
        guy._run_way = 1.0 if guy.x >= van.x else -1.0
        van.way = guy._run_way
    for guy in crew:
        if guy.state == "baffled":
            guy._foe = None
            guy._begin("rest", now)


def _watch_the_screen(now):
    """Has something gone full-screen, or stopped being full-screen?

    One flag for the whole crew, worked out here rather than by each of them:
    six windows asking Windows the same question sixty times a second is the
    kind of thing that turns a mascot into something you uninstall.
    """
    global shy, _shy_at
    if now - _shy_at < SHY_EVERY:
        return
    _shy_at = now
    try:
        want = bool(winkit.foreground_fullscreen())
    except Exception:               # never let a Windows call stop the frame
        want = False
    if want == shy:
        return
    shy = want
    if shy:
        yard.hide()
        for guy in list(crew):
            if guy.state in ("held", "shy", "inside"):
                continue            # in somebody's hand, already going, or
                                    # already a withdrawn window in a hut
            sitting = guy.state == "vigil"
            guy._leave_scene(now)
            guy._begin("shy", now)
            # He was sitting with a note. His fire is still burning behind
            # whatever went full-screen, so he goes back to it rather than
            # wandering off when it is over.
            guy._shy_sat = sitting
        return
    yard.show()
    for guy in list(crew):
        if guy.state == "shy":
            guy.come_out(now)


def _scene_near(guy, reach=WATCH_R):
    """The running scene he has walked in on, if any: the nearest one on his
    own floor that he is not already part of.

    The reach is how far he is prepared to notice from: as far as he can see
    when he is picking somewhere to walk, and only WATCH_R when the question
    is whether he has arrived at it.
    """
    best, near = None, reach
    for scene in scenes:
        if not scene.cast or guy in scene.cast:
            continue
        if abs(scene.cast[0].y - guy.y) > 30.0:
            continue
        gap = abs(guy.x - scene.mid)
        if gap < near:
            best, near = scene, gap
    return best


def _incoming(band, group, now):
    """Is somebody else still on his way over to this lot?

    Whichever two are nearest arrive first, and starting the moment they do
    leaves the third walking in on a conversation that would have had him in
    it had it waited half a second. Measured over three minutes, that was
    every scene a pair and never once a three-way. So they hold off while
    anyone is walking in at them - he is only half a second away.
    """
    if len(group) >= MAX_CAST:
        return False
    mid = sum(g.x for g in group) / float(len(group))
    for guy in band:
        if guy in group or guy.state != "walk" or not guy.sociable(now):
            continue
        # Walking, and walking this way. Somebody heading off in the other
        # direction is not somebody to stand about waiting for, and one who is
        # a rally away is too far off to wait for either.
        if abs(guy.x - mid) < RALLY_R and (mid - guy.x) * (guy._goal - guy.x) > 0:
            return True
    return False


def _pick_scene(ready):
    """Talk, football, or - once there are three of them - a hut or a fire.

    One roll cut into three rather than a roll each. A chain of independent
    odds makes whatever is last on the list far rarer than its number reads,
    and these numbers are meant to say how often you see each of them.
    """
    roll = random.random()
    if len(ready) > 2 and yard.hut() is None and roll < BUILD_ODDS:
        return "build", BUILD
    if roll < BUILD_ODDS + FOOTY_ODDS:
        return "footy", FOOTY
    if (len(ready) > 2 and yard.fire() is None
            and roll < BUILD_ODDS + FOOTY_ODDS + FIRE_ODDS):
        return "fire", FIRE
    return "talk", TALK[len(ready)]


def _space_out():
    """Nobody stands inside anybody.

    One pass over the crew before they draw: two of them on the same floor and
    closer than SPACE_R shuffle apart by half the overlap each, up to
    SPACE_PUSH a frame. Sorted by x, so the moment the man to the right is
    clear everybody past him is clear too.

    Solved here, once, for the same reason the pairing is: each of them backing
    off on his own turns a crowd into everybody stepping into the space
    somebody else has just left. A frame's worth at a time rather than the
    whole overlap, because a body that jumps clear reads as a collision in a
    game and a body that shuffles clear reads as somebody making room.

    ponytail: O(n^2) over a crew capped at MAX_ROAMERS - six, and the inner
    loop breaks on the first man who is already clear.
    """
    out = sorted((g for g in crew
                  if g.state in SPACE_STATES and g.floor is not None),
                 key=lambda g: g.x)
    for i, guy in enumerate(out):
        for other in out[i + 1:]:
            gap = other.x - guy.x
            if gap >= SPACE_R:
                break
            if abs(other.floor - guy.floor) > 4.0:
                continue            # one of them is on another screen
            gives = (guy.state in SPACE_SHUFFLE, other.state in SPACE_SHUFFLE)
            if not any(gives):
                continue            # two of them mid-stride: they cross
            # Half each when both are standing about, all of it from whichever
            # one is - so a man walked into gets out of the way properly
            # rather than half way.
            share = (SPACE_R - gap) / (2.0 if all(gives) else 1.0)
            push = min(share, SPACE_PUSH)
            if gives[0]:
                guy.x = _clamp(guy.x - push, *guy.walk_line)
            if gives[1]:
                other.x = _clamp(other.x + push, *other.walk_line)


def _kick_off(scene, now):
    """A ball, thrown in between them. No ball, no game."""
    first = scene.cast[0]
    if yard.kick_off(scene.mid, first.floor) is None:
        _close(scene, now)


def _light(scene, now):
    """A fire, in the middle of them. No fire, no evening.

    Lit with exactly as long in it as the table spends getting to the beat
    where they stand up, so it goes out under them rather than at some time
    of its own that the scene then has to wait for.
    """
    if yard.light_fire(scene.mid, scene.cast[0].floor, FIRE_S) is None:
        _close(scene, now)


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
            ready = [g for g in group if g.sociable(now)][:MAX_CAST]
            if len(ready) >= 2 and not _incoming(band, group, now):
                kind, table = _pick_scene(ready)
                scene = _open(ready, kind, table, now)
                if kind == "footy":
                    _kick_off(scene, now)
                elif kind == "fire":
                    _light(scene, now)
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


def focus(window, seconds=None):
    """Sit with this note until the fire goes out.

    Whoever belongs to the note does it - he comes off the paper if he is
    still on it - and he goes back to it at the end. None if there is nobody
    to ask: no mascot, no room on the bar, or no fire to be had.
    """
    if yard.fire() is not None:
        # One fire at a time. Sitting down beside somebody else's means his
        # twenty-five minutes end when their fifteen seconds do.
        return None
    now = _time()
    guy = for_note(window.note["id"])
    if guy is None:
        if len(crew) >= MAX_ROAMERS:
            return None
        try:
            guy = window.detach_for_focus()
        except tk.TclError:
            return None
        if guy is None:
            return None
    guy._leave_scene(now)
    guy._focus_s = FOCUS_S if seconds is None else float(seconds)
    guy._begin("vigil", now)
    _cancel()
    _arm(TICK_MS)
    return guy


def _pointer():
    """Where the mouse is, asked through whoever is around to ask.

    A seam as much as a helper: the suite puts its own answer in here, the
    same way it does for the full-screen check.
    """
    for guy in crew:
        try:
            return guy.winfo_pointerxy()
        except tk.TclError:
            continue
    return None


def race(now=None):
    """Line them up and race them: down the bar and back.

    Whoever is stood about takes part, up to four of them. False if there
    are not enough, or something bigger is already happening.
    """
    global _race_t0
    now = _time() if now is None else now
    if _racers or yard.van() is not None:
        return False
    fit = [guy for guy in crew if guy.state in ("rest", "walk", "chat")
           and guy.floor is not None and _game(guy, now)]
    if len(fit) < RACE_MIN:
        return False
    field = sorted(fit, key=lambda guy: guy.x)[:4]
    x1, x2 = field[0]._walls()
    for i, guy in enumerate(field):
        guy._leave_scene(now)
        guy._watching = None
        guy._begin("race", now)
        guy._race_mark = x1 + 70.0 + i * 40.0
        guy._race_far = x2 - 60.0
        guy._race_pace = random.uniform(0.92, 1.10)
        guy._race_trip_at = None
        _racers.append(guy)
    _race_t0 = None
    if random.random() < RACE_TRIP:
        # Somebody is going over. Armed here, timed at the gun.
        random.choice(field)._race_trip_at = -1.0
    _cancel()
    _arm(TICK_MS)
    return True


def _run_race(now):
    """The whole race, refereed once a frame rather than by each runner.

    _do_race gets one man round the course; everything two of them have to
    agree on - the gun, the result, who is owed an ambulance - is here.
    """
    global _race_t0, _race_tripped
    if _race_tripped is not None:
        if _race_tripped not in crew:
            _race_tripped = None
        elif _race_tripped.state == "rest":
            # He came down at full tilt, and now that he has stopped
            # bouncing it hurts. The ambulance takes it from there.
            _race_tripped.perform("beaten")
            _race_tripped = None
    if not _racers:
        return
    racing = [guy for guy in _racers if guy in crew and guy.state == "race"]
    if not racing:
        if _race_tripped is None:
            del _racers[:]
            del _race_order[:]
            _race_t0 = None
        return
    if _race_t0 is None:
        if all(guy._race_leg != "line" for guy in racing):
            _race_t0 = now + RACE_SET_S
        return
    if now >= _race_t0:
        for guy in racing:
            if guy._race_leg == "set":
                guy._race_leg = "out"
                guy._mark = None
                if guy._race_trip_at == -1.0:
                    guy._race_trip_at = now + random.uniform(0.6, 2.2)
    done = [guy for guy in racing if guy._race_leg == "done"]
    if done and len(done) == len(racing):
        first = next(guy for guy in _race_order if guy in racing)
        for guy in racing:
            if guy is first:
                guy.feel("happy")
                guy.perform("celebrate")
            else:
                guy._begin("clap", now)
                guy._song_x = first.x
                guy._until = now + 2.5
        del _racers[:]
        del _race_order[:]
        _race_t0 = None


def act(guy, what, seconds=None):
    """Ask one of them to do something, by name. False if he cannot.

    The way in for everything outside this file: a scene, a menu, or a check
    says act(guy, "sing") and does not have to know that singing is a state
    and celebrating is a different one that already existed.
    """
    if guy is None or guy not in crew:
        return False
    return guy.perform(what, seconds)


def scrap(one, other, seconds=None):
    """Two of them fall out. One ends up celebrating and one sat down.

    Set up here rather than by each of them, for the same reason pairing is:
    two men who each pick a fight with the other are two fights.
    """
    if one is other or one not in crew or other not in crew:
        return False
    now = _time()
    for guy, foe in ((one, other), (other, one)):
        guy._leave_scene(now)
        guy._foe = foe
        guy.feel("angry")
        guy._begin("fight", now)
        if seconds is not None:
            guy._until = now + float(seconds)
    _cancel()
    _arm(TICK_MS)
    return True


def chase(one, other, seconds=None):
    """One of them runs after the other, up and down the bar.

    Paired here rather than by each of them, the same way a scrap is: a chase
    is one man running and one man after him, and two men who each decide
    they are the one being chased is nobody chasing anybody.
    """
    if one is other or one not in crew or other not in crew:
        return False
    now = _time()
    for guy, foe, leg in ((one, other, "after"), (other, one, "away")):
        guy._leave_scene(now)
        guy._begin("run", now)          # clears the foe, so it is set after
        guy._foe = foe
        guy._run_leg = leg
        if seconds is not None:
            guy._until = now + float(seconds)
    # Both of them the same way, away from the one doing the chasing, so it
    # starts as a chase rather than as the two of them running at each other.
    one._run_way = other._run_way = 1.0 if other.x >= one.x else -1.0
    _cancel()
    _arm(TICK_MS)
    return True


def provoke(bully, other, seconds=None):
    """One of them starts on another who never asked for it.

    Paired here for the same reason a scrap is: it takes two, and the two of
    them have to agree about which is which. The one started on stands there
    baffled while it goes on, and when it is over he either walks off or has
    had enough - `_do_provoke` decides that, once, at the end of it.
    """
    if bully is other or bully not in crew or other not in crew:
        return False
    now = _time()
    for guy in (bully, other):
        guy._leave_scene(now)
    bully._begin("provoke", now)        # clears the foe, so it is set after
    other._begin("baffled", now)
    bully._foe, other._foe = other, bully
    if seconds is not None:
        bully._shove_s = float(seconds)
        bully._until = now + float(seconds)
    _cancel()
    _arm(TICK_MS)
    return True


def applaud(x, note_id=None):
    """Somebody finished a list. Anybody near it comes over for it.

    Near enough rather than everybody: a whole crew abandoning a game of
    football and sprinting the length of the bar for a ticked box is a
    celebration that reads as an alarm. The man off that note is the
    exception - it is his note, so he comes however far away he is.
    """
    now = _time()
    came = []
    for guy in list(crew):
        if guy.state not in ("rest", "walk", "sleep", "watch", "chat"):
            continue            # held, falling, hiding, on a note, in a hut
        his = note_id is not None and guy.home_id == note_id
        if not his and abs(guy.x - x) > APPLAUD_R:
            continue
        guy._leave_scene(now)
        guy._watching = None
        guy._begin("cheer", now)
        came.append(guy)
    # A place each, in the order they were already standing, so nobody crosses
    # anybody to get to the note.
    came.sort(key=lambda g: g.x)
    for i, guy in enumerate(came):
        spot = x + (i - (len(came) - 1) / 2.0) * CHEER_GAP
        guy._cheer_x = _clamp(spot, *guy.walk_line)
    if came:
        _cancel()
        _arm(TICK_MS)
    return came


def shutdown():
    """Everyone back on their notes and nothing left running. Called at quit,
    and whenever the mascot is switched off."""
    _cancel()
    for guy in list(crew):
        guy.go_home()
    del crew[:]
    del scenes[:]
    global _last, shy, _shy_at
    _last = None
    shy = False
    _shy_at = 0.0
    yard.clear()


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
        self.key = key
        # The yard is built on demand, but it is told where and in what colour
        # here: app.root outlives every roamer, where the module's own _root is
        # taken away under the tests to stop tick() arming timers behind them.
        yard.attach(app.root, key)
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
        self._act = None                # what he is doing with his hands
        self._act_from = 0.0
        self._act_at = now + random.uniform(*IDLE_EVERY)
        self._swing = 0.0               # how far he is trailing the hand
        self._startle_until = 0.0

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
        self._nosy = False
        self._social_at = 0.0
        self._social_until = 0.0
        self._cross_until = 0.0
        self._lift_since = None
        self.carry = False      # he is holding a plank
        self._fetch = "out"     # which leg of the errand he is on
        self._fetch_way = -1.0
        self._site_x = self.x
        self._turn_at = 0.0
        self._panic_until = 0.0
        self._vigil_leg = "walk"        # sitting with a note while it burns
        self._vigil_x = self.x
        self._focus_s = FOCUS_S
        self._cheer_x = self.x          # the note that has just been finished
        self._shy_home = self.x         # where he was when something went
        self._shove_s = SHOVE_S         # how long he squares up for
        self._help_kind = "medic"       # what he is phoning for
        self._help_at = self.x          # what he is phoning about
        self._help_x = self.x           # ...and where he stands to do it
        self._help_leg = "over"         # walking over, or on the phone
        self._stalk_leg = "creep"       # stalking the pointer, or wound up
        self._prey = (0.0, 0.0)         # where it was when he committed
        self._race_leg = "line"         # his lane of the race
        self._race_mark = self.x        # where his lane starts
        self._race_far = self.x         # ...and where it turns
        self._race_pace = 1.0           # nobody runs quite the same speed
        self._race_trip_at = None       # when his race ends early, if it does
        self._queue_i = 0               # his place in the ice cream queue
        self._lick_x = self.x           # where he ambles off to with it
        self._hat_until = 0.0           # a party hat, while there is a party
        self._bday_done = False         # this note's birthday has been had
        self._pizza_done = False        # this note's pizza run has been made
        self._grump_until = 0.0         # while set, he is not joining anything
        self._song_x = self.x           # who he is clapping at
        self._song_home = self.x        # ...and the spot he dances about
        self._shy_leg = "out"           # full-screen, and which leg he is on
        self._shy_way = -1.0
        self.mood = None                # happy, sad, angry, sleepy, or nothing
        self.temper = None              # ...and the one the note itself sets
        try:
            words = "%s %s" % (note_window.note.get("heading", ""),
                               note_window.note.get("body", ""))
            self.temper = temper_of(words)
            # A birthday already on the note is not a party every time he is
            # dragged off it; only the word arriving fresh is. Pizza the same.
            self._bday_done = _has_bday(words)
            self._pizza_done = _has_pizza(words)
        except (AttributeError, tk.TclError):
            pass
        self._mood_until = 0.0
        self.prop = None                # something in his hands: "phone"
        self._foe = None                # who he is scrapping or running with
        self._run_way = 1.0             # which way he is running
        self._run_leg = "solo"          # on his own, "after" him, or "away"
        self._phone_leg = "type"        # typing on it, or talking into it
        self._shy_sat = False           # he was sitting with a note when it
                                        # went full-screen

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
        self._swing = 0.0
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
        carried = max([abs(s[1] - self.x) + abs(s[2] - self.y)
                       for s in self._trail] or [0.0])
        if now - self.since < TAP_S and carried < TAP_SLOP:
            # Clicked rather than dragged. He is not thrown anywhere - he hops
            # where he stands and gives you a look for it, which is the whole
            # difference between poking him and picking him up.
            self.vx = self.spin = 0.0
            self.vy = -STARTLE_VY
            self._startle_until = now + STARTLE_S
        elif recent:
            t0, x0, y0 = recent[0]
            dt = max(now - t0, 1e-3)
            self.vx = _clamp((self.x - x0) / dt * THROW_K, -THROW_MAX, THROW_MAX)
            self.vy = _clamp((self.y - y0) / dt * THROW_K, -THROW_MAX, THROW_MAX)
            self.spin = _clamp(-self.vx / 120.0, -6.0, 6.0)
        self._trail = []
        self._find_floor(now, force=True)
        if shy:
            # Dragged off a note while something is full-screen. He is not
            # going to stand on top of it for the rest of the film.
            self._begin("shy", now)
        elif not self._take_hold(now):
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
            yard.clear()

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
            self._act = None
            self._act_at = now + random.uniform(*IDLE_EVERY)
        elif state == "leave":
            self._launched = False
            self.hands = self.feet = None
            self.vx = self.vy = self.spin = 0.0
        elif state == "bye":
            self._until = now + BYE_S
            self.hands = self.feet = None
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
        elif state == "vigil":
            # Under the note, on the floor, and not so near the edge that the
            # fire would be half off the screen.
            self._vigil_leg = "walk"
            self.hands = self.feet = None
            try:
                middle = (self.home().winfo_rootx()
                          + self.home().winfo_width() / 2.0)
            except (AttributeError, tk.TclError):
                middle = self.x
            x1, x2 = self.walk_line
            self._vigil_x = _clamp(middle, x1 + FIRE_SEAT, x2 - FIRE_SEAT)
        elif state == "sing":
            self._until = now + ACTS["sing"]
            self.hands = self.feet = None
        elif state in ("clap", "dance"):
            # However long is left of the song. Whoever starts them off says
            # so; on their own they are worth about one chorus.
            self._until = now + ACTS["sing"]
            self._song_home = self.x
            self.hands = self.feet = None
        elif state == "phone":
            self._until = now + ACTS["phone"]
            self.prop = "phone"
            self.hands = self.feet = None
        elif state == "beaten":
            self._until = now + ACTS["beaten"]
            self.hands = self.feet = None
        elif state == "fight":
            self._until = now + ACTS["fight"]
            self.hands = self.feet = None
        elif state == "provoke":
            # Timed from arriving rather than from setting off: the squaring
            # up is the point, and a man who spent all of it walking over has
            # not started on anybody.
            self._shove_s = SHOVE_S
            self._until = now + SHOVE_S
            self._foe = None
            self.hands = self.feet = None
        elif state == "baffled":
            self._until = now + BAFFLED_S
            self._foe = None
            self.hands = self.feet = None
        elif state == "help":
            self._until = now + HELP_MAX_S
            self._help_leg = "over"
            self.hands = self.feet = None
        elif state == "stalk":
            self._until = now + 14.0
            self._stalk_leg = "creep"
            self.hands = self.feet = None
        elif state == "errand":
            self._until = now + FETCH_MAX_S
            x1, x2 = self._walls()
            self._fetch = "out"
            # Out the nearest side: the pizza place is wherever is closest.
            self._fetch_way = 1.0 if (x2 - self.x) < (self.x - x1) else -1.0
            self.prop = None
            self.hands = self.feet = None
        elif state == "picnic":
            self._until = now + PICNIC_S
            self.hands = self.feet = None
        elif state == "race":
            self._until = now + 60.0
            self._race_leg = "line"
            self.hands = self.feet = None
        elif state == "queue":
            self._until = now + 30.0
            self.hands = self.feet = None
        elif state == "lick":
            self._until = now + LICK_S
            self._lick_x = self.x + random.choice((-1.0, 1.0)) * 90.0
            self.hands = self.feet = None
        elif state == "carted":
            # However long the van takes. Nothing here ends it - the van
            # does, by driving off with him.
            self._until = now + VAN_PATIENCE
            self.hands = self.feet = None
        elif state == "cheer":
            self._until = now + CHEER_S
            self.hands = self.feet = None
        elif state == "shy":
            # Where he was standing, so he can come back to it rather than
            # reappearing at the edge he left by - but inside the line he
            # walks. Somebody who was out past the edge fetching wood when the
            # video started would otherwise be sent home to a place off the
            # screen, and stand there.
            self._shy_home = _clamp(self.x, *self.walk_line)
            self._shy_leg = "out"
            x1, x2 = self._walls()
            self._shy_way = -1.0 if (self.x - x1) < (x2 - self.x) else 1.0
            self.hands = self.feet = None
            self._mark = None
        elif state == "run":
            self._until = now + ACTS["run"]
            self._run_leg = "solo"
            self._foe = None
            self._run_way = random.choice((-1.0, 1.0))
            self.hands = self.feet = None
        elif state == "panic":
            self._until = now + PANIC_S
            self._panic_until = now + PANIC_S + PANIC_FACE_S
            self._leave_way = random.choice((-1.0, 1.0))
            self._turn_at = now + PANIC_TURN
            self.hands = self.feet = None
        elif state == "walk":
            self._stir_at = now
            x1, x2 = self.walk_line
            want = self._company(now)
            if want is not None:
                self._goal = _clamp(want, x1, x2)
            else:
                span = (random.uniform(LEG_MIN, LEG_MAX)
                        * random.choice((-1.0, 1.0)))
                self._goal = _clamp(self.x + span, x1, x2)
                if abs(self._goal - self.x) < 20.0:
                    self._goal = x2 if self.x < (x1 + x2) / 2.0 else x1
            self.hands = self.feet = None

    def rate(self):
        # Standing about is 200 ms a frame, which is plenty for a blink and
        # nowhere near enough for an arm going over his head. So an idle buys
        # him the full rate for as long as it lasts, and no longer.
        if self.state == "shy" and self._shy_leg == "gone":
            return SLEEP_MS         # off the screen entirely: nothing to draw
        if self._act is not None and self.state == "rest":
            return TICK_MS
        return {"grip": GRIP_MS, "rest": REST_MS, "sleep": SLEEP_MS,
                "inside": SLEEP_MS}.get(self.state, TICK_MS)

    def step(self, now):
        dt = STEP if STEP is not None else min(now - self._t, MAX_STEP)
        self._t = now
        if self.state == "inside":
            # Nothing to place and nothing to draw: he is a withdrawn window
            # with a time on it.
            self._do_inside(now, dt)
            return self.rate()
        if self.state == "shy" and self._shy_leg == "gone":
            return self.rate()      # stood off the edge, waiting it out
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
        # How fast the hand is going, smoothed, so he trails behind it and
        # swings back when it stops. Without it he is a sprite pinned to the
        # pointer: the same pose whether he is being carried gently across the
        # desk or swung about, which is the one thing a dragged body must not
        # look like. Measured off the same trail the throw is, so a hand that
        # has stopped moving reads as stopped rather than as its last frame.
        recent = [g for g in self._trail if now - g[0] < THROW_WINDOW]
        want = 0.0
        if len(recent) >= 2:
            span = max(recent[-1][0] - recent[0][0], 1e-3)
            want = _clamp((recent[-1][1] - recent[0][1]) / span / DRAG_SWING,
                          -SWING_MAX_LEAN, SWING_MAX_LEAN)
        self._swing = _mix(self._swing, want, 0.25)
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
        self.lean -= self._swing
        self.roll += self._swing * 0.016

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

        # The first fifth of a second of it. He is yanked up off the floor
        # rather than thrashing on the frame he was touched: stretched along
        # the pull, arms and legs trailing under him, and a face that has not
        # caught up with what is happening to him yet.
        pull = _smooth(1.0 - _clamp((now - self.since) / GRAB_S, 0.0, 1.0))
        if pull > 0.0:
            self.squash = _mix(self.squash, 1.16, pull)
            self.roll = _mix(self.roll, 0.0, pull)
            self.face = _face_mix(self.face, FACES["wtf"], pull)
            trail_h = tuple((self.x + side * (hw * 0.5), arm_y + 15.0)
                            for side in (-1.0, 1.0))
            trail_f = tuple((self.x + side * 8.0, self.y + 7.0)
                            for side in (-1.0, 1.0))
            self.hands = tuple(_lerp2(h, t, pull)
                               for h, t in zip(self.hands, trail_h))
            self.feet = tuple(_lerp2(f, t, pull)
                              for f, t in zip(self.feet, trail_f))

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
        self.lean = 0.0
        self.squash = _clamp(1.0 + self.vy / 2600.0, 0.92, 1.16)
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
        self._breathe(now)
        self.phase = 0.0
        self.face = FACES["calm"]
        self.facing = _mix(self.facing, 0.0, 0.25)
        self.y = self._floor_y()
        self._watch_pointer()
        if self._act is None and now >= self._act_at:
            self._act = random.choice(IDLE_ACTS)
            self._act_from = now
        if self._act is not None:
            u = (now - self._act_from) / IDLE_S[self._act]
            if u < 1.0:
                self._idle_act(self._act, u)
                return          # he finishes it before he walks off anywhere
            self._act = None
            self.hands = self.feet = None
            self._act_at = now + random.uniform(*IDLE_EVERY)
        if now >= self._until:
            dozes = (SLEEP_AFTER * DOZY_HASTE
                     if self.temper == "sleepy" else SLEEP_AFTER)
            if now - self._stir_at > dozes:
                self._begin("sleep", now)
            else:
                self._begin("walk", now)

    def _idle_act(self, act, u):
        """Something to do with his hands, over `u` from 0 to 1.

        Solved against the same two-bone arms everything else uses rather than
        keyframed, so an idle is four lines and reads as a body rather than as
        a sprite swap. `wave` takes each of them out and back inside its own
        length, which is what keeps them from snapping on the last frame.
        """
        fy = self._face_y()
        hw = HEAD / 2.0
        wave = math.sin(u * math.pi)
        if act == "stretch":
            # Both arms up and over, and he comes up off his heels with them.
            self.hands = tuple((self.x + side * (hw * 0.7 + 4.0),
                                fy - HEAD * (0.5 + 0.4 * wave))
                               for side in (-1.0, 1.0))
            self.squash = 1.0 + 0.09 * wave
            self.y = self._floor_y() - 3.0 * wave
            self.face = _face_mix(FACES["calm"], FACES["strain"], wave * 0.45)
        elif act == "yawn":
            # One hand up at his face, eyes shut, and his mouth doing the work.
            self.hands = ((self.x - hw * 0.8, fy - hw * 0.1), None)
            self.face = FACES["calm"]._replace(
                eye=0.12, lid=0.85, brow=0.3, mouth=0.9,
                curve=-0.25, open=0.2 + 0.65 * wave)
            self.squash = 1.0 + 0.04 * wave
        elif act == "scratch":
            side = -1.0 if self.facing <= 0.0 else 1.0
            self.hands = ((self.x + side * hw * 0.9,
                           fy - hw * 0.5 + math.sin(u * 30.0) * 3.0), None)
            self.roll = math.sin(u * 30.0) * 0.03
            self.face = _face_mix(FACES["calm"], FACES["think"], 0.7)
        else:                                   # look: a check either way
            swing = math.sin(u * TAU)
            self.facing = _clamp(swing * 0.8, -1.0, 1.0)
            self.look = (swing * 3.0, -0.8)
            self.hands = self.feet = None

    def _do_sleep(self, now, _dt):
        self.face = FACES["calm"]
        self.facing, self.look, self.phase = 0.0, (0.0, 0.0), 0.0
        # In a heap, heads go together: he tips towards the nearest one
        # asleep beside him, and stays upright sleeping alone.
        near = [guy for guy in crew if guy is not self
                and guy.state == "sleep" and abs(guy.x - self.x) < PILE_R]
        if near:
            other = min(near, key=lambda guy: abs(guy.x - self.x))
            self.roll = 0.12 if other.x > self.x else -0.12
        else:
            self.roll = 0.0
        self._breathe(now, 0.035, 0.14)     # slower, deeper, properly asleep
        self._say("z" if int(now * 0.8) % 2 else "Z")
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
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
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

    def _do_vigil(self, now, dt):
        """Over to the note, a fire, and a seat by it until it burns out.

        Three legs and no beat table: twenty-five minutes cannot be written as
        frames, and nothing here has to happen on a particular one. The fire
        is the clock - when the yard says it has gone, so has the sitting.
        """
        floor = self._floor_y()
        self.squash, self.roll = 1.0, 0.0
        self.y = floor
        blaze = yard.fire()

        if self._vigil_leg == "walk":
            self.crouch, self.lean = 0.0, 0.0
            self.hands = self.feet = None
            gap = self._vigil_x - self.x
            if abs(gap) > WALK_SPEED * dt + 0.5:
                way = 1.0 if gap > 0 else -1.0
                self.x += way * WALK_SPEED * dt
                self.phase += WALK_SPEED * dt / STEP_PX * math.pi
                self.facing, self.lean = way * 0.62, way * 2.4
                self.face = _face_mix(FACES["calm"], FACES["happy"], 0.3)
                return
            self.x = self._vigil_x
            self.phase = 0.0
            if blaze is None:
                blaze = yard.light_fire(self.x, floor, self._focus_s)
                if blaze is None:
                    self._begin("rest", now)    # nowhere to put a fire
                    return
            self._vigil_leg = "sit"
            self.since = now
            return

        if self._vigil_leg == "sit":
            # Sat beside it rather than on it, facing in.
            inwards = 1.0 if self.x <= (blaze.x if blaze else self.x) else -1.0
            sunk = _smooth(_clamp((now - self.since) / (FIRE[1][1] * FRAME_S),
                                  0.0, 1.0))
            self.y = floor + SIT_DROP * sunk
            self.crouch = sunk
            self.feet = ((self.x + inwards * 9.0, floor),
                         (self.x + inwards * 18.0, floor))
            self.hands = None
            self._breathe(now, 0.024, 0.20)
            self.facing = _clamp(inwards * 0.72, -1.0, 1.0)
            self.lean, self.phase = 0.0, 0.0
            if blaze is None:
                self._vigil_leg = "up"
                self.since = now
                return
            self.look = _aim((self.x, self._face_y()),
                             (blaze.x, floor - FIRE_LOOK * blaze.scale))
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.3)
            self._idle_look(now)
            return

        # up: on his feet, a wave, and back to the note he sat with.
        self.crouch, self.feet = 0.0, None
        self.y = floor
        self.face = FACES["happy"]
        self.hands = self._one_hand(
            -1.0 if self.facing < 0 else 1.0, 22.0,
            -18.0 + math.sin((now - self.since) * 16.0) * 4.0)
        self._say("bye!")
        if now - self.since >= VIGIL_WAVE_S:
            self.go_home()

    def _idle_look(self, now):
        """Something to do with his eyes while he sits: every so often he
        looks up at you instead of at the fire."""
        if int((now - self.since) / 7.0) % 3 != 2:
            return
        try:
            px, py = self.winfo_pointerxy()
        except tk.TclError:
            return
        self.look = _aim((self.x, self._face_y()), (px, py))

    def _do_sing(self, now, dt):
        """Head back, one hand out, and something over his head.

        The note over him is the same speech mark everything else uses: a
        second way of drawing something above a mascot would be a second thing
        to keep in the right place while he walks.
        """
        u = (now - self.since)
        self.squash, self.crouch = 1.0 + 0.05 * math.sin(u * 5.0), 0.0
        self.roll = math.sin(u * 2.2) * 0.06
        self.lean, self.phase = 0.0, 0.0
        self.feet = None
        self.y = self._floor_y() - abs(math.sin(u * 3.4)) * 3.0
        fy = self._face_y()
        self.hands = ((self.x - 26.0, fy - 6.0 - math.sin(u * 3.4) * 8.0), None)
        self.facing = _mix(self.facing, 0.25, 0.08)
        self.look = (0.0, -1.6)
        self.face = _face_mix(FACES["happy"], FACES["talk"],
                              0.35 + 0.35 * abs(math.sin(u * 3.0)))._replace(
            open=0.35 + 0.5 * abs(math.sin(u * 3.0)))
        self._say(SING_LINES[int(u * 1.6) % len(SING_LINES)])
        if now >= self._until:
            self._begin("rest", now)

    def _do_clap(self, now, dt):
        """On the beat, and looking at whoever is making the noise.

        The hands are the whole thing: they come together on the beat and
        open again between, and the rest of him bobs with it. A man clapping
        with his arms at his sides is a man standing still.
        """
        u = now - self.since
        beat = math.cos(u * CLAP_HZ * TAU)
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.phase, self.lean = 0.0, 0.0
        self.y = self._floor_y() - max(0.0, beat) * 2.0
        self.roll = 0.05 * beat
        fy = self._face_y()
        apart = 3.0 + (1.0 - beat) / 2.0 * CLAP_REACH
        self.hands = ((self.x - apart, fy + 9.0), (self.x + apart, fy + 9.0))
        self.feet = None
        self.facing = _mix(self.facing,
                           0.5 if self._song_x > self.x else -0.5, 0.12)
        self.look = _aim((self.x, fy), (self._song_x, fy - 6.0))
        self.face = FACES["happy"]
        if now >= self._until:
            self._social_at = now
            self._begin("rest", now)

    def _do_dance(self, now, dt):
        """Side to side about the spot he was standing on, arms up.

        Round his own spot rather than off along the bar: six men dancing
        across the taskbar end up in a heap at one end of it, and the man
        singing gets danced straight through.
        """
        u = now - self.since
        sway = math.sin(u * DANCE_HZ * TAU)
        hop = abs(math.sin(u * DANCE_HZ * TAU))
        x1, x2 = self._walls()
        self.x = _clamp(self._song_home + sway * DANCE_STEP, x1, x2)
        self.y = self._floor_y() - hop * DANCE_HOP
        self.squash = 0.95 + 0.10 * hop
        self.crouch = 0.0
        self.roll = sway * 0.12
        self.lean = sway * 2.0
        self.phase = 0.0
        fy = self._face_y()
        # Whichever arm is on the outside of the sway goes up; the other one
        # stays in. Both up at once is a celebration, and he is not cheering.
        high = fy - 16.0 - max(0.0, sway) * 10.0
        low = fy - 16.0 - max(0.0, -sway) * 10.0
        self.hands = ((self.x - 20.0, low), (self.x + 20.0, high))
        self.feet = None
        self.facing = _mix(self.facing, sway * 0.45, 0.2)
        self.look = _aim((self.x, fy), (self._song_x, fy - 6.0))
        self.face = FACES["laugh"]
        if now >= self._until:
            self._social_at = now
            self._begin("rest", now)

    def _do_phone(self, now, dt):
        """Two ways of holding it: thumbing at it, or talking into it.

        The phone itself is drawn by paint() off `prop`, the same way the
        plank is drawn off `carry` - the pose puts a hand somewhere and the
        drawing puts the thing in it.
        """
        u = now - self.since
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.lean, self.phase = 0.0, 0.0
        self.feet = None
        self.y = self._floor_y()
        fy = self._face_y()
        if self._phone_leg == "talk":
            # At his ear, the other hand going while he talks.
            self.facing = _mix(self.facing, 0.55, 0.1)
            self.hands = ((self.x - 13.0, fy - 2.0),
                          (self.x + 20.0 + math.sin(u * 4.0) * 5.0,
                           fy + 10.0 + math.cos(u * 3.0) * 4.0))
            self.look = (1.2, -0.4)
            self.roll = 0.03 * math.sin(u * 3.0)
            self.face = FACES["talk"]._replace(
                open=0.2 + 0.5 * abs(math.sin(now * 4.0 * TAU)))
        else:
            # Both hands down in front of him, thumbs going, head bent to it.
            self.facing = _mix(self.facing, 0.0, 0.15)
            self.hands = ((self.x - 9.0, fy + 17.0 + math.sin(u * 9.0) * 1.5),
                          (self.x + 9.0, fy + 17.0 + math.cos(u * 9.0) * 1.5))
            self.look = (0.0, 2.6)
            self.roll = 0.02 * math.sin(u * 4.5)
            self.face = _face_mix(FACES["calm"], FACES["think"], 0.5)
            self.y = self._floor_y() + 1.0
        if now >= self._until:
            self.prop = None
            self._begin("rest", now)

    def _do_beaten(self, now, dt):
        """Sat down where he lost it: knees up, head down, and not over it."""
        u = _smooth(_clamp((now - self.since) / 0.5, 0.0, 1.0))
        floor = self._floor_y()
        self.roll = 0.0
        # A sigh, not a breath: all exhale, on a slow beat.
        self.squash = 1.0 - 0.025 * abs(math.sin((now - self.since) * 0.35 * TAU))
        self.lean, self.phase = 0.0, 0.0
        self.crouch = u
        self.y = floor + SIT_DROP * u
        self.feet = ((self.x - 9.0, floor), (self.x + 9.0, floor))
        fy = self._face_y()
        self.hands = ((self.x - 15.0, fy + 20.0), (self.x + 15.0, fy + 20.0))
        self.facing = _mix(self.facing, 0.0, 0.1)
        self.look = (0.0, 2.2)
        self.face = FACES["sad"]
        if now >= self._until:
            self.feel("sad")
            self._begin("rest", now)

    def _do_fight(self, now, dt):
        """A scrap: two of them squaring up, all elbows and no damage.

        Cartoon rules - they swing at each other, neither of them ever
        connects, and it ends with one of them celebrating and the other sat
        down. Who wins is decided when it ends rather than when it starts, so
        a hand closing on one of them mid-scrap simply ends it.
        """
        foe = self._foe
        u = now - self.since
        floor = self._floor_y()
        self.squash, self.crouch = 1.0, 0.0
        self.phase = 0.0
        self.feet = None
        way = 1.0 if (foe is not None and foe.x > self.x) else -1.0
        self.facing = _clamp(way * 0.8, -1.0, 1.0)
        self.lean = way * 4.0
        self.roll = math.sin(u * SWING_HZ * TAU) * 0.09
        self.x += math.sin(u * SWING_HZ * TAU * 0.5) * DUST_R * dt * 4.0
        self.y = floor - abs(math.sin(u * SWING_HZ * TAU * 0.5)) * 2.0
        fy = self._face_y()
        swing = math.sin(u * SWING_HZ * TAU)
        self.hands = ((self.x + way * (14.0 + swing * 16.0), fy + 2.0),
                      (self.x - way * 8.0, fy + 12.0))
        self.look = _aim((self.x, fy), (foe.x, foe._face_y())) if foe else (0.0, 0.0)
        self.face = FACES["cross"]
        if now < self._until:
            return
        # Somebody has to lose. Both of them are told here, once, so they do
        # not each decide it and both win.
        if foe is not None and foe.state == "fight" and foe._foe is self:
            winner, loser = ((self, foe) if random.random() < 0.5 else (foe, self))
            winner._foe = loser._foe = None
            winner.feel("happy")
            winner.perform("celebrate")
            loser.perform("beaten")
        else:
            self._foe = None
            self._begin("rest", now)

    def _do_provoke(self, now, dt):
        """Over to him, and then all elbows at nothing in particular.

        The walk is not counted against the squaring up - `_until` is pushed
        along until he arrives - so somebody started on from the other end of
        the bar still gets started on rather than watching a man walk towards
        him and give up. He gives up eventually all the same: a foe who keeps
        walking away is not worth the whole afternoon.
        """
        foe = self._foe if self._foe in crew else None
        if foe is None or foe.state not in ("baffled", "provoke"):
            self._foe = None
            self._begin("rest", now)
            return
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y()
        fy = self._face_y()
        gap = foe.x - self.x
        way = 1.0 if gap > 0 else -1.0
        self.look = _aim((self.x, fy), (foe.x, foe._face_y()))
        if abs(gap) > PROVOKE_NEAR:
            if now - self.since >= PROVOKE_MAX_S:
                # Following somebody who keeps walking off is not worth the
                # whole afternoon, and neither of them is left mid-scene.
                foe._foe = None
                foe._begin("rest", now)
                self._foe = None
                self._begin("rest", now)
                return
            x1, x2 = self._walls()
            self.x = _clamp(self.x + way * PROVOKE_SPEED * dt, x1, x2)
            self.phase += PROVOKE_SPEED * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.62, way * 3.0
            self.face = FACES["smug"]
            self.hands = self.feet = None
            self._until = now + self._shove_s
            return
        # Squared up: one fist out at his face and back, and nothing lands.
        u = now - self.since
        swing = math.sin(u * SHOVE_HZ * TAU)
        self.phase = 0.0
        self.facing = _clamp(way * 0.8, -1.0, 1.0)
        self.lean = way * 4.5
        self.face = FACES["cross"]
        self.hands = ((self.x + way * (12.0 + max(swing, 0.0) * 20.0), fy),
                      (self.x - way * 10.0, fy + 12.0))
        self.y = self._floor_y() - max(0.0, swing) * 1.8
        self.feet = None
        self._say("!" if swing > 0.0 else None)
        if now < self._until:
            return
        # He has made whatever point he had. What comes of it is the other
        # man's to decide, and it is decided here, once, so the two of them
        # do not each decide it and disagree.
        # What comes back depends on who he started on. An angry note
        # always answers; a sad one never does.
        odds = {"angry": 1.0, "sad": 0.0}.get(foe.temper, FIGHT_BACK)
        if random.random() < odds:
            scrap(self, foe)
            return
        foe.shrug_off(now)
        self._foe = None
        self.feel("happy")
        self._begin("rest", now)

    def _do_baffled(self, now, dt):
        """Somebody has started on him and he has no idea why.

        Hands out and a face on him, and that is all: what happens next is
        not his to start. The clock is only here so that a man whose bully
        was picked up mid-shove is not stood like that for the afternoon.
        """
        foe = self._foe if self._foe in crew else None
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.phase = 0.0
        self.y = self._floor_y()
        fy = self._face_y()
        way = 1.0 if (foe is not None and foe.x > self.x) else -1.0
        self.facing = _clamp(way * 0.7, -1.0, 1.0)
        self.lean = -way * 2.6         # leaning off him, not into him
        # The head goes over the way the body leans: the tilt IS confusion,
        # and the waver keeps it a thing he is doing rather than a pose.
        self.roll = -way * (0.12 + 0.02 * math.sin((now - self.since)
                                                   * 1.1 * TAU))
        self.face = FACES["wtf"]
        self.look = (_aim((self.x, fy), (foe.x, foe._face_y()))
                     if foe is not None else (0.0, 0.0))
        # Palms out and low: the shape of a man asking what this is about.
        self.hands = ((self.x - 20.0, fy + 16.0), (self.x + 20.0, fy + 16.0))
        self.feet = None
        self._say("?")
        if foe is None or now >= self._until:
            self._foe = None
            self._begin("rest", now)

    def shrug_off(self, now):
        """Started on, and not interested. He goes and stands somewhere else.

        The mood is what carries it: a man who walks away from this with his
        ordinary face on reads as a man who did not notice, and he did.
        """
        self._foe = None
        self.feel("sad")
        self._begin("walk", now)
        x1, x2 = self.walk_line
        away = FIGHT_BACK_STEP * (-1.0 if self.facing > 0.0 else 1.0)
        self._goal = _clamp(self.x + away, x1, x2)

    def _do_cheer(self, now, dt):
        """Over to the note, and a fuss about it.

        He walks while he is further off than CHEER_NEAR and celebrates from
        wherever he has got to when the time is up - the point is the noise,
        not arriving. Somebody sprinting for a spot he only reaches as it ends
        would read as having missed it.
        """
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y()
        gap = self._cheer_x - self.x
        if abs(gap) > CHEER_NEAR:
            way = 1.0 if gap > 0 else -1.0
            x1, x2 = self._walls()
            self.x = _clamp(self.x + way * WALK_SPEED * 1.8 * dt, x1, x2)
            self.phase += WALK_SPEED * 1.8 * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.62, way * 2.6
            self.face = FACES["happy"]
            self.hands = self.feet = None
        else:
            # Both hands up, and up off the floor with them.
            beat = abs(math.sin((now - self.since) * 7.0))
            fy = self._face_y()
            self.phase, self.lean = 0.0, 0.0
            self.facing = _mix(self.facing, 0.0, 0.2)
            self.y = self._floor_y() - beat * 6.0
            self.squash = 0.95 + beat * 0.12
            self.hands = ((self.x - 24.0, fy - 14.0 - beat * 8.0),
                          (self.x + 24.0, fy - 14.0 - beat * 8.0))
            self.feet = None
            self.face = FACES["laugh"]
            self.look = _aim((self.x, fy), (self._cheer_x, fy - 40.0))
        if now >= self._until:
            self._stir_at = now
            self._social_at = now
            self._begin("rest", now)

    def _do_shy(self, now, dt):
        """Off the screen while something covers it, and back after.

        The same three legs the errand for wood has, and for the same reason:
        walking off the edge of his own window is how he leaves without
        anything being switched off, and it reads as a man leaving rather than
        as a sprite being hidden.
        """
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        self.face = FACES["calm"]
        self.look = (0.0, 0.0)
        self.y = self._floor_y()
        x1, x2 = self._walls()
        if self._shy_leg == "out":
            way = self._shy_way
            self.x += way * SHY_SPEED * dt
            self.phase += SHY_SPEED * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.62, way * 3.0
            if self.x < x1 - SHY_OFF or self.x > x2 + SHY_OFF:
                self._shy_leg = "gone"
                try:
                    self.withdraw()
                except tk.TclError:
                    pass
            return
        if self._shy_leg == "gone":
            return
        # back: in from the edge, to where he was standing when it started.
        way = 1.0 if self._shy_home > self.x else -1.0
        self.x += way * SHY_SPEED * dt
        self.phase += SHY_SPEED * dt / STEP_PX * math.pi
        self.facing, self.lean = way * 0.62, way * 3.0
        if abs(self.x - self._shy_home) < SHY_SPEED * dt + 0.5:
            self.x = self._shy_home
            self._stir_at = now
            self._begin("rest", now)

    def come_out(self, now):
        """Whatever was over the screen has gone. Walk back on."""
        if self.state != "shy":
            return
        if self._shy_leg == "gone":
            try:
                self.deiconify()
            except tk.TclError:
                pass
        if self._shy_sat and yard.fire() is not None:
            self._shy_sat = False
            self._begin("vigil", now)   # back to the note he was sitting with
            return
        self._shy_sat = False
        self._shy_leg = "back"
        self.since = now

    def _do_run(self, now, dt):
        """Running - on his own, after somebody, or away from somebody.

        One state for the three, because they are the same legs and differ
        only in who chooses the way. The man in front turns at the walls and
        runs straight back past the man after him, which is what a chase
        looks like; the man behind brakes rather than walking through him.
        """
        x1, x2 = self._walls()
        foe = self._foe if self._foe in crew else None
        step = RUN_SPEED * dt
        if self._run_leg == "off":
            # Not running about: running off. The walls are not walls any
            # more, and what is behind him has a blue light on it.
            self.x += self._run_way * FLEE_SPEED * dt
            self._run_pose(way=self._run_way, dt=dt)
            if not (x1 - FLEE_OFF <= self.x <= x2 + FLEE_OFF):
                self.go_home()
            return
        if foe is not None and self._run_leg == "after":
            self._run_way = 1.0 if foe.x > self.x else -1.0
            step = min(step, max(0.0, abs(foe.x - self.x) - CHASE_GAP))
        way = self._run_way
        self.x += way * step
        if self.x <= x1 or self.x >= x2:
            self.x = _clamp(self.x, x1, x2)
            self._run_way = -way
        self._run_pose(way, dt)
        if now >= self._until:
            self._foe = None
            self._stir_at = now
            self._begin("rest", now)

    def _do_stalk(self, now, dt):
        """The pointer, stalked: the creep, the wiggle, and the pounce.

        He always misses - the pounce is a throw into the ordinary fall, and
        by the time he lands the pointer has moved or it never mattered. The
        landing's dazed-to-calm recovery reads as him deciding he meant to
        do that, which is the whole joke.
        """
        self.y = self._floor_y()
        self.feet = None
        if self._stalk_leg == "creep":
            spot = _pointer()
            if (spot is None or abs(spot[0] - self.x) > STALK_R
                    or now >= self._until):
                # It has wandered off, or he has been at this too long.
                # Straighten up and pretend nothing.
                self._stir_at = now
                self._begin("rest", now)
                return
            px, py = spot
            way = 1.0 if px > self.x else -1.0
            if abs(px - self.x) > POUNCE_NEAR + 26.0:
                x1, x2 = self._walls()
                self.x = _clamp(self.x + way * STALK_SPEED * dt, x1, x2)
                self.phase += STALK_SPEED * dt / STEP_PX * math.pi
                self.squash, self.roll = 1.0, 0.0
                self.crouch = 0.5
                self.facing, self.lean = way * 0.7, way * 1.6
                self.look = _aim((self.x, self._face_y()), (px, py))
                self.face = FACES["smug"]
                self.hands = None
                return
            self._stalk_leg = "wiggle"
            self._prey = (float(px), float(py))
            self.since = now
            return
        # Wound up: down on his haunches, everything wagging.
        u = now - self.since
        px, py = self._prey
        way = 1.0 if px > self.x else -1.0
        self.phase, self.lean = 0.0, 0.0
        self.crouch = 0.68
        self.squash = 1.0 - 0.04 * math.sin(u * 16.0)
        self.roll = math.sin(u * 18.0) * 0.06
        self.facing = _clamp(way * 0.8, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()), (px, py))
        self.face = FACES["smug"]
        self.hands = None
        if u < WIGGLE_S:
            return
        self.vx = _clamp((px - self.x) * 2.6, -260.0, 260.0)
        self.vy = -330.0
        self.spin = 0.0
        self.feel("happy")
        self._begin("fall", now)

    def _do_race(self, now, dt):
        """His lane of it. The gun and the result belong to _run_race."""
        global _race_tripped
        x1, x2 = self._walls()
        self.y = self._floor_y()
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.hands = self.feet = None
        if now >= self._until:
            self._begin("rest", now)
            return
        leg = self._race_leg
        if leg == "line":
            gap = self._race_mark - self.x
            if abs(gap) > 4.0:
                way = 1.0 if gap > 0 else -1.0
                self.x = _clamp(self.x + way * WALK_SPEED * 1.5 * dt, x1, x2)
                self.phase += WALK_SPEED * 1.5 * dt / STEP_PX * math.pi
                self.facing, self.lean = way * 0.62, way * 2.6
                self.face = FACES["happy"]
                return
            self.x = self._race_mark
            self._race_leg = "set"
            return
        if leg == "set":
            way = 1.0 if self._race_far > self.x else -1.0
            self.phase = 0.0
            self.crouch = 0.55
            self.facing, self.lean = way * 0.8, way * 3.0
            self.look = (way * 2.0, 0.5)
            self.face = FACES["strain"]
            if _race_t0 is not None:
                left = _race_t0 - now
                self._say(str(min(3, int(left / (RACE_SET_S / 3.0)) + 1))
                          if left > 0 else "GO")
            return
        if leg in ("out", "home"):
            goal = self._race_far if leg == "out" else self._race_mark
            way = 1.0 if goal > self.x else -1.0
            if (self._race_trip_at is not None
                    and 0.0 < self._race_trip_at <= now):
                # Over he goes, at full tilt.
                _race_tripped = self
                self.vx, self.vy = way * 240.0, -170.0
                self.spin = way * 5.0
                self._begin("fall", now)
                return
            self.x = _clamp(self.x + way * RUN_SPEED * self._race_pace * dt,
                            x1, x2)
            self._run_leg = "solo"      # the effort face
            self._run_pose(way, dt)
            if abs(self.x - goal) < 6.0:
                if leg == "out":
                    self._race_leg = "home"
                else:
                    self._race_leg = "done"
                    _race_order.append(self)
            return
        # done: stood at the line, getting his breath back, awaiting the
        # judges.
        self.phase = 0.0
        self._breathe(now, 0.03, 0.6)
        self.face = FACES["happy"]

    def _do_queue(self, now, dt):
        """His place in the ice cream queue, walked to and then kept."""
        van = yard.van()
        if (van is None or van.kind != "icecream" or van.phase != "serve"
                or now >= self._until):
            self._begin("rest", now)
            return
        x1, x2 = self._walls()
        self.y = self._floor_y()
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        spot = _clamp(van.door + van.side * (16.0 + self._queue_i * QUEUE_GAP),
                      x1, x2)
        gap = spot - self.x
        way = 1.0 if van.x > self.x else -1.0
        if abs(gap) > 4.0:
            step_way = 1.0 if gap > 0 else -1.0
            self.x = _clamp(self.x + step_way * WALK_SPEED * 1.3 * dt, x1, x2)
            self.phase += WALK_SPEED * 1.3 * dt / STEP_PX * math.pi
            self.facing, self.lean = step_way * 0.62, step_way * 2.4
            self.face = FACES["happy"]
            self.hands = self.feet = None
            return
        self.phase, self.lean = 0.0, 0.0
        self._breathe(now)
        self.facing = _mix(self.facing, way * 0.6, 0.15)
        self.look = _aim((self.x, self._face_y()),
                         (van.x, self._face_y() - 14.0))
        self.face = FACES["happy"]
        self.hands = self.feet = None

    def _do_lick(self, now, dt):
        """Off with his cone, in no hurry at all."""
        x1, x2 = self._walls()
        self.y = self._floor_y()
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        u = now - self.since
        gap = self._lick_x - self.x
        if abs(gap) > 6.0:
            way = 1.0 if gap > 0 else -1.0
            self.x = _clamp(self.x + way * WALK_SPEED * 0.6 * dt, x1, x2)
            self.phase += WALK_SPEED * 0.6 * dt / STEP_PX * math.pi
            self.facing, self.lean = way * 0.5, way * 1.2
        else:
            self.phase, self.lean = 0.0, 0.0
            self.facing = _mix(self.facing, 0.0, 0.1)
        # The cone hand stays up by his face, and dips for each lick.
        dip = max(0.0, math.sin(u * 2.2 * TAU))
        fy = self._face_y()
        side = 1.0 if self.facing >= 0 else -1.0
        self.hands = ((self.x + side * 9.0, fy + 7.0 - dip * 3.5), None)
        self.feet = None
        self.look = (side * 1.5, 1.8)
        self.face = FACES["happy"]._replace(open=0.25 * dip)
        if now >= self._until:
            self.prop = None
            self._stir_at = now
            self._begin("rest", now)

    def _do_errand(self, now, dt):
        """Off the side of the screen for a pizza, and back with the box.

        The same three legs the errand for wood has, and the same trick: he
        is never hidden, he has just walked off the edge of his own window.
        No scene behind this one - the picnic is whoever is about when he
        gets back.
        """
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.feet = None
        self.y = self._floor_y()
        self.face = FACES["happy"]
        self.look = (0.0, 0.0)
        x1, x2 = self._walls()
        if now - self.since > FETCH_MAX_S:
            self.prop = None
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
        if now < self._until:
            return                      # out of sight, paying for it
        self.prop = "pizza"
        way = 1.0 if self._site_x > self.x else -1.0
        self.x += way * FETCH_SPEED * dt
        self.phase += FETCH_SPEED * dt / STEP_PX * math.pi
        self.facing, self.lean = way * 0.62, way * 3.0
        fy = self._face_y() + HEAD * 0.35
        self.hands = ((self.x - BOX_W / 2.0, fy), (self.x + BOX_W / 2.0, fy))
        if abs(self.x - self._site_x) < FETCH_SPEED * dt + 0.5:
            self.x = self._site_x
            _serve_picnic(self, now)

    def _do_picnic(self, now, dt):
        """Sat around the box, working through a slice."""
        x1, x2 = self._walls()
        self.y = self._floor_y()
        self.squash, self.roll = 1.0, 0.0
        gap = self._lick_x - self.x
        if abs(gap) > 4.0 and now < self._until:
            way = 1.0 if gap > 0 else -1.0
            self.x = _clamp(self.x + way * WALK_SPEED * dt, x1, x2)
            self.phase += WALK_SPEED * dt / STEP_PX * math.pi
            self.crouch = 0.0
            self.facing, self.lean = way * 0.5, way * 1.2
            self.hands = self.feet = None
            self.face = FACES["happy"]
            return
        # Down at his place, face to the box, slice going up and down - out
        # of step with his neighbour, because six men chewing on one beat is
        # a chorus line, not a picnic.
        floor = self._floor_y()
        way = 1.0 if self._site_x >= self.x else -1.0
        u = now - self.since
        self.phase, self.lean = 0.0, 0.0
        self.crouch = 0.62
        self.facing = _mix(self.facing, way * 0.6, 0.15)
        self._breathe(now, 0.02, 0.25)
        bite = max(0.0, math.sin((u + self._queue_i * 0.7) * BITE_HZ * TAU))
        fy = self._face_y()
        self.hands = ((self.x + way * (9.0 - bite * 4.0),
                       fy + 9.0 - bite * 6.0), None)
        self.feet = ((self.x + way * 9.0, floor),
                     (self.x + way * 16.0, floor))
        self.look = (way * 1.4, 2.2) if bite < 0.4 else (0.0, 0.6)
        self.face = FACES["happy"]._replace(open=0.3 * bite)
        if now >= self._until:
            self.prop = None            # the host's box goes with the rest
            self._stir_at = now
            self._begin("rest", now)

    def _do_help(self, now, dt):
        """Over to whatever has happened, and then straight on the phone.

        The walk is not the point and neither is the phone - what matters is
        that somebody did something, in front of you, before anything turned
        up. An ambulance that arrives out of nowhere is a bug with a siren.
        """
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y()
        fy = self._face_y()
        if self._help_leg == "over":
            gap = self._help_x - self.x
            if abs(gap) > 8.0 and now - self.since < HELP_MAX_S:
                way = 1.0 if gap > 0 else -1.0
                x1, x2 = self._walls()
                self.x = _clamp(self.x + way * HELP_WALK * dt, x1, x2)
                self.phase += HELP_WALK * dt / STEP_PX * math.pi
                self.facing, self.lean = way * 0.62, way * 3.4
                self.face = FACES["panic"]
                self.hands = self.feet = None
                self.look = _aim((self.x, fy), (self._help_at, fy))
                return
            self._help_leg = "call"
            self._until = now + CALL_S
            self.prop = "phone"
            self.since = now
        # On the phone: it at his ear, the other hand going, and looking at
        # the thing he is describing rather than at the phone.
        u = now - self.since
        self.phase, self.lean = 0.0, 0.0
        self.facing = _mix(self.facing, 0.55, 0.12)
        self.hands = ((self.x - 13.0, fy - 2.0),
                      (self.x + 18.0 + math.sin(u * 5.0) * 6.0, fy + 8.0))
        self.look = _aim((self.x, fy), (self._help_at, fy + 10.0))
        self.face = FACES["panic"]._replace(
            open=0.25 + 0.5 * abs(math.sin(now * 4.0 * TAU)))
        self._say("!")
        if now < self._until:
            return
        self.prop = None
        self._mark = None
        yard.call_van(self._help_kind, self._help_at, self._floor_y())
        self._stir_at = now
        self._begin("rest", now)

    def _do_carted(self, now, dt):
        """Onto the stretcher, into the van, and away with it.

        He is carried by the van rather than by anything he does: the yard
        says where the stretcher is and he lies on it. Keeping him a roamer
        instead of drawing a body on the prop is what makes it him being
        carried off - his colours, his face, and his note to come back from.
        """
        van = yard.van()
        spot = None if van is None else van.stretcher()
        self.squash, self.crouch = 1.0, 0.0
        self.phase, self.lean = 0.0, 0.0
        self.hands = self.feet = None
        self.facing = 0.0
        self.face = FACES["dazed"]
        self.look = (0.0, -1.0)
        if spot is not None:
            self.x, self.y = spot[0], spot[1] + STAND_H
            self.roll = math.pi / 2.0 * (1.0 if van.way > 0 else -1.0)
            return
        if van is not None and van.phase == "away":
            # Inside it. Withdrawn rather than drawn over the doors, and the
            # van is what takes him off the screen.
            try:
                if self.winfo_viewable():
                    self.withdraw()
            except tk.TclError:
                pass
            return
        # It has gone, or it never came. Either way he is not lying there for
        # the rest of the afternoon.
        self.roll = 0.0
        self.go_home()

    def _run_pose(self, way, dt):
        """What a running man looks like, whichever kind of running it is.

        The legs go at the pace he is running, not at the pace he is getting
        anywhere: a chaser holding his distance is still running, and so is
        a man who has just crossed the edge of the screen.
        """
        self.phase += RUN_SPEED * (STEP if STEP is not None else 1.0 / 60.0) \
            / STEP_PX * math.pi
        self.facing, self.lean = way * 0.5, way * RUN_LEAN
        self.look = (0.0, 0.0)
        self.face = FACES["laugh" if self._run_leg == "away" else "strain"]
        fy = self._face_y()
        swing = math.sin(self.phase)
        self.hands = ((self.x + way * (12.0 + swing * 14.0), fy + 4.0),
                      (self.x - way * (12.0 - swing * 14.0), fy + 10.0))
        self.feet = None
        self.squash, self.roll, self.crouch = 1.0, 0.0, 0.0
        self.y = self._floor_y() - abs(math.sin(self.phase)) * RUN_BOB

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
                and scene.victim is self)

    def _company(self, now):
        """Where he would rather be walking than nowhere in particular.

        Every leg used to be a random span off wherever he stood, which on a
        thousand pixels of taskbar is a random walk: three of them drift apart
        on the first leg and never come back inside CHAT_R again. Measured over
        two minutes with them dropped a screen apart, that was no conversation
        at all - the scenes underneath were all reachable and none of them was
        ever reached. So most legs are aimed at somebody instead.

        Not gated on being up for talking. One still cooling off wanders over
        anyway, and that is the whole supply of onlookers: somebody has to be
        stood near a conversation he is not in for there to be one.
        """
        if random.random() > SEEK_ODDS or now < self._cross_until:
            return None                 # in a huff, or off on his own
        scene = _scene_near(self, float("inf"))
        if scene is not None:
            return scene.mid
        near = None
        for other in crew:
            if (other is self or other.floor is None or self.floor is None
                    or abs(other.floor - self.floor) > 4.0
                    or other.state not in ("rest", "walk", "chat", "watch")):
                continue
            if near is None or abs(other.x - self.x) < abs(near.x - self.x):
                near = other
        if near is None or abs(near.x - self.x) <= CHAT_GAP:
            return None
        return near.x - math.copysign(CHAT_GAP, near.x - self.x)

    def sociable(self, now):
        # Both a cooldown and having actually parted. A cooldown on its own
        # loops forever if they never move apart; parting on its own starts
        # again the moment they drift back together.
        return (self.scene is None
                and now >= self._social_until
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

    def _do_chat(self, now, dt):
        scene = self.scene
        if scene is None or scene not in scenes or self not in scene.cast:
            self._social_at = now
            self.scene = None
            self._begin("rest", now)
            return
        self._breathe(now)
        beat, u = _beat(scene.table, scene.i)
        if beat == "done":
            _close(scene, now)
            return
        if beat in SPEAKS:
            scene.last_speaker = scene.speaker()
        if beat != scene.beat_was:
            # A shape a sentence, settled on the frame the sentence starts.
            # Whoever steps first this frame picks it and everybody else in
            # the cast reads the same one, which is what keeps a gesture from
            # strobing and the listeners from watching a different hand.
            scene.beat_was = beat
            scene.gesture = random.choice(TALK_GESTURES)
        if scene.kind == "mock":
            self._mock_beat(scene, beat, u, now)
        elif scene.kind == "footy":
            self._footy_beat(scene, u, now, dt)
        elif scene.kind == "build":
            self._build_beat(scene, beat, u, now)
        elif scene.kind == "fire":
            self._fire_beat(scene, beat, u, now, dt)
        else:
            self._talk_beat(scene, beat, u, now)

    def watch(self, scene, now):
        if self.state == "watch" and self._watching is scene:
            return
        self._watching = scene
        # Decided once, on arrival, rather than every frame: whether he has
        # the manners to stay out of it. Without this there is no way into
        # being laughed at on his own - he is stopped at WATCH_R the moment
        # a scene starts near him, and a conversation is over in four seconds,
        # which is not long enough to walk in from out there.
        self._nosy = random.random() < NOSY_ODDS
        self._begin("watch", now)

    def _do_watch(self, now, dt):
        """Stood at the edge of somebody else's conversation.

        His eyes come off the pointer, which nothing but the look out at the
        camera does, and for the same reason: there is something on the screen
        more interesting than the user. Nobody in the scene ever acknowledges
        him. That is the whole of it - unless he is the nosy sort, and then he
        edges in, slower than he walks, until he is close enough to be noticed.
        """
        scene = self._watching
        if scene is None or scene not in scenes or not scene.cast:
            self._watching = None
            self._begin("rest", now)
            return
        self.squash, self.roll, self.crouch, self.lean = 1.0, 0.0, 0.0, 0.0
        self._breathe(now)
        self.hands = self.feet = None
        self.y = self._floor_y()
        self.face = _face_mix(FACES["calm"], FACES["happy"], 0.30)
        if self._nosy and abs(self.x - scene.mid) > 1.0:
            way = 1.0 if scene.mid > self.x else -1.0
            x1, x2 = self._walls()
            self.x = _clamp(self.x + way * CREEP_SPEED * dt, x1, x2)
            self.phase += CREEP_SPEED * dt / STEP_PX * math.pi
            self.lean = way * 1.2
        else:
            self.phase = 0.0
        # Aimed last, from where he has got to rather than from where he stood
        # a frame ago: a head pointed at the speaker from his old position is
        # a head pointed slightly past him.
        who = scene.speaker() or scene.last_speaker or scene.cast[0]
        self.facing = _clamp((who.x - self.x) / 70.0, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (who.x, who._face_y()))

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
        elif beat == "wave":
            # Somebody has just excused himself. They see him off - both of
            # them turning the same way, after him, which is the only beat in
            # any of these tables where they are not looking at each other.
            self.face = FACES["happy"]
            self.facing = _clamp(scene.gone_way * 0.6, -1.0, 1.0)
            self.hands = self._one_hand(
                scene.gone_way, 22.0, -18.0 + math.sin(u * 14.0) * 4.0)
        elif beat == "greet":
            if self.role == 0:
                self.hands = self._one_hand(side, 22.0, -16.0)
                if scene.i == 35:
                    self._say("!")
            self.face = _face_mix(FACES["calm"], FACES["happy"], _smooth(u))
        elif speaking:
            # The gesture is a moving target rather than keyframes: the arm is
            # solved to wherever the hand ought to be and the elbow sorts
            # itself out. That is what the two-bone solver is for. Which shape
            # he makes is the scene's, and changes with the sentence.
            self.hands = self._say_hands(scene.gesture, side, u)
            self.face = FACES["talk"]._replace(
                open=0.25 + 0.55 * abs(math.sin(now * 5.0 * TAU)))
            if scene.gesture == "shrug":
                # The shoulders go with it, or it is only two hands out.
                self.y = self._floor_y() - math.sin(u * math.pi) * 3.0
            elif scene.gesture == "chop":
                self.lean = side * 3.0 * abs(math.sin(u * math.pi * 4.0))
            elif scene.gesture == "point":
                self.lean = side * 2.6
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

    def _say_hands(self, gesture, side, u):
        """The shape his hands make for one sentence, over `u` from 0 to 1.

        Six of them, all solved to a point the arm reaches for rather than
        keyframed, and all of them coming back to about where they started so
        the next sentence does not begin with a jump.
        """
        fy = self._face_y()
        hw = HEAD / 2.0
        w = u * math.pi
        if gesture == "both":
            # Both hands out and opening, the way somebody lays out a case.
            out = 18.0 + 12.0 * math.sin(w)
            return tuple((self.x + s * out, fy + 2.0 + math.cos(w * 2.0) * 5.0)
                         for s in (-1.0, 1.0))
        if gesture == "count":
            # Ticking them off: the hand steps rather than sweeps, because
            # that is the difference between counting and waving.
            step = min(int(u * 3.0), 2)
            return self._one_hand(side, 17.0 + step * 6.0, -3.0 - step * 8.0)
        if gesture == "chop":
            # One flat hand coming down on it, four times to the sentence.
            return self._one_hand(side, 20.0,
                                  4.0 - 20.0 * abs(math.sin(u * math.pi * 4.0)))
        if gesture == "point":
            # Straight at whoever he is talking to, held there.
            return self._one_hand(side, 26.0 + 4.0 * math.sin(w), -2.0)
        if gesture == "shrug":
            # Hands low and wide, palms out. Nothing to do with his face: a
            # shrug is shoulders and hands, and he has no shoulders to speak of.
            return tuple((self.x + s * (hw * 0.9 + 7.0 + 3.0 * math.sin(w)),
                          fy + hw * 0.5)
                         for s in (-1.0, 1.0))
        return self._one_hand(side, 24.0 + 10.0 * math.sin(u * math.pi * 3.0),
                              -6.0 + 8.0 * math.cos(u * math.pi * 2.0))

    def _mock_beat(self, scene, beat, u, now):
        """Two of them pointing, and the one they are pointing at.

        Carried the same way the conversation is - by where they are facing
        and what their faces are doing - and with no more dialogue than that
        one has. A written "ha ha" would be the first line anybody in this app
        had spoken, and it would cheapen a scene that is stronger silent.
        """
        victim = scene.victim
        if victim is None or victim not in scene.cast:
            _close(scene, now)
            return
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

    def _footy_beat(self, scene, u, now, dt):
        """A ball, and whoever is nearest it.

        No sides, no goals and no score. The chaser is worked out from
        distance every frame rather than being appointed, so possession
        changes hands the instant somebody else is closer - which is what
        makes two of them converging on a loose ball read as a game.

        He kicks it at one of the others rather than at nowhere, and only on
        the way down: without the vy >= 0 he re-boots the same ball on the
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

    def _fire_beat(self, scene, beat, u, now, dt):
        """An evening round a fire, in one method because it is one shape.

        Everything below is the same seated body with a different thing on
        top of it: they walk to a place round the flame, sit into it, talk
        across it, watch it go out, stand up out of it and wave. The fire
        itself is the yard's - all this does is sit where it is and end when
        it does.
        """
        seat = scene.seat_x(self)
        floor = self._floor_y()
        inwards = 1.0 if seat < scene.mid else -1.0
        self.squash, self.roll = 1.0, 0.0
        self.lean, self.crouch = 0.0, 0.0
        self.hands = self.feet = None
        self.phase = 0.0
        self.y = floor
        self.facing = _clamp(inwards * 0.72, -1.0, 1.0)
        self.look = _aim((self.x, self._face_y()),
                         (scene.mid, floor - FIRE_LOOK))

        if beat == "gather":
            # To his place, and stood there if he is early. Somebody who was
            # already sat where he wanted is not walked into: the crowd rule
            # gets him out of the way, and this only aims at the seat.
            way = 1.0 if seat > self.x else -1.0
            if abs(self.x - seat) > WALK_SPEED * dt + 0.5:
                self.x += way * WALK_SPEED * dt
                self.phase += WALK_SPEED * dt / STEP_PX * math.pi
                self.facing, self.lean = way * 0.62, way * 2.2
            else:
                self.x = seat
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.35)
            return

        # How far down he is: into the sit, out of it on the way up, and all
        # the way down for everything between.
        if beat == "sit":
            sunk = _smooth(u)
        elif beat == "stand":
            sunk = 1.0 - _smooth(u)
        elif beat == "part":
            sunk = 0.0
        else:
            sunk = 1.0
        if sunk > 0.0:
            # Still easing onto his place while he is down: the gather beat is
            # a fixed length and a walk is not, so anybody who was late slides
            # the last of it rather than sitting where he ran out of beat.
            self.x = _mix(self.x, seat, 0.08)
            # His hips come down and his feet stay on the floor in front of
            # him, so the two-bone legs fold into a sit rather than shrinking.
            self.y = floor + SIT_DROP * sunk
            self.crouch = sunk
            self.feet = ((self.x + inwards * 9.0, floor),
                         (self.x + inwards * 18.0, floor))

        speaking = scene.speaker() is self
        listening = scene.speaker() is not None and not speaking
        blaze = yard.fire()
        if beat == "part":
            # Up, and away. All of them wave, because all of them are leaving:
            # this is not one man excusing himself from a conversation.
            self.face = FACES["happy"]
            self.facing = _clamp(inwards * 0.4, -1.0, 1.0)
            self.hands = self._one_hand(
                inwards, 22.0, -18.0 + math.sin(u * 16.0) * 4.0)
            self._say("bye!")
        elif beat == "stand":
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.4)
        elif beat == "dim":
            # Nobody talks over a fire going out. They watch it instead, and
            # the light going off their faces is the whole beat.
            self.face = _face_mix(FACES["calm"], FACES["think"], 0.35)
            if blaze is not None:
                self.look = _aim((self.x, self._face_y()),
                                 (blaze.x, floor - FIRE_LOOK * blaze.scale))
        elif speaking:
            self.hands = self._say_hands(scene.gesture, -inwards, u)
            self.face = FACES["talk"]._replace(
                open=0.25 + 0.55 * abs(math.sin(now * 5.0 * TAU)))
        elif listening:
            who = scene.speaker()
            self.look = _aim((self.x, self._face_y()),
                             (who.x, who._face_y()))
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.45)
        elif beat == "react":
            if scene.last_speaker is self:
                self.face = _face_mix(FACES["calm"], FACES["think"], 0.6)
            else:
                self.face = FACES["laugh"]
                fy = self._face_y()
                self.hands = ((self.x - 26.0, fy + 8.0),
                              (self.x + 26.0, fy + 8.0))
        else:
            self.face = _face_mix(FACES["calm"], FACES["happy"], 0.3)

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

    def feel(self, mood, seconds=MOOD_S):
        """Put a mood on him. Unknown moods are simply not moods."""
        if mood is not None and mood not in MOOD_FACE:
            return False
        self.mood = mood
        self._mood_until = _time() + float(seconds)
        return True

    def perform(self, act, seconds=None):
        """Do one of the things in ACTS, by name. False if it is not one."""
        if act not in ACTS:
            return False
        now = _time()
        self._leave_scene(now)
        if act == "celebrate":
            self._cheer_x = self.x
            self._begin("cheer", now)
        elif act == "sleep":
            self._begin("sleep", now)
        else:
            state = "phone" if act in ("phone", "call") else act
            self._phone_leg = "talk" if act == "call" else "type"
            self._begin(state, now)
            if seconds is not None or ACTS[act] is not None:
                self._until = now + float(
                    seconds if seconds is not None else ACTS[act])
        _cancel()
        _arm(TICK_MS)
        return True

    def _breathe(self, now, depth=0.018, rate=0.30):
        """The idle breath: about eighteen a minute, and barely there.

        Squash only - the width compensation in the figure turns it into the
        chest filling and emptying rather than the whole man scaling.
        """
        self.squash = 1.0 + depth * math.sin(now * rate * TAU)

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
        # The anger outlives the stomping off. Without this he is fine the
        # instant he stops walking, which reads as a bug rather than as a man
        # getting over it.
        if now < self._cross_until:
            weight = _clamp((self._cross_until - now) / CROSS_S, 0.0, 1.0)
            self.face = _face_mix(self.face, FACES["cross"], weight)
        # ...and so does the fright, for the same reason: a man who is
        # perfectly calm the instant he stops running reads as a bug rather
        # than as somebody getting his breath back.
        if self.mood is not None and now >= self._mood_until:
            self.mood = None
        if self.mood is None and self.temper is not None:
            # A mood wears off; a temper is what the note says, so it is
            # simply put back on.
            self.mood = self.temper
            self._mood_until = now + MOOD_S
        if self.mood is not None:
            look = (GRIN if self.mood == "angry" and self.temper == "angry"
                    else FACES[MOOD_FACE[self.mood]])
            self.face = _face_mix(self.face, look, MOOD_MIX)
        # A poke he gets over about as fast as he got the fright, and for the
        # same reason: a face that snaps back on the landing frame reads as a
        # bug rather than as somebody deciding to let it go.
        if now < self._startle_until:
            weight = _clamp((self._startle_until - now) / STARTLE_S, 0.0, 1.0)
            self.face = _face_mix(self.face, FACES["wtf"], weight * 0.8)
        if now < self._panic_until:
            weight = _clamp((self._panic_until - now) / PANIC_FACE_S,
                            0.0, 1.0)
            self.face = _face_mix(self.face, FACES["panic"], weight * 0.6)

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
                self.hands, self.feet, self.carry,
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
        if self.prop == "phone" and self.hands is not None:
            # In whichever hand is doing the holding: the one at his ear when
            # he is talking, the near one when he is thumbing at it.
            hand = self.hands[0] if self.hands[0] is not None else self.hands[1]
            if hand is not None:
                hx, hy = hand[0] - dx, hand[1] - dy
                cv.create_rectangle(hx - PHONE_W / 2.0, hy - PHONE_H / 2.0,
                                    hx + PHONE_W / 2.0, hy + PHONE_H / 2.0,
                                    fill=PHONE_C, outline=self.ink, width=1,
                                    tags="walker")
        if self.prop == "cone" and self.hands is not None:
            hand = self.hands[0] if self.hands[0] is not None else self.hands[1]
            if hand is not None:
                hx, hy = hand[0] - dx, hand[1] - dy
                cv.create_polygon(hx - 4.0, hy - 1.0, hx + 4.0, hy - 1.0,
                                  hx, hy + 11.0, fill=CONE_C,
                                  outline=self.ink, width=1, tags="walker")
                cv.create_oval(hx - 5.0, hy - 10.0, hx + 5.0, hy,
                               fill=SCOOP_C, outline=self.ink, width=1,
                               tags="walker")
        if self.prop == "pizza" and self.hands is not None:
            # The box flat across both hands, the way the plank rides.
            (lx, ly), (rx, ry) = self.hands
            mid = (ly + ry) / 2.0 - dy
            cv.create_rectangle(lx - dx - 2.0, mid - BOX_H, rx - dx + 2.0,
                                mid, fill=BOX_C, outline=self.ink, width=1,
                                tags="walker")
        if self.prop == "pizza_open" and self.state == "picnic":
            # ponytail: drawn only while the picnic runs; a host yanked away
            # takes the box with him rather than leaving one painted forever.
            bx = self._site_x - dx
            base = self._floor_y() - dy
            cv.create_rectangle(bx - BOX_W / 2.0, base - BOX_H,
                                bx + BOX_W / 2.0, base, fill=BOX_C,
                                outline=self.ink, width=1, tags="walker")
            cv.create_polygon(bx - BOX_W / 2.0, base - BOX_H,
                              bx - BOX_W / 2.0 - 5.0, base - BOX_H - 13.0,
                              bx + BOX_W / 2.0 - 9.0, base - BOX_H - 13.0,
                              bx + BOX_W / 2.0, base - BOX_H, fill=BOX_C,
                              outline=self.ink, width=1, tags="walker")
            cv.create_oval(bx - 8.0, base - BOX_H - 4.0, bx + 8.0,
                           base - BOX_H + 3.0, fill=CRUST_C,
                           outline=self.ink, width=1, tags="walker")
            for px_, py_ in ((-3.5, -1.5), (3.0, -0.5), (0.0, 1.0)):
                cv.create_oval(bx + px_ - 1.4, base - BOX_H + py_ - 1.4,
                               bx + px_ + 1.4, base - BOX_H + py_ + 1.4,
                               fill=PEP_C, outline="", tags="walker")
        if self._t < self._hat_until:
            # The party hat, stuck straight on whatever he is doing.
            top = self.y - dy - STAND_H - HEAD / 2.0
            hx = self.x - dx
            cv.create_polygon(hx - 7.0, top + 3.0, hx + 7.0, top + 3.0,
                              hx, top - HAT_H, fill=HAT_C,
                              outline=self.ink, width=1, tags="walker")
            cv.create_oval(hx - 2.4, top - HAT_H - 4.5, hx + 2.4,
                           top - HAT_H + 0.3, fill=POM_C, outline="",
                           tags="walker")
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
        if self._mark:
            cv.create_text(self.x - dx, self.y - dy - STAND_H - HEAD,
                           text=self._mark, fill=self.limb, font=MARK_FONT,
                           tags="walker")
