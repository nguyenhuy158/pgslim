"""The optional 'textual' dependency must never load on the plain CLI path."""

import sys

import pytest


def test_import_main_does_not_import_textual():
    for mod in ("textual", "pgslim.tui"):
        sys.modules.pop(mod, None)

    import pgslim.main  # noqa: F401

    assert "textual" not in sys.modules
    assert "pgslim.tui" not in sys.modules


def test_ui_without_textual_prints_install_hint_and_exits(monkeypatch, capsys, tmp_path):
    """--ui must fail gracefully (install hint + exit(1)) when textual is unavailable,
    instead of crashing with a raw ImportError traceback.

    Other test modules (test_tui.py) import textual at collection time, so its
    submodules are already cached in sys.modules by the time this runs. Scrub every
    cached `textual*`/`pgslim.tui` entry first, then poison "textual" with the standard
    None-sentinel, so the re-import below genuinely fails instead of hitting the cache.
    """
    for name in list(sys.modules):
        if name == "textual" or name.startswith("textual.") or name == "pgslim.tui":
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "textual", None)

    import pgslim.main as main

    dump = tmp_path / "dump.sql"
    dump.write_text("-- empty dump\n")

    with pytest.raises(SystemExit) as exc_info:
        main.run_ui_mode(str(dump), str(tmp_path / "out.sql"))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "textual" in captured.err
    assert "pgslim[tui]" in captured.err
