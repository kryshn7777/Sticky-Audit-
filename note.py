"""The sticky note itself: a borderless paper window on the desktop.

View mode  - the note is a solid object. Press and drag it anywhere,
             double-click it to start writing.
Edit mode  - heading and body become live text, and a toolbar appears with
             the colour swatches, Move to Trash, and OK.

Everything is event driven. When nothing is happening the window costs
nothing: no timer, no polling loop, no background thread. The one exception
is the mascot, and only while he is switched on - see mascot.py, which
explains exactly what he does and does not cost.
"""

import math
import time
import tkinter as tk
import tkinter.font as tkfont

import mascot as mascot_mod
import roamer
import store
import winkit
from store import shade      # re-exported: board.py imports it from here

# Chroma key for the folded corner. Any pixel painted this colour is punched
# out of the window, which is how the corner can be cut away cleanly.
KEY = "#010203"

# Handwriting, but the printed kind you can actually read. Ink Free and Segoe
# Script are scrawls at note sizes; Segoe UI is not handwriting at all. Segoe
# Print sits in the middle: hand-lettered shapes, upright and separated.
NOTE_FONTS = ("Segoe Print", "Comic Sans MS", "Ink Free", "Segoe UI")
MIN_FONT, MAX_FONT = 8, 24

# Sheet sizes. These describe the paper, not the window: with the mascot on,
# the window is the paper plus his margins, so switching him on and off never
# changes how much room there is to write in.
MIN_W, MIN_H = 292, 214
MAX_W, MAX_H = 424, 524
SHADOW = 0        # no drop shadow: see _redraw for why
PAD = 18          # breathing room around the writing
GRIP_H = 16       # the adhesive strip along the top: always draggable
CURL = 28         # the lifted corner, bottom right: the resize grab handle
CLIP_W, CLIP_H = 15, 30   # the paperclip that pins a note to another window
CLIP_AT = 0.72            # where along the top edge it sits
CLIP_ABOVE = 17           # room the window takes above the sheet for the clip
CLIP_STEPS, CLIP_MS = 9, 20   # it snaps on rather than appearing
PIN_HINT_S = 0.05         # how often a drag may go looking for a title bar
RESIZE_EDGE = 6   # how close to the right or bottom edge counts as a resize
RADIUS = 2        # sticky notes are square-cut, not rounded like a UI card
VIGNETTE = 12     # nested edge outlines; must stay under PAD so the flat
                  # text widgets never sit on top of a shaded area
DRAG_SLOP = 5     # pixels of movement before a press becomes a drag
SAVE_DELAY = 700  # ms of quiet after the last keystroke before writing to disk
RESIZE_DELAY = 90  # ms of quiet before the note is allowed to change size
RESIZE_FRAME = 1 / 60.0   # seconds: the fastest a drag will resize the window


def pick_font(root, candidates):
    available = set(tkfont.families(root))
    for name in candidates:
        if name in available:
            return name
    return candidates[-1]


def _short(text, limit=28):
    """Window titles run long. Menus do not."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """A rounded rectangle, drawn as a smoothed polygon."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Toast(tk.Toplevel):
    """A small, self-dismissing message with one action. Used to offer Undo
    right after a note is trashed, so deleting is never a dead end."""

    def __init__(self, master, message, action_label, action, x, y, ms=6000):
        tk.Toplevel.__init__(self, master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._action = action
        scale = winkit.text_scale()
        family = pick_font(self, ("Segoe UI Variable Text", "Segoe UI"))
        ui = (family, int(9 * scale))

        frame = tk.Frame(self, bg="#2B2B2B", padx=14, pady=10)
        frame.pack()
        tk.Label(frame, text=message, bg="#2B2B2B", fg="#F2F2F2", font=ui).pack(side="left")
        link = tk.Label(frame, text=action_label, bg="#2B2B2B", fg="#8CC2FF",
                        font=(family, int(9 * scale), "underline"),
                        cursor="hand2", padx=12)
        link.pack(side="left")
        link.bind("<Button-1>", self._fire)

        self.update_idletasks()
        self.geometry("+%d+%d" % (int(x), int(y)))
        self._timer = self.after(ms, self.close)

    def _fire(self, _event=None):
        action, self._action = self._action, None
        self.close()
        if action:
            action()

    def close(self):
        try:
            self.after_cancel(self._timer)
        except (tk.TclError, ValueError):
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class NoteWindow(tk.Toplevel):
    def __init__(self, app, note):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self.note = note
        self.editing = False
        self._save_job = None
        self._snapshot = None      # heading/body as they were when editing began
        self._press = None
        self._dragging = False
        self._resizing = False
        self._mode = None
        self._moved_to = None
        self._size_job = None
        self._tapped = False
        self._host = None          # hwnd of the window this note is clipped to
        self._host_at = None       # where that window was when we last looked
        self._host_hidden = False  # we withdrew because the host went away
        self._clip_job = None
        self._pin_hint = None      # a title bar this drag is hovering over
        self._hinted = False
        self._hint_at = 0.0
        self._want_size = None     # the size the last motion event asked for
        self._resize_job = None
        self._resized_at = 0.0
        self._roamer = None        # he is in somebody's hand right now

        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-transparentcolor", KEY)
            self._keyed = True
        except tk.TclError:
            self._keyed = False    # no chroma key: square corners, still fine
        # The mascot's swipe animation needs the same key for its own window.
        self.chroma_key = KEY if self._keyed else None

        self.scale = winkit.text_scale()
        self.family = pick_font(self, NOTE_FONTS)
        self.f_head = tkfont.Font(family=self.family, weight="bold")
        self.f_body = tkfont.Font(family=self.family)
        self.f_bold = tkfont.Font(family=self.family, weight="bold")
        self.f_italic = tkfont.Font(family=self.family, slant="italic")
        self.f_bolditalic = tkfont.Font(family=self.family, weight="bold",
                                        slant="italic")
        self.f_ui = tkfont.Font(family=self.family, size=int(9 * self.scale))
        self._apply_font_size()

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=KEY if self._keyed else self._paper()["paper"])
        self.canvas.pack(fill="both", expand=True)
        self.mascot = mascot_mod.Mascot(self)

        self.head = tk.Text(self, height=1, wrap="none", undo=True, maxundo=200,
                            bd=0, highlightthickness=0, padx=0, pady=0,
                            font=self.f_head, cursor="arrow")
        self.body = tk.Text(self, wrap="word", undo=True, maxundo=400,
                            bd=0, highlightthickness=0, padx=0, pady=0,
                            font=self.f_body, cursor="arrow", spacing1=1, spacing3=3)
        self.scroll = tk.Scrollbar(self, command=self.body.yview, width=8,
                                   bd=0, highlightthickness=0)
        self.body.configure(yscrollcommand=self.scroll.set)

        self.toolbar = tk.Frame(self)
        row1 = tk.Frame(self.toolbar)          # colours and formatting
        row1.pack(fill="x")
        row2 = tk.Frame(self.toolbar)          # Move to Trash / OK
        row2.pack(fill="x", pady=(6, 0))
        self.rows = (row1, row2)

        self.swatches = {}
        for name in store.COLORS:
            dot = tk.Canvas(row1, width=16, height=16, bd=0,
                            highlightthickness=0, cursor="hand2", takefocus=True)
            dot.bind("<Button-1>", lambda e, c=name: self.set_color(c))
            dot.bind("<Return>", lambda e, c=name: self.set_color(c))
            dot.bind("<space>", lambda e, c=name: self.set_color(c))
            dot.pack(side="left", padx=(0, 4))
            self.swatches[name] = dot

        self.fmt_buttons = {}
        for tag, label, font_kw in (("bold", "B", {"weight": "bold"}),
                                    ("italic", "I", {"slant": "italic"}),
                                    ("underline", "U", {"underline": 1})):
            btn = tk.Button(row1, text=label, bd=0, relief="flat", cursor="hand2",
                            width=2, padx=0, pady=0,
                            font=tkfont.Font(family=self.family,
                                             size=int(9 * self.scale), **font_kw),
                            command=lambda t=tag: self.toggle_format(t))
            btn.pack(side="left", padx=1)
            self.fmt_buttons[tag] = btn

        self.btn_smaller = tk.Button(row1, text="A-", font=self.f_ui, bd=0,
                                     relief="flat", cursor="hand2", width=2,
                                     padx=0, pady=0,
                                     command=lambda: self.bump_font(-1))
        self.btn_larger = tk.Button(row1, text="A+", font=self.f_ui, bd=0,
                                    relief="flat", cursor="hand2", width=2,
                                    padx=0, pady=0,
                                    command=lambda: self.bump_font(1))
        self.btn_larger.pack(side="right")
        self.btn_smaller.pack(side="right", padx=(0, 2))

        self.btn_trash = tk.Button(row2, text="Move to Trash", font=self.f_ui,
                                   bd=0, relief="flat", cursor="hand2", padx=8, pady=2,
                                   command=self.move_to_trash)
        self.btn_ok = tk.Button(row2, text="OK", font=self.f_ui, bd=0,
                                relief="flat", cursor="hand2", padx=14, pady=2,
                                command=self.finish_edit)
        self.btn_ok.pack(side="right")
        self.btn_trash.pack(side="right", padx=(0, 8))

        self._build_menu()
        self._bind_all()
        self._apply_color()
        self._apply_geometry(note["w"], note["h"], note["x"], note["y"])
        self.head.insert("1.0", note["heading"])
        self.body.insert("1.0", note["body"])
        self.head.edit_reset()
        self.body.edit_reset()
        self._configure_tags()
        self._restore_marks()
        self.head.edit_modified(False)
        self.body.edit_modified(False)
        self.set_topmost(note["topmost"])
        self._enter_view()
        self.deiconify()
        tracker = self._tracker()
        if tracker is not None:
            tracker.register(self.mascot)
            if note.get("pin"):
                # The window we were clipped to may or may not be running.
                # Either way this is the tracker's problem from now on.
                self._settle_pose()
                tracker.follow(self)
        self.after_idle(self._autosize)

    def _tracker(self):
        return getattr(self.app, "tracker", None)

    def destroy(self):
        tracker = self._tracker()
        if tracker is not None:
            tracker.unregister(self.mascot)
            tracker.unfollow(self)
        self._cancel_clip()
        guy = roamer.for_note(self.note["id"])
        if guy is not None:
            # His note has gone in the bin. He carries on living out there
            # rather than winking out with it; he simply has nowhere left to
            # go back to.
            guy.orphan()
        # A pending autosave outlives the window unless it is called off here,
        # and an "after" job that fires into a destroyed widget is Tk's
        # "invalid command name" at shutdown. Write first, then cancel.
        if self._save_job is not None:
            try:
                self.flush()
            except tk.TclError:
                pass
            self._cancel_after("_save_job")
        self._cancel_after("_size_job")
        self._cancel_after("_resize_job")
        self.mascot.destroy()
        tk.Toplevel.destroy(self)

    def _cancel_after(self, name):
        job = getattr(self, name, None)
        if job is None:
            return
        try:
            self.after_cancel(job)
        except (tk.TclError, ValueError):
            pass
        setattr(self, name, None)

    # ------------------------------------------------------------- appearance

    def _paper(self):
        return store.COLORS[self.note["color"]]

    def _apply_color(self):
        c = self._paper()
        paper, ink, edge = c["paper"], c["ink"], c["edge"]
        for widget in (self.head, self.body):
            state = widget["state"]
            widget.configure(state="normal")
            widget.configure(bg=paper, fg=ink, insertbackground=ink,
                             selectbackground=shade(paper, 0.82), selectforeground=ink)
            widget.configure(state=state)
        self.configure(bg=paper)
        self.canvas.configure(bg=KEY if self._keyed else paper)
        self.toolbar.configure(bg=paper)
        for row in self.rows:
            row.configure(bg=paper)
        for btn in list(self.fmt_buttons.values()) + [self.btn_smaller, self.btn_larger]:
            btn.configure(bg=paper, fg=ink, activebackground=shade(paper, 0.86),
                          activeforeground=ink)
        for dot in self.swatches.values():
            dot.configure(bg=paper)
        self.btn_ok.configure(bg=shade(paper, 0.88), fg=ink,
                              activebackground=shade(paper, 0.80), activeforeground=ink)
        self.btn_trash.configure(bg=paper, fg=shade(ink, 1.6),
                                 activebackground=shade(paper, 0.92), activeforeground=ink)
        self.scroll.configure(bg=edge, activebackground=shade(edge, 0.85), troughcolor=paper)
        self._redraw()
        self._draw_swatches()

    def _margins(self):
        """Room around the sheet for the mascot: (left, top, right, bottom).

        Which side needs room depends on where he is holding on, so this
        follows his pose. All zeroes when he is switched off, which is what
        makes him free.
        """
        l, t, r, b = mascot_mod.margins(self.mascot_enabled(), self.mascot.pose)
        if self.note.get("pin"):
            # A paperclip has to straddle the edge it is clipping, and the
            # window has to reach above the paper for it to be drawn there.
            # Most poses leave no room at the top, so a pinned note takes it.
            t = max(t, CLIP_ABOVE)
        return (l, t, r, b)

    def mascot_enabled(self):
        try:
            return bool(self.app.store.settings.get("mascot", True))
        except AttributeError:
            return False

    def _apply_geometry(self, w, h, x=None, y=None):
        """Size and place the window from the sheet's rectangle.

        The note's stored x/y/w/h always describe the paper you can see. The
        window is the paper plus the mascot's margins, offset so the sheet
        itself does not move when he is switched on or off.
        """
        l, t, r, b = self._margins()
        spec = "%dx%d" % (w + l + r, h + t + b)
        if x is not None:
            spec += "+%d+%d" % (x - l, y - t)
        self.geometry(spec)

    def paper_rect(self):
        """The sheet in window coordinates: (x, y, width, height)."""
        l, t, r, b = self._margins()
        return (l, t, self.winfo_width() - l - r, self.winfo_height() - t - b)

    def _redraw(self, w=None, h=None):
        """Paint one sheet of paper.

        Layers, bottom up: the mascot, then flat colour, a vignette that
        darkens the edges the way a sheet does where it meets the surface, the
        sheen along the top left where the light falls, and the folded corner.

        The mascot goes down first on purpose. The paper is drawn over his
        shoulders and hips, so the sheet clips his limbs and he reads as
        standing behind it rather than being pasted on.

        The caller may pass the size it just asked for, because winfo_width and
        winfo_height still report the old one until Tk processes the request.
        """
        c = self._paper()
        paper, edge, ink = c["paper"], c["edge"], c["ink"]
        l, t, _r, _b = self._margins()
        pw = max(w if w is not None else self.winfo_width() - l - _r, MIN_W)
        ph = max(h if h is not None else self.winfo_height() - t - _b, MIN_H)
        cv = self.canvas
        cv.delete("all")
        if self.mascot_enabled():
            # draw() clears him itself, and carries his mood across the wipe.
            # Clearing him here as well would throw that away, and a resize
            # repaints on every mouse move: he would flicker all the way.
            self.mascot.draw(l, t, pw, ph, paper, ink)
        else:
            self.mascot.clear()

        # No drop shadow. Tk cannot do per-pixel alpha, and the dithered
        # stand-in it can do renders as a hard dark band down the right and
        # bottom edges - a black border, not a shadow.
        cv.create_rectangle(l, t, l + pw, t + ph, fill=paper, outline="")

        # Vignette: paper picks up shade around its edges. Drawn as nested
        # outlines rather than an alpha wash, because canvas shapes are opaque
        # and the blend can simply be computed instead.
        #
        # It stops short of PAD, so it lies entirely in the margin. The text
        # widgets sit on flat `paper` and Tk cannot make them transparent, so
        # any shading that reached under them would draw their rectangles as a
        # visible seam. Keeping the interior one flat tone is what stops the
        # note looking like a box with a lighter box inside it.
        # x0/y0 is the sheet's top-left corner in canvas coordinates; x1/y1 its
        # bottom-right. They are the origin for everything below.
        x0, y0 = l, t
        x1, y1 = l + pw, t + ph

        for i in range(VIGNETTE):
            k = i / float(VIGNETTE - 1)
            cv.create_rectangle(x0 + i, y0 + i, x1 - 1 - i, y1 - 1 - i,
                                outline=shade(paper, 0.938 + 0.062 * k), width=1)
        # light falling from the top left
        cv.create_line(x0 + 1, y0 + 1, x1 - 1, y0 + 1, fill=shade(paper, 1.045))
        cv.create_line(x0 + 1, y0 + 1, x0 + 1, y1 - 1, fill=shade(paper, 1.030))

        # the glue strip showing faintly through from the back
        cv.create_rectangle(x0, y0, x1, y0 + GRIP_H,
                            fill=shade(paper, 0.978), outline="")

        # Cut the bottom-right corner away, then lay the lifted flap over it.
        cv.create_polygon([x1 - CURL, y1, x1, y1 - CURL, x1, y1],
                          fill=KEY if self._keyed else edge, outline="")
        cv.create_polygon([x1 - CURL, y1, x1, y1 - CURL, x1 - 5, y1 - 5],
                          fill=shade(paper, 0.66), outline="")
        for i in range(8):
            k = i / 7.0
            cv.create_polygon(
                [x1 - CURL + CURL * k * 0.5, y1 - CURL * k * 0.5,
                 x1 - CURL, y1 - CURL,
                 x1 - CURL * (1 - k) * 0.5, y1 - CURL + CURL * (1 - k) * 0.5],
                fill=shade(paper, 1.15 - 0.13 * k), outline="")
        cv.create_line(x1 - CURL, y1, x1, y1 - CURL, fill=shade(paper, 0.74))

        # A single hairline all the way round: one edge, one sheet.
        cv.create_line(x0, y1 - 1, x1 - CURL, y1 - 1, fill=shade(paper, 0.84))
        cv.create_line(x1 - 1, y0, x1 - 1, y1 - CURL, fill=shade(paper, 0.84))

        # The paperclip that holds the note to another app's title bar.
        if self.note.get("pin"):
            self._draw_clip(l, t, pw)

        # Last: the few parts of him that belong in front of the paper - the
        # legs he kicks down the front of it, the fingers curled over an edge.
        if self.mascot_enabled():
            self.mascot.draw_front(l, t, pw, ph)

    def _draw_clip(self, ox, oy, pw, drop=0.0, tilt=0.0):
        """A paperclip over the top edge of the sheet.

        Two nested wire hooks, the outer one straddling the edge so it reads
        as being in front of the paper and behind the title bar at once -
        which is what a paperclip does.

        Drawn as plain polylines with the arcs written out point by point.
        Tk's `smooth` would spline the corners and, under a stroke this thick,
        turn the wire into a smudge; and a pale halo under a dark core - which
        the mascot's limbs want, so they read against any wallpaper - reads
        here as a blurred double line. This wants one crisp stroke and one
        highlight, nothing else.

        `drop` lifts it for its arrival, `tilt` leans it, so it can swing into
        place rather than simply appear.
        """
        cv = self.canvas
        # Metal, not paper. The top half of the clip lies over somebody else's
        # title bar, which may be any colour at all, so it is drawn the way a
        # wire is drawn: a dark edge, a grey body and one bright glint. Three
        # concentric strokes of different widths stay crisp; a pale halo under
        # a dark core - which the mascot's limbs want - would read as blur.
        edge, wire, lit = "#33333A", "#9A9AA4", "#F0F0F6"
        cx = ox + pw * CLIP_AT
        top = oy - CLIP_ABOVE + 3 - drop
        sin_t, cos_t = math.sin(tilt), math.cos(tilt)

        def turn(x, y):
            """Lean the whole clip about the point it hangs from."""
            dx, dy = x - cx, y - top
            return (cx + dx * cos_t - dy * sin_t, top + dx * sin_t + dy * cos_t)

        def hook(half, head, foot, tail):
            """One wire: down the left, round the bottom, back up the right."""
            mid = foot - half
            pts = [(cx - half, head)]
            for k in range(13):
                a = math.pi * (1.0 + k / 12.0)
                pts.append((cx + half * math.cos(a), mid - half * math.sin(a)))
            pts.append((cx + half, tail))
            return [c for p in pts for c in turn(*p)]

        outer = hook(CLIP_W / 2.0, top, top + CLIP_H, top + CLIP_H * 0.16)
        inner = hook(CLIP_W / 5.0, top + CLIP_H * 0.30, top + CLIP_H * 0.80,
                     top + CLIP_H * 0.42)
        for colour, width in ((edge, 4), (wire, 2)):
            for path in (outer, inner):
                cv.create_line(*path, fill=colour, width=width,
                               capstyle="round", joinstyle="round", tags="clip")
        # The glint, a pixel up and to the left, where the light would fall.
        for path in (outer, inner):
            cv.create_line(*[c - 1 for c in path], fill=lit, width=1,
                           capstyle="round", joinstyle="round", tags="clip")

    def _draw_swatches(self):
        for name, dot in self.swatches.items():
            colors = store.COLORS[name]
            dot.delete("all")
            selected = name == self.note["color"]
            dot.create_oval(1, 1, 15, 15, fill=colors["paper"],
                            outline=colors["ink"] if selected else colors["edge"],
                            width=2 if selected else 1)

    # --------------------------------------------------------------- geometry

    def _place(self, w=None, h=None):
        """Position the text widgets over the painted paper.

        w/h are the sheet's size, not the window's; ox/oy shift everything
        into the sheet when the mascot's margins are there.
        """
        ox, oy, cur_w, cur_h = self.paper_rect()
        pw = w if w is not None else cur_w
        ph = h if h is not None else cur_h
        head_h = self.f_head.metrics("linespace") + 4
        bar_h = 62 if self.editing else 0
        top = GRIP_H + 8
        self.head.place(x=ox + PAD, y=oy + top,
                        width=max(pw - 2 * PAD, 20), height=head_h)
        body_y = top + head_h + 8
        # keep the last line clear of the curled corner
        body_h = max(ph - body_y - PAD - bar_h - (0 if self.editing else 8), 20)
        # Put the body where it is going first, then ask whether it overflows.
        # Asking first measures the wrapping at the width it is leaving, which
        # during a resize is the wrong one - and the answer flips back and
        # forth every frame, which is the scrollbar blinking as you drag.
        full_w = max(pw - 2 * PAD, 20)
        self.body.place(x=ox + PAD, y=oy + body_y, width=full_w, height=body_h)
        self.update_idletasks()
        show_scroll = self._body_overflows(body_h)
        if show_scroll:
            self.body.place_configure(width=max(full_w - 12, 20))
            self.scroll.place(x=ox + pw - PAD - 8, y=oy + body_y,
                              width=8, height=body_h)
        else:
            self.scroll.place_forget()
        if self.editing:
            self.toolbar.place(x=ox + PAD, y=oy + ph - PAD - bar_h + 4,
                               width=max(pw - 2 * PAD, 20), height=bar_h - 6)
        else:
            self.toolbar.place_forget()

    def _body_overflows(self, body_h):
        try:
            lines = self.body.count("1.0", "end", "displaylines")[0]
        except (tk.TclError, TypeError, IndexError):
            return False
        return lines * self.f_body.metrics("linespace") > body_h

    def _schedule_autosize(self):
        """Resizing on every keystroke makes typing stutter: coalesce them."""
        if self._size_job is not None:
            self.after_cancel(self._size_job)
        self._size_job = self.after(RESIZE_DELAY, self._autosize)

    def _autosize(self):
        """Grow to fit the writing, then stop and let the body scroll."""
        if self._size_job is not None:
            self.after_cancel(self._size_job)
            self._size_job = None
        if not self.note.get("auto_size", True) or self._resizing:
            self._place()
            return

        heading = self.head.get("1.0", "end-1c")
        body = self.body.get("1.0", "end-1c")
        widths = [self.f_head.measure(heading)]
        widths += [self.f_body.measure(line) for line in body.split("\n")]
        w = max(MIN_W, min(MAX_W, max(widths) + 2 * PAD + 24))

        _ox, _oy, cur_w, cur_h = self.paper_rect()
        if w != cur_w:
            # Re-wrap at the new width before counting the lines it produces.
            self._apply_geometry(w, cur_h)
            self._place(w, cur_h)
            self.update_idletasks()

        head_h = self.f_head.metrics("linespace") + 4
        bar_h = 62 if self.editing else 0
        chrome = GRIP_H + 8 + head_h + 8 + PAD + bar_h + 10
        try:
            lines = max(1, self.body.count("1.0", "end", "displaylines")[0])
        except (tk.TclError, TypeError, IndexError):
            lines = max(1, body.count("\n") + 1)
        h = max(MIN_H, min(MAX_H, chrome + lines * self.f_body.metrics("linespace") + 6))

        if (w, h) == (cur_w, cur_h):
            self._place(w, h)      # nothing moved: no geometry call, no repaint
            return

        self._apply_geometry(w, h)
        self.update_idletasks()
        self.note["w"], self.note["h"] = w, h
        self.schedule_save()
        self._redraw(w, h)
        self._place(w, h)

    # ------------------------------------------------------------- formatting

    def _apply_font_size(self):
        """Resize every face this note draws with, from its own stored size."""
        size = int(self.note.get("font_size", 12) * self.scale)
        self.f_body.configure(size=size)
        self.f_bold.configure(size=size)
        self.f_italic.configure(size=size)
        self.f_bolditalic.configure(size=size)
        self.f_head.configure(size=size + 3)

    def _configure_tags(self):
        """Bold, italic and underline as text tags.

        'bi' carries the bold-italic face and outranks the other two, so text
        marked both ways renders correctly instead of picking one at random.
        """
        self.body.tag_configure("bold", font=self.f_bold)
        self.body.tag_configure("italic", font=self.f_italic)
        self.body.tag_configure("underline", underline=True)
        self.body.tag_configure("bi", font=self.f_bolditalic)
        self.body.tag_raise("bi")
        self.body.tag_raise("underline")

    def _offset(self, index):
        try:
            return self.body.count("1.0", index, "chars")[0]
        except (tk.TclError, TypeError, IndexError):
            return 0

    def _spans(self, tag):
        raw = self.body.tag_ranges(tag)
        return [(self._offset(raw[i]), self._offset(raw[i + 1]))
                for i in range(0, len(raw), 2)]

    def _sync_bi(self):
        """Re-derive the bold-italic runs wherever bold and italic overlap."""
        self.body.tag_remove("bi", "1.0", "end")
        for b0, b1 in self._spans("bold"):
            for i0, i1 in self._spans("italic"):
                lo, hi = max(b0, i0), min(b1, i1)
                if lo < hi:
                    self.body.tag_add("bi", "1.0+%dc" % lo, "1.0+%dc" % hi)

    def _target_range(self):
        """The selection, or the whole note when nothing is selected."""
        try:
            return self.body.index("sel.first"), self.body.index("sel.last")
        except tk.TclError:
            return "1.0", self.body.index("end-1c")

    def toggle_format(self, tag, _event=None):
        if not self.editing:
            self.start_edit(on_heading=False)
        start, end = self._target_range()
        if self.body.compare(start, "==", end):
            return "break"
        self.body.configure(state="normal")
        if tag in self.body.tag_names(start):
            self.body.tag_remove(tag, start, end)
        else:
            self.body.tag_add(tag, start, end)
        self._sync_bi()
        self._capture()
        self.schedule_save()
        self._schedule_autosize()
        return "break"

    def bump_font(self, step):
        size = max(MIN_FONT, min(MAX_FONT, int(self.note.get("font_size", 12)) + step))
        if size == self.note.get("font_size"):
            return "break"
        self.note["font_size"] = size
        self._apply_font_size()
        self._capture()
        self.flush()
        self._autosize()
        return "break"

    def _read_marks(self):
        marks = []
        for tag in ("bold", "italic", "underline"):
            raw = self.body.tag_ranges(tag)
            for i in range(0, len(raw), 2):
                marks.append([tag, str(raw[i]), str(raw[i + 1])])
        return marks

    def _restore_marks(self):
        for entry in self.note.get("marks", []):
            tag, start, end = entry[0], entry[1], entry[2]
            try:
                self.body.tag_add(tag, start, end)
            except tk.TclError:
                pass          # the text shrank under a saved range: drop it
        self._sync_bi()

    # ------------------------------------------------------------ checkboxes

    def toggle_checkbox(self, _event=None):
        """Make the current line a checkbox, or take the checkbox away.

        Applies to every line of the selection when there is one, so a list
        you have already written becomes a list you can tick off.
        """
        if not self.editing:
            self.start_edit(on_heading=False)
        try:
            first = int(self.body.index("sel.first").split(".")[0])
            last = int(self.body.index("sel.last").split(".")[0])
        except tk.TclError:
            first = last = int(self.body.index("insert").split(".")[0])
        self.body.configure(state="normal")
        adding = None
        for line in range(first, last + 1):
            text = self.body.get("%d.0" % line, "%d.end" % line)
            prefix, _rest = mascot_mod.strip_box(text)
            if adding is None:
                adding = not prefix     # the first line decides for the rest
            if adding and not prefix:
                self.body.insert("%d.0" % line, mascot_mod.BOX_OPEN)
            elif not adding and prefix:
                self.body.delete("%d.0" % line, "%d.%d" % (line, len(prefix)))
        self._after_box_change()
        return "break"

    def _maybe_toggle_box(self, event):
        """A click on the box itself ticks it. No edit mode, no caret, no
        chance of typing over the line you meant to check off."""
        if event is None or getattr(event, "widget", None) is not self.body:
            return
        try:
            line, col = (int(part) for part in
                         self.body.index("@%d,%d" % (event.x, event.y)).split("."))
        except (tk.TclError, AttributeError, ValueError):
            return
        text = self.body.get("%d.0" % line, "%d.end" % line)
        prefix, _rest = mascot_mod.strip_box(text)
        if not prefix or col >= len(prefix):
            return
        was_editing = self.editing
        self.body.configure(state="normal")
        self.body.replace("%d.0" % line, "%d.%d" % (line, len(prefix)),
                          mascot_mod.BOX_DONE if prefix == mascot_mod.BOX_OPEN
                          else mascot_mod.BOX_OPEN)
        if not was_editing:
            self.body.configure(state="disabled")
        self._after_box_change()

    def _after_box_change(self):
        # View-mode ticks never reach <<Modified>>, which ignores anything
        # outside edit mode, so the save is asked for here explicitly.
        self._capture()
        self.schedule_save()
        self._schedule_autosize()

    # ----------------------------------------------------------- context menu

    def _build_menu(self):
        """Right-click menu. Everything the toolbar offers, without having to
        enter edit mode first."""
        self.var_color = tk.StringVar(value=self.note["color"])
        self.var_top = tk.BooleanVar(value=self.note["topmost"])
        self.var_mascot = tk.BooleanVar(value=self.mascot_enabled())

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Edit note", command=self._menu_edit)
        menu.add_command(label="Checkbox", command=self.toggle_checkbox,
                         accelerator="Ctrl+Shift+K")
        menu.add_separator()
        for name in store.COLORS:
            menu.add_radiobutton(label=name.capitalize(), value=name,
                                 variable=self.var_color,
                                 command=lambda n=name: self.set_color(n))
        menu.add_separator()
        menu.add_command(label="Unpin", command=self._menu_unpin)
        menu.add_checkbutton(label="Always on top", variable=self.var_top,
                             command=self._menu_topmost)
        menu.add_checkbutton(label="Show mascot", variable=self.var_mascot,
                             command=self._menu_mascot)
        menu.add_command(label="Send him home", command=self._menu_home)
        menu.add_command(label="New note", command=self._menu_new)
        menu.add_separator()
        menu.add_command(label="Move to Trash", command=self.move_to_trash)
        self.menu = menu
        self._unpin_index = menu.index("Unpin")
        self._home_index = menu.index("Send him home")

    def _sync_menu(self):
        """Reflect the note's current state in the menu. Its own method so it
        can be checked without popping a menu up over the screen."""
        self.var_color.set(self.note["color"])
        self.var_top.set(self.note["topmost"])
        self.var_mascot.set(self.mascot_enabled())
        self.menu.entryconfigure(0, label="Done editing" if self.editing else "Edit note")
        pin = self.note.get("pin")
        self.menu.entryconfigure(
            self._unpin_index,
            label="Unpin from %s" % _short(pin["title"]) if pin else "Not pinned",
            state="normal" if pin else "disabled")
        self.menu.entryconfigure(
            self._home_index,
            state="normal" if self.mascot.away else "disabled")

    def _context_menu(self, event):
        self.lift()
        self.app.select(self)
        self._sync_menu()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
        return "break"

    def _menu_edit(self):
        if self.editing:
            self.finish_edit()
        else:
            self.start_edit(on_heading=not self.note["heading"])

    def _menu_unpin(self):
        self.unpin()

    def _menu_topmost(self):
        self.set_topmost(self.var_top.get())
        self.flush()

    def _menu_mascot(self):
        self.app.set_mascot(self.var_mascot.get())

    def _detach_mascot(self, event):
        """Peel him off the note and hand him to whoever is dragging. True if
        he came off, and False if there was no room for him out there.

        He starts exactly where he was standing rather than under the cursor,
        so the hand-off never blinks - and the sheet does not move, because
        the margins he needs are left in place the whole time he is away.
        Reclaiming that space here would reflow the writing under the user's
        hand at the very moment they are using it.
        """
        if len(roamer.crew) >= roamer.MAX_ROAMERS:
            return False
        head = self.mascot.head_at()
        try:
            guy = roamer.Roamer(self.app, self,
                                self.winfo_rootx() + head[0],
                                self.winfo_rooty() + head[1] + roamer.STAND_H)
        except tk.TclError:
            return False                # no chroma key: he stays on the note
        self.mascot.leave()
        self._roamer = guy
        # Taken hold of where he was standing rather than snapped under the
        # pointer. The drag has only just passed the slop, so he barely moves.
        guy.pick_up(event.x_root, event.y_root)
        return True

    def mascot_home(self):
        """He is back, and the note draws him again."""
        self._roamer = None
        self.mascot.come_back()

    def _menu_home(self):
        guy = roamer.for_note(self.note["id"])
        if guy is not None:
            guy.go_home()
        else:
            self.mascot_home()

    def apply_mascot(self):
        """Switch him on or off, or move him to a new pose. The sheet keeps its
        size and its place on the desktop; the window grows or shrinks around
        it to make room wherever he is now holding on."""
        self.mascot.finish_swipe()
        self.mascot.hush()
        self._apply_geometry(self.note["w"], self.note["h"],
                             self.note["x"], self.note["y"])
        self.update_idletasks()
        self._redraw(self.note["w"], self.note["h"])
        self._place(self.note["w"], self.note["h"])

    def _menu_new(self):
        self.app.new_note(self.note["color"])

    # --------------------------------------------------------------- bindings

    def _bind_all(self):
        for widget in (self.canvas, self.head, self.body):
            widget.bind("<Button-3>", self._context_menu, add="+")
            widget.bind("<ButtonPress-1>", self._press_start, add="+")
            widget.bind("<B1-Motion>", self._press_move, add="+")
            widget.bind("<ButtonRelease-1>", self._press_end, add="+")
            widget.bind("<Double-Button-1>", self._double_click, add="+")

        self.head.bind("<Return>", self._heading_return)
        self.head.bind("<Tab>", self._to_body)
        self.body.bind("<Tab>", self._to_ok)
        for widget in (self.head, self.body):
            widget.bind("<<Modified>>", self._on_modified)
            widget.bind("<Control-s>", self._force_save)
            widget.bind("<Control-S>", self._force_save)
            widget.bind("<Control-y>", self._redo)
            widget.bind("<Control-Y>", self._redo)
            widget.bind("<Escape>", self._cancel_edit)
        for key, tag in (("b", "bold"), ("i", "italic"), ("u", "underline")):
            for variant in ("<Control-%s>" % key, "<Control-%s>" % key.upper()):
                self.body.bind(variant, lambda e, t=tag: self.toggle_format(t))
        self.body.bind("<Control-plus>", lambda e: self.bump_font(1))
        self.body.bind("<Control-equal>", lambda e: self.bump_font(1))
        self.body.bind("<Control-minus>", lambda e: self.bump_font(-1))
        self.body.bind("<MouseWheel>", self._wheel)
        for widget in (self.head, self.body):
            widget.bind("<Control-K>", self.toggle_checkbox)
            widget.bind("<Control-Shift-K>", self.toggle_checkbox)
        self.bind("<Escape>", self._cancel_edit)
        self.bind("<FocusOut>", self._focus_out)
        self.canvas.bind("<Motion>", self._hover)
        # The mascot's eyes are event driven wherever the pointer can see
        # them: <Motion> here beats waiting for the next poll.
        for widget in (self.canvas, self.head, self.body):
            widget.bind("<Motion>", self._wake_mascot, add="+")
        self.bind("<Enter>", self._wake_mascot, add="+")

    def _to_body(self, _event=None):
        self.body.focus_set()
        return "break"

    def _to_ok(self, _event=None):
        self.btn_ok.focus_set()
        return "break"

    def _redo(self, event):
        try:
            event.widget.edit_redo()
        except tk.TclError:
            pass                    # nothing to redo
        return "break"

    def _focus_out(self, _event=None):
        """Losing focus is a good moment to write - but only if there is
        anything to write.

        <FocusOut> fires far more often than anyone would guess: borderless
        top-level windows hand focus back and forth between themselves, and
        with a few notes open that was several times a second. Each one used
        to be a full rewrite of notes.json, fsync and all, plus a complete
        rebuild of the overview - about nine per cent of a core, and a disk
        write every second, on a note nobody was touching.
        """
        if self._save_job is None and not self.editing:
            return                  # nothing pending and nothing being typed
        self.flush()

    def _wheel(self, event):
        self.body.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _wake_mascot(self, _event=None):
        tracker = self._tracker()
        if tracker is not None:
            tracker.wake()

    def _hover(self, event):
        if self._on_mascot(event):
            self.canvas.configure(cursor="hand2")   # so the tap is findable
            return
        mode = self._resize_mode(event)
        self.canvas.configure(cursor={"se": "size_nw_se",
                                      "e": "sb_h_double_arrow",
                                      "s": "sb_v_double_arrow"}.get(mode, "arrow"))

    # ------------------------------------------------------- drag and resize

    def _resize_mode(self, event):
        """Which way this press would resize the note, if at all.

        The folded corner is the obvious grab handle, but the right and bottom
        edges work too, so a note can be made wider without also making it
        taller.
        """
        ox, oy, w, h = self.paper_rect()
        x = event.x_root - self.winfo_rootx() - ox
        y = event.y_root - self.winfo_rooty() - oy
        if not (0 <= x <= w and 0 <= y <= h):
            return None
        in_curl = x > w - CURL and y > h - CURL
        right = x > w - RESIZE_EDGE
        bottom = y > h - RESIZE_EDGE
        if in_curl or (right and bottom):
            return "se"
        if right:
            return "e"
        if bottom:
            return "s"
        return None

    def _on_mascot(self, event):
        """Did this press land on the mascot's face?"""
        if not self.mascot_enabled():
            return False
        return self.mascot.hit(event.x_root - self.winfo_rootx(),
                               event.y_root - self.winfo_rooty())

    def _press_start(self, event):
        # Everything here is in sheet coordinates: where the paper is, and how
        # big the paper is, never the window around it.
        ox, oy, pw, ph = self.paper_rect()
        self._press = (event.x_root, event.y_root,
                       self.winfo_x() + ox, self.winfo_y() + oy, pw, ph)
        self._tapped = self._on_mascot(event)
        self._dragging = False
        self._mode = self._resize_mode(event)
        self._resizing = self._mode is not None
        self.lift()
        if self.editing and event.widget in (self.head, self.body) and not self._resizing:
            return None                     # let the caret land where it was clicked
        self.app.select(self)
        return None

    def _press_move(self, event):
        if self._roamer is not None:
            self._roamer.drag_to(event.x_root, event.y_root)
            return "break"
        if self._press is None:
            return None
        ox, oy, wx, wy, ww, wh = self._press
        dx, dy = event.x_root - ox, event.y_root - oy
        if not self._dragging:
            if abs(dx) < DRAG_SLOP and abs(dy) < DRAG_SLOP:
                return None                 # a click, not a drag: leave the note alone
            if self._tapped and self._detach_mascot(event):
                # A drag that began on his face is for him. The note stays
                # exactly where it is - dragging the note is what the rest of
                # the paper, and the strip along the top, are for. If he
                # cannot come off - the crew is full, or there is no chroma
                # key to give him a window - the drag falls through to the
                # note, because a drag that does nothing at all reads as the
                # note being broken rather than as the crew being full.
                return "break"
            on_grip = (event.widget is self.canvas
                       or event.y_root - self.winfo_rooty() - self._margins()[1] < GRIP_H)
            if self.editing and not on_grip and not self._resizing:
                return None                 # dragging inside text selects text
            self._dragging = True
        if self._resizing:
            # A note the user has sized by hand stops sizing itself, and is
            # bounded only by the screen: the auto-size ceiling is for growth
            # the user did not ask for.
            self.note["auto_size"] = False
            w = ww + dx if self._mode in ("se", "e") else ww
            h = wh + dy if self._mode in ("se", "s") else wh
            w = max(MIN_W, min(self.winfo_screenwidth(), w))
            h = max(MIN_H, min(self.winfo_screenheight(), h))
            self._want_size = (w, h)
            self._pump_resize()
        else:
            l, t = self._margins()[:2]
            self._moved_to = (wx + dx, wy + dy)
            self.geometry("+%d+%d" % (self._moved_to[0] - l, self._moved_to[1] - t))
            self._hint_pin()
        return "break"

    # Resizing, at a rate the screen can actually show.
    #
    # A mouse reports at 125 Hz and a window resize is expensive: asking for
    # one per motion event queues up more work than the compositor can do, and
    # the note falls behind the cursor. So the last size asked for always
    # wins, and it is applied at most once a frame - a trailing timer catches
    # the final position when the events stop.

    def _pump_resize(self):
        self._resize_job = None
        if self._want_size is None:
            return
        now = time.monotonic()
        wait = RESIZE_FRAME - (now - self._resized_at)
        if wait > 0.001:
            self._resize_job = self.after(int(wait * 1000) + 1, self._pump_resize)
            return
        w, h = self._want_size
        self._want_size = None
        self._resized_at = now
        self.note["w"], self.note["h"] = w, h
        self._apply_geometry(w, h)
        # Let Tk settle the new size before anything is painted into it.
        # Without this the paper is drawn at the size we just asked for while
        # the widgets are still the old one, so the writing spills over the
        # bottom edge and the scrollbar blinks in and out all the way down.
        self.update_idletasks()
        self._redraw(w, h)
        self._place(w, h)

    def _finish_resize(self):
        """Apply whatever the last motion asked for, now, and stop pumping."""
        self._cancel_after("_resize_job")
        if self._want_size is not None:
            self._resized_at = 0.0
            self._pump_resize()

    def _press_end(self, event=None):
        if self._roamer is not None:
            self._roamer.let_go()       # the crew has him from here
            self._roamer = None
            self._press, self._tapped, self._dragging = None, False, False
            return "break"
        if self._resizing:
            self._finish_resize()
        was_dragging, self._press = self._dragging, None
        tapped, self._tapped = self._tapped, False
        self._dragging = False
        if tapped and not was_dragging:
            # A tap on him is for him. Dragging from him still moves the note.
            self._resizing = False
            self.mascot.react()
            return "break"
        if not was_dragging and not self._resizing:
            self._maybe_toggle_box(event)
        if was_dragging:
            # Read back where we asked the sheet to go: winfo_x/y can still be
            # a frame behind at this point in the event stream.
            l, t = self._margins()[:2]
            self.note["x"], self.note["y"] = self._moved_to or (self.winfo_x() + l,
                                                                self.winfo_y() + t)
            self._moved_to = None
            was_resizing, self._resizing = self._resizing, False
            if not was_resizing:
                self._settle_drop(event)
            self.flush()                    # position and size land on disk at once
            return "break"
        self._resizing = False
        return None

    def _pin_target(self, at=None):
        """The window this note's top edge is lying on, if it is a title bar.

        The note decides this, not the pointer. Testing where the cursor
        happens to be pins to whatever is under your hand - which, when you
        drag a note by its middle, is the application's contents, or a
        different window entirely a hundred pixels lower down. What the user
        lined up is the note's own top strip, so that is what is asked about.

        `at` is the sheet's top-left while a drag is still in flight, because
        the window has been moved but nothing has been stored yet.
        """
        ox, oy, pw, ph = self.paper_rect()
        x0, y0 = at if at is not None else (self.winfo_x() + ox,
                                            self.winfo_y() + oy)
        probe = [(int(x0 + pw * frac), int(y0 + GRIP_H // 2))
                 for frac in (0.5, CLIP_AT, 0.25)]
        try:
            return winkit.title_bar_under(probe)
        except Exception:                   # a shim failing must never eat a drag
            return None

    def _settle_drop(self, event):
        """Where a drag ended decides whether the note clips to something.

        Left with its top strip on another window's title bar, it pins there.
        Left anywhere else, an existing pin comes off - dragging a note away
        from a window is how you say you no longer want it stuck to it.
        """
        # Asked again here, not taken from the drag's last look: that look is
        # throttled, so it can be up to a frame or two out of date, and a note
        # let go the instant it reached the bar would be judged on where it
        # was before it got there. note["x"]/["y"] have just been settled.
        target = self._pin_target((self.note["x"], self.note["y"]))
        self._pin_hint, self._hinted = None, False
        if target is not None:
            self.pin_to(*target)
        elif self.note.get("pin"):
            self.unpin()
        else:
            self._clear_clip()

    def _hint_pin(self):
        """While a drag is in flight, show the clip the moment the note's top
        edge crosses a title bar - snapping on before the button comes up, so
        it is obvious the note is about to attach rather than merely land."""
        now = time.monotonic()
        if now - self._hint_at < PIN_HINT_S:
            return
        self._hint_at = now
        before = self._pin_hint
        self._pin_hint = self._pin_target(self._moved_to)
        self._hinted = True
        if (self._pin_hint is None) != (before is None):
            if self._pin_hint is None:
                self._clear_clip()
            else:
                self._clip_in(0)

    def _clear_clip(self):
        self._cancel_clip()
        try:
            self.canvas.delete("clip")
        except tk.TclError:
            pass

    def _double_click(self, event):
        if self._on_mascot(event):
            return "break"          # poking him twice pokes him twice
        if not self.editing:
            self.start_edit(event.widget is self.head)
            return "break"
        return None

    # ------------------------------------------------------------ edit modes

    def _enter_view(self):
        self.editing = False
        self.head.configure(state="disabled", cursor="arrow")
        self.body.configure(state="disabled", cursor="arrow")
        self._place()

    def start_edit(self, on_heading=True):
        if self.editing:
            return
        self.editing = True
        self._snapshot = (self.head.get("1.0", "end-1c"),
                          self.body.get("1.0", "end-1c"),
                          self._read_marks())
        self.head.configure(state="normal", cursor="xterm")
        self.body.configure(state="normal", cursor="xterm")
        self._autosize()
        target = self.head if on_heading else self.body
        self.focus_force()
        target.focus_set()
        target.mark_set("insert", "end-1c")

    def finish_edit(self, _event=None):
        """OK: keep everything and go back to being a note."""
        if not self.editing:
            return "break"
        self._capture()
        self._enter_view()
        self._autosize()
        self.flush()
        return "break"

    def _cancel_edit(self, _event=None):
        """Esc: put the text back the way it was when editing started."""
        if not self.editing:
            return None
        if self._snapshot:
            heading, body, marks = self._snapshot
            for widget, text in ((self.head, heading), (self.body, body)):
                widget.configure(state="normal")
                widget.delete("1.0", "end")
                widget.insert("1.0", text)
                widget.edit_modified(False)
            self.note["marks"] = marks
            self._restore_marks()
        self._capture()
        self._enter_view()
        self._autosize()
        self.flush()
        return "break"

    def _heading_return(self, _event):
        """Enter confirms the heading and drops into the content."""
        self.body.focus_set()
        self.body.mark_set("insert", "end-1c")
        return "break"

    # ---------------------------------------------------------------- saving

    def _on_modified(self, event):
        widget = event.widget
        if not widget.edit_modified():
            return
        widget.edit_modified(False)
        if not self.editing:
            return
        if self.mascot_enabled():
            self.mascot.perk()      # he notices you have started writing
        self._capture()
        self.schedule_save()
        self._schedule_autosize()

    def _capture(self):
        self.note["heading"] = self.head.get("1.0", "end-1c").replace("\n", " ").strip()
        self.note["body"] = self.body.get("1.0", "end-1c")
        self.note["marks"] = self._read_marks()

    def schedule_save(self):
        """Autosave: write once the typing pauses, not on every keystroke."""
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(SAVE_DELAY, self.flush)

    def flush(self, _event=None):
        if self._save_job is not None:
            self.after_cancel(self._save_job)
            self._save_job = None
        if self.editing:
            self._capture()
        self.app.persist()

    def _force_save(self, _event=None):
        self.flush()
        return "break"

    # --------------------------------------------------------------- actions

    def set_color(self, name):
        """Recolour the note. The mascot wipes the new colour across it.

        The stored colour changes immediately and the animation is only ever
        cosmetic: nothing about saving, the overview, or the next action waits
        for it, so a colour is never lost because a wipe was interrupted.
        """
        if name not in store.COLORS or name == self.note["color"]:
            return "break"
        self.note["color"] = name
        self.flush()
        self.app.refresh_board()
        colors = store.COLORS[name]
        if not (self.mascot_enabled()
                and self.mascot.swipe(colors["paper"], colors["edge"],
                                      colors["ink"], self._apply_color)):
            self._apply_color()
        return "break"

    # ------------------------------------------------------------ pinning
    #
    # Drop a note on another application's title bar and it clips itself
    # there: a paperclip drops onto the top edge, and from then on the note
    # travels with that window and hides when it does.

    def pinned(self):
        return bool(self.note.get("pin")) and self._host is not None

    def pin_to(self, hwnd, title, rect):
        """Clip this note to a window. Remembers where it sits on that window,
        not where it sits on the desktop, so it can be put back either way."""
        x, y = self.note["x"], self.note["y"]
        self.note["pin"] = {"title": title,
                            "dx": int(x - rect[0]), "dy": int(y - rect[1])}
        self._host = hwnd
        self._host_at = (rect[0], rect[1])
        tracker = self._tracker()
        if tracker is not None:
            tracker.follow(self)
        self._settle_pose()
        self.apply_mascot()          # the clip's margin changes the window
        # A clipped note that is not on top is a note you have just watched
        # slide behind the very window you clipped it to. Pinning turns it on
        # and leaves it on: unpinning does not take it away again, because by
        # then it is a setting you have seen and can turn off yourself.
        self.set_topmost(True)
        self._clip_in(0)
        self.flush()
        return True

    def unpin(self, redraw=True):
        """Take the clip off. The note stays exactly where it is on screen."""
        if not self.note.get("pin"):
            return False
        self.note["pin"] = None
        self._host = None
        self._host_at = None
        tracker = self._tracker()
        if tracker is not None:
            tracker.unfollow(self)
        self._cancel_clip()
        self._settle_pose()
        if redraw:
            self.apply_mascot()      # and it gives that margin back again
        self.flush()
        return True

    def _settle_pose(self):
        """A note clipped to a title bar has no top edge to sit on: the bar is
        in the way, and he would be behind it. So he lets go and drops to
        hanging off the bottom instead, and climbs back up when unpinned."""
        natural = mascot_mod.pose_for(self.note["id"])
        wanted = "hang" if (self.note.get("pin") and natural == "top") else natural
        if wanted == self.mascot.pose:
            return
        self.mascot.pose = wanted
        self.apply_mascot()

    def _clip_in(self, step):
        """The paperclip drops onto the edge and settles. Nine frames, once."""
        self._clip_job = None
        if not (self.note.get("pin") or self._pin_hint):
            return
        k = step / float(CLIP_STEPS)
        ease = 1.0 - (1.0 - k) ** 3
        l, t, pw, _ph = self.paper_rect()
        try:
            self.canvas.delete("clip")
            self._draw_clip(l, t, pw, drop=(1.0 - ease) * 34.0,
                            tilt=(1.0 - ease) * 0.9 * (1.0 if step % 2 else -1.0))
        except tk.TclError:
            return
        if step < CLIP_STEPS:
            try:
                self._clip_job = self.after(CLIP_MS, self._clip_in, step + 1)
            except tk.TclError:
                self._clip_job = None

    def _cancel_clip(self):
        if self._clip_job is not None:
            try:
                self.after_cancel(self._clip_job)
            except (tk.TclError, ValueError):
                pass
            self._clip_job = None

    def find_host(self):
        """Pick the pinned window back up, by the title we wrote down.

        Handles do not survive a restart and neither does the app we were
        clipped to, so this is allowed to come back empty - the note simply
        sits where it is until that window turns up again.
        """
        pin = self.note.get("pin")
        if not pin or self._host is not None:
            return False
        found = winkit.find_window(pin["title"])
        if found is None:
            return False
        self._host, rect = found[0], found[2]
        self._host_at = (rect[0], rect[1])
        self.note["x"] = rect[0] + pin["dx"]
        self.note["y"] = rect[1] + pin["dy"]
        self._apply_geometry(self.note["w"], self.note["h"],
                             self.note["x"], self.note["y"])
        return True

    def follow_host(self):
        """One step of keeping up with the window we are clipped to.

        Called from the shared tracker, so this is the whole per-tick cost of
        a pinned note: one GetWindowRect, and a move only if it actually went
        somewhere.
        """
        pin = self.note.get("pin")
        if not pin:
            return False
        if self._press is not None:
            return False           # the user has hold of it; it goes where they say
        if self._host is None:
            return self.find_host()
        if not winkit.window_alive(self._host):
            # The app was closed. Keep the note, drop the clip: a note that
            # vanished with someone else's window would look like data loss.
            self._host = None
            self.unpin()
            self._show_with_host()
            return False
        if not winkit.window_showing(self._host):
            self._hide_with_host()
            return False
        rect = winkit.window_rect(self._host)
        if rect is None:
            return False
        self._show_with_host()
        if (rect[0], rect[1]) == self._host_at:
            return False                # it has not moved: nothing to do
        self._host_at = (rect[0], rect[1])
        self.note["x"] = rect[0] + pin["dx"]
        self.note["y"] = rect[1] + pin["dy"]
        l, t = self._margins()[:2]
        try:
            self.geometry("+%d+%d" % (self.note["x"] - l, self.note["y"] - t))
        except tk.TclError:
            return False
        return True

    def _hide_with_host(self):
        if not self._host_hidden:
            self._host_hidden = True
            try:
                self.withdraw()
            except tk.TclError:
                pass

    def _show_with_host(self):
        if self._host_hidden:
            self._host_hidden = False
            # Forget where the host was, so the next look repositions the note
            # even if the window came back exactly where it went: deiconify
            # does not promise to put an overrideredirect window back.
            self._host_at = None
            try:
                self.deiconify()
            except tk.TclError:
                pass

    def set_topmost(self, on):
        self.note["topmost"] = bool(on)
        try:
            self.attributes("-topmost", bool(on))
        except tk.TclError:
            pass

    def move_to_trash(self):
        self.app.trash_note(self.note["id"])
        return "break"

    def raise_note(self):
        self.deiconify()
        self.lift()
        self.focus_force()
