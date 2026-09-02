"""The overview window: every note in one list, plus the Trash and settings.

This is the window the taskbar icon owns. Closing it minimises rather than
quits, so the notes on the desktop stay exactly where they were.
"""

import time
import tkinter as tk

import store
import winkit
from note import pick_font, shade

LIGHT = {"bg": "#F5F5F3", "card": "#FFFFFF", "fg": "#1B1B1B", "dim": "#6B6B6B",
         "line": "#E1E1DE", "hover": "#EDEDEA", "accent": "#3B6EA5"}
DARK = {"bg": "#1F1F1F", "card": "#2A2A2A", "fg": "#F0F0F0", "dim": "#A0A0A0",
        "line": "#3A3A3A", "hover": "#333333", "accent": "#7FB2E5"}


def ago(when):
    """Human-sized elapsed time. No ticking clock, computed only on redraw."""
    seconds = max(0, int(time.time() - (when or 0)))
    for limit, size, label in ((60, 1, "s"), (3600, 60, "m"),
                               (86400, 3600, "h"), (2592000, 86400, "d")):
        if seconds < limit:
            return "just now" if seconds < 10 and label == "s" else "%d%s ago" % (seconds // size, label)
    return time.strftime("%d %b", time.localtime(when))


class Board(tk.Toplevel):
    def __init__(self, app):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self._jobs = []            # pending after() ids, cancelled on destroy
        self.view = "notes"
        self.new_color = store.DEFAULT_COLOR
        self.theme = DARK if winkit.dark_mode() else LIGHT

        self.title(winkit.BOARD_TITLE)
        self.geometry("380x520")
        self.minsize(340, 380)
        self.configure(bg=self.theme["bg"])
        self.protocol("WM_DELETE_WINDOW", self.hide)

        scale = winkit.text_scale()
        family = pick_font(self, ("Segoe UI Variable Text", "Segoe UI"))
        self.f_ui = (family, int(9 * scale))
        self.f_row = (family, int(10 * scale))
        self.f_head = (family, int(10 * scale), "bold")
        self.f_title = (family, int(13 * scale), "bold")

        self._build()
        self._later(60, lambda: winkit.dark_titlebar(self, winkit.dark_mode()))
        self.refresh()

    def _later(self, ms, callback):
        """after() that will not fire into a destroyed window."""
        job = self.after(ms, callback)
        # Only the most recent handful can still be pending; keeping every id
        # ever issued would grow without bound over a long session.
        self._jobs = self._jobs[-8:] + [job]
        return job

    def destroy(self):
        for job in self._jobs:
            try:
                self.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        self._jobs = []
        tk.Toplevel.destroy(self)

    # ------------------------------------------------------------------ chrome

    def _build(self):
        t = self.theme
        top = tk.Frame(self, bg=t["bg"], padx=16, pady=14)
        top.pack(fill="x")
        tk.Label(top, text="Sticky Notes", bg=t["bg"], fg=t["fg"],
                 font=self.f_title).pack(side="left")

        self.swatches = {}
        picker = tk.Frame(top, bg=t["bg"])
        picker.pack(side="right")
        for name in store.COLORS:
            dot = tk.Canvas(picker, width=16, height=16, bg=t["bg"], bd=0,
                            highlightthickness=0, cursor="hand2", takefocus=True)
            dot.bind("<Button-1>", lambda e, c=name: self._pick(c))
            dot.bind("<Return>", lambda e, c=name: self._pick(c))
            dot.pack(side="left", padx=1)
            self.swatches[name] = dot
        self.btn_new = tk.Button(top, text="New note", font=self.f_ui, bd=0,
                                 relief="flat", cursor="hand2", padx=12, pady=4,
                                 bg=t["accent"], fg="#FFFFFF",
                                 activebackground=shade(t["accent"], 0.9),
                                 activeforeground="#FFFFFF",
                                 command=self._new_note)
        self.btn_new.pack(side="right", padx=(0, 10))

        tabs = tk.Frame(self, bg=t["bg"], padx=16)
        tabs.pack(fill="x")
        self.tab_notes = self._tab(tabs, "Notes", "notes")
        self.tab_trash = self._tab(tabs, "Trash", "trash")

        wrap = tk.Frame(self, bg=t["line"], padx=1, pady=1)
        wrap.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        self.canvas = tk.Canvas(wrap, bg=t["bg"], highlightthickness=0, bd=0)
        bar = tk.Scrollbar(wrap, command=self.canvas.yview, width=10, bd=0,
                           highlightthickness=0, bg=t["line"], troughcolor=t["bg"],
                           activebackground=t["dim"])
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list = tk.Frame(self.canvas, bg=t["bg"])
        self._window = self.canvas.create_window((0, 0), window=self.list, anchor="nw")
        self.list.bind("<Configure>", self._on_list_resize)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<MouseWheel>", self._wheel)

        foot = tk.Frame(self, bg=t["bg"], padx=16)
        foot.pack(fill="x", pady=(0, 12))
        self.var_top = tk.BooleanVar(value=self.app.store.settings["always_on_top"])
        tk.Checkbutton(foot, text="Always on top", variable=self.var_top,
                       command=self._toggle_top, font=self.f_ui,
                       bg=t["bg"], fg=t["dim"], selectcolor=t["card"],
                       activebackground=t["bg"], activeforeground=t["fg"],
                       bd=0, highlightthickness=0, cursor="hand2",
                       anchor="w").pack(fill="x")

        if winkit.packaged():
            # An installed package cannot set its own startup entry; Windows
            # owns that list. Send the user to the place that does work.
            link = tk.Label(foot, text="Start with Windows -  open Settings",
                            font=self.f_ui, bg=t["bg"], fg=t["accent"],
                            cursor="hand2", anchor="w")
            link.pack(fill="x", pady=(2, 0))
            link.bind("<Button-1>", lambda e: winkit.open_startup_settings())
        else:
            self.var_run = tk.BooleanVar(value=winkit.get_run_at_startup())
            tk.Checkbutton(foot, text="Start with Windows", variable=self.var_run,
                           command=self._toggle_run, font=self.f_ui,
                           bg=t["bg"], fg=t["dim"], selectcolor=t["card"],
                           activebackground=t["bg"], activeforeground=t["fg"],
                           bd=0, highlightthickness=0, cursor="hand2",
                           anchor="w").pack(fill="x")
        tk.Button(foot, text="Quit", font=self.f_ui, bd=0, relief="flat",
                  cursor="hand2", padx=10, bg=t["bg"], fg=t["dim"],
                  activebackground=t["hover"], activeforeground=t["fg"],
                  command=self.app.quit_app).pack(anchor="e", pady=(6, 0))

    def _tab(self, parent, label, key):
        t = self.theme
        btn = tk.Label(parent, text=label, font=self.f_head, bg=t["bg"], fg=t["dim"],
                       cursor="hand2", padx=2, pady=6)
        btn.pack(side="left", padx=(0, 18))
        btn.bind("<Button-1>", lambda e, k=key: self._switch(k))
        return btn

    def _on_list_resize(self, _event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass          # queued redraw arrived after the window went away

    def _wheel(self, event):
        if self.list.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    # ----------------------------------------------------------------- actions

    def _pick(self, color):
        self.new_color = color
        self._draw_swatches()

    def _new_note(self):
        self.app.new_note(self.new_color)

    def _switch(self, view):
        self.view = view
        self.refresh()

    def _toggle_top(self):
        self.app.set_always_on_top(self.var_top.get())

    def _toggle_run(self):
        if not winkit.set_run_at_startup(self.var_run.get()):
            self.var_run.set(winkit.get_run_at_startup())

    def hide(self):
        """Closing the overview must never take the notes away with it."""
        self.iconify()

    def show(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()

    # ------------------------------------------------------------------ render

    def _draw_swatches(self):
        for name, dot in self.swatches.items():
            colors = store.COLORS[name]
            dot.delete("all")
            selected = name == self.new_color
            dot.create_oval(1, 1, 15, 15, fill=colors["paper"],
                            outline=self.theme["fg"] if selected else colors["edge"],
                            width=2 if selected else 1)

    def refresh(self):
        t = self.theme
        self._draw_swatches()
        for tab, key in ((self.tab_notes, "notes"), (self.tab_trash, "trash")):
            active = self.view == key
            count = len(self.app.store.notes if key == "notes" else self.app.store.trash)
            tab.configure(fg=t["fg"] if active else t["dim"],
                          text=("Notes" if key == "notes" else "Trash") +
                               ("  %d" % count if count else ""))
        for child in self.list.winfo_children():
            child.destroy()

        rows = self.app.store.notes if self.view == "notes" else self.app.store.trash
        if not rows:
            empty = ("No notes yet. Press New note to start one."
                     if self.view == "notes" else
                     "Trash is empty. Deleted notes wait here until you clear them.")
            tk.Label(self.list, text=empty, bg=t["bg"], fg=t["dim"], font=self.f_ui,
                     wraplength=300, justify="left", padx=14, pady=24).pack(fill="x")
        else:
            for note in rows:
                self._row(note)
        if self.view == "trash" and rows:
            tk.Button(self.list, text="Empty Trash", font=self.f_ui, bd=0, relief="flat",
                      cursor="hand2", bg=t["bg"], fg=t["dim"], activeforeground=t["fg"],
                      activebackground=t["hover"],
                      command=self.app.empty_trash).pack(anchor="e", padx=10, pady=8)
        self._later(1, self._on_list_resize)

    def _row(self, note):
        t = self.theme
        colors = store.COLORS[note["color"]]
        card = tk.Frame(self.list, bg=t["card"], padx=10, pady=8)
        card.pack(fill="x", padx=6, pady=3)

        chip = tk.Canvas(card, width=10, height=34, bg=t["card"], bd=0,
                         highlightthickness=0)
        chip.create_rectangle(0, 0, 10, 34, fill=colors["paper"], outline=colors["edge"])
        chip.pack(side="left", padx=(0, 10))

        # Pack the actions before the text: Tk gives space in packing order, so
        # a long snippet packed first squeezes the buttons off the card.
        actions = tk.Frame(card, bg=t["card"])
        actions.pack(side="right")

        text = tk.Frame(card, bg=t["card"])
        text.pack(side="left", fill="x", expand=True)
        heading = note["heading"].strip() or "Untitled note"
        snippet = " ".join(note["body"].split())[:48] or "empty"
        stamp = note.get("deleted_at") if self.view == "trash" else note.get("updated")
        prefix = "deleted " if self.view == "trash" else ""
        tk.Label(text, text=heading, bg=t["card"], fg=t["fg"], font=self.f_head,
                 anchor="w").pack(fill="x")
        tk.Label(text, text="%s  -  %s%s" % (snippet, prefix, ago(stamp)), bg=t["card"],
                 fg=t["dim"], font=self.f_ui, anchor="w").pack(fill="x")

        if self.view == "notes":
            self._action(actions, "Show", lambda: self.app.show_note(note["id"]))
            self._action(actions, "Trash", lambda: self.app.trash_note(note["id"]))
            for widget in (card, text, chip) + tuple(text.winfo_children()):
                widget.bind("<Double-Button-1>",
                            lambda e, i=note["id"]: self.app.show_note(i, edit=True))
        else:
            self._action(actions, "Restore", lambda: self.app.restore_note(note["id"]))
            self._action(actions, "Delete", lambda: self.app.purge_note(note["id"]),
                         danger=True)

    def _action(self, parent, label, command, danger=False):
        t = self.theme
        tk.Button(parent, text=label, font=self.f_ui, bd=0, relief="flat", cursor="hand2",
                  padx=8, pady=2, bg=t["card"],
                  fg="#C4544B" if danger else t["accent"],
                  activebackground=t["hover"],
                  activeforeground="#C4544B" if danger else t["accent"],
                  command=command).pack(side="left", padx=2)
