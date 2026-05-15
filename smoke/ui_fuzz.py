"""Step 38: UI crash fuzzer. Random-walks through enabled UI actions and
catches any uncaught exception as a failure, with the seed printed so the
sequence can be replayed.

Companion to Step 37: where 37 asserts specific roundtrips, this is the
net for the long-tail None.attr / IndexError / unhandled-edge-case bugs
that nobody is currently looking for. Reproduce a found crash with
``crash_fuzz(seed=<seed>, iterations=<step+1>)``.

Blocking UI (QMessageBox / QFileDialog / QDialog.exec / os.startfile) is
stubbed for the duration of the run so a random button click never hangs
offscreen; crashes inside the click handlers still surface. The stubs
themselves consume the walk RNG for Yes/No decisions, so a Save → Yes vs
Save → No branch is part of the reproducible sequence.

**Slot-raised exceptions.** PySide6 wraps slot execution: a slot that
raises has its exception routed through sys.excepthook and then
SWALLOWED — click() returns normally. The walk hooks sys.excepthook so
the failure list actually reflects what crashed.

**Wired into the smoke baseline as of Step 41.** Default iterations
tuned to land in the 10-20s budget on a Windows dev box. Replay a found
crash with explicit ``iterations=<reported step + 1>``.
"""
import os
import random
import string
import sys
import tempfile
import time
import traceback


def _silenceBlockingUI(walk_rng):
    """Stub QMessageBox / QFileDialog / QDialog.exec / os.startfile so any
    button click returns quickly even when it would normally spawn a modal.
    QMessageBox.question is randomized off ``walk_rng`` so we explore both
    confirm / cancel branches. Returns a restore callable."""
    from PySide6.QtWidgets import QDialog, QMessageBox, QFileDialog

    orig = {
        "mb_info": QMessageBox.information,
        "mb_crit": QMessageBox.critical,
        "mb_warn": QMessageBox.warning,
        "mb_ques": QMessageBox.question,
        "fd_open": QFileDialog.getOpenFileName,
        "fd_save": QFileDialog.getSaveFileName,
        "fd_dir": QFileDialog.getExistingDirectory,
        "dialog_exec": QDialog.exec,
        "os_startfile": getattr(os, "startfile", None),
    }

    Yes = QMessageBox.StandardButton.Yes
    No = QMessageBox.StandardButton.No
    Ok = QMessageBox.StandardButton.Ok
    Cancel = QMessageBox.StandardButton.Cancel

    def question_stub(*_a, **_kw):
        return Yes if walk_rng.random() < 0.5 else No

    QMessageBox.information = staticmethod(lambda *a, **kw: Ok)  # type: ignore[assignment]
    QMessageBox.critical = staticmethod(lambda *a, **kw: Ok)  # type: ignore[assignment]
    QMessageBox.warning = staticmethod(lambda *a, **kw: Cancel)  # type: ignore[assignment]
    QMessageBox.question = staticmethod(question_stub)  # type: ignore[assignment]
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **kw: ("", ""))  # type: ignore[assignment]
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **kw: ("", ""))  # type: ignore[assignment]
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **kw: "")  # type: ignore[assignment]
    QDialog.exec = lambda self: QDialog.DialogCode.Rejected  # type: ignore[assignment]
    if hasattr(os, "startfile"):
        os.startfile = lambda *a, **kw: None  # type: ignore[assignment]

    def restore():
        QMessageBox.information = orig["mb_info"]  # type: ignore[assignment]
        QMessageBox.critical = orig["mb_crit"]  # type: ignore[assignment]
        QMessageBox.warning = orig["mb_warn"]  # type: ignore[assignment]
        QMessageBox.question = orig["mb_ques"]  # type: ignore[assignment]
        QFileDialog.getOpenFileName = orig["fd_open"]  # type: ignore[assignment]
        QFileDialog.getSaveFileName = orig["fd_save"]  # type: ignore[assignment]
        QFileDialog.getExistingDirectory = orig["fd_dir"]  # type: ignore[assignment]
        QDialog.exec = orig["dialog_exec"]  # type: ignore[assignment]
        if orig["os_startfile"] is not None:
            os.startfile = orig["os_startfile"]  # type: ignore[assignment]

    return restore


def _seedFuzzData(w, rng):
    """Populate ``w.db`` using fuzz_db's tiny preset driven by ``rng``.
    Same pattern as Step 35's ``product_employee_reports`` and Step 37's
    ``_seedTinyFuzzDB`` — no file I/O, populated directly against the
    in-memory ``MainWindow().db``. Caller is responsible for refreshing
    tabs afterward."""
    import datetime
    import fuzz_db as F

    cfg = F.SCALES["tiny"]
    today = datetime.date.today()
    db = w.db
    materialNames = F.populateMaterials(db, rng, cfg["materials"])
    mixtureNames = F.populateMixtures(db, rng, cfg["mixtures"], materialNames)
    F.populatePackaging(db, rng, cfg["packaging"])
    packagingByKind = {k: [] for k in F.PACKAGING_POOL}
    for name in db.packaging:
        packagingByKind[db.packaging[name].kind].append(name)
    F.populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
    idNums = F.populateEmployees(db, rng, cfg["employees"], today)
    F.populateReviews(db, rng, idNums, today)
    F.populateTraining(db, rng, idNums, today)
    F.populateAttendance(db, rng, idNums, today)
    F.populatePTO(db, rng, idNums, today)
    F.populateNotes(db, rng, idNums, today)
    F.populateHolidays(db, rng, today)


# Action kind tags. Tuples are (kind, target, label) so the dispatcher can
# stay short and the label string is what shows up in a crash report.
_BUTTON, _COMBO, _TAB, _LINE, _SPIN, _DSPIN, _CHECK = (
    "button", "combo", "tab", "line", "spin", "dspin", "check",
)


def _enumerateActions(window):
    """Walk ``window``'s child widget tree and bucket enabled controls
    into legal random-walk actions. Re-enumerated every step because a
    click or tab switch can enable / disable / create widgets.

    Filters only on ``isEnabled()``, not ``isVisible()`` — offscreen
    widgets on non-current tabs still have working signal handlers, and
    exercising them is the whole point.
    """
    from PySide6.QtWidgets import (
        QPushButton, QComboBox, QTabWidget, QLineEdit,
        QSpinBox, QDoubleSpinBox, QCheckBox,
    )
    actions = []

    for btn in window.findChildren(QPushButton):
        if btn.isEnabled():
            actions.append((_BUTTON, btn,
                            f"btn:{btn.text() or btn.objectName() or '?'}"))
    for cb in window.findChildren(QComboBox):
        if cb.isEnabled() and cb.count() > 0:
            actions.append((_COMBO, cb,
                            f"combo:{cb.objectName() or '?'}"))
    for tw in window.findChildren(QTabWidget):
        if tw.isEnabled() and tw.count() > 1:
            actions.append((_TAB, tw,
                            f"tab:{tw.objectName() or '?'}"))
    for le in window.findChildren(QLineEdit):
        if le.isEnabled() and not le.isReadOnly():
            actions.append((_LINE, le,
                            f"line:{le.objectName() or '?'}"))
    for sb in window.findChildren(QSpinBox):
        if sb.isEnabled() and not sb.isReadOnly():
            actions.append((_SPIN, sb,
                            f"spin:{sb.objectName() or '?'}"))
    for sb in window.findChildren(QDoubleSpinBox):
        if sb.isEnabled() and not sb.isReadOnly():
            actions.append((_DSPIN, sb,
                            f"dspin:{sb.objectName() or '?'}"))
    for chk in window.findChildren(QCheckBox):
        if chk.isEnabled():
            actions.append((_CHECK, chk,
                            f"chk:{chk.text() or chk.objectName() or '?'}"))

    return actions


_TEXT_ALPHABET = string.ascii_letters + string.digits + " ./-_"


def _randomText(rng):
    n = rng.choices([0, 4, 12, 30, 100], weights=[1, 3, 3, 2, 1])[0]
    return "".join(rng.choices(_TEXT_ALPHABET, k=n))


def _spinValue(sb, rng):
    """Pick a value for an int spinbox, mixing edge values and random.
    Range-bounded values use rng deterministically."""
    lo, hi = sb.minimum(), sb.maximum()
    if hi <= lo:
        return lo
    edges = [v for v in (lo, hi, 0, sb.value() + 1, sb.value() - 1) if lo <= v <= hi]
    if edges and rng.random() < 0.5:
        return rng.choice(edges)
    return rng.randint(lo, hi)


def _dspinValue(sb, rng):
    lo, hi = sb.minimum(), sb.maximum()
    if hi <= lo:
        return lo
    if rng.random() < 0.3:
        edges = [v for v in (lo, hi, 0.0) if lo <= v <= hi]
        if edges:
            return rng.choice(edges)
    return rng.uniform(lo, hi)


def _executeAction(kind, target, rng):
    if kind == _BUTTON:
        target.click()
    elif kind == _COMBO:
        target.setCurrentIndex(rng.randrange(target.count()))
    elif kind == _TAB:
        target.setCurrentIndex(rng.randrange(target.count()))
    elif kind == _LINE:
        target.setText(_randomText(rng))
    elif kind == _SPIN:
        target.setValue(_spinValue(target, rng))
    elif kind == _DSPIN:
        target.setValue(_dspinValue(target, rng))
    elif kind == _CHECK:
        target.setChecked(not target.isChecked())


# Default tuned for ~10-20s offscreen on a Windows dev box (20-run sweep at
# 1000 iter post-Steps-39/40/41 saw 7.03-12.70s, median ~11s, 0/20 failures).
# Replay uses an explicit ``iterations=`` matching the reported crash step + 1.
DEFAULT_ITERATIONS = 1000


def crash_fuzz(seed=None, iterations=DEFAULT_ITERATIONS) -> list[str]:
    """Step 38: random-walk the MainWindow widget tree, return any uncaught
    exception as a failure with the seed for replay.

    On crash, returns one-element list ``["seed=X step=N: <label> crashed
    with <ExcName>: <msg>\\n<traceback>"]``. Reproduce with
    ``crash_fuzz(seed=X, iterations=N+1)``.

    ``seed=None`` rolls a fresh ``time.time()``-based seed each run and
    reports it on failure for replay.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow

    if seed is None:
        seed = int(time.time() * 1000) & 0xFFFFFFFF
    walk_rng = random.Random(seed)
    fixture_rng = random.Random(seed ^ 0xCAFEBEEF)

    QApplication.instance() or QApplication(sys.argv)

    # PySide6 wraps slot execution: a slot that raises has its exception printed
    # via sys.excepthook and then SWALLOWED — click() returns normally. So a
    # plain try/except around _executeAction sees nothing. Capture via a custom
    # excepthook that records (type, value, tb) on each invocation; we check it
    # after every action.
    captured: list = []
    orig_hook = sys.excepthook
    def _capture_hook(t, v, tb):
        captured.append((t, v, tb))
    sys.excepthook = _capture_hook

    restore = _silenceBlockingUI(walk_rng)
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            return [f"seed={seed} setup: setFile returned False on tmp DB"]
        _seedFuzzData(w, fixture_rng)
        w._refreshAllTabs()

        for i in range(iterations):
            actions = _enumerateActions(w)
            if not actions:
                return [f"seed={seed} step={i}: no enabled actions enumerated"]
            kind, target, label = walk_rng.choice(actions)
            captured.clear()
            try:
                _executeAction(kind, target, walk_rng)
            except Exception as e:
                tb = traceback.format_exc()
                return [f"seed={seed} step={i}: {label} crashed with "
                        f"{type(e).__name__}: {e}\n{tb}"]
            if captured:
                t, v, tb = captured[0]
                tb_str = "".join(traceback.format_exception(t, v, tb))
                return [f"seed={seed} step={i}: {label} crashed with "
                        f"{t.__name__}: {v}\n{tb_str}"]
        return []
    finally:
        # No w.close(): closeEvent calls QMessageBox.warning which our stub
        # vetoes with Cancel, but offscreen w.close() never returns cleanly
        # even when the close is rejected. Match the other smoke checks that
        # let the MainWindow leak until process exit.
        sys.excepthook = orig_hook
        restore()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
