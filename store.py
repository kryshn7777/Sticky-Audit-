"""Crash-safe local persistence for Sticky Notes.

One JSON document under %APPDATA%/StickyNote/notes.json. Every write is
atomic (temp file -> fsync -> os.replace), so a power cut or forced shutdown
can never leave a half-written file behind: the reader either sees the old
document or the new one, never a torn one.

No network, no database, no dependencies.
"""

import json
import os
import time
import uuid

APP_NAME = "StickyNote"
SCHEMA_VERSION = 1

# Paper colours. `ink` is checked against `paper` for >= 4.5:1 contrast by
# test_store.py, so every note stays legible regardless of the colour chosen.
COLORS = {
    "yellow": {"paper": "#FDF08B", "edge": "#F0DE64", "ink": "#3B3616"},
    "green":  {"paper": "#C7F0BD", "edge": "#A6DE99", "ink": "#1F3A18"},
    "pink":   {"paper": "#F5C4D4", "edge": "#E5A2B9", "ink": "#451E2C"},
    "purple": {"paper": "#D0BCF3", "edge": "#B49FE0", "ink": "#2E1F4D"},
    "blue":   {"paper": "#B4E5FA", "edge": "#8ACDEC", "ink": "#14323F"},
}
DEFAULT_COLOR = "yellow"

DEFAULT_SETTINGS = {
    "always_on_top": True,
    "run_at_startup": False,
    "mascot": True,          # the stickman behind the sheet
    "next_offset": 0,        # cascades new notes so they don't stack exactly
}


def shade(hex_color, factor):
    """Darken (<1) or lighten (>1) a #rrggbb colour.

    Lives here because this module owns the palette; note.py and mascot.py
    both derive their tones from it.
    """
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    clamp = lambda v: max(0, min(255, int(v * factor)))
    return "#%02X%02X%02X" % (clamp(r), clamp(g), clamp(b))


def blend(a, b, u):
    """Part of the way from one #rrggbb colour to another.

    Beside shade() for the same reason: the palette lives here, and the colour
    change animates the mascot from his old paper to his new one while the
    sheet behind him is doing exactly the same thing.
    """
    if u <= 0.0:
        return a
    if u >= 1.0:
        return b
    out = []
    for i in (1, 3, 5):
        p, q = int(a[i:i + 2], 16), int(b[i:i + 2], 16)
        out.append(max(0, min(255, int(round(p + (q - p) * u)))))
    return "#%02X%02X%02X" % tuple(out)


def data_dir():
    """Windows user-data location, created on demand."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def default_path():
    return os.path.join(data_dir(), "notes.json")


def _coerce_pin(raw):
    """A pin from disk, or None. Anything malformed is simply not a pin."""
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "")
    if not title:
        return None
    try:
        return {"title": title, "dx": int(raw["dx"]), "dy": int(raw["dy"])}
    except (KeyError, TypeError, ValueError):
        return None


def new_note(color=DEFAULT_COLOR, x=140, y=140):
    now = time.time()
    return {
        "id": uuid.uuid4().hex,
        "color": color if color in COLORS else DEFAULT_COLOR,
        "x": int(x), "y": int(y),
        "w": 292, "h": 272,
        "heading": "",
        "body": "",
        "topmost": True,
        "auto_size": True,
        "font_size": 12,
        "marks": [],
        # Clipped to another application's window, or None. The handle itself
        # does not survive a restart, so what is stored is the title on the
        # bar plus the offset from that window's top-left corner.
        "pin": None,
        "created": now,
        "updated": now,
    }


class Store:
    """The whole document, held in memory, flushed atomically on demand."""

    def __init__(self, path=None):
        self.path = path or default_path()
        self.notes = []
        self.trash = []
        self.settings = dict(DEFAULT_SETTINGS)
        self.load()

    # ---------------------------------------------------------------- io

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            return
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # Never silently discard user data: park the unreadable file
            # beside the new one so it can be recovered by hand.
            self._quarantine()
            return
        if not isinstance(doc, dict):
            self._quarantine()
            return
        self.notes = [self._coerce(n) for n in doc.get("notes", []) if isinstance(n, dict)]
        self.trash = [self._coerce(n) for n in doc.get("trash", []) if isinstance(n, dict)]
        saved = doc.get("settings")
        if isinstance(saved, dict):
            self.settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})

    def _quarantine(self):
        try:
            os.replace(self.path, "%s.corrupt-%d" % (self.path, int(time.time())))
        except OSError:
            pass

    def save(self):
        """Atomic write. Safe to call as often as you like."""
        doc = {
            "version": SCHEMA_VERSION,
            "notes": self.notes,
            "trash": self.trash,
            "settings": self.settings,
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())      # data is on the platter before the swap
        os.replace(tmp, self.path)     # atomic on NTFS

    @staticmethod
    def _coerce(raw):
        """Fill in anything a hand-edited or older file is missing."""
        note = new_note()
        note.update({k: v for k, v in raw.items() if k in note})
        note["id"] = str(raw.get("id") or note["id"])
        if note["color"] not in COLORS:
            note["color"] = DEFAULT_COLOR
        for key in ("x", "y", "w", "h"):
            try:
                note[key] = int(note[key])
            except (TypeError, ValueError):
                note[key] = new_note()[key]
        note["pin"] = _coerce_pin(raw.get("pin"))
        note["heading"] = str(note["heading"])
        note["body"] = str(note["body"])
        note["topmost"] = bool(note["topmost"])
        note["auto_size"] = bool(note["auto_size"])
        try:
            note["font_size"] = max(8, min(24, int(note["font_size"])))
        except (TypeError, ValueError):
            note["font_size"] = 12
        # [tag, start, end] triples for bold / italic / underline runs
        note["marks"] = [list(m)[:3] for m in note["marks"]
                         if isinstance(m, (list, tuple)) and len(m) >= 3
                         and m[0] in ("bold", "italic", "underline")]
        if "deleted_at" in raw:
            note["deleted_at"] = raw["deleted_at"]
        return note

    # ------------------------------------------------------------ lookup

    def get(self, note_id):
        for note in self.notes:
            if note["id"] == note_id:
                return note
        return None

    # ----------------------------------------------------------- mutate

    def add(self, color=DEFAULT_COLOR, x=None, y=None):
        step = self.settings["next_offset"]
        note = new_note(color,
                        x=140 + step * 26 if x is None else x,
                        y=140 + step * 26 if y is None else y)
        self.settings["next_offset"] = (step + 1) % 8
        self.notes.append(note)
        self.save()
        return note

    def update(self, note_id, **fields):
        note = self.get(note_id)
        if note is None:
            return None
        changed = False
        for key, value in fields.items():
            if key in note and note[key] != value:
                note[key] = value
                changed = True
        if changed:
            note["updated"] = time.time()
        return note

    def trash_note(self, note_id):
        """Reversible delete. Returns the note, or None if it was not there."""
        note = self.get(note_id)
        if note is None:
            return None
        self.notes.remove(note)
        note["deleted_at"] = time.time()
        self.trash.insert(0, note)
        self.save()
        return note

    def restore(self, note_id):
        for note in self.trash:
            if note["id"] == note_id:
                self.trash.remove(note)
                note.pop("deleted_at", None)
                note["updated"] = time.time()
                self.notes.append(note)
                self.save()
                return note
        return None

    def purge(self, note_id):
        """Permanent. There is no recovery after this."""
        for note in self.trash:
            if note["id"] == note_id:
                self.trash.remove(note)
                self.save()
                return True
        return False

    def empty_trash(self):
        count = len(self.trash)
        self.trash = []
        self.save()
        return count
