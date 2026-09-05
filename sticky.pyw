"""Sticky - a lightweight paper surface that behaves like a Windows app.

Launch with pythonw.exe so no console window appears:

    pythonw sticky.pyw

One process owns every note window and the overview. It sits in Tk's event
loop doing nothing at all until you touch something: no polling, no threads,
no network, no timers other than the short autosave debounce.
"""

import atexit
import os
import random
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import winkit

# Both must happen before the first Tk window exists.
winkit.set_dpi_awareness()
winkit.set_app_id()

import mascot                     # noqa: E402
import roamer                     # noqa: E402
import store                      # noqa: E402
from board import Board           # noqa: E402
from note import NoteWindow, Toast  # noqa: E402

ICON = winkit.resource_path("assets", "sticky.ico")

# How often the mascot is even allowed to consider speaking. One timer for the
# whole app, a coin flip when it fires, and a long cooldown per note: that
# works out at a line every quarter of an hour or so, and never the same note
# twice in fifteen minutes.
HELLO_MS = 2600          # long enough to have looked at the note first
CAPTURE_W, CAPTURE_H = 260, 200   # room kept for a captured note on screen

NAG_EVERY_MS = 210000
NAG_CHANCE = 0.25
NAG_COOLDOWN_S = 900

# The first ten minutes run the crew fast. Everything they do on their own is
# on a clock measured in minutes, which is right for a machine you leave on all
# day and useless to somebody who has just installed this and is watching: the
# whole point of the app happens off-screen while they decide it does nothing.
SHOWTIME_MS = 600000
SHOWTIME_HASTE = 0.15

# The three notes a brand new desk opens with. Between them they say what the
# app is: he reads the words, here is a list to try things from, and a note
# whose mood he has already taken on. No trigger word appears in the text of
# the note that asks for one - a man reads his own note as he is born, and
# would count the word as already used and never go.
STARTER_NOTES = (
    ("yellow", "He reads your notes",
     "A little guy lives on every note and reads what you write.\n\n"
     "Type the name of his favourite cheesy round food and watch him go\n"
     "and get one."),
    ("green", "Things to try",
     "[ ] right-click me and open Scenes\n"
     "[ ] find \"What do they react to?\" on the board\n"
     "[ ] tick every box on this note"),
    ("blue", "So sleepy",
     "yawn... nap time... zzz"),
)


class App:
    def __init__(self):
        self.store = store.Store()
        self.windows = {}          # note id -> NoteWindow
        self.toast = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(winkit.BOARD_TITLE + " (host)")
        self._scale_for_dpi()
        if os.path.exists(ICON):
            try:
                self.root.iconbitmap(default=ICON)
            except tk.TclError:
                pass

        # One pointer tracker for every note there will ever be.
        self.tracker = mascot.PointerTracker(self.root)
        self._nagged = {}
        self._nag_job = None

        # Ctrl+Alt+N from anywhere. Off again the moment Windows says no:
        # the combination may already belong to somebody else, and an app that
        # will not start over a hotkey is worse than one without a hotkey.
        self.hotkey = winkit.Hotkey()
        if self.store.settings.get("quick_capture", True):
            # The setting is what you asked for, not what Windows said today.
            # Somebody else may hold Ctrl+Alt+N this morning and not this
            # afternoon, and writing the refusal into the settings turned the
            # feature off for good over a temporary no.
            if self.hotkey.register():
                self.tracker.also = self._check_hotkey

        self.board = Board(self)
        self.board.title(winkit.BOARD_TITLE)

        for note in self.store.notes:
            self._open(note)

        # said_hello is only written a few seconds from now, so it still says
        # whether this is the first time the app has ever been opened.
        first_run = not self.store.settings.get("said_hello")

        if not self.store.notes:
            # An empty desk looks like the app failed to start, and a sticky
            # note app with nothing on screen has nothing to offer. Trash is
            # not a note: having thrown one away is no reason to open to
            # nothing the next morning.
            if first_run and not self.store.trash:
                self._starter_notes()
            else:
                self.new_note()
        self.board.show()
        self._schedule_nag()
        self._hello_job = None
        self._show_job = None
        if first_run:
            self._hello_job = self.root.after(HELLO_MS, self._hello)
            roamer.HASTE = SHOWTIME_HASTE
            self._show_job = self.root.after(SHOWTIME_MS, self._end_showtime)

        atexit.register(self._save_quietly)

    def _scale_for_dpi(self):
        """Match Tk's point size to the monitor so text is the right size."""
        try:
            dpi = self.root.winfo_fpixels("1i")
            self.root.tk.call("tk", "scaling", dpi / 72.0)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ note windows

    def _open(self, note):
        window = NoteWindow(self, note)
        self.windows[note["id"]] = window
        return window

    def _starter_notes(self):
        """The desk a brand new user opens to. Written once, ever.

        Through store.add rather than new_note: three notes each grabbing the
        cursor is three notes fighting over it, and the first one wants to be
        read rather than typed into.
        """
        for color, heading, body in STARTER_NOTES:
            note = self.store.add(color)
            note["heading"] = heading
            note["body"] = body
            note["topmost"] = self.store.settings["always_on_top"]
            self._open(note)
        self.store.save()

    def _end_showtime(self):
        """Ten minutes up: the crew goes back to normal time."""
        self._show_job = None
        roamer.HASTE = 1.0

    def new_note(self, color=store.DEFAULT_COLOR, at=None):
        note = self.store.add(color, *(at if at is not None else (None, None)))
        note["topmost"] = self.store.settings["always_on_top"]
        window = self._open(note)
        window.raise_note()
        window.start_edit()
        self.refresh_board()
        return window

    def _check_hotkey(self):
        """Was Ctrl+Alt+N pressed? Asked on the tracker's tick.

        The key itself arrives without a timer - Windows dispatches it to our
        own window procedure through the loop Tk is already running - but a
        window procedure may only set a flag, and reading that flag is what
        this is. No timer of its own: the tracker is already ticking, and it
        holds itself to ALSO_MS while anybody is riding on it.
        """
        if self.hotkey.take():
            self.capture_note()

    def capture_note(self):
        """The hotkey. A note at the pointer, ready to type into.

        Where the pointer is rather than where the cascade was up to: the
        whole point of a key you press without looking is that you are already
        looking somewhere, and the note has to arrive there.
        """
        at = None
        try:
            px, py = self.root.winfo_pointerxy()
        except tk.TclError:
            px = py = None
        if px is not None:
            area = winkit.work_area(px, py)
            if area is None:
                area = (0, 0, self.root.winfo_screenwidth(),
                        self.root.winfo_screenheight())
            # Placed under the pointer, and kept far enough inside the work
            # area that the whole sheet is on the screen it was asked for.
            at = (int(min(max(px - 24, area[0] + 8), area[2] - CAPTURE_W)),
                  int(min(max(py - 18, area[1] + 8), area[3] - CAPTURE_H)))
        window = self.new_note(at=at)
        window.raise_note()
        return window

    def set_quick_capture(self, enabled):
        """Turn the hotkey on or off. Returns what actually happened."""
        if enabled:
            self.store.settings["quick_capture"] = bool(self.hotkey.register())
            self.tracker.also = (self._check_hotkey
                                 if self.store.settings["quick_capture"] else None)
        else:
            self.hotkey.unregister()
            self.store.settings["quick_capture"] = False
            self.tracker.also = None
        self.store.save()
        return self.store.settings["quick_capture"]

    def show_note(self, note_id, edit=False):
        window = self.windows.get(note_id)
        if window is None:
            note = self.store.get(note_id)
            if note is None:
                return
            window = self._open(note)
        window.raise_note()
        if edit:
            window.start_edit(on_heading=not window.note["heading"])

    def select(self, window):
        """A plain click on a note brings it forward. It does not edit it."""
        for other in self.windows.values():
            if other is not window and other.editing:
                other.finish_edit()
        window.lift()

    # ----------------------------------------------------------------- storage

    def persist(self):
        self.store.save()
        self.refresh_board()

    def _save_quietly(self):
        try:
            self.store.save()
        except OSError:
            pass

    def refresh_board(self):
        try:
            if self.board.winfo_exists():
                self.board.refresh()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------- trash

    def trash_note(self, note_id):
        window = self.windows.pop(note_id, None)
        x = y = None
        if window is not None:
            try:
                x, y = window.winfo_rootx(), window.winfo_rooty()
                window.destroy()
            except tk.TclError:
                pass
        if self.store.trash_note(note_id) is None:
            return
        self.refresh_board()
        if x is None:
            x, y = self.root.winfo_screenwidth() - 320, self.root.winfo_screenheight() - 140
        self._show_toast("Note moved to Trash", "Undo",
                         lambda: self.restore_note(note_id), x, y)

    def restore_note(self, note_id):
        note = self.store.restore(note_id)
        if note is None:
            return
        self._open(note).raise_note()
        self.refresh_board()

    def purge_note(self, note_id):
        note = next((n for n in self.store.trash if n["id"] == note_id), None)
        if note is None:
            return
        label = note["heading"].strip() or "this note"
        if not self._confirm("Delete permanently",
                             "Delete %s for good?\n\nThis cannot be undone." % label):
            return
        self.store.purge(note_id)
        self.refresh_board()

    def empty_trash(self):
        count = len(self.store.trash)
        if not count:
            return
        if not self._confirm("Empty Trash",
                             "Permanently delete %d note%s?\n\nThis cannot be undone."
                             % (count, "" if count == 1 else "s")):
            return
        self.store.empty_trash()
        self.refresh_board()

    def _confirm(self, title, message):
        from tkinter import messagebox
        return messagebox.askyesno(title, message, icon="warning", parent=self.board)

    def _show_toast(self, message, action_label, action, x, y):
        if self.toast is not None:
            self.toast.close()
        self.toast = Toast(self.root, message, action_label, action, x, y + 10)

    # ---------------------------------------------------------------- settings

    def set_always_on_top(self, enabled):
        self.store.settings["always_on_top"] = bool(enabled)
        for window in self.windows.values():
            window.set_topmost(enabled)
        self.store.save()

    def set_mascot(self, enabled):
        """Right-click > Show mascot. One setting for every note: he is the
        app's face, not a per-note decoration."""
        self.store.settings["mascot"] = bool(enabled)
        if not enabled:
            roamer.shutdown()       # nobody left wandering about, switched off
        for window in self.windows.values():
            window.apply_mascot()
        self.store.save()

    # ------------------------------------------------------------- the mascot

    def _hello(self):
        """The first thing he ever says, and the only time he says it.

        The flag is written whether or not the bubble went up. A man who was
        switched off, or a note that has already been closed, is not a reason
        to keep trying every launch until it lands: this is a hello, not a
        thing to be nagged with.
        """
        self._hello_job = None
        if self.store.settings.get("said_hello"):
            return              # once means once, however it is called
        self.store.settings["said_hello"] = True
        self._save_quietly()
        if not self.store.settings.get("mascot", True):
            return
        for window in self.windows.values():
            try:
                if window.mascot.visible() and window.mascot.say(mascot.HELLO_LINE):
                    return
            except tk.TclError:
                continue

    def _cancel_jobs(self):
        """Every after() this app owns, called off."""
        for name in ("_nag_job", "_hello_job", "_show_job"):
            job = getattr(self, name, None)
            if job is None:
                continue
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
            setattr(self, name, None)

    def _schedule_nag(self):
        self._nag_job = self.root.after(NAG_EVERY_MS, self._nag)

    def _nag(self):
        """Every so often, if a note has boxes left unticked and nobody is
        looking at it, he says something. One timer, one dice roll, no loop."""
        self._schedule_nag()
        if not self.store.settings.get("mascot", True):
            return
        if random.random() > NAG_CHANCE:
            return
        now = time.monotonic()
        candidates = [w for w in self.windows.values()
                      if not w.editing
                      and w.mascot.visible()
                      and not w.mascot.near()          # you are already here
                      and now - self._nagged.get(w.note["id"], 0.0) > NAG_COOLDOWN_S
                      and mascot.has_open_box(w.note["body"])]
        if not candidates:
            return
        window = random.choice(candidates)
        if window.mascot.say():
            self._nagged[window.note["id"]] = now

    # -------------------------------------------------------------------- life

    def quit_app(self):
        # Every timer first, before anything slow. Taking the crew down and
        # stopping the tracker is real work, and a timer that comes due in the
        # middle of it fires into a half-dismantled app - which is Tk's
        # "invalid command name" on the way out, printed at the user.
        self._cancel_jobs()
        # Everyone back on their notes. An overlay outliving the root is the
        # same error from the other end.
        roamer.shutdown()
        self.hotkey.close()
        self.tracker.stop()
        # A speech bubble is a window with a timer to close itself. Destroying
        # the root takes the window without running any of this file's code,
        # and the timer then fires into a command that has gone - which Tk
        # prints. Nothing else notices, and it is still ours to tidy up.
        for window in list(self.windows.values()):
            try:
                window.mascot.hush()
            except (tk.TclError, AttributeError):
                pass
        # An Undo toast is the same shape of thing: a window with a timer to
        # close itself, and nobody left to run it.
        if self.toast is not None:
            try:
                self.toast.close()
            except tk.TclError:
                pass
            self.toast = None
        for window in list(self.windows.values()):
            try:
                window.flush()
            except tk.TclError:
                pass
        self.store.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if not winkit.claim_single_instance():
        return 0               # already running: we raised its window, now step aside
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
