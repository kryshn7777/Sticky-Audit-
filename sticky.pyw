"""Sticky Notes - a lightweight paper surface that behaves like a Windows app.

Launch with pythonw.exe so no console window appears:

    pythonw stickynote.pyw

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

ICON = winkit.resource_path("assets", "stickynote.ico")

# How often the mascot is even allowed to consider speaking. One timer for the
# whole app, a coin flip when it fires, and a long cooldown per note: that
# works out at a line every quarter of an hour or so, and never the same note
# twice in fifteen minutes.
NAG_EVERY_MS = 210000
NAG_CHANCE = 0.25
NAG_COOLDOWN_S = 900


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

        self.board = Board(self)
        self.board.title(winkit.BOARD_TITLE)

        for note in self.store.notes:
            self._open(note)

        if not self.store.notes:
            # An empty desk looks like the app failed to start, and a sticky
            # note app with nothing on screen has nothing to offer. Trash is
            # not a note: having thrown one away is no reason to open to
            # nothing the next morning.
            self.new_note()
        self.board.show()
        self._schedule_nag()

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

    def new_note(self, color=store.DEFAULT_COLOR):
        note = self.store.add(color)
        note["topmost"] = self.store.settings["always_on_top"]
        window = self._open(note)
        window.raise_note()
        window.start_edit()
        self.refresh_board()
        return window

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
        # Everyone back on their notes first. An overlay outliving the root
        # is how you get Tk's "invalid command name" on the way out.
        roamer.shutdown()
        self.tracker.stop()
        if self._nag_job is not None:
            try:
                self.root.after_cancel(self._nag_job)
            except (tk.TclError, ValueError):
                pass
            self._nag_job = None
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
