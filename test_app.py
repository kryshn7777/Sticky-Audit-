"""End-to-end check of the running app: real windows, real event loop, real file.

Runs against a throwaway APPDATA so your own notes are never touched.

    python test_app.py

Windows will flash on screen for a second or two - that is the point, these
are the actual widgets, not stubs.
"""

import ctypes
import importlib.util
import os
import sys
import tempfile
import time

FAKE_APPDATA = tempfile.mkdtemp(prefix="stickynote-test-")
os.environ["APPDATA"] = FAKE_APPDATA

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load_entrypoint():
    """stickynote.pyw is not importable by name, so load it by path."""
    spec = importlib.util.spec_from_file_location(
        "stickynote_app", os.path.join(HERE, "stickynote.pyw"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_module = _load_entrypoint()
import roamer  # noqa: E402
import store  # noqa: E402


def pump(widget, times=3):
    for _ in range(times):
        widget.update_idletasks()
        widget.update()


def sheet(window):
    """The paper's own rectangle on screen: (x, y, w, h).

    The window can be larger than the sheet, because the mascot's head, hands
    and feet need room outside it. Everything the user thinks of as "the note"
    - its position, its size, what is stored - is this rectangle.
    """
    ox, oy, w, h = window.paper_rect()
    return (window.winfo_x() + ox, window.winfo_y() + oy, w, h)


def _area(poly):
    """Shoelace. Used to check how much of the sheet the fold has covered."""
    total = 0.0
    for i, (x, y) in enumerate(poly):
        px, py = poly[i - 1]
        total += px * y - x * py
    return abs(total) / 2.0


def type_into(app, window, widget, text):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    pump(app.root)


def main():
    app = app_module.App()
    pump(app.root)
    data_file = app.store.path
    assert FAKE_APPDATA in data_file, "test must not touch the real notes file"

    # --- first run hands the user a blank note, already in edit mode ----------
    assert len(app.store.notes) == 1, app.store.notes
    note_id = app.store.notes[0]["id"]
    window = app.windows[note_id]
    assert window.editing, "a brand new note should be ready to write in"
    assert window.toolbar.winfo_ismapped(), "edit mode must show the OK / Trash toolbar"
    print("ok  first run opens one editable note")

    # --- typing autosaves without anyone pressing OK --------------------------
    type_into(app, window, window.head, "Groceries")
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.flush()
    reloaded = store.Store(data_file)
    assert reloaded.notes[0]["heading"] == "Groceries", reloaded.notes[0]
    assert reloaded.notes[0]["body"] == "milk\neggs\nbread"
    print("ok  edits autosave to disk with no OK pressed")

    # --- Enter in the heading moves to the content ----------------------------
    window.head.focus_set()
    pump(app.root)
    window._heading_return(None)
    pump(app.root)
    # focus_lastfor, not focus_get: focus_get reports None whenever the app does
    # not hold OS focus, which is normal for a test launched in the background.
    # focus_lastfor asks Tk which widget owns focus inside this window either way.
    assert window.focus_lastfor() is window.body, "Enter in the heading must jump to the body"
    print("ok  Enter in heading moves to content")

    # --- Esc restores the text as it was when editing began -------------------
    window.finish_edit()
    pump(app.root)
    assert not window.editing
    window.start_edit()
    type_into(app, window, window.body, "scribbled over everything")
    window._cancel_edit()
    pump(app.root)
    assert window.note["body"] == "milk\neggs\nbread", window.note["body"]
    assert not window.editing, "Esc must leave edit mode"
    print("ok  Esc cancels the edit and restores the text")

    # --- undo is wired to the text widget ------------------------------------
    window.start_edit()
    window.body.configure(state="normal")
    window.body.insert("end", "\nbutter")
    window.body.edit_undo()
    pump(app.root)
    assert "butter" not in window.body.get("1.0", "end-1c"), "Ctrl+Z must undo"
    window.finish_edit()
    print("ok  undo works in the content area")

    # --- the note grows for content, then stops and scrolls -------------------
    small = sheet(window)[3]
    window.start_edit()
    type_into(app, window, window.body, "\n".join("line %d" % i for i in range(80)))
    window._autosize()
    pump(app.root)
    grown = sheet(window)[3]
    assert grown > small, "note should grow with content (%d -> %d)" % (small, grown)
    import note as note_module
    assert grown <= note_module.MAX_H, "note must not grow past its maximum"
    assert window.scroll.winfo_ismapped(), "past the maximum the body must scroll"
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.finish_edit()
    pump(app.root)
    print("ok  auto-size grows to a limit, then scrolls")

    # --- a click is not a drag -----------------------------------------------
    before = sheet(window)[:2]
    fake = type("E", (), {"x_root": before[0] + 40, "y_root": before[1] + 6,
                          "widget": window.canvas, "x": 40, "y": 6})()
    window._press_start(fake)
    fake.x_root += 3                       # 3px twitch: under the drag threshold
    window._press_move(fake)
    pump(app.root)
    assert sheet(window)[:2] == before, "a 3px twitch must not move it"
    fake.x_root += 60                      # now a real drag
    window._press_move(fake)
    window._press_end(fake)
    pump(app.root)
    assert sheet(window)[0] != before[0], "a real drag must move the note"
    assert store.Store(data_file).notes[0]["x"] == sheet(window)[0], "position must persist"
    print("ok  drag needs real movement, and the new position is saved")

    # --- manual resize, and the content reflowing into the new shape ----------
    window.start_edit()
    type_into(app, window, window.body,
              "a long line of text that has to rewrap when the note changes width")
    window._autosize()
    window.finish_edit()
    pump(app.root)
    ox, oy, start_w, start_h = window.paper_rect()
    body_w0 = window.body.winfo_width()

    corner = (window.winfo_rootx() + ox + start_w - 3,
              window.winfo_rooty() + oy + start_h - 3)
    grab = type("E", (), {"x_root": corner[0], "y_root": corner[1],
                          "widget": window.canvas, "x": ox + start_w - 3,
                          "y": oy + start_h - 3})()
    assert window._resize_mode(grab) == "se", "the folded corner must grab as a resize"
    window._press_start(grab)
    grab.x_root += 90
    grab.y_root += 70
    window._press_move(grab)
    window._press_end(grab)
    pump(app.root)

    assert sheet(window)[2] > start_w and sheet(window)[3] > start_h, \
        "dragging the corner must resize the note"
    assert window.note["auto_size"] is False, "a hand-sized note stops resizing itself"
    assert window.body.winfo_width() > body_w0, "the content area must follow the new size"
    saved = store.Store(data_file).notes[0]
    assert (saved["w"], saved["h"]) == sheet(window)[2:], "the new size must persist"

    # past the auto-size ceiling by hand, which manual resizing is allowed to do
    import note as note_mod
    ox, oy, cur_w, cur_h = window.paper_rect()
    wide = type("E", (), {"x_root": window.winfo_rootx() + ox + cur_w - 2,
                          "y_root": window.winfo_rooty() + oy + 60,
                          "widget": window.canvas, "x": ox + cur_w - 2, "y": oy + 60})()
    assert window._resize_mode(wide) == "e", "the right edge must resize width only"
    tall_before = sheet(window)[3]
    window._press_start(wide)
    wide.x_root += 260
    window._press_move(wide)
    window._press_end(wide)
    pump(app.root)
    assert sheet(window)[2] > note_mod.MAX_W, "hand resizing is bounded by the screen"
    assert sheet(window)[3] == tall_before, "the right edge must not change height"
    print("ok  notes resize by corner and edge, content reflows, size persists")
    window.start_edit()
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.finish_edit()
    pump(app.root)

    # --- colour ---------------------------------------------------------------
    window.set_color("green")
    pump(app.root)
    assert store.Store(data_file).notes[0]["color"] == "green"
    window.mascot.finish_swipe()
    pump(app.root)
    print("ok  colour change persists")

    # --- bold / italic / underline and font size ------------------------------
    window.start_edit()
    type_into(app, window, window.body, "plain and loud")
    window.body.tag_add("sel", "1.0+10c", "1.0+14c")     # select "loud"
    window.toggle_format("bold")
    window.toggle_format("italic")
    pump(app.root)
    assert "bold" in window.body.tag_names("1.0+11c"), "bold must apply to the selection"
    assert "italic" in window.body.tag_names("1.0+11c")
    assert "bi" in window.body.tag_names("1.0+11c"), \
        "bold plus italic must resolve to the bold-italic face"
    assert "bold" not in window.body.tag_names("1.0+2c"), "must not spill past the selection"

    window.body.tag_add("sel", "1.0", "1.0+5c")
    window.toggle_format("underline")
    pump(app.root)
    window.flush()
    marks = {tuple(m[:1]) for m in store.Store(data_file).notes[0]["marks"]}
    assert {("bold",), ("italic",), ("underline",)} <= marks, marks

    size0 = window.note["font_size"]
    window.bump_font(3)
    pump(app.root)
    assert window.note["font_size"] == size0 + 3
    assert window.f_body.cget("size") > 0
    for _ in range(40):
        window.bump_font(1)
    assert window.note["font_size"] == note_mod.MAX_FONT, "font size must clamp"
    window.note["font_size"] = size0
    window._apply_font_size()
    window.finish_edit()
    pump(app.root)
    print("ok  bold, italic, underline and font size apply, clamp and persist")

    # formatting must survive a reload, not just a save
    reborn = app_module.App()
    pump(reborn.root)
    body = list(reborn.windows.values())[0].body
    assert "bold" in body.tag_names("1.0+11c"), "formatting must come back on reload"
    assert "bi" in body.tag_names("1.0+11c"), "bold-italic must be re-derived on reload"
    reborn.quit_app()
    print("ok  formatting survives a restart")

    window.start_edit()
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.finish_edit()
    pump(app.root)

    # --- the mascot: eyes, tears, and the cost of both ------------------------
    import mascot as mascot_mod
    figure = window.mascot
    assert len(figure._eyes) == 2, "the mascot needs two eyes"
    assert figure.pose in mascot_mod.POSES, figure.pose
    assert mascot_mod.pose_for("1a2b3c4d") == mascot_mod.pose_for("1a2b3c4d"), \
        "a note must get the same pose every time it is opened"
    assert len({mascot_mod.pose_for("%08x" % i) for i in range(64)}) > 1, \
        "different notes must not all strike the same pose"

    # Every pose has to draw, and none of them may move or resize the sheet:
    # only the transparent room around it changes.
    base = sheet(window)
    for pose in mascot_mod.POSES:
        figure.pose = pose
        window.apply_mascot()
        pump(app.root)
        assert len(figure._eyes) == 2, "%s must draw a face with eyes" % pose
        assert window.paper_rect()[:2] == mascot_mod.POSE_MARGINS[pose][:2], pose
        assert sheet(window) == base, "the %s pose moved the sheet" % pose
    figure.pose = mascot_mod.pose_for(window.note["id"])
    window.apply_mascot()
    pump(app.root)

    head_x = window.winfo_rootx() + figure._head[0]
    head_y = window.winfo_rooty() + figure._head[1]
    figure.look_at(head_x - 500, head_y)
    left = figure._pupil
    eye_left = window.canvas.coords(figure._eyes[0])
    figure.look_at(head_x + 500, head_y)
    right = figure._pupil
    assert left[0] < 0 < right[0], "the eyes must follow the pointer (%s, %s)" % (left, right)
    # + half a pixel: offsets are quantised to half-pixel steps, so the
    # furthest reach can round up by one step.
    assert abs(left[0]) <= mascot_mod.PUPIL_TRAVEL + 0.5, "pupils stay inside the head"
    assert window.canvas.coords(figure._eyes[0]) != eye_left, "the eye must actually move"

    figure.rest()
    assert figure._pupil == (0.0, 0.0), "with nothing to look at the eyes recentre"

    # He must watch the whole desktop, not only his own note - and a pointer
    # you have stopped moving is still somewhere, so the aim has to hold.
    sx0, sy0 = sheet(window)[:2]
    figure.look_at(sx0 - 700, sy0 + 50)
    aimed = figure._pupil
    assert aimed[0] < 0, "the eyes must follow a pointer far away to the left"
    figure.look_at(sx0 + 900, sy0 + 50)
    assert figure._pupil[0] > 0, "and back the other way, still off the note"

    parked = app.root.winfo_pointerxy()
    aimed = figure._pupil
    real_pointer = app.root.winfo_pointerxy
    app.root.winfo_pointerxy = lambda: parked
    try:
        app.tracker._last = parked
        app.tracker._moved_at -= 10          # as if parked for ten seconds
        for _ in range(4):
            app.tracker.tick()
    finally:
        app.root.winfo_pointerxy = real_pointer
    assert figure._pupil == aimed, \
        "a parked pointer must not make the eyes snap back to centre"
    assert app.tracker._resting, "and the poll must back off while it is parked"

    def settle():
        """Let the two or three frames of the eye animation play out."""
        for _ in range(mascot_mod.GROW_STEPS + 2):
            pump(app.root)
            if figure._grow_job is not None:
                window.after(mascot_mod.GROW_MS + 10)
        pump(app.root)

    def gaze(x, y):
        """look_at, with the real pointer parked in the same place.

        The tracker owns a timer of its own and it runs during settle(), so it
        re-aims him at wherever the mouse actually is. A mouse left lying on
        the note then fails "he settles once the pointer leaves" for a reason
        that has nothing whatever to do with the code.
        """
        app.root.winfo_pointerxy = lambda: (int(x), int(y))
        figure.look_at(x, y)

    def eye_width():
        box = window.canvas.coords(figure._eyes[0])
        return box[2] - box[0]

    sx, sy, sw, sh = sheet(window)
    gaze(sx + sw // 2, sy + sh // 2)
    settle()
    assert figure.near(), "a pointer on the note must cheer him up"
    assert window.canvas.find_withtag("mascot_glint"), "his eyes must catch the light"
    assert abs(eye_width() - 2 * mascot_mod.EYE_R_WIDE) < 0.01, \
        "delighted eyes must open all the way (%.2f)" % eye_width()

    gaze(sx - 900, sy - 900)
    settle()
    assert not figure.near(), "and settle again once the pointer leaves"
    assert not window.canvas.find_withtag("mascot_glint"), "the catchlights must clear"
    assert figure._grow_job is None, "no timer may be left running behind them"
    assert abs(eye_width() - 2 * mascot_mod.EYE_R) < 0.01, \
        "and the eyes must go back to their resting size (%.2f)" % eye_width()

    # Resizing repaints the note on every mouse move, and each repaint rebuilds
    # him from nothing. If that forgot he was already pleased to see you, the
    # tracker would light him up again on its next tick - ten times a second,
    # all the way through the drag, which is what a flicker is.
    gaze(sx + sw // 2, sy + sh // 2)
    settle()
    assert figure.near() and figure._glints, "he should be pleased before we start"
    wide = eye_width()
    for _ in range(3):
        window._redraw()
        pump(app.root)
        assert figure.near(), "a repaint must not talk him out of it"
        assert window.canvas.find_withtag("mascot_glint"), \
            "and must not drop the catchlights it is about to want back"
        assert abs(eye_width() - wide) < 0.01, \
            "and must not restart the widening animation (%.2f)" % eye_width()

    # His smile is drawn once, not moved by _apply_eyes, so it has to carry the
    # "mascot" tag or a hop leaves it hanging in mid air.
    mouth_before = window.canvas.coords(figure._mouth)
    figure._reaction = "hop"
    figure._react_step(4)                       # mid jump: he is off the ground
    assert figure._offset[1] < -1.0, "the hop has to actually lift him"
    assert window.canvas.coords(figure._mouth) != mouth_before, \
        "his mouth must go up with the rest of his face"
    figure._cancel_react()
    pump(app.root)
    gaze(sx - 900, sy - 900)
    settle()

    # The whole performance claim in one assertion: a tick with a pointer that
    # has not moved must not touch a canvas. His idle beat rides that same tick
    # on purpose, so park it: what is being measured here is the cost of the
    # pointer, and a blink that happens to land mid-measurement is not that.
    figure.quiet_down(999.0)
    figure.rest()
    app.tracker._last = app.root.winfo_pointerxy()
    app.tracker._resting = True
    quiet = window.canvas.coords(figure._eyes[0])
    app.tracker.tick()
    assert window.canvas.coords(figure._eyes[0]) == quiet, \
        "an unmoved pointer must cost nothing but the timer"
    app.root.winfo_pointerxy = real_pointer
    print("ok  four poses draw, none moves the sheet; eyes track, light up, idle free")

    # --- he wipes a new colour across the note --------------------------------
    window.set_color("purple")
    pump(app.root)
    assert window.note["color"] == "purple", "the colour changes at once..."
    assert store.Store(data_file).notes[0]["color"] == "purple", \
        "...and reaches disk without waiting for the animation to finish"
    flip = figure._swipe
    assert flip is not None and flip.winfo_exists(), "he must turn the sheet over"

    # He works from the corner the note already draws as lifted off the pad,
    # and the fold he pushes starts there and finishes past the far side.
    ox, oy, pw, ph = window.paper_rect()
    assert flip.corner[0] > ox + pw, \
        "he has to work from the right-hand side, where the curled corner is"
    assert flip.floor + mascot_mod.LEG_H + mascot_mod.HEAD / 2 > oy + ph, \
        "and stand on the floor beneath the sheet, not up on it"
    assert _area(flip._covered(0.0)) < 1.0, "nothing is covered before he starts"
    assert abs(_area(flip._covered(1.0)) - pw * ph) < 1.0, \
        "by the end the fold is over the whole sheet, so the repaint never shows"
    midway = _area(flip._covered(0.5))
    assert 0 < midway < pw * ph, "and it gets there gradually (%s)" % midway
    for u in (0.0, 0.3, 0.7, 1.0):
        hand = flip._grip(u)
        assert ox <= hand[0] <= ox + pw and oy <= hand[1] <= oy + ph, \
            "his hand stays on the sheet he has hold of (%s)" % (hand,)

    # Whichever pose he set off from, he goes round the note rather than over
    # it. Only the blank strip along the bottom edge is his to cross.
    for route in (flip.out, flip.back):
        for k in range(41):
            (x, y), _way = flip._along(route, k / 40.0)
            assert not (ox < x < ox + pw and oy < y < oy + ph - 30), \
                "his route must not cross the writing (%.0f, %.0f)" % (x, y)

    assert window.canvas.itemcget(figure._eyes[0], "state") == "hidden", \
        "and the figure on the note steps aside while he does it"

    # The words go over with the page. The face coming into view is the same
    # note, so it carries the same writing in the new ink - without it the
    # sheet turns over blank and everything pops back at the end.
    said = {run[2] for run in flip.words}
    assert "milk" in " ".join(said), ("the writing must come off the widgets", said)
    drag_at = sum(n for name, n in flip.beats
                  if name in ("brace", "walk", "turn", "reach"))
    if flip._job is not None:
        flip.after_cancel(flip._job)    # or its own next frame lands first
        flip._job = None
    flip._step(drag_at + dict(flip.beats)["drag"] // 2)
    if flip._job is not None:
        flip.after_cancel(flip._job)
        flip._job = None
    drawn = [flip.canvas.itemcget(i, "text")
             for i in flip.canvas.find_all()
             if flip.canvas.type(i) == "text"]
    assert drawn, "the fold has to carry the words across with it"
    # ...and he changes colour over the same crossing rather than snapping to
    # it at the end, because he is standing on the side that has turned.
    assert 0.0 < flip._turned < 1.0, flip._turned

    flip.finish()
    pump(app.root)
    assert figure._swipe is None, "and clear the animation away after itself"
    assert flip._job is None, "leaving no timer behind"
    assert window.canvas.itemcget(figure._eyes[0], "state") != "hidden", \
        "and put the real one back"
    assert window.body.cget("bg") == store.COLORS["purple"]["paper"], \
        "the note must end up actually repainted"
    window.set_color("green")
    window.mascot.finish_swipe()
    pump(app.root)
    print("ok  a colour change is folded across by hand, round the note not over it")

    # --- tapping him gets a reaction ------------------------------------------
    def at(wx, wy):
        return type("E", (), {"x_root": window.winfo_rootx() + int(wx),
                              "y_root": window.winfo_rooty() + int(wy),
                              "widget": window.canvas,
                              "x": int(wx), "y": int(wy)})()

    fx, fy = figure.head_at()
    tap = at(fx, fy)
    assert window._on_mascot(tap), "his face has to be tappable"
    ox, oy, pw, ph = window.paper_rect()
    assert not window._on_mascot(at(ox + pw / 2, oy + ph / 2)), \
        "the middle of the note is not him"

    # The real pointer is wherever the person running this left it. If it
    # happens to be near the note he sways, and a swaying figure is never
    # exactly back at nought - so take him off the tracker for this part and
    # measure the reactions on their own.
    app.tracker.unregister(figure)
    figure.quiet_down(999.0)          # and no blinking through the reactions

    seen = set()
    for _ in range(len(mascot_mod.REACTIONS)):
        # Space the taps out, or the fourth in a row trips the "you are
        # enjoying this" special and forces the same reaction twice.
        figure._taps, figure._last_tap = 0, 0.0
        window._press_start(tap)
        window._press_end(tap)
        pump(app.root)
        assert figure._reaction is not None, "a tap must get a reaction out of him"
        seen.add(figure._reaction)
        for _ in range(mascot_mod.REACT_FRAMES + 3):
            pump(app.root)
            if figure._react_job is not None:
                window.after(mascot_mod.REACT_MS + 8)
        pump(app.root)
        assert figure._react_job is None, "a reaction must not leave a timer running"
        assert figure._reaction is None, "and must finish"
        assert figure._offset == (0.0, 0.0), "and must put him back where he was"
        assert not window.canvas.find_withtag("mascot_pop"), \
            "and must clear away whatever it popped up"
    assert len(seen) == len(mascot_mod.REACTIONS), \
        "poking him repeatedly must not give the same reaction every time: %s" % seen

    # ...and a drag that starts on him is for him: his face picks him up, and
    # the note stays exactly where it was. It used to drag the note, which is
    # what the rest of the paper and the strip along the top are still for.
    stayed = sheet(window)
    was_wide = window.winfo_width()
    window._press_start(at(fx, fy))
    pull = at(fx + 70, fy)
    window._press_move(pull)
    pump(app.root)
    guy = window._roamer
    assert guy is not None and guy.state == "held", "his face has to pick him up"
    assert not figure.visible(), "and the note has to stop drawing him"
    assert figure._reaction is None, "and it must not count as a tap"
    # The margins he needs are left in place the whole time he is away. Taking
    # them back here would reflow the writing and pull the sheet out from under
    # the hand that is doing the dragging.
    assert sheet(window) == stayed, "the sheet must not move under the drag"
    assert window.winfo_width() == was_wide, "and must not resize either"
    window._press_end(pull)
    pump(app.root)
    assert window._roamer is None, "letting go hands him over to the crew"
    roamer.send_all_home()
    pump(app.root)
    assert figure.visible() and not roamer.crew, "and he can always be sent back"
    assert sheet(window) == stayed
    app.tracker.register(figure)
    figure.hush()
    print("ok  tapping him reacts, dragging him picks him up, the note stays put")

    # --- switching him off gives the space back -------------------------------
    sheet_before = sheet(window)
    window_before = (window.winfo_width(), window.winfo_height())
    app.set_mascot(False)
    pump(app.root)
    assert not figure.visible(), "switched off, there is nothing left to track"
    assert window.paper_rect()[:2] == (0, 0), "no mascot, no margins"
    now = (window.winfo_width(), window.winfo_height())
    assert now[0] <= window_before[0] and now[1] <= window_before[1] \
        and now != window_before, \
        "the window gives back whichever side he was holding on to"
    assert sheet(window) == sheet_before, "but the sheet must not move or resize"
    assert store.Store(data_file).settings["mascot"] is False, "the choice must persist"

    labels = [window.menu.entrycget(i, "label")
              for i in range(window.menu.index("end") + 1)
              if window.menu.type(i) != "separator"]
    assert "Show mascot" in labels, "he must be switchable from the right-click menu"

    app.set_mascot(True)
    pump(app.root)
    assert sheet(window) == sheet_before, "and must not move coming back either"
    assert window.mascot.visible()
    print("ok  right-click switches the mascot off and on, sheet unmoved")

    # --- checkboxes -----------------------------------------------------------
    window.start_edit()
    type_into(app, window, window.body, "milk\neggs")
    window.body.mark_set("insert", "1.0")
    window.toggle_checkbox()
    pump(app.root)
    assert window.body.get("1.0", "1.end") == "[ ] milk", window.body.get("1.0", "1.end")
    window.toggle_checkbox()
    assert window.body.get("1.0", "1.end") == "milk", "toggling again takes it away"

    window.body.tag_add("sel", "1.0", "2.end")
    window.toggle_checkbox()
    pump(app.root)
    assert window.body.get("1.0", "end-1c") == "[ ] milk\n[ ] eggs", \
        "a selection turns every line into a checkbox"
    window.finish_edit()
    pump(app.root)

    box = window.body.bbox("1.1")
    assert box, "the checkbox must be on screen to be clickable"
    click = type("E", (), {"widget": window.body, "x": box[0] + 1, "y": box[1] + 1})()
    window._maybe_toggle_box(click)
    pump(app.root)
    assert window.body.get("1.0", "1.end") == "[x] milk", "clicking the box must tick it"
    assert str(window.body["state"]) == "disabled", \
        "ticking a box must not drop the note into edit mode"
    window.flush()
    assert store.Store(data_file).notes[0]["body"] == "[x] milk\n[ ] eggs", \
        "ticked boxes must persist as ordinary text"
    assert mascot_mod.has_open_box(window.note["body"]), "one box is still open"
    assert not mascot_mod.has_open_box("[x] milk\n[x] eggs")
    print("ok  checkboxes add, tick by click, and persist as plain text")

    # --- and that is what he has to talk about --------------------------------
    assert window.mascot.say("test line"), "the mascot must be able to speak"
    pump(app.root)
    bubble = window.mascot._bubble
    assert bubble is not None and bubble.winfo_exists(), "the line needs a bubble"
    window.mascot.hush()
    pump(app.root)
    assert window.mascot._bubble is None, "and the bubble must clean itself up"
    app._nag()                                 # must never raise, whatever it decides
    pump(app.root)
    print("ok  the mascot mentions unticked boxes, then gets out of the way")

    window.start_edit()
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.finish_edit()
    pump(app.root)

    # --- the right-click menu -------------------------------------------------
    window._sync_menu()            # what opening it does, minus the popup
    menu = window.menu
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
              if menu.type(i) != "separator"]
    for expected in ("Edit note", "Yellow", "Green", "Pink", "Purple", "Blue",
                     "Always on top", "New note", "Move to Trash"):
        assert expected in labels, "%r missing from the right-click menu: %s" % (expected, labels)
    menu.invoke(labels.index("Pink") + 1)          # +1 for the separator above
    pump(app.root)
    assert window.note["color"] == "pink", "menu colour must apply"
    window.set_color("green")
    pump(app.root)
    print("ok  right-click menu offers edit, colours, on-top, new and trash")

    # --- trash is reversible, straight from the right-click menu --------------
    trash_index = menu.index("Move to Trash")
    menu.invoke(trash_index)
    pump(app.root)
    assert note_id not in app.windows, "trashing must close the note window"
    assert len(store.Store(data_file).trash) == 1, "trashed note lives in Trash"
    assert app.toast is not None and app.toast.winfo_exists(), "Undo must be offered"
    app.toast._fire()
    pump(app.root)
    assert note_id in app.windows, "Undo must bring the note back"
    assert store.Store(data_file).notes[0]["body"] == "milk\neggs\nbread"
    print("ok  Move to Trash is reversible, with an Undo offered")

    # --- more notes, each with its own everything -----------------------------
    second = app.new_note("blue")
    type_into(app, second, second.head, "Second")
    second.finish_edit()
    pump(app.root)
    saved = store.Store(data_file)
    assert len(saved.notes) == 2
    assert {n["color"] for n in saved.notes} == {"green", "blue"}
    assert len({(n["x"], n["y"]) for n in saved.notes}) == 2, "new notes must cascade"
    print("ok  multiple notes keep their own colour, text and position")

    # --- closing the overview must not take the notes with it -----------------
    app.board.hide()
    pump(app.root)
    assert all(w.winfo_exists() for w in app.windows.values()), \
        "closing the overview must leave the notes on the desktop"
    app.board.show()
    pump(app.root)
    print("ok  closing the overview leaves the notes alone")

    # --- off the note: he falls, walks, takes hold, and has opinions ----------
    # How he moves cannot be asserted - that has to be watched - but every
    # state he can get into is reachable from here, and the two things that
    # really would hurt can be: a timer left running when nobody has picked him
    # up, and an arm that has quietly stopped being an arm.
    roamer.STEP = 1.0 / 60.0            # pinned, so the physics repeats exactly

    def steps(n, stop=None):
        """Exactly n steps of the crew, and no others.

        tick() arms a real timer on its way out, pump() runs it, and that one
        arms the next, so a plain crank of five measured 106 steps here -
        enough to run a whole conversation to its end before the assertion
        underneath it had looked. The scene checks need a beat they can point
        at, so they use this. _arm gives up when there is no root, so the root
        goes away for the duration and is put back, armed, on the way out.
        """
        saved, roamer._root = roamer._root, None
        roamer._cancel()
        try:
            for i in range(n):
                roamer.tick()
                pump(app.root, 1)
                if stop is not None and stop():
                    return i
            return None
        finally:
            roamer._root = saved
            roamer._arm(roamer.TICK_MS)

    crank = steps

    reach = mascot_mod.UPPER_ARM + mascot_mod.FOREARM
    elbow, hand = mascot_mod._reach((0.0, 0.0), (500.0, 0.0),
                                    mascot_mod.UPPER_ARM, mascot_mod.FOREARM)
    assert abs(hand[0] - reach * 0.995) < 0.01 and abs(hand[1]) < 0.01, hand
    assert abs(mascot_mod._dist((0.0, 0.0), elbow) - mascot_mod.UPPER_ARM) < 0.01
    assert abs(mascot_mod._dist(elbow, hand) - mascot_mod.FOREARM) < 0.01
    down = mascot_mod._reach((0.0, 0.0), (12.0, 0.0), 8.5, 9.0, bend=1.0)[0]
    up = mascot_mod._reach((0.0, 0.0), (12.0, 0.0), 8.5, 9.0, bend=-1.0)[0]
    assert down[1] * up[1] < 0, "bend has to put the elbow on either side"

    # An angry face, and not the same angry as the look out at the camera.
    cross = mascot_mod.FACES["cross"]
    wtf = mascot_mod.FACES["wtf"]
    assert cross.brow < 0 and cross.tilt < 0, "brows down and in, or it is not anger"
    assert cross.curve < 0, "and a frown, not a smile"
    assert cross.eye < 1.0 < wtf.eye, \
        "cross narrows his eyes where wtf makes saucers - that is the difference"
    print("ok  he has a face for being laughed at")

    # The one-armed call the colour flip makes is left alone, stretch and all:
    # he never steps close enough to that crease for a real elbow to reach it,
    # and the flip is finished work. Routing it through the solver would leave
    # his hand short of the paper, which is the regression this pins.
    probe = app_module.tk.Canvas(app.root, width=240, height=240)
    far = (140.0, 130.0)

    def hand_lands_on(point, **kw):
        probe.delete("probe")
        mascot_mod._walker(probe, 100.0, 100.0, None, "#ffffff", "#888888",
                           "#000000", facing=0.9, tag="probe", **kw)
        for item in probe.find_withtag("probe"):
            box = probe.coords(item)
            if len(box) != 4:
                continue
            if (abs((box[0] + box[2]) / 2.0 - point[0]) < 0.5
                    and abs((box[1] + box[3]) / 2.0 - point[1]) < 0.5):
                return True
        return False

    assert hand_lands_on(far, hand=far), "hand= must still reach all the way"
    assert not hand_lands_on(far, hands=(None, far)), \
        "a jointed arm has to stop at its own length"
    probe.destroy()
    print("ok  the arm bends both ways, reaches its limit and no further")

    # Undo reopened the first note as a new window, so take a fresh hold of it.
    window = app.windows[note_id]
    line = roamer.floor_at(600, 600)
    if line is None:
        print("ok  roaming skipped: nowhere to stand")
    else:
        left, right, floor = line
        # Park both sheets in one corner: earlier checks have dragged and
        # resized them, and he takes hold of whatever edge he lands beside.
        for paper in (window, second):
            paper._apply_geometry(paper.note["w"], paper.note["h"], 40, 40)
        pump(app.root)
        base = sheet(window)

        # thrown, and he falls, bounces off the side of the screen, and
        # arrives on the taskbar
        guy = roamer.Roamer(app, window, right - 60.0, floor - 300.0)
        assert roamer._job is not None, "somebody out there needs a timer"
        guy.let_go()
        assert guy.state == "fall", guy.state
        guy.vx, guy.vy = 700.0, -260.0

        # The overlay must not chase him. Moving a layered top-level window
        # does not take effect until the event loop runs again, while the
        # canvas inside it is redrawn against the new origin at once - so a
        # window that follows him composites the figure at its new offset in a
        # window still at the old place, and a throw judders and flicks about.
        # It is the size of the screen and it stays where it is.
        moved = []
        settled = guy.geometry

        def watched(spec=None):
            if spec is None:
                return settled()
            moved.append(spec)
            return settled(spec)

        guy.geometry = watched
        far = [guy.x]

        def down():
            far[0] = max(far[0], guy.x)
            return guy.state in ("rest", "walk")

        crank(900, down)
        assert guy.state in ("rest", "walk"), guy.state
        assert abs(guy.y - guy.floor) < 3.0, (guy.y, guy.floor)
        assert not moved, ("the overlay must not follow him: %s" % moved[:2])
        # In the air the walls are the screen. The patrol line stops short of
        # the clock, and bouncing off that in mid-flight is an invisible wall.
        walls = guy._walls()
        assert far[0] > right, ("thrown, he has to be able to pass the patrol "
                                "line: %.0f vs %.0f" % (far[0], right))
        assert walls[0] <= guy.x <= walls[1], (guy.x, walls)
        guy.vanish()

        # let go by a sheet and he takes hold of the edge and hangs there
        second._apply_geometry(second.note["w"], second.note["h"], 600, 260)
        pump(app.root)
        ox, oy, pw, ph = second.paper_rect()
        edge_x = second.winfo_rootx() + ox + pw / 2.0
        edge_y = second.winfo_rooty() + oy + ph
        held = roamer.Roamer(app, window, edge_x, edge_y + roamer.STAND_H + 18.0)
        held.let_go()
        assert held.state == "reach" and held.grip_note is second, held.state
        crank(300, lambda: held.state == "grip")
        assert held.state == "grip", held.state
        for got, want in zip(held.hands, held._grip_points()):
            assert mascot_mod._dist(got, want) < roamer.GRIP_SLOP, (got, want)

        # the note goes somewhere and his hands go with it, one frame behind
        was = second.winfo_rootx()
        second._apply_geometry(second.note["w"], second.note["h"], 660, 260)
        pump(app.root)
        assert second.winfo_rootx() != was, "the note has to have actually moved"
        crank(2)
        # Right after the shove, not thirty frames later: by then the swing has
        # damped back through the middle and the check is a coin toss.
        assert held.swinging(), (held.sway, held.sway_v)
        was_side, was_t = held.grip_side, held.grip_t
        crank(28)
        for got, want in zip(held.hands, held._grip_points()):
            assert mascot_mod._dist(got, want) < roamer.GRIP_SLOP, (got, want)

        # and a note that goes away leaves him holding nothing
        second.withdraw()
        pump(app.root)
        crank(4)
        assert held.state == "fall", held.state
        second.deiconify()
        pump(app.root)
        held.vanish()
        assert was_side == "bottom" and 0.3 < was_t < 0.7, (was_side, was_t)
        print("ok  he takes hold of a sheet, travels with it, drops when it goes")

        # Dropped on the sheet itself he takes the nearest edge, at the point
        # he came down - and stands on the top one rather than hanging from it,
        # which would put his body straight over the writing.
        ox, oy, pw, ph = second.paper_rect()
        sx = second.winfo_rootx() + ox
        sy = second.winfo_rooty() + oy
        want = sx + pw * 0.72
        perch = roamer.Roamer(app, window, want, sy + ph * 0.25 + roamer.STAND_H)
        perch.let_go()
        assert perch.grip_side == "top", perch.grip_side
        crank(300, lambda: perch.state == "grip")
        assert perch.state == "grip", perch.state
        assert perch.feet is not None and perch.hands is None, "he stands on it"
        assert abs((perch.feet[0][0] + perch.feet[1][0]) / 2.0 - want) < 14.0, \
            "and where he was dropped, not somewhere of its own choosing"
        assert abs(perch.y - sy) < 1.0, ("on top of the sheet", perch.y, sy)
        perch.vanish()
        print("ok  he takes hold where he is dropped, and stands on a top edge")

        # two of them on the same floor hold a conversation, once
        a = roamer.Roamer(app, window, right - 420.0, floor)
        b = roamer.Roamer(app, second, right - 420.0 + roamer.CHAT_R * 0.7, floor)
        for one in (a, b):
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one._until = time.monotonic() + 999.0
            one._social_at = 0.0
        crank(5)
        assert a.state == "chat" and b.state == "chat", (a.state, b.state)
        assert a.partner is b and b.partner is a, "and they know who with"
        crank(500, lambda: a.state != "chat" and b.state != "chat")
        assert a.state == "walk" and b.state == "walk", (a.state, b.state)
        assert (a._goal - a.x) * (b._goal - b.x) < 0, \
            "they have to leave in opposite directions"
        crank(600)
        assert a.state != "chat" and b.state != "chat", "once, not on a loop"
        print("ok  two of them talk, and only the once")

        step = steps

        def park(guys, gap=roamer.CHAT_R * 0.6):
            """Everybody on the floor, in a row, and willing to talk."""
            for stale in list(roamer.scenes):
                roamer._close(stale, roamer._time())
            for k, one in enumerate(guys):
                one.x = right - 460.0 + k * gap
                one.state, one.floor, one.y = "rest", floor, floor
                one.vx = one.vy = 0.0
                one._until = time.monotonic() + 999.0
                one._social_at = 0.0
                one._social_until = 0.0

        # three of them together talk as three, and everybody gets a turn
        third = app.new_note("green")
        pump(app.root)
        trio = [a, b, roamer.Roamer(app, third, 0.0, floor)]
        park(trio)
        step(5)
        assert all(one.state == "chat" for one in trio), \
            [one.state for one in trio]
        scene = trio[0].scene
        assert scene is not None and len(scene.cast) == 3, "one cast of three"
        assert all(one.scene is scene for one in trio), "and all in the same one"
        assert sorted(one.role for one in trio) == [0, 1, 2], "distinct roles"
        assert [one.x for one in scene.cast] == sorted(one.x for one in trio), \
            "the cast is ordered left to right"
        spoke = set()

        def note_speaker():
            scene = trio[0].scene
            if scene is not None:
                who = scene.speaker()
                if who is not None:
                    spoke.add(who.role)
            return scene is None

        step(600, note_speaker)
        assert spoke == {0, 1, 2}, ("everybody gets a turn", spoke)
        assert all(one.state == "walk" for one in trio), \
            [one.state for one in trio]
        step(600)
        assert all(one.state != "chat" for one in trio), "once, not on a loop"
        # Only the third one goes: a and b are the pair the checks either side
        # of this one are built around.
        trio[2].vanish()
        print("ok  three of them talk, and everybody gets a turn")

        # two of them talking, and a third who turns up and hangs back
        onlooker = roamer.Roamer(app, third, 0.0, floor)
        pair = [a, b]
        park(pair + [onlooker])
        # Out of talking distance of either of them, but inside watching
        # distance of the pair - so he can never be cast, only an audience.
        onlooker.x = (pair[0].x + pair[1].x) / 2.0 + 200.0
        step(8)
        scene = a.scene
        assert scene is not None and len(scene.cast) == 2, "the two of them"
        assert onlooker not in scene.cast, "he is not in it"
        assert onlooker.state == "watch", onlooker.state
        assert scene.i > 0, "and the conversation is running normally"

        # His eyes are on whoever is talking rather than on the pointer, which
        # is the only other thing they are ever on. Not asserted by comparing
        # one speaker against the other: they stand on the same floor, so the
        # line to either of them from out here is flat, and _aim normalises
        # both to the same offset. Aiming at the right head is the check.
        seen = {}

        def note_eyes():
            if a.scene is None:
                return True
            who = a.scene.speaker()
            if who is not None:
                seen[who.role] = (
                    onlooker.look,
                    mascot_mod._aim((onlooker.x, onlooker._face_y()),
                                    (who.x, who._face_y())),
                    onlooker.facing)
            return False

        step(600, note_eyes)
        assert set(seen) == {0, 1}, ("he saw both of them speak", set(seen))
        for role, (look, want, facing) in seen.items():
            assert look == want, ("his eyes are on the speaker", role, look, want)
            assert facing < -0.5, ("and he is turned their way", role, facing)
        assert onlooker.state == "rest", onlooker.state
        onlooker.vanish()
        print("ok  one who turns up late hangs back and watches")

        # lift one over the other and the one left behind looks straight out
        b.state, b.y, b.floor, b.facing = "rest", floor, floor, 0.9
        b._until = time.monotonic() + 999.0
        # Held over him. pick_up() takes hold where he already is - it does
        # not drag him under the pointer - so he is put there first.
        a.x, a.y = b.x + 30.0, b.y - roamer.STAND_H - 120.0
        a.pick_up()
        crank(30, lambda: b.state == "wtf")
        assert b.state == "wtf", b.state
        crank(14)
        assert abs(b.facing) < 0.05, b.facing
        assert b.look == (0.0, 0.0), "his eyes come off the pointer for it"
        print("ok  one of them lifted over the other gets a look")

        # asked to leave, he goes, and does not come back
        goer = roamer.Roamer(app, window, (left + right) / 2.0, floor)
        goer.state, goer.floor, goer.y = "rest", floor, floor
        goer._until = time.monotonic() + 999.0
        goer.excuse_me()
        assert goer.state == "leave", goer.state
        crank(3)
        assert abs(goer.y - floor) < 0.01, "he winds up before he jumps"
        crank(20, lambda: goer._launched)
        assert goer._launched and goer.vy < 0.0, (goer._launched, goer.vy)
        peak = [goer.y]

        def apex():
            peak[0] = min(peak[0], goer.y)
            return goer not in roamer.crew

        crank(600, apex)
        high = peak[0]
        assert floor - high > 100.0, ("that has to read as a leap", floor - high)
        assert goer not in roamer.crew and not goer.winfo_exists(), \
            "and he has to be gone off the screen at the end of it"
        print("ok  asked to leave, he jumps off the bar and is gone")

        # --- and none of it is left running ---------------------------------
        roamer.send_all_home()
        pump(app.root)
        assert not roamer.crew, "everybody goes back on his note"
        assert roamer._job is None, "an empty crew must not own a timer"
        assert window.mascot.visible() and second.mascot.visible()
        assert sheet(window) == base, "and the sheet is where it always was"

        # The performance claim again, now that all of that has happened: an
        # unmoved pointer still costs nothing, and nothing is ticking behind it.
        window.mascot.quiet_down(999.0)
        window.mascot.rest()
        app.tracker._last = app.root.winfo_pointerxy()
        app.tracker._resting = True
        quiet = window.canvas.coords(window.mascot._eyes[0])
        app.tracker.tick()
        assert window.canvas.coords(window.mascot._eyes[0]) == quiet, \
            "an unmoved pointer must still cost nothing but the timer"
        window.mascot.hush()
        print("ok  he goes home, and leaves nothing running behind him")

        # The third sheet was only ever somewhere for the third of them to
        # come from. The checks past here count what is on the desk.
        app.trash_note(third.note["id"])
        pump(app.root)
    roamer.STEP = None

    # --- pinning a note to another application's window -----------------------
    # A real second window, from a real second process, because the whole
    # feature is about talking to something that is not us: a stand-in inside
    # this process would be skipped by the very check that makes it work.
    import subprocess
    pin_title = "PIN TARGET %d" % os.getpid()
    host = subprocess.Popen(
        [sys.executable, "-c",
         "import sys,tkinter as tk;r=tk.Tk();r.title(sys.argv[1]);"
         "r.geometry('320x200+90+90');r.attributes('-topmost',True);r.mainloop()",
         pin_title])
    # If anything below fails, that window must still go: a stray host left
    # running gets picked up by the next run and makes it fail for the wrong
    # reason - which is exactly how this line came to be here.
    import atexit
    atexit.register(lambda: host.poll() is None and host.kill())
    target = None
    for _ in range(80):
        pump(app.root)
        window.after(60)
        target = app_module.winkit.find_window(pin_title)
        if target:
            break
    if target is None:
        host.kill()
        print("ok  pinning skipped: the host window never appeared")
    else:
        hwnd, title, rect = target
        pinned = app.windows[note_id]
        pinned.unpin()
        natural = mascot_mod.pose_for(pinned.note["id"])

        bar = type("E", (), {"x_root": rect[0] + 60, "y_root": rect[1] + 8,
                             "widget": pinned.canvas, "x": 60, "y": 8})()
        assert app_module.winkit.title_bar_target(bar.x_root, bar.y_root),             "the top of another app's window must read as a title bar"
        assert not app_module.winkit.title_bar_target(rect[0] + 60, rect[1] + 150),             "but the middle of it must not - a note does not clip to content"

        # Lay the note's own top strip on the bar: that is what the pin looks
        # at now, not wherever the pointer happens to be.
        pinned.note["x"], pinned.note["y"] = rect[0] + 40, rect[1] + 8
        pinned._apply_geometry(pinned.note["w"], pinned.note["h"],
                               pinned.note["x"], pinned.note["y"])
        pump(app.root)
        pinned._settle_drop(bar)
        pump(app.root)
        assert pinned.note["pin"], "dropping on a title bar must pin the note"
        assert pinned.note["pin"]["title"] == pin_title
        assert pinned in app.tracker.pinned, "and the tracker must start following it"
        assert pinned.canvas.find_withtag("clip"), "a paperclip must appear on it"
        if natural == "top":
            assert pinned.mascot.pose == "hang",                 "he cannot sit on an edge that is under a title bar"
        assert store.Store(data_file).get(note_id)["pin"], "the pin must persist"

        # ...and the note travels with the window it is clipped to
        assert pinned.canvas.find_withtag("clip"), "a paperclip must appear on it"
        offset = (pinned.note["x"] - rect[0], pinned.note["y"] - rect[1])
        app_module.winkit._pin_api().MoveWindow(
            ctypes.c_void_p(hwnd), rect[0] + 140, rect[1] + 70, 320, 200, True)
        moved = None
        for _ in range(60):
            pump(app.root)
            window.after(40)
            app.tracker.tick()
            moved = app_module.winkit.window_rect(hwnd)
            if moved and (moved[0], moved[1]) != (rect[0], rect[1]):
                break
        pump(app.root)
        app.tracker.tick()
        pump(app.root)
        assert (pinned.note["x"] - moved[0], pinned.note["y"] - moved[1]) == offset,             "a pinned note must keep its place on the window it is clipped to"

        # closing that app leaves the note behind, without its clip
        host.kill()
        host.wait(timeout=10)
        for _ in range(60):
            pump(app.root)
            window.after(40)
            app.tracker.tick()
            if not pinned.note["pin"]:
                break
        pump(app.root)
        assert not pinned.note["pin"], "closing the host must take the clip off"
        assert pinned.winfo_exists(), "but must never take the note with it"
        assert pinned not in app.tracker.pinned, "and stop the following"
        assert pinned.mascot.pose == natural, "he goes back to his usual spot"
        print("ok  a note clips to another app's title bar and travels with it")

    # --- restart: everything comes back ---------------------------------------
    app.quit_app()
    restarted = app_module.App()
    pump(restarted.root)
    assert len(restarted.store.notes) == 2, "notes must survive a restart"
    assert len(restarted.windows) == 2, "each saved note reopens as a window"
    headings = {n["heading"] for n in restarted.store.notes}
    assert "Groceries" in headings and "Second" in headings, headings
    print("ok  notes and their windows return after a restart")

    # --- an empty desk is a blank sheet, not an empty screen ------------------
    # Throwing the last note away and starting again used to open to nothing at
    # all: the trash was treated as "not a first run", so no sheet was handed
    # out. From the outside that is indistinguishable from the app not starting.
    for note in list(restarted.store.notes):
        restarted.trash_note(note["id"])
    restarted.quit_app()
    empty = app_module.App()
    pump(empty.root)
    assert empty.store.trash, "this only means anything with notes in the trash"
    assert len(empty.windows) == 1, \
        "starting with nothing on the desk must still put a sheet out"
    assert empty.windows and list(empty.windows.values())[0].editing, \
        "and it should be ready to write in, like any new note"
    print("ok  a desk emptied into the trash still opens a blank sheet")

    empty.quit_app()
    print("\nall app checks passed")
    print("test data was written to %s" % FAKE_APPDATA)


if __name__ == "__main__":
    main()
