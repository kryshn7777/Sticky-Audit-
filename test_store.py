"""Self-check for the persistence layer and the note palette.

Run:  python test_store.py
This is the one runnable check behind the code that can lose user data.
"""

import json
import os
import tempfile

import store


def _contrast(hex_a, hex_b):
    """WCAG 2.1 contrast ratio between two #rrggbb colours."""
    def luminance(value):
        channels = []
        for i in (1, 3, 5):
            c = int(value[i:i + 2], 16) / 255.0
            channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        r, g, b = channels
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    light, dark = sorted((luminance(hex_a), luminance(hex_b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_roundtrip(path):
    s = store.Store(path)
    note = s.add("blue", x=10, y=20)
    s.update(note["id"], heading="Milk", body="two\nlines")
    s.save()

    reloaded = store.Store(path)
    assert len(reloaded.notes) == 1, reloaded.notes
    got = reloaded.notes[0]
    assert got["heading"] == "Milk"
    assert got["body"] == "two\nlines"
    assert got["color"] == "blue"
    assert (got["x"], got["y"]) == (10, 20)
    assert got["id"] == note["id"]


def test_trash_restore_purge(path):
    s = store.Store(path)
    note = s.add()
    s.update(note["id"], heading="oops")

    s.trash_note(note["id"])
    assert s.notes == [] and len(s.trash) == 1
    assert "deleted_at" in s.trash[0], "trashed note must record when it was deleted"

    # Trash survives a restart -- a deleted note is recoverable tomorrow.
    assert len(store.Store(path).trash) == 1

    s.restore(note["id"])
    assert len(s.notes) == 1 and s.trash == []
    assert s.notes[0]["heading"] == "oops", "restore must not lose content"
    assert "deleted_at" not in s.notes[0]

    s.trash_note(note["id"])
    assert s.purge(note["id"]) is True
    assert s.trash == [] and s.purge(note["id"]) is False
    assert store.Store(path).trash == []


def test_atomic_write_leaves_no_temp(path):
    s = store.Store(path)
    s.add()
    s.save()
    assert not os.path.exists(path + ".tmp"), "temp file must be renamed, not left behind"
    with open(path, encoding="utf-8") as fh:
        json.load(fh)  # raises if the document was written torn


def test_corrupt_file_is_quarantined_not_lost(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")
    s = store.Store(path)
    assert s.notes == [], "must start clean rather than crash"
    leftovers = [n for n in os.listdir(os.path.dirname(path)) if ".corrupt-" in n]
    assert leftovers, "unreadable file must be kept aside, never deleted"


def test_unknown_fields_do_not_crash(path):
    """A hand-edited backup file must still load."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"version": 1,
                   "notes": [{"id": "abc", "heading": "kept", "color": "chartreuse",
                              "x": "not-a-number", "mystery": 1}],
                   "trash": ["garbage"]}, fh)
    s = store.Store(path)
    assert len(s.notes) == 1
    assert s.notes[0]["heading"] == "kept"
    assert s.notes[0]["color"] == store.DEFAULT_COLOR, "bad colour falls back"
    assert isinstance(s.notes[0]["x"], int), "bad coordinate falls back"
    assert s.trash == [], "non-dict trash entries are dropped"


def test_history_keeps_the_last_few(path):
    """Crash-proof is not regret-proof: what you overwrote is still there."""
    s = store.Store(path)
    note = s.add("yellow")

    def age_it():
        """Push the newest version back past the gap, so the next save keeps
        it rather than rewriting it. Standing in for the two minutes."""
        s.notes[0]["history"][-1]["t"] -= store.HISTORY_GAP + 1.0

    for text in ("one", "two", "three"):
        s.update(note["id"], body=text)
        s.save()
    assert [v["body"] for v in s.notes[0]["history"]] == ["three"], (
        "saves inside the gap rewrite the newest version rather than piling up",
        [v["body"] for v in s.notes[0]["history"]])
    assert store.remember(s.notes[0]) is False, \
        "a note that has not changed adds nothing"

    for text in ("four", "five"):
        age_it()
        s.update(note["id"], body=text)
        s.save()
    assert [v["body"] for v in s.notes[0]["history"]] == \
        ["three", "four", "five"], [v["body"] for v in s.notes[0]["history"]]

    for i in range(store.HISTORY_MAX + 4):
        age_it()
        s.update(note["id"], body="v%d" % i)
        s.save()
    assert len(s.notes[0]["history"]) == store.HISTORY_MAX, \
        "the history is capped, or a note grows for ever"
    assert s.notes[0]["history"][-1]["body"] == "v%d" % (store.HISTORY_MAX + 3)

    reloaded = store.Store(path)
    assert [v["body"] for v in reloaded.notes[0]["history"]] == \
        [v["body"] for v in s.notes[0]["history"]], "and it survives a restart"

    # A hand-edited file must cost the versions, never the note.
    s.notes[0]["history"].append("not a version at all")
    s.save()
    back = store.Store(path)
    assert all(isinstance(v, dict) for v in back.notes[0]["history"]), \
        "rubbish in the history is dropped"
    assert back.notes[0]["body"] == s.notes[0]["body"], "and the note is fine"


def test_old_folder_keeps_its_notes(_path):
    """It was StickyNote before it was Sticky.

    A machine that has the old folder goes on reading and writing it; a
    machine with neither gets the new one. Never both, and nothing is moved.
    """
    import tempfile as _tempfile
    was = os.environ.get("APPDATA")
    with _tempfile.TemporaryDirectory() as fake:
        os.environ["APPDATA"] = fake
        try:
            older = os.path.join(fake, store.LEGACY_NAME)
            os.makedirs(older)
            assert store.data_dir() == older, (
                "notes written under the old name stay where they are")
            assert not os.path.isdir(os.path.join(fake, store.APP_NAME)), (
                "and nothing is created beside them")
        finally:
            if was is None:
                del os.environ["APPDATA"]
            else:
                os.environ["APPDATA"] = was

    with _tempfile.TemporaryDirectory() as fresh:
        os.environ["APPDATA"] = fresh
        try:
            assert store.data_dir() == os.path.join(fresh, store.APP_NAME), (
                "a machine with neither folder gets the new one")
        finally:
            if was is None:
                del os.environ["APPDATA"]
            else:
                os.environ["APPDATA"] = was


def test_palette_is_readable():
    for name, c in store.COLORS.items():
        ratio = _contrast(c["ink"], c["paper"])
        assert ratio >= 4.5, "%s ink on paper is %.2f:1, below WCAG AA 4.5:1" % (name, ratio)


def main():
    cases = [test_roundtrip, test_trash_restore_purge, test_atomic_write_leaves_no_temp,
             test_corrupt_file_is_quarantined_not_lost, test_unknown_fields_do_not_crash,
             test_history_keeps_the_last_few, test_old_folder_keeps_its_notes]
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            case(os.path.join(tmp, "notes.json"))
        print("ok  %s" % case.__name__)
    test_palette_is_readable()
    print("ok  test_palette_is_readable")
    for name, c in store.COLORS.items():
        print("    %-6s ink/paper contrast %.2f:1" % (name, _contrast(c["ink"], c["paper"])))
    print("\nall checks passed")


if __name__ == "__main__":
    main()
