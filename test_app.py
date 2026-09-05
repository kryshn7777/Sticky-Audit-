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

FAKE_APPDATA = tempfile.mkdtemp(prefix="sticky-test-")
os.environ["APPDATA"] = FAKE_APPDATA

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if os.environ.get("STICKY_TEST_NO_TOPMOST"):
    # These are real windows, and real windows sit on top of whatever the
    # person running the suite is doing for the minute or two it takes. Set
    # STICKY_TEST_NO_TOPMOST=1 to get the screen back. Off by default, so
    # what runs unattended is still what ships. The foreign window the clip
    # check puts up is a separate process and stays on top either way, which
    # is the point of it.
    import tkinter as _tk

    _real_attributes = _tk.Wm.attributes

    def _no_topmost(self, *args):
        if len(args) >= 2 and args[0] == "-topmost":
            args = ("-topmost", False) + args[2:]
        return _real_attributes(self, *args)

    _tk.Wm.attributes = _no_topmost


def _load_entrypoint():
    """sticky.pyw is not importable by name, so load it by path."""
    spec = importlib.util.spec_from_file_location(
        "sticky_app", os.path.join(HERE, "sticky.pyw"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app_module = _load_entrypoint()
import board as board_mod  # noqa: E402
import roamer  # noqa: E402
import store  # noqa: E402
import yard  # noqa: E402


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

    # --- the first thing he ever says -----------------------------------------
    # Driven rather than waited for: the bubble is on a timer, and a check that
    # sleeps for it would put a speech bubble into the middle of whichever
    # block the suite happened to be running when it fired.
    assert app._hello_job is not None, "a first run has a hello pending"
    assert not app.store.settings["said_hello"], "and has not said it yet"
    app.root.after_cancel(app._hello_job)
    app._hello()
    said = [w for w in app.windows.values() if w.mascot._bubble is not None]
    assert len(said) == 1, ("one of them says it, once", len(said))
    assert app.store.settings["said_hello"], "and it is written down"
    said[0].mascot.hush()
    app._hello()
    assert not any(w.mascot._bubble is not None for w in app.windows.values()), \
        "saying it again is not what once means"
    pump(app.root)
    print("ok  he introduces himself on the first run, and only then")

    # --- Ctrl+Alt+N, from whatever you were doing -----------------------------
    # Windows will not press a key for the suite, so the press itself is posted
    # to the same window a real one goes to. That is the half worth checking:
    # a hotkey registered against the thread instead never arrives at all,
    # because Tcl's notifier drains the thread queue before anything of ours
    # can look at it.
    assert app.store.settings["quick_capture"], "on by default"
    assert app.hotkey.hwnd, "and it owns a window to be told through"
    # Every argument declared, or ctypes passes the module handle as a C int
    # and the app dies on start - but only on the boots where Windows happened
    # to load it above 2GB, which is why this is checked and not just run.
    make = app_module.winkit._user32().CreateWindowExW
    assert make.argtypes is not None, (
        "an argument left undeclared goes across as an int")
    assert ctypes.sizeof(make.argtypes[10]) == ctypes.sizeof(ctypes.c_void_p), (
        "and hInstance is a whole address, not half of one")
    before = len(app.store.notes)
    winkit_mod = app_module.winkit
    _wt = ctypes.wintypes
    ctypes.windll.user32.PostMessageW(_wt.HWND(app.hotkey.hwnd),
                                      winkit_mod._WM_HOTKEY,
                                      winkit_mod._HOTKEY_ID, 0)
    pump(app.root)
    assert app.hotkey.pressed, "the window procedure has to see it"
    assert app.tracker.also is not None, "and the tracker has to be looking"
    app.tracker.tick()           # the look, driven rather than waited on
    pump(app.root)
    assert len(app.store.notes) == before + 1, (
        "the key has to make a note", len(app.store.notes), before)
    caught = app.windows[app.store.notes[-1]["id"]]
    assert caught.editing, "and hand it to you ready to type into"
    px, py = app.root.winfo_pointerxy()
    assert abs(caught.winfo_rootx() - px) < 300 and \
        abs(caught.winfo_rooty() - py) < 300, (
        "somewhere near the pointer, not where the cascade was up to",
        (caught.winfo_rootx(), caught.winfo_rooty()), (px, py))
    caught.finish_edit()
    # Taken off the desk completely rather than binned: the Trash is counted
    # further down, and a note left in it there is this check's fingerprint on
    # somebody else's.
    app.trash_note(caught.note["id"])
    app.store.purge(caught.note["id"])
    app.store.save()
    if app.toast is not None:
        app.toast.close()
        app.toast = None
    app.refresh_board()
    pump(app.root)
    assert not app.store.trash, "and the Trash is as it was"

    # Turned off, the key goes back to whoever else wants it.
    assert app.set_quick_capture(False) is False, "off is off"
    assert not app.store.settings["quick_capture"]
    assert app.set_quick_capture(True) is True, "and on again is on"
    print("ok  Ctrl+Alt+N drops a note where the pointer is")

    # --- first run hands the user a desk that shows what the app does ---------
    # Three notes, not one: a stranger who sees an empty sheet never finds out
    # that anybody reads it.
    assert len(app.store.notes) == 3, app.store.notes
    starters = {n["heading"]: n for n in app.store.notes}
    assert set(starters) == {"He reads your notes", "Things to try",
                             "So sleepy"}, sorted(starters)
    # The note that asks for a pizza must not contain the word. He reads his
    # own note as he is born and would count it as already ordered, so the
    # first thing a new user is told to try would do nothing at all.
    ask = starters["He reads your notes"]
    words = ("%s %s" % (ask["heading"], ask["body"])).lower()
    for word in roamer.PIZZA_WORDS + roamer.BDAY_WORDS:
        assert word not in words, ("a one-shot word in the note that asks for "
                                   "it is a one-shot already spent", word)
    assert app_module.mascot.has_open_box(starters["Things to try"]["body"]), \
        "the list has to have something left to tick"
    assert roamer.temper_of(starters["So sleepy"]["body"]) == "sleepy", \
        "and the sleepy note has to actually make a sleepy man"
    print("ok  first run opens a desk that introduces the crew")

    # --- the first ten minutes run the crew fast ------------------------------
    # Everything they do on their own is on a clock measured in minutes, which
    # is nothing to watch on the day you install it.
    assert roamer.HASTE == app_module.SHOWTIME_HASTE, "a first run hurries them"
    assert app._show_job is not None, "and has an end to it pending"
    far = roamer._time() + 9999.0
    roamer._pounce_at = 1.0             # long due, so the next look fires
    fired = roamer._due("_pounce_at", roamer.POUNCE_EVERY, far)
    assert fired, "a clock this far past due has to fire"
    assert roamer._pounce_at - far <= roamer.POUNCE_EVERY[1] * roamer.HASTE, \
        ("and be wound by the haste, not the full wait",
         roamer._pounce_at - far)
    app.root.after_cancel(app._show_job)
    app._end_showtime()
    assert roamer.HASTE == 1.0, "then normal time, for good"
    assert app._show_job is None
    roamer._pounce_at = 0.0
    print("ok  a first run hurries the fun along, then stops")

    # Back to one blank note: everything below was written against a desk with
    # a single sheet on it, and the starter notes have said their piece.
    for note in list(app.store.notes):
        app.trash_note(note["id"])
        app.store.purge(note["id"])
    if app.toast is not None:
        app.toast.close()
        app.toast = None
    app.store.save()
    window = app.new_note()
    note_id = window.note["id"]
    pump(app.root)
    assert len(app.store.notes) == 1, app.store.notes
    assert window.editing, "a brand new note should be ready to write in"
    assert window.toolbar.winfo_ismapped(), "edit mode must show the OK / Trash toolbar"
    print("ok  a new note opens ready to write in")

    # --- typing autosaves without anyone pressing OK --------------------------
    type_into(app, window, window.head, "Groceries")
    type_into(app, window, window.body, "milk\neggs\nbread")
    window.flush()
    reloaded = store.Store(data_file)
    assert reloaded.notes[0]["heading"] == "Groceries", reloaded.notes[0]
    assert reloaded.notes[0]["body"] == "milk\neggs\nbread"
    print("ok  edits autosave to disk with no OK pressed")

    # --- an earlier version of a note is one menu away -------------------------
    # On a note of its own: the checks further down were written against what
    # they typed into the first one, and this would be overwriting it.
    drafts = app.new_note("purple")
    pump(app.root)
    for text in ("first thoughts", "second thoughts"):
        drafts.start_edit()
        drafts.body.delete("1.0", "end")
        type_into(app, drafts, drafts.body, text)
        drafts.finish_edit()
        pump(app.root)
        # Two saves a second apart are one sitting, and the newest version is
        # rewritten rather than piling up - which is the point of the gap. So
        # the clock is pushed on here instead of the suite waiting two minutes
        # to find out whether a menu has an entry in it.
        if drafts.note["history"]:
            drafts.note["history"][-1]["t"] -= store.HISTORY_GAP + 1.0

    older = drafts.earlier_versions()
    assert any(v["body"].strip() == "first thoughts" for v in older), (
        "what it said before is still there", [v["body"] for v in older])
    drafts._sync_menu()          # what opening the menu does, minus the popup
    hist = drafts.menu_history
    labels = [hist.entrycget(i, "label") for i in range(hist.index("end") + 1)]
    assert any("first thoughts" in label for label in labels), labels

    assert drafts.restore_version(
        [i for i, v in enumerate(older)
         if v["body"].strip() == "first thoughts"][0])
    assert drafts.body.get("1.0", "end-1c").strip() == "first thoughts", (
        "and putting it back puts it back", drafts.body.get("1.0", "end-1c"))
    assert any(v["body"].strip() == "second thoughts"
               for v in drafts.earlier_versions()), (
        "restoring is itself undoable")

    app.trash_note(drafts.note["id"])
    app.store.purge(drafts.note["id"])
    app.store.save()
    if app.toast is not None:
        app.toast.close()
        app.toast = None
    app.refresh_board()
    pump(app.root)
    assert not app.store.trash, "and the desk is as it was"
    print("ok  an earlier version of a note is one menu away")

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

    # The overlay is pinned to the note's corner, and every coordinate in it
    # is the note window's own - so a note dragged out from under a colour
    # change has to take the crease with it. It used to be placed once, when
    # the fold was built, and the sheet would walk off and leave it folding
    # thin air where the note had been.
    home_at = (window.winfo_x(), window.winfo_y())
    window.geometry("+%d+%d" % (home_at[0] + 90, home_at[1] + 40))
    pump(app.root)
    flip._step(drag_at + dict(flip.beats)["drag"] // 2)
    if flip._job is not None:
        flip.after_cancel(flip._job)
        flip._job = None
    pump(app.root)
    assert (flip.winfo_rootx(), flip.winfo_rooty()) == \
        (window.winfo_rootx(), window.winfo_rooty()), \
        ("the fold has to travel with the note",
         (flip.winfo_rootx(), flip.winfo_rooty()),
         (window.winfo_rootx(), window.winfo_rooty()))
    window.geometry("+%d+%d" % home_at)
    pump(app.root)

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
        # Everything the tap depends on, read before _press_end throws it away.
        # A bare "he did not react" says nothing about which of the four things
        # that have to be true was not.
        why = (window._tapped, window._roamer, figure.away, bool(figure._eyes),
               figure._offset, figure._face_box, (tap.x, tap.y))
        window._press_end(tap)
        # Read before the pump, not after. react() picks the reaction and puts
        # up its first frame in the same call, so this is the whole of what a
        # tap is meant to do; pumping first asks a second question - whether
        # it is still running some frames later - which is a question about
        # how long the machine took, and it answered no often enough to be
        # worth not asking.
        started = figure._reaction
        pump(app.root)
        assert started is not None,             "a tap must get a reaction out of him: %r" % (why,)
        seen.add(started)
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

    # ...and when the crew is full he cannot come off, so the drag has to fall
    # through to what a drag does everywhere else on the note. It used to be
    # swallowed: the mascot stayed, the note stayed, and the drag did nothing
    # at all. Pinned to nought rather than to the real cap, because this is
    # about what happens when there is no room, not about how much room
    # there is.
    was_max, roamer.MAX_ROAMERS = roamer.MAX_ROAMERS, 0
    try:
        was_at = sheet(window)
        window._press_start(at(fx, fy))
        window._press_move(at(fx + 70, fy))
        pump(app.root)
        assert window._roamer is None, "a full crew has no room for him"
        assert figure.visible(), "so the note goes on drawing him"
        assert sheet(window)[0] - was_at[0] == 70, \
            ("and the drag moves the note instead", sheet(window), was_at)
        # The gesture is dropped rather than finished. All of this lives
        # in _press_move; letting _press_end land the drag would run the
        # drop through _settle_drop, which asks Windows what is under the
        # note's top strip - and that is whatever the person running this
        # happens to have open, so the note would pin itself to something
        # different every run. What a landed drag does is checked where
        # the note is dragged on purpose.
        window._press = None
        window._dragging = window._tapped = False
        pump(app.root)
    finally:
        roamer.MAX_ROAMERS = was_max
    window.note["x"], window.note["y"] = was_at[0], was_at[1]
    window._apply_geometry(window.note["w"], window.note["h"],
                           was_at[0], was_at[1])
    window.flush()
    pump(app.root)
    assert sheet(window) == was_at, "and it goes back where it was"
    app.tracker.register(figure)
    figure.hush()
    # The face survives a squash: it is a rounded twelve-point polygon, and
    # a reaction that fed coords() two corners used to collapse it to a
    # sliver - a mascot with eyes and no box.
    figure._face_scale = (1.3, 0.7)
    figure._apply_face()
    assert len(figure.cv.coords(figure._face_item)) >= 24, \
        "the squashed face is still the whole rounded box"
    figure._face_scale = (1.0, 1.0)
    figure._apply_face()
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

    # --- finding a note by what is written on it ------------------------------
    board = app.board
    board.show()
    pump(app.root)
    rows_before = len(board.list.winfo_children())
    assert rows_before >= 2, "there have to be a few notes to search"

    board.var_find.set("milk")
    pump(app.root)
    assert board.matches({"heading": "", "body": "milk\neggs"}, ["milk"])
    assert not board.matches({"heading": "", "body": "eggs"}, ["milk"])
    assert board.matches({"heading": "Shop", "body": "milk"}, ["shop", "milk"]), \
        "every word, not any of them"
    assert not board.matches({"heading": "Shop", "body": "milk"},
                             ["shop", "bread"])
    found = len(board.list.winfo_children())
    assert 0 < found < rows_before, (
        "the list has to actually narrow", found, rows_before)
    assert "/" in board.tab_notes.cget("text"), (
        "and say how many of how many", board.tab_notes.cget("text"))

    board.var_find.set("zzzz nothing says this")
    pump(app.root)
    labels = [w.cget("text") for w in board.list.winfo_children()
              if w.winfo_class() == "Label"]
    assert any("Nothing here says" in label for label in labels), labels

    board._clear_find()
    pump(app.root)
    assert board.var_find.get() == "", "and clearing it clears it"
    assert len(board.list.winfo_children()) == rows_before, (
        "with everything back", len(board.list.winfo_children()), rows_before)
    print("ok  the overview finds a note by what is written on it")

    # --- the words they react to are written down somewhere -------------------
    # Built from the crew's own lists rather than typed out again, so the day
    # somebody adds a word the page says so.
    legend = board_mod.legend_text()
    for word in roamer.PIZZA_WORDS[:1] + roamer.BDAY_WORDS[:1]:
        assert word in legend, ("a trigger word missing from the legend", word)
    for mood, words in roamer.TEMPER_WORDS.items():
        assert mood.upper() in legend, ("a mood nobody is told about", mood)
        assert words[0] in legend, ("and no word to type for it", mood)
    assert "[ ]" in legend, "the boxes are a trigger too"
    print("ok  the board says what they react to")

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
    # ...and nothing is full-screen as far as the crew is concerned. Whatever
    # the suite is being watched in is a window over the top of it, and a
    # maximised one would send them off the bar in the middle of a check that
    # is about something else entirely. The check that is about it puts its
    # own answer in for as long as it needs one.
    roamer.winkit.foreground_fullscreen = lambda: False
    roamer.shy = False
    # ...and nobody starts anything on his own while the suite is looking at
    # something else. A scrap out of nowhere in the middle of the errand for
    # wood is a check that fails once a fortnight for a reason nobody can
    # reproduce. The checks that are about it turn it back on.
    roamer.SPONTANEOUS = False

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
        # Clear of the paper as well as high up. A note that has grown to its
        # limit is wider than a small work area, so the corner it was parked
        # in reaches all the way across the throw - and a man dropped on a
        # sheet takes hold of it rather than falling off it.
        under = max([paper.winfo_rooty() + paper.winfo_height()
                     for paper in app.windows.values()] or [0.0])
        drop = min(max(floor - 300.0,
                       under + roamer.GRAB_NEAR + roamer.STAND_H + 40.0),
                   floor - 20.0)
        guy = roamer.Roamer(app, window, right - 60.0, drop)
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

        # picked up, carried, and put down again: the three things a hand ever
        # does to him, and each of them has to read as something happening to a
        # body rather than as a sprite following the pointer.
        mine = roamer.Roamer(app, window, right - 400.0, floor)
        mine._begin("rest", roamer._time())
        crank(2)
        mine.pick_up(mine.x, mine.y)
        crank(1)
        assert mine.state == "held", mine.state
        assert mine.squash > 1.05, ("the yank has to stretch him", mine.squash)
        crank(int(roamer.GRAB_S / roamer.STEP) + 4)
        assert mine.squash < 1.06, ("and be over inside GRAB_S", mine.squash)

        # carried left, he hangs back the way he came, and the other way when
        # the hand turns round. A pose that does not change with the direction
        # of travel is the sprite on a string this replaces.
        for i in range(4):
            mine.drag_to(right - 400.0 - 40.0 * (i + 1), mine.y)
            crank(1)
        assert mine._swing < -1.0, ("he has to trail the hand", mine._swing)
        left_lean = mine.lean
        for i in range(4):
            mine.drag_to(right - 560.0 + 40.0 * (i + 1), mine.y)
            crank(1)
        assert mine._swing > 1.0 and mine.lean < left_lean, \
            ("and swing the other way when it turns round",
             mine._swing, mine.lean, left_lean)

        # clicked rather than dragged: a poke. He hops where he stands and has
        # something to say about it - he is not thrown across the desk.
        mine.pick_up(mine.x, mine.y)
        crank(1)
        was_x = mine.x
        mine.let_go()
        assert mine.vy < 0.0 and abs(mine.vx) < 1.0, \
            ("a poke is a hop, not a throw", mine.vx, mine.vy)
        assert mine._startle_until > roamer._time(), "and he has words about it"
        crank(300, lambda: mine.state in ("rest", "walk"))
        assert abs(mine.x - was_x) < 40.0, \
            ("and he comes down where he was", mine.x, was_x)
        mine.vanish()
        print("ok  he is yanked up, trails the hand, and hops when poked")

        # stood about with nothing on, he does something with his hands
        idler = roamer.Roamer(app, window, right - 500.0, floor)
        was_every, roamer.IDLE_EVERY = roamer.IDLE_EVERY, (0.0, 0.0)
        idler._begin("rest", roamer._time())
        idler._until = roamer._time() + 999.0
        crank(3)
        assert idler._act in roamer.IDLE_ACTS, ("something, and soon", idler._act)
        assert idler.rate() == roamer.TICK_MS, \
            "an arm going over his head is worth the frames"
        acted = idler._act
        # An idle every zero seconds is only for getting one started. Left on,
        # the next begins on the frame this one ends and nothing is ever seen
        # to finish.
        roamer.IDLE_EVERY = (999.0, 999.0)
        crank(int(max(roamer.IDLE_S.values()) / roamer.STEP) + 10)
        assert idler._act is None, ("and it ends", idler._act, acted)
        assert idler.hands is None and idler.feet is None, \
            "with his arms back at his sides"
        roamer.IDLE_EVERY = was_every
        idler.vanish()
        print("ok  standing still, he stretches, yawns, scratches and looks about")

        # ...and nobody stands inside anybody. Two of them dropped on the same
        # pixel shuffle apart rather than sharing a body, and they do it
        # without a conversation to space them out.
        near = [roamer.Roamer(app, window, right - 460.0, floor),
                roamer.Roamer(app, window, right - 460.0, floor)]
        spot = roamer._time()
        for one in near:
            one.floor, one.y = floor, floor
            one.vx = one.vy = 0.0
            one._begin("rest", spot)
            one._until = spot + 999.0
            one._social_until = spot + 999.0    # a queue, not a chat
        crank(90)
        assert abs(near[0].x - near[1].x) >= roamer.SPACE_R - 1.0, (
            "nobody stands inside anybody", near[0].x, near[1].x)
        assert all(one.state == "rest" for one in near), (
            "and making room is not something they walk off to do",
            [one.state for one in near])
        for one in near:
            one.vanish()
        print("ok  two of them on one spot make room for each other")

        # every mood, and every act any of them can be asked to do
        mover = roamer.Roamer(app, window, left + 500.0, floor)
        mover.floor, mover.y = floor, floor
        mover.vx = mover.vy = 0.0
        mover._begin("rest", roamer._time())

        for mood in roamer.MOODS:
            assert mover.feel(mood), mood
            crank(2)
            assert mover.mood == mood, (mood, mover.mood)
            assert mover.face == mascot_mod._face_mix(
                mover.face, mascot_mod.FACES[roamer.MOOD_FACE[mood]], 0.0), \
                "the mood is a face, not a state"
        assert not mover.feel("peckish"), "and only the four are moods"
        mover.mood = None

        for what in ("sing", "phone", "call", "beaten", "clap", "dance"):
            assert roamer.act(mover, what), what
            crank(3)
            assert mover.state in ("sing", "phone", "beaten", "clap",
                                   "dance"), (what, mover.state)
            assert mover.hands is not None, ("something has to be drawn", what)
            if what in ("phone", "call"):
                assert mover.prop == "phone", what
            lasts = roamer.ACTS[what] or roamer.ACTS["sing"]
            crank(int(lasts / roamer.STEP) + 10)
            assert mover.state == "rest", (
                "and he has to come back out of it", what, mover.state)
            assert mover.prop is None, ("and put the phone away", what)
        assert not roamer.act(mover, "juggle"), "only what is in ACTS"

        assert roamer.act(mover, "celebrate") and mover.state == "cheer"
        crank(int(roamer.CHEER_S / roamer.STEP) + 10)
        assert roamer.act(mover, "sleep") and mover.state == "sleep"
        mover._begin("rest", roamer._time())

        # a scrap: one of them ends up celebrating and one sat down
        other = roamer.Roamer(app, second, left + 560.0, floor)
        other.floor, other.y = floor, floor
        other.vx = other.vy = 0.0
        other._begin("rest", roamer._time())
        assert roamer.scrap(mover, other)
        crank(3)
        assert mover.state == other.state == "fight", (mover.state, other.state)
        assert mover.mood == "angry" and other.mood == "angry"
        crank(int(roamer.ACTS["fight"] / roamer.STEP) + 20)
        ends = sorted((mover.state, other.state))
        assert ends == ["beaten", "cheer"], ("one wins, one does not", ends)
        assert not roamer.scrap(mover, mover), "and nobody fights himself"

        # a run on his own, and then a chase: one after the other
        for one in (mover, other):
            one.mood = None
            one._begin("rest", roamer._time())
        assert roamer.act(mover, "run") and mover.state == "run"
        crank(3)
        assert mover.hands is not None, "something has to be drawn while he runs"
        was = mover.x
        crank(10)
        assert mover.x != was, "and running has to move him"
        crank(int(roamer.ACTS["run"] / roamer.STEP) + 10)
        assert mover.state == "rest", ("and he has to stop", mover.state)

        mover.x, other.x = left + 500.0, left + 560.0
        assert roamer.chase(mover, other)
        crank(3)
        assert mover.state == other.state == "run", (mover.state, other.state)
        assert (mover._run_leg, other._run_leg) == ("after", "away")
        crank(20)
        assert abs(mover.x - other.x) >= roamer.CHASE_GAP, (
            "the one behind holds off rather than standing on him",
            mover.x, other.x)
        crank(int(roamer.ACTS["run"] / roamer.STEP) + 20)
        assert mover.state == other.state == "rest", (mover.state, other.state)
        assert mover._foe is None and other._foe is None, "and nobody is left on"
        assert not roamer.chase(mover, mover), "and nobody chases himself"

        # started on for no reason at all: he is baffled first, and then he
        # either has a go back or walks off wondering what that was about
        was_random = roamer.random.random
        for pick, ends in ((0.0, "fight"), (0.99, "walk")):
            for one in (mover, other):
                one._foe = None
                one.mood = None
                one._begin("rest", roamer._time())
            mover.x, other.x = left + 500.0, left + 540.0
            roamer.random.random = lambda: pick
            try:
                assert roamer.provoke(mover, other)
                crank(3)
                assert mover.state == "provoke" and other.state == "baffled", (
                    mover.state, other.state)
                assert other.hands is not None, "he has to be shown asking why"
                assert other.face == mascot_mod.FACES["wtf"], (
                    "and it has to be on his face, not just in his state")
                crank(int(roamer.SHOVE_S / roamer.STEP) + 20)
                if ends == "fight":
                    assert mover.state == other.state == "fight", (
                        "one who has had enough gives it back",
                        mover.state, other.state)
                    crank(int(roamer.ACTS["fight"] / roamer.STEP) + 20)
                else:
                    assert other.state in ("walk", "rest"), (
                        "and one who has not walks off", other.state)
                    assert other.mood == "sad", "wondering what that was about"
                    assert mover.state != "fight", mover.state
            finally:
                roamer.random.random = was_random
        assert not roamer.provoke(mover, mover), "and nobody starts on himself"
        for one in (mover, other):
            one._foe = None
            one.mood = None
            one._begin("rest", roamer._time())
        for one in (mover, other):
            one.vanish()
        print("ok  four moods, and everything any of them can be asked to do")

        # Somebody is on the floor, somebody else sees it, and an ambulance
        # turns up for him: the call, the van, the lift, and the man gone
        # with it. Driven on the real clock rather than poked into place -
        # every one of those hands off to the next, and the handover is the
        # part worth checking.
        roamer.SPONTANEOUS = True
        try:
            # First, the thing that starts all of this: one of them takes
            # against another for no reason at all. The clock is wound to
            # nothing so the suite does not wait a minute and a half for it.
            was_every, roamer.ANGER_EVERY = roamer.ANGER_EVERY, (0.0, 0.0)
            roamer._anger_at = 0.0
            try:
                mad = roamer.Roamer(app, window, left + 400.0, floor)
                poor = roamer.Roamer(app, second, left + 500.0, floor)
                for guy in (mad, poor):
                    guy.floor, guy.y = floor, floor
                    guy.vx = guy.vy = 0.0
                    guy._begin("rest", roamer._time())
                went = crank(60 * 4, lambda: mad.state in ("provoke", "baffled"))
                assert went is not None, (
                    "somebody has to start something eventually",
                    mad.state, poor.state)
                assert sorted((mad.state, poor.state)) ==                     ["baffled", "provoke"], (mad.state, poor.state)
                for guy in (mad, poor):
                    guy.vanish()
            finally:
                roamer.ANGER_EVERY = was_every
                roamer._anger_at = 0.0
            print("ok  one of them takes against another off his own bat")

            # A song, and everybody near enough joining in. Nobody is told
            # what to do here beyond the singing: who claps and who dances
            # is theirs, and the point of the check is that the whole thing
            # starts and stops as one.
            singer = roamer.Roamer(app, window, left + 420.0, floor)
            crowd = [roamer.Roamer(app, second, left + 520.0, floor),
                     roamer.Roamer(app, window, left + 600.0, floor)]
            for guy in [singer] + crowd:
                guy.floor, guy.y = floor, floor
                guy.vx = guy.vy = 0.0
                guy._begin("rest", roamer._time())
            assert roamer.act(singer, "sing")
            joined = crank(60 * 3, lambda: all(guy.state in ("clap", "dance")
                                               for guy in crowd))
            assert joined is not None, (
                "nobody sings at nobody", [guy.state for guy in crowd])
            for guy in crowd:
                assert guy.hands is not None, ("and it has to be drawn",
                                               guy.state)
                assert abs(guy._until - singer._until) < 0.001, (
                    "they stop when he does, not one at a time")
            crank(int(roamer.ACTS["sing"] / roamer.STEP) + 20)
            if not all(guy.state == "rest" for guy in [singer] + crowd):
                now = roamer._time()
                print("DEBUG song_at-now", round(roamer._song_at - now, 2),
                      "anger_at-now", round(roamer._anger_at - now, 2))
                for tag, guy in [("singer", singer)] + [
                        ("crowd%d" % i, g) for i, g in enumerate(crowd)]:
                    print("DEBUG", tag, guy.state,
                          "until-now", round(guy._until - now, 2),
                          "since-now", round(guy.since - now, 2))
            assert all(guy.state == "rest" for guy in [singer] + crowd), (
                "and the song ends as one thing",
                [guy.state for guy in [singer] + crowd])
            for guy in [singer] + crowd:
                guy.vanish()
            print("ok  one starts singing and the rest clap or dance to it")

            hurt = roamer.Roamer(app, window, left + 420.0, floor)
            witness = roamer.Roamer(app, second, left + 560.0, floor)
            for one in (hurt, witness):
                one.floor, one.y = floor, floor
                one.vx = one.vy = 0.0
                one._begin("rest", roamer._time())
            hurt._begin("beaten", roamer._time())
            crank(4)
            assert witness.state == "help", (
                "somebody has to see it and do something about it",
                witness.state)
            came = crank(60 * 14, lambda: roamer.yard.van() is not None)
            assert came is not None, "and something has to turn up"
            assert roamer.yard.van().kind == "medic", roamer.yard.van().kind
            assert witness.prop is None or witness.state == "help"
            lifted = crank(60 * 14, lambda: hurt.state == "carted")
            assert lifted is not None, (
                "they have to get him onto the stretcher", hurt.state)
            assert abs(hurt.roll) > 1.0, "and he is lying on it, not stood on it"
            away = crank(60 * 25, lambda: hurt not in roamer.crew)
            assert away is not None, ("and it takes him away with it",
                                      hurt.state, roamer.yard.van())
            witness.vanish()
            roamer.yard.send_off()
            print("ok  he is picked up off the floor and driven away")

            # ...and a scrap that somebody calls the police to instead. The
            # fight is given long enough to still be going when they arrive:
            # a police car that pulls up after it is over is a police car
            # nobody sees.
            was_odds = roamer.POLICE_ODDS
            roamer.POLICE_ODDS = 1.0
            roamer._scrap_seen = None
            try:
                one = roamer.Roamer(app, window, left + 380.0, floor)
                two = roamer.Roamer(app, second, left + 440.0, floor)
                seen = roamer.Roamer(app, window, left + 620.0, floor)
                for guy in (one, two, seen):
                    guy.floor, guy.y = floor, floor
                    guy.vx = guy.vy = 0.0
                    guy._begin("rest", roamer._time())
                assert roamer.scrap(one, two, seconds=40.0)
                crank(4)
                assert seen.state == "help", (
                    "the third man phones it in", seen.state)
                blue = crank(60 * 14, lambda: roamer.yard.van() is not None)
                assert blue is not None, "and a car has to come"
                assert roamer.yard.van().kind == "police"
                bolt = crank(60 * 6, lambda: one.state == two.state == "run")
                assert bolt is not None, (
                    "and the two of them do not stay to explain it",
                    one.state, two.state)
                assert one._run_leg == two._run_leg == "off"
                out = crank(60 * 20,
                            lambda: one not in roamer.crew
                            and two not in roamer.crew)
                assert out is not None, (
                    "they go off the screen entirely", one.x, two.x)
                car = roamer.yard.van()
                assert car is None or car.phase == "away", (
                    "and the car does not sit there once they have gone")
                seen.vanish()
                roamer.yard.send_off()
            finally:
                roamer.POLICE_ODDS = was_odds
        finally:
            roamer.SPONTANEOUS = False
        print("ok  a scrap gets called in, and everybody leaves in a hurry")

        # what is written on the note colours the man who lives on it
        assert roamer.temper_of("so angry and MAD about all of it") == "angry"
        assert roamer.temper_of("made a list of groceries") is None,             "whole words, or every 'made' is a temper"
        assert roamer.temper_of("sad and lonely") == "sad"
        assert roamer.temper_of("what a happy lovely day") == "happy"
        assert roamer.temper_of("tired, nap soon") == "sleepy"

        roamer.SPONTANEOUS = True
        try:
            bully = roamer.Roamer(app, window, left + 480.0, floor)
            meek = roamer.Roamer(app, second, left + 540.0, floor)
            for guy in (bully, meek):
                guy.floor, guy.y = floor, floor
                guy.vx = guy.vy = 0.0
                guy._begin("rest", roamer._time())

            # An angry note answers a shove every time, whatever the dice say.
            was_random = roamer.random.random
            roamer.random.random = lambda: 0.5
            try:
                meek.temper = "angry"
                assert roamer.provoke(bully, meek)
                crank(int(roamer.SHOVE_S / roamer.STEP) + 20)
                assert bully.state == meek.state == "fight", (
                    "an angry note always answers", bully.state, meek.state)
                for guy in (bully, meek):
                    guy._foe = None
                    guy.mood = None
                    guy.temper = None
                    guy._begin("rest", roamer._time())

                # ...and a sad one never does.
                meek.temper = "sad"
                assert roamer.provoke(bully, meek)
                crank(int(roamer.SHOVE_S / roamer.STEP) + 20)
                assert meek.state not in ("fight", "beaten"), (
                    "a sad note never answers", meek.state)
                assert bully.state != "fight", bully.state
                assert meek.mood == "sad", "and it shows on him"
            finally:
                roamer.random.random = was_random

            # The wiring from the sheet: retype the note and he re-reads it.
            bully.mood = None
            assert roamer.retune(bully.home_id,
                                 "FURIOUS about everything") == "angry"
            assert bully.temper == "angry" and bully.mood == "angry"
            assert roamer.retune(bully.home_id, "calm seas") is None
            assert bully.temper is None

            # A sad man does not stay to watch a scrap: he runs from it.
            for guy in (bully, meek):
                guy._foe = None
                guy.mood = None
                guy.temper = None
                guy._begin("rest", roamer._time())
            meek.temper = "sad"
            meek.x = left + 600.0
            third = roamer.Roamer(app, window, left + 500.0, floor)
            third.floor, third.y = floor, floor
            third.vx = third.vy = 0.0
            third._begin("rest", roamer._time())
            assert roamer.scrap(bully, third, seconds=10.0)
            fled = crank(60 * 3, lambda: meek.state == "run")
            assert fled is not None, ("the sad one runs from it", meek.state)
            crank(60 * 5)
            for guy in (bully, meek, third):
                if guy in roamer.crew:
                    guy._foe = None
                    guy._begin("rest", roamer._time())
                    guy.vanish()
        finally:
            roamer.SPONTANEOUS = False
        print("ok  the words on the note decide who fights and who runs")

        # The fun: five things that happen for no reason except that they
        # are funny. Each check winds only its own clock; every other
        # spontaneous clock is pinned out past the end of the suite.
        far = roamer._time() + 9999.0
        roamer._song_at = roamer._anger_at = far
        roamer._pounce_at = roamer._race_at = far
        roamer._ice_at = roamer._pile_at = far

        # 1. The pointer, stalked: creep, wiggle, pounce, and the miss.
        roamer.SPONTANEOUS = True
        was_pointer = roamer._pointer
        try:
            cat = roamer.Roamer(app, window, left + 400.0, floor)
            cat.floor, cat.y = floor, floor
            cat.vx = cat.vy = 0.0
            cat._begin("rest", roamer._time())
            prey = (int(left + 550.0), int(floor))
            roamer._pointer = lambda: prey
            roamer._pounce_at = roamer._time()
            crept = crank(60 * 3, lambda: cat.state == "stalk")
            assert crept is not None, ("the pointer catches his eye", cat.state)
            pounced = crank(60 * 12, lambda: cat.state == "fall")
            assert pounced is not None, ("and he goes for it", cat.state,
                                         cat._stalk_leg)
            assert cat.mood == "happy", "having the time of his life"
            landed = crank(60 * 10, lambda: cat.state == "rest")
            assert landed is not None, ("he lands and pretends nothing",
                                        cat.state)
            cat.vanish()
        finally:
            roamer._pointer = was_pointer
            roamer._pounce_at = far
        print("ok  one of them stalks the pointer, pounces, and misses")

        # 2. Race day, run clean: the line-up, the gun, and the result.
        # The switch goes off for the races so the man who trips is not
        # carried off by an ambulance mid-check; the referee runs regardless.
        roamer.SPONTANEOUS = False
        was_random = roamer.random.random
        roamer.random.random = lambda: 0.9      # nobody trips today
        try:
            field = [roamer.Roamer(app, window, left + 380.0, floor),
                     roamer.Roamer(app, second, left + 460.0, floor),
                     roamer.Roamer(app, window, left + 540.0, floor)]
            for guy in field:
                guy.floor, guy.y = floor, floor
                guy.vx = guy.vy = 0.0
                guy._begin("rest", roamer._time())
            assert roamer.race()
            assert all(guy.state == "race" for guy in field)
            off = crank(60 * 20, lambda: any(guy._race_leg == "out"
                                             for guy in field))
            assert off is not None, ("the gun has to go",
                                     [guy._race_leg for guy in field])
            won = crank(60 * 40, lambda: any(guy.state == "cheer"
                                             for guy in field))
            assert won is not None, ("somebody comes home first",
                                     [(guy.state, guy._race_leg)
                                      for guy in field])
            first = next(guy for guy in field if guy.state == "cheer")
            assert all(guy.state == "clap" for guy in field
                       if guy is not first), (
                "and the rest are good sports about it",
                [guy.state for guy in field])
            assert not roamer._racers, "the race is over when it is over"
            crank(60 * 4)
            for guy in field:
                guy._begin("rest", roamer._time())
                guy.vanish()
        finally:
            roamer.random.random = was_random
        print("ok  three of them race down the bar and back")

        # ...and run dirty: somebody goes over at full tilt, and once he
        # stops bouncing it hurts.
        roamer.random.random = lambda: 0.0      # somebody is going over
        try:
            field = [roamer.Roamer(app, window, left + 380.0, floor),
                     roamer.Roamer(app, second, left + 460.0, floor),
                     roamer.Roamer(app, window, left + 540.0, floor)]
            for guy in field:
                guy.floor, guy.y = floor, floor
                guy.vx = guy.vy = 0.0
                guy._begin("rest", roamer._time())
            assert roamer.race()
            down = crank(60 * 40, lambda: any(guy.state == "beaten"
                                              for guy in field))
            assert down is not None, ("the trip has to land him in a heap",
                                      [(guy.state, guy._race_trip_at)
                                       for guy in field])
            assert roamer._race_tripped is None, "and the referee saw it"
            crank(60 * 4)
            for guy in field:
                if guy in roamer.crew:
                    guy._begin("rest", roamer._time())
                    guy.vanish()
        finally:
            roamer.random.random = was_random
        print("ok  a race with a fall in it ends with a man on the floor")

        roamer.SPONTANEOUS = True
        # 3. The nap pile: two sleepy notes find each other and go down in
        # a heap, heads together. The clock fires twice, the way it does in
        # the wild: once to gather them, once to put them down.
        dozy = [roamer.Roamer(app, window, left + 380.0, floor),
                roamer.Roamer(app, second, left + 560.0, floor)]
        for guy in dozy:
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy.temper = "sleepy"
            guy._begin("rest", roamer._time())
            # No chat scenes muscling in on the nap: the pile clock fires
            # twice here and a chat between the two firings starves it.
            guy._social_until = roamer._time() + 999.0
        roamer._pile_at = roamer._time()
        met = crank(60 * 8, lambda: all(guy.state in ("rest", "chat")
                                        for guy in dozy)
                    and abs(dozy[0].x - dozy[1].x) < roamer.PILE_R)
        assert met is not None, ("they have to find each other",
                                 [(guy.state, round(guy.x)) for guy in dozy])
        roamer._pile_at = roamer._time()
        piled = crank(60 * 2, lambda: all(guy.state == "sleep"
                                          for guy in dozy))
        assert piled is not None, ("and go down in a heap",
                                   [(guy.state, round(guy.x)) for guy in dozy])
        crank(4)
        assert dozy[0].roll != 0.0 and dozy[1].roll != 0.0, (
            "and the heads go together", dozy[0].roll, dozy[1].roll)
        assert (dozy[0].roll > 0) != (dozy[1].roll > 0), (
            "towards each other, not the same way")
        roamer._pile_at = far
        for guy in dozy:
            guy.temper = None
            guy._begin("rest", roamer._time())
            guy.vanish()
        print("ok  two sleepy notes nap in a pile, heads together")

        # 4. The ice cream van: it turns up, they queue, everybody gets a
        # cone, and it leaves when the queue is done.
        sweet = [roamer.Roamer(app, window, left + 400.0, floor),
                 roamer.Roamer(app, second, left + 480.0, floor)]
        for guy in sweet:
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy._begin("rest", roamer._time())
        roamer._ice_at = roamer._time()
        came = crank(60 * 4, lambda: roamer.yard.van() is not None)
        assert came is not None, "the van has to come"
        assert roamer.yard.van().kind == "icecream"
        roamer._ice_at = far                    # one van is plenty
        queued = crank(60 * 20, lambda: any(guy.state == "queue"
                                            for guy in sweet))
        assert queued is not None, ("and they queue at it",
                                    [guy.state for guy in sweet])
        served = crank(60 * 20, lambda: any(guy.state == "lick"
                                            for guy in sweet))
        assert served is not None, ("the front of the queue gets his",
                                    [guy.state for guy in sweet])
        front = next(guy for guy in sweet if guy.state == "lick")
        assert front.prop == "cone", "and it is drawn in his hand"
        gone = crank(60 * 40, lambda: roamer.yard.van() is None
                     and all(guy.prop is None for guy in sweet))
        assert gone is not None, ("everybody served, and off it goes",
                                  [(guy.state, guy.prop) for guy in sweet],
                                  roamer.yard.van())
        for guy in sweet:
            guy._begin("rest", roamer._time())
            guy.vanish()
        roamer.yard.send_off()
        print("ok  the ice cream van serves the queue and drives off")

        # 5. A birthday on the note is a party: hats, a song, and the man
        # himself up celebrating - once per birthday, not once per keystroke.
        host = roamer.Roamer(app, window, left + 420.0, floor)
        guest = roamer.Roamer(app, second, left + 520.0, floor)
        for guy in (host, guest):
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy._begin("rest", roamer._time())
        roamer.retune(host.home_id, "happy birthday!!")
        assert host.state == "cheer", ("his own party, celebrated",
                                       host.state)
        assert host._bday_done, "and it is marked as had"
        now = roamer._time()
        assert host._hat_until > now and guest._hat_until > now, (
            "hats for everybody at the party")
        assert guest.state == "sing", ("somebody strikes up the song",
                                       guest.state)
        # Retyping the same word is not a second party.
        host._begin("rest", roamer._time())
        guest._begin("rest", roamer._time())
        roamer.retune(host.home_id, "happy birthday again")
        assert host.state == "rest", "the word staying is not the word arriving"
        # ...but a fresh one, after the word has gone, is.
        roamer.retune(host.home_id, "plain list of jobs")
        assert not host._bday_done
        roamer.retune(host.home_id, "bday next week")
        assert host.state == "cheer", "a fresh birthday is a fresh party"
        crank(4)
        for guy in (host, guest):
            guy._begin("rest", roamer._time())
            guy.vanish()
        print("ok  a birthday on the note throws a party, once")

        # An angry note is not much fun at parties: mostly he wants no part
        # of anything but a scrap, and says so. The dice decide, so both
        # answers are pinned and checked.
        stage = roamer.Roamer(app, window, left + 420.0, floor)
        grump = roamer.Roamer(app, second, left + 500.0, floor)
        for guy in (stage, grump):
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy._begin("rest", roamer._time())
        grump.temper = "angry"
        was_random = roamer.random.random
        roamer.random.random = lambda: 0.0      # the "no" side of the roll
        try:
            assert roamer.act(stage, "sing")
            crank(30)
            assert grump.state == "rest", ("he wants no part of it",
                                           grump.state)
            assert grump._grump_until > roamer._time(), (
                "and the no is remembered, not re-rolled")
            stage._begin("rest", roamer._time())
            grump._grump_until = 0.0
            grump.mood = None
            roamer.random.random = lambda: 0.9  # ...and the rare "yes"
            assert roamer.act(stage, "sing")
            joined = crank(60 * 2, lambda: grump.state == "dance")
            assert joined is not None, ("even a grump has his days",
                                        grump.state)
        finally:
            roamer.random.random = was_random
        for guy in (stage, grump):
            guy.temper = None
            guy._begin("rest", roamer._time())
            guy.vanish()
        print("ok  an angry note mostly turns the fun down")

        # The same scenes, asked for off the menu rather than waited on. A
        # stranger who saw a clip of the pizza wants the pizza now, not the
        # odds of one - and the menu must not touch the once-per-note latch
        # the typed word uses, or asking twice would be asking once.
        asker = roamer.Roamer(app, window, left + 400.0, floor)
        mate = roamer.Roamer(app, second, left + 470.0, floor)
        for guy in (asker, mate):
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy._begin("rest", roamer._time())
        assert window._scenes_index is not None, "the menu has a Scenes cascade"
        window._scene_pizza()
        assert asker.state == "errand", ("asked for, he goes",
                                         asker.state)
        assert not asker._pizza_done, (
            "and the menu does not spend the note's one-shot")
        asker._begin("rest", roamer._time())
        window._scene_party()
        assert asker._hat_until > roamer._time(), "a party on demand is hats"
        asker._begin("rest", roamer._time())
        mate._begin("rest", roamer._time())
        for guy in (asker, mate):
            guy._hat_until = 0.0
        assert roamer.yard.van() is None, "no van yet"
        assert window._scene_icecream(), "two men stood about is a round"
        assert roamer.yard.van() is not None, "and the van comes"
        assert not window._scene_icecream(), "one van at a time"
        roamer.yard.send_off()
        crank(4)
        # Switched off, there is nobody to ask. The cascade goes grey rather
        # than firing into an empty crew.
        window._sync_menu()
        assert str(window.menu.entrycget(window._scenes_index, "state")) == \
            "normal", "with him on the note, the scenes are there to ask for"
        for guy in (asker, mate):
            guy._begin("rest", roamer._time())
            guy.vanish()
        print("ok  the scenes can be asked for off the menu")

        # A pizza on the note is an errand and then a picnic: off the edge,
        # back with the box, and everybody near enough sits down to a slice.
        host = roamer.Roamer(app, window, left + 300.0, floor)
        mate = roamer.Roamer(app, second, left + 420.0, floor)
        for guy in (host, mate):
            guy.floor, guy.y = floor, floor
            guy.vx = guy.vy = 0.0
            guy._begin("rest", roamer._time())
            guy._social_until = roamer._time() + 999.0
        roamer.retune(host.home_id, "pizza tonight")
        assert host.state == "errand", ("his stomach, his errand", host.state)
        gone = crank(60 * 20, lambda: host._fetch == "back")
        assert gone is not None, ("he has to go off the edge",
                                  host.x, host._fetch)
        x1, x2 = host._walls()
        assert (host.x <= x1 - roamer.FETCH_OFF + 2.0
                or host.x >= x2 + roamer.FETCH_OFF - 2.0), (
            "properly off it, not loitering", host.x)
        back = crank(60 * 20, lambda: host.state == "picnic")
        assert back is not None, ("and come back with the box",
                                  host.state, host._fetch)
        assert host.prop == "pizza_open", host.prop
        joined = crank(60 * 6, lambda: mate.state == "picnic")
        assert joined is not None, ("nobody eats alone", mate.state)
        seated = crank(60 * 8, lambda: mate.hands is not None
                       and mate.feet is not None)
        assert seated is not None, "sat down to it, not stood over it"
        over = crank(int(roamer.PICNIC_S / roamer.STEP) + 90,
                     lambda: host.state == mate.state == "rest")
        assert over is not None, ("and it ends as one thing",
                                  host.state, mate.state)
        assert host.prop is None, "the box does not outlive the picnic"
        # One pizza per typing: the word still on the sheet orders nothing.
        roamer.retune(host.home_id, "pizza again, still hungry")
        assert host.state == "rest", ("the word staying is not an order",
                                      host.state)
        for guy in (host, mate):
            guy._begin("rest", roamer._time())
            guy.vanish()
        roamer.SPONTANEOUS = False
        roamer._song_at = roamer._anger_at = 0.0
        roamer._pounce_at = roamer._race_at = 0.0
        roamer._ice_at = roamer._pile_at = 0.0
        print("ok  a pizza on the note fetches a box and seats a picnic")

        # something goes full-screen and they get off the bar until it is over
        assert roamer.winkit.covers((0, 0, 1280, 768), (0, 0, 1280, 768)), (
            "a window the size of the screen covers it")
        assert not roamer.winkit.covers((0, 0, 1280, 720), (0, 0, 1280, 768)), (
            "and a maximised one, which stops at the taskbar, does not")

        # A real prop on the screen, so "the yard goes too" is a check rather
        # than a line that quietly passes because there is no yard yet.
        yard.kick_off(left + 400.0, floor)
        assert yard.ball() is not None and yard._win is not None, "a yard to hide"

        shy_pair = [roamer.Roamer(app, window, left + 150.0, floor),
                    roamer.Roamer(app, second, left + 220.0, floor)]
        settled = roamer._time()
        for one in shy_pair:
            one.floor, one.y = floor, floor
            one.vx = one.vy = 0.0
            one._begin("rest", settled)
            one._until = settled + 999.0
            one._social_until = settled + 999.0
        # The second of them is out past the edge, the way somebody fetching
        # wood is. Where he comes back to has to be somewhere he can stand.
        shy_pair[1].x = shy_pair[1]._walls()[0] - 90.0
        homes = [one.x for one in shy_pair]

        was_check = roamer.winkit.foreground_fullscreen
        roamer.winkit.foreground_fullscreen = lambda: True
        try:
            roamer._shy_at = 0.0            # ask now rather than in half a second
            crank(2)
            assert roamer.shy, "the crew has to notice"
            assert all(one.state == "shy" for one in shy_pair), (
                [one.state for one in shy_pair])
            gone = crank(60 * 8, lambda: all(one._shy_leg == "gone"
                                             for one in shy_pair))
            assert gone is not None, (
                "they have to actually walk off it",
                [(one._shy_leg, one.x) for one in shy_pair])
            crank(1)
            assert not any(one.winfo_viewable() for one in shy_pair), (
                "and be off the screen, not drawn over the top of it")
            assert not yard._win.winfo_viewable(), "the yard goes too"

            # Peeled off a note in the middle of it: he lands and hides too,
            # rather than standing on top of whatever is full-screen.
            late = roamer.Roamer(app, window, left + 300.0, floor)
            late.let_go()
            assert late.state == "shy", (
                "somebody dragged off during it hides as well", late.state)
            late.vanish()
        finally:
            roamer.winkit.foreground_fullscreen = was_check

        roamer._shy_at = 0.0
        crank(2)
        assert not roamer.shy, "and notice when it is over"
        back = crank(60 * 12, lambda: all(one.state == "rest"
                                          for one in shy_pair))
        assert back is not None, (
            "they have to come back", [(one.state, one.x) for one in shy_pair])
        assert all(one.winfo_viewable() for one in shy_pair), "and be visible"
        assert yard._win.winfo_viewable() and yard.ball() is not None, (
            "and so does the yard, with the ball still in it")
        assert abs(shy_pair[0].x - homes[0]) < 4.0, (
            "to where he was standing, not to the edge he left by",
            shy_pair[0].x, homes[0])
        walls = shy_pair[1]._walls()
        assert walls[0] <= shy_pair[1].x <= walls[1], (
            "and somebody who was off the edge comes back onto the screen",
            shy_pair[1].x, walls)
        yard.drop_ball()
        for one in shy_pair:
            one.vanish()
        print("ok  something full-screen and they clear off the bar for it")

        # "Sit with me": a fire under the note, and he stays until it is out
        was_focus, roamer.FOCUS_S = roamer.FOCUS_S, 4.0
        try:
            sitter = roamer.focus(second)
            assert sitter is not None, "somebody has to come"
            assert sitter.state == "vigil", sitter.state
            lit = crank(60 * 30, lambda: yard.fire() is not None)
            assert lit is not None and yard.fire() is not None, (
                "he has to light one", sitter._vigil_leg, sitter.x)
            assert sitter._vigil_leg == "sit", sitter._vigil_leg
            near = abs(yard.fire().x - sitter.x)
            assert near < roamer.FIRE_SEAT * 2, ("and sit by it", near)
            crank(30)
            assert sitter.crouch > 0.8 and sitter.y > sitter.floor, (
                "sitting, not standing about", sitter.crouch)
            assert roamer.focus(window) is None, (
                "one fire at a time: his twenty-five minutes must not end "
                "when somebody else's fifteen seconds do")

            # Something full-screen in the middle of it does not end it. He
            # hides like everybody else and comes back to his own fire.
            was_check = roamer.winkit.foreground_fullscreen
            roamer.winkit.foreground_fullscreen = lambda: True
            try:
                roamer._shy_at = 0.0
                crank(2)
                assert sitter.state == "shy", sitter.state
            finally:
                roamer.winkit.foreground_fullscreen = was_check
            roamer._shy_at = 0.0
            crank(2)
            assert sitter.state == "vigil", (
                "and goes back to the note he was sitting with", sitter.state)
            assert yard.fire() is not None, "which is still burning"
            crank(60 * 8, lambda: sitter._vigil_leg == "sit")
            assert sitter._vigil_leg == "sit", sitter._vigil_leg

            # It is the fire that ends this, not a frame count: a right-click
            # on it is the same ending, earlier.
            assert yard._win is not None
            poke = type("Poke", (), {"x_root": yard.fire().x,
                                     "y_root": floor - 10.0})()
            was_popup = app_module.tk.Menu.tk_popup
            app_module.tk.Menu.tk_popup = lambda self, *a, **k: None
            try:
                yard._win._click(poke)
            finally:
                app_module.tk.Menu.tk_popup = was_popup
            menu = yard._win._menu
            labels = [menu.entrycget(i, "label")
                      for i in range(menu.index("end") + 1)]
            assert "Put it out" in labels, labels
            assert yard.fire() is not None, "asking is not doing"
            menu.invoke(labels.index("Put it out"))
            assert yard.fire() is None, "and the menu entry puts it out"

            gone = crank(60 * 10, lambda: sitter not in roamer.crew)
            assert gone is not None and sitter not in roamer.crew, (
                "then he goes back to the note", sitter.state)
            assert second.mascot.visible(), "and is on it again"
        finally:
            roamer.FOCUS_S = was_focus
        print("ok  he sits with a note until the fire goes out")

        # the last box on a note gets ticked, and he is not the only one who
        # notices
        boxes = app.new_note("green")
        pump(app.root)
        boxes.start_edit()
        type_into(app, boxes, boxes.body, "[ ] milk\n[ ] eggs")
        boxes.finish_edit()
        pump(app.root)
        assert mascot_mod.box_counts(boxes.note["body"]) == (2, 0), (
            boxes.note["body"])

        def tick(win, line):
            """Tick one box the way a click on it does."""
            win.body.configure(state="normal")
            win.body.replace("%d.0" % line, "%d.%d" % (line, len(mascot_mod.BOX_OPEN)),
                             mascot_mod.BOX_DONE)
            win.body.configure(state="disabled")
            win._after_box_change()

        # Off a different note, so the man from this one is still on the paper
        # and both halves of it can be seen at once.
        watcher = roamer.Roamer(app, window,
                                boxes.winfo_rootx() + 40.0, floor)
        watcher.floor, watcher.y = floor, floor
        watcher.vx = watcher.vy = 0.0
        watcher._begin("rest", roamer._time())
        watcher._until = roamer._time() + 999.0

        # A second one, close enough that both come over: they have to end up
        # in a row rather than in one shape.
        crowder = roamer.Roamer(app, window, watcher.x + 8.0, floor)
        crowder.floor, crowder.y = floor, floor
        crowder.vx = crowder.vy = 0.0
        crowder._begin("rest", roamer._time())
        crowder._until = roamer._time() + 999.0

        boxes.mascot.hush()
        tick(boxes, 1)
        assert watcher.state == "rest", (
            "one box out of two is not a finished list", watcher.state)
        assert boxes.mascot._bubble is None, "and nothing to say about it yet"

        tick(boxes, 2)
        assert mascot_mod.box_counts(boxes.note["body"]) == (0, 2), (
            boxes.note["body"])
        assert boxes.mascot._bubble is not None, (
            "the man on the note has to notice")
        assert watcher.state == "cheer" and crowder.state == "cheer", (
            "and whoever is near enough comes over",
            watcher.state, crowder.state)
        assert abs(watcher._cheer_x - crowder._cheer_x) >= roamer.CHEER_GAP - 1.0, (
            "with a place each", watcher._cheer_x, crowder._cheer_x)
        crank(90)
        assert abs(watcher.x - crowder.x) >= roamer.SPACE_R, (
            "so two of them at one note are not one shape",
            watcher.x, crowder.x)
        crowder.vanish()
        crank(60 * 6, lambda: watcher.state != "cheer")
        assert watcher.state == "rest", (
            "and goes back to what he was doing", watcher.state)

        # Ticking a box on a list that was already finished is not finishing
        # it again: there has to have been something left to do.
        boxes.mascot.hush()
        watcher._begin("rest", roamer._time())
        boxes._after_box_change()
        assert watcher.state == "rest" and boxes.mascot._bubble is None, (
            "a list that was already done stays done")

        watcher.vanish()
        boxes.mascot.hush()
        app.trash_note(boxes.note["id"])
        pump(app.root)
        print("ok  tick the last box and the note - and the bar - notice")

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

        # Every scene check from here down to the kickabout is about a
        # conversation running to its end with everybody in it. Left to
        # itself _pick_scene hands a quarter of them a ball and a fifth of
        # the threes a hut, and a third of the threes that do talk lose
        # somebody before the last one has spoken - so a check waiting on a
        # conversation would be sat waiting on a game of football, and one
        # counting who spoke would be counting two of three. The blocks that
        # want those turn them on for themselves.
        roamer.BUILD_ODDS = roamer.FOOTY_ODDS = roamer.BOW_ODDS = 0.0
        roamer.FIRE_ODDS = 0.0          # ...and a fifth of them a fire

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

        # Four of them, and the fourth is in it rather than left stood
        # outside it: a hut and a game of football want everybody who is
        # there, not the first three to have turned up.
        quad = [a, b, roamer.Roamer(app, third, 0.0, floor),
                roamer.Roamer(app, third, 0.0, floor)]
        park(quad)
        step(5)
        scene = quad[0].scene
        assert scene is not None and len(scene.cast) == 4, "one cast of four"
        assert all(one.scene is scene for one in quad), "and all in the same one"
        assert sorted(one.role for one in quad) == [0, 1, 2, 3], "distinct roles"
        spoke = set()

        def note_fourth():
            here = quad[0].scene
            if here is not None:
                who = here.speaker()
                if who is not None:
                    spoke.add(who.role)
            return here is None

        step(900, note_fourth)
        assert spoke == {0, 1, 2, 3}, ("everybody gets a turn", spoke)
        for one in quad[2:]:
            one.vanish()
        print("ok  four of them talk, and everybody gets a turn")

        # A gesture a sentence. He waves, lays it out with both hands, counts
        # it off, chops at it, points, or shrugs - and whichever it is, it
        # holds for the whole sentence rather than being re-rolled per frame.
        park([a, b])
        step(5)
        talk = a.scene
        assert talk is not None and talk.kind == "talk", talk
        drift = []

        def note_gesture():
            live = a.scene
            if live is None:
                return True
            # scene.i has already been advanced past the frame that was
            # drawn by the time this looks, so the beat that went with this
            # gesture is the one before it.
            beat, _ = roamer._beat(live.table, max(live.i - 1, 0))
            drift.append((beat, live.gesture))
            return False

        step(900, note_gesture)
        assert drift, "the conversation has to have run"
        per_beat = {}
        for beat, gesture in drift:
            per_beat.setdefault(beat, set()).add(gesture)
        assert all(len(shapes) == 1 for shapes in per_beat.values()), (
            "one gesture holds for a whole sentence", per_beat)
        assert len(set(g for _, g in drift)) > 1, (
            "and they are not all the same shape", per_beat)
        assert set(g for _, g in drift) <= set(roamer.TALK_GESTURES), per_beat
        print("ok  every sentence gets its own gesture, and keeps it")

        # two of them talking, and a third who turns up and hangs back
        onlooker = roamer.Roamer(app, third, 0.0, floor)
        pair = [a, b]
        park(pair + [onlooker])
        # Out of talking distance of either of them, but inside watching
        # distance of the pair - so he can never be cast, only an audience.
        onlooker.x = (pair[0].x + pair[1].x) / 2.0 + 200.0
        step(8)
        # This one has the manners to stay out of it. The nosy sort edges in
        # instead, and gets laughed at for it - that is the check below.
        onlooker._nosy = False
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

        # ...and one who walks right into the middle of it gets what he asked
        # for
        victim = roamer.Roamer(app, third, 0.0, floor)
        park(pair, gap=roamer.CHAT_GAP)
        step(40)                        # let them get talking first
        scene = a.scene
        assert scene is not None and scene.kind == "talk", "a conversation"
        was = scene.i
        victim.state, victim.floor, victim.y = "rest", floor, floor
        victim.vx = victim.vy = 0.0
        victim.scene = None
        victim._until = time.monotonic() + 999.0
        victim._social_at = 0.0
        victim._social_until = 0.0
        victim.x = scene.mid            # straight into the gap
        step(3)
        assert victim.scene is scene, "he is in it now, whether he likes it or not"
        assert scene.kind == "mock", scene.kind
        assert scene.i < was, "and they break off mid-sentence to do it"
        assert scene.victim is victim, "and the scene knows who it is about"
        assert victim.mocked and not a.mocked, "and only him"
        step(400, lambda: victim.scene is None)
        assert victim.scene is None and a.scene is None, "it ends"
        print("ok  walk into a conversation and the two of them turn on you")

        def mock_him(guy):
            """Get the pair talking, then put him in the middle of it."""
            # Well clear of them first, or he walks into the conversation
            # while it is still being set up and the whole thing happens a
            # beat early.
            guy.state, guy.floor, guy.y = "rest", floor, floor
            guy.x = right - 100.0
            guy._until = time.monotonic() + 999.0
            park(pair, gap=roamer.CHAT_GAP)
            step(40)
            live = a.scene
            assert live is not None and live.kind == "talk", "a conversation"
            guy.state, guy.floor, guy.y = "rest", floor, floor
            guy.vx = guy.vy = 0.0
            guy.scene = None
            guy._until = time.monotonic() + 999.0
            guy._social_at = 0.0
            guy._social_until = 0.0
            guy.x = live.mid
            step(3)
            assert guy.mocked, "the setup has to have taken"
            return live

        # he does not take it well, and he is off in the other direction
        scene = mock_him(victim)
        mid = scene.mid
        step(400, lambda: victim.state == "stomp")
        assert victim.state == "stomp", victim.state
        assert (victim.x - mid) * victim._leave_way >= 0.0, \
            "he walks away from them, not back through them"
        here = victim.x
        step(20)
        assert abs(victim.x - here) > abs(roamer.WALK_SPEED * 20 * roamer.STEP), \
            "and faster than his ordinary walk"
        assert not victim.sociable(roamer._time()), \
            "he is not in the mood for anybody"
        step(400, lambda: victim.state != "stomp")
        assert victim.state in ("rest", "walk"), victim.state
        assert victim._cross_until > 0.0, "the anger outlives the stomping"
        victim.vanish()
        print("ok  the one they laughed at storms off and stays cross")

        # lift the one they are laughing at and the scene comes apart cleanly
        rescued = roamer.Roamer(app, third, 0.0, floor)
        scene = mock_him(rescued)
        rescued.pick_up()
        step(2)
        assert rescued.scene is None, "he is out of it"
        assert scene not in roamer.scenes, "and it is over for the other two"
        assert all(one.state in ("rest", "walk") for one in pair), \
            [one.state for one in pair]

        # a three-way that loses one of them ends for the other two as well,
        # rather than carrying on as a two-way with the roles shuffled
        rescued.let_go()
        park(pair + [rescued])
        step(5)
        big = rescued.scene
        assert big is not None and len(big.cast) == 3, "a cast of three"
        rescued.pick_up()
        step(2)
        assert big not in roamer.scenes, "lifting one ends it for all of them"
        assert all(one.scene is None for one in pair), "nobody left in a scene"

        # and holding him over them gets the pair of them turning round
        for one in pair:
            one.state, one.floor, one.y = "rest", floor, floor
            one._until = time.monotonic() + 999.0
            one.facing = 0.9
        rescued.x = (pair[0].x + pair[1].x) / 2.0
        rescued.y = floor - roamer.STAND_H - 120.0
        step(40, lambda: all(one.state == "wtf" for one in pair))
        assert all(one.state == "wtf" for one in pair), \
            ("both of them", [one.state for one in pair])
        rescued.vanish()
        print("ok  rescuing him ends it, and both of them get the look")

        # left to themselves on an empty taskbar, they go and find each other.
        # Every scene above starts with them already stood together, which is
        # the one thing the real thing never does: dropped a screen apart and
        # given a random leg each they drift, and three minutes of it measured
        # nothing at all - every scene underneath reachable and none reached.
        finder = roamer.Roamer(app, third, 0.0, floor)
        far = [a, b, finder]
        for stale in list(roamer.scenes):
            roamer._close(stale, roamer._time())
        for k, one in enumerate(far):
            one.x = left + 60.0 + k * (right - left - 120.0) / 2.0
            one.state, one.floor, one.y = "rest", floor, floor
            one.vx = one.vy = 0.0
            one._until = 0.0
            one._social_at = one._social_until = one._cross_until = 0.0
        assert min(abs(one.x - other.x) for one in far for other in far
                   if one is not other) > roamer.CHAT_R,             "they have to start out of reach of each other"
        met = step(60 * 40, lambda: bool(roamer.scenes))
        assert met is not None,             "spread out and left alone they never once got together"
        assert met < 60 * 30, ("and it must not take all day", met / 60.0)
        print("ok  spread out on the taskbar, they go and find each other")

        # ...and a nosy onlooker closes the last of the gap himself, which is
        # the only way into being laughed at that does not need a hand to drop
        # him there: a talk is over in four seconds and the edge of WATCH_R is
        # a five second walk, so whoever stops out there has to be able to
        # sidle in.
        for one in far:
            one._leave_scene(roamer._time())
            one._begin("rest", roamer._time())
            one._until = time.monotonic() + 999.0
        # Well out of it, and in no mood, so he can neither be cast in the
        # conversation nor keep the pair of them waiting for him.
        finder.x = left + 40.0
        finder._social_until = roamer._time() + 999.0
        park(pair, gap=roamer.CHAT_GAP)
        step(60, lambda: a.scene is not None)
        talk = a.scene
        assert talk is not None and len(talk.cast) == 2, "the two of them first"
        finder.x = talk.mid + roamer.WATCH_R * 0.5
        finder.state, finder.floor, finder.y = "rest", floor, floor
        finder._until = time.monotonic() + 999.0
        step(3)
        assert finder.state == "watch", finder.state
        finder._nosy = True
        was = abs(finder.x - talk.mid)
        step(60)
        assert abs(finder.x - talk.mid) < was - 20.0,             ("he has to be closing the gap", was, abs(finder.x - talk.mid))
        step(300, lambda: finder.scene is not None)
        if finder.scene is None or finder.scene.kind != "mock":
            print("DEBUG mock: finder", finder.state, round(finder.x, 1),
                  "nosy", finder._nosy, "social_until-now",
                  round(finder._social_until - roamer._time(), 1))
            print("DEBUG scenes", [(s.kind, round(s.mid, 1),
                                    [round(g.x, 1) for g in s.cast])
                                   for s in roamer.scenes])
            print("DEBUG pair", a.state, round(a.x, 1),
                  None if a.scene is None else a.scene.kind,
                  "|", b.state, round(b.x, 1),
                  None if b.scene is None else b.scene.kind,
                  "| talk.kind", talk.kind, "mid", round(talk.mid, 1))
        assert finder.scene is not None and finder.scene.kind == "mock",             "and edging in has to get him laughed at"
        assert finder.scene.victim is finder, "he is the one they turn on"
        finder.vanish()
        print("ok  a nosy onlooker edges in and gets himself laughed at")

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
            scene.i = roamer._beat_start(roamer.TALK3, "say1") - 1
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

        # they kick a ball about, and it goes when they do
        was_build, was_footy = roamer.BUILD_ODDS, roamer.FOOTY_ODDS
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = 0.0, 1.0
        settle(crowd)
        step(3)
        scene = crowd[0].scene
        assert scene is not None and scene.kind == "footy", scene
        assert yard.ball() is not None, "a kickabout needs a ball"
        assert yard.ball().y < floor - roamer.STAND_H,             "and it is thrown in above their heads"
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

        # three of them light a fire, sit round it and see it out
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = 0.0, 0.0
        was_fire, roamer.FIRE_ODDS = roamer.FIRE_ODDS, 1.0
        settle(crowd)
        step(3)
        scene = crowd[0].scene
        assert scene is not None and scene.kind == "fire", scene
        assert yard.fire() is not None, "a campfire needs a fire"
        seats = sorted(scene.seat_x(one) for one in crowd)
        assert seats[0] < scene.mid < seats[-1], (
            "they sit round it rather than beside it", seats, scene.mid)

        sat = step(60 * 8, lambda: all(one.crouch > 0.9 for one in crowd))
        assert sat is not None, (
            "they have to sit down", [one.crouch for one in crowd])
        assert all(one.y > one.floor for one in crowd), (
            "hips on the floor, feet in front of him",
            [(one.y, one.floor) for one in crowd])
        assert all(abs(one.x - scene.seat_x(one)) < 8.0 for one in crowd), (
            "and each in his own place round it")

        spoke = set()

        def note_fire():
            live = crowd[0].scene
            if live is None:
                return True
            who = live.speaker()
            if who is not None:
                spoke.add(who.role)
            return yard.fire() is None

        out = step(60 * 40, note_fire)
        assert out is not None and yard.fire() is None, "the fire has to go out"
        assert spoke, ("and they talk while it burns", spoke)
        assert all(one.state == "chat" for one in crowd), (
            "nobody leaves before it does", [one.state for one in crowd])

        waved = step(60 * 6, lambda: all(one._mark == "bye!" for one in crowd))
        assert waved is not None, (
            "everybody says goodbye", [one._mark for one in crowd])
        assert all(one.crouch < 0.2 for one in crowd), (
            "on their feet to do it", [one.crouch for one in crowd])
        step(60 * 6, lambda: not roamer.scenes)
        assert not roamer.scenes, "and the evening is over"
        assert all(one.state == "walk" for one in crowd), (
            "and they walk off", [one.state for one in crowd])
        roamer.FIRE_ODDS = was_fire
        print("ok  three of them sit round a fire until it burns out")

        # three of them fetch wood off the sides of the screen and build a hut
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = 1.0, 0.0
        was_inside, roamer.INSIDE_S = roamer.INSIDE_S, (600.0, 600.0)
        # Near the left edge, so the errand is a few seconds rather than the
        # twenty a walk from the middle of a wide screen would take.
        settle(crowd, at=left + 140.0)
        # A fourth, stood well clear of the site and in nothing. He carries no
        # wood, but when the hut goes up he goes in with them: one of them left
        # standing outside it reads as having been forgotten.
        bystander = roamer.Roamer(app, paper, 0.0, floor)
        # Out of the chain (further than CHAT_R from the rightmost of
        # them, or he is cast in the build himself) and inside WATCH_R,
        # so the walk to the door is a few seconds rather than twenty.
        bystander.x = left + 350.0
        bystander.state, bystander.floor, bystander.y = "rest", floor, floor
        bystander.vx = bystander.vy = 0.0
        bystander._until = time.monotonic() + 999.0
        bystander._social_at = bystander._social_until = 0.0
        step(3)
        scene = crowd[0].scene
        assert scene is not None and scene.kind == "build", scene
        assert bystander not in scene.cast, "he is not in the build"
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
        assert bystander.state == "enter", \
            ("the hut going up sends everybody in", bystander.state)
        everyone = crowd + [bystander]
        step(60 * 30, lambda: all(one.state == "inside" for one in everyone))
        assert all(one.state == "inside" for one in everyone), \
            [one.state for one in everyone]
        pump(app.root)
        assert not any(one.winfo_viewable() for one in everyone), \
            "indoors is indoors"
        assert not roamer.scenes, "and the build is over"
        print("ok  they fetch wood off the screen and build a hut to go into")

        # Something full-screen while they are indoors does not turn them out
        # of the hut: they are a withdrawn window already, and a sweep that
        # walked them to the edge would put them back outside it.
        was_check = roamer.winkit.foreground_fullscreen
        roamer.winkit.foreground_fullscreen = lambda: True
        try:
            roamer._shy_at = 0.0
            step(2)
            assert all(one.state == "inside" for one in crowd), (
                "a man in a hut stays in it", [one.state for one in crowd])
        finally:
            roamer.winkit.foreground_fullscreen = was_check
        roamer._shy_at = 0.0
        step(2)
        assert not roamer.shy, "and the flag comes back down"

        # ...and right-clicking it brings them out screaming. The fourth
        # goes here: the checks under this one are built around the three
        # who put it up, and one more body running about proves nothing
        # they do not.
        bystander.vanish()
        where = yard.hut().x
        # The click itself only asks. tk_popup is stubbed out for the length
        # of it: a real popup takes a grab, and a check that has to dismiss a
        # grab is a check that hangs the suite the day it fails.
        poke = type("Poke", (), {"x_root": where, "y_root": floor - 10.0})()
        was_popup = app_module.tk.Menu.tk_popup
        app_module.tk.Menu.tk_popup = lambda self, *a, **k: None
        try:
            yard._win._click(poke)
        finally:
            app_module.tk.Menu.tk_popup = was_popup
        assert yard.hut() is not None, "a right-click on its own leaves it up"
        menu = yard._win._menu
        labels = [menu.entrycget(i, "label")
                  for i in range(menu.index("end") + 1)]
        assert "Knock it down" in labels and "Leave it standing" in labels, labels
        menu.invoke(labels.index("Knock it down"))
        assert yard.hut() is None, "and the menu entry is what takes it down"
        planks = len(yard._wreck)
        assert planks == yard.WRECK_N, ("it leaves a wreck behind", planks)
        assert all(abs(plank[0] - where) < yard.HUT_W for plank in yard._wreck), (
            "lying where the hut stood")
        step(2)
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
        # Every plank has its own time on it, so the pile thins out rather
        # than blinking out whole. Six seconds in, the shortest-lived of them
        # are gone; another eight and there is nothing left to draw.
        step(60 * 3)
        assert len(yard._wreck) < planks, (
            "the wreck goes a plank at a time", len(yard._wreck), planks)
        step(60 * 8)
        assert not yard._wreck, "until there is nothing left of it"
        roamer.BUILD_ODDS, roamer.FOOTY_ODDS = was_build, was_footy
        roamer.INSIDE_S = was_inside
        print("ok  knock the hut down and they come out screaming")

        # --- and none of it is left running ---------------------------------
        roamer.send_all_home()
        pump(app.root)
        assert not roamer.crew, "everybody goes back on his note"
        assert roamer._job is None, "an empty crew must not own a timer"
        assert yard.hut() is None and yard.ball() is None, \
            "an empty crew must not leave a yard behind either"
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
        # come from. The checks past here count what is on the desk - and a
        # note going in the bin takes whoever came off it with it, or clearing
        # the desk leaves him stood on the taskbar with nothing behind him.
        stray = roamer.Roamer(app, third, 0.0, floor)
        app.trash_note(third.note["id"])
        pump(app.root)
        assert stray not in roamer.crew and not roamer.crew,             "his note went in the bin and he went with it"
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
        # Off, so that pinning has to be what turns it on.
        pinned.set_topmost(False)
        pinned._settle_drop(bar)
        pump(app.root)
        assert pinned.note["pin"], "dropping on a title bar must pin the note"
        # The stored flag, not the window attribute: STICKY_TEST_NO_TOPMOST
        # forces the attribute off, and that switch exists so the suite can be
        # run without covering the screen. Asserting on it would check the
        # harness rather than the note.
        assert pinned.note["topmost"],             "a clipped note that is not on top slides behind what it is clipped to"
        assert pinned.note["pin"]["title"] == pin_title
        assert pinned in app.tracker.pinned, "and the tracker must start following it"
        assert pinned.canvas.find_withtag("clip"), "a paperclip must appear on it"
        if natural == "top":
            assert pinned.mascot.pose == "hang",                 "he cannot sit on an edge that is under a title bar"
        assert store.Store(data_file).get(note_id)["pin"], "the pin must persist"
        assert store.Store(data_file).get(note_id)["topmost"],             "...and so must the appear-on-top it turned on"

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
