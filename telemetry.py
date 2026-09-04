"""Passive usage telemetry — T1.7 of the web transition (mercy-web TRANSITION_PLAN §16).

Feeds the Phase 4 screen triage: with no on-site observation possible, weeks
of measured tab usage stand in for watching the office work. Counts SCREENS,
not work — one JSONL line per tab activation plus a launch marker per
session; no record data, no field contents, no per-employee anything (the
guardrail promised to the team in transition decision 5).

Storage: ``%LOCALAPPDATA%/MERCY/telemetry/usage-<hostname>.jsonl``, one file
per machine, append-only. ``MERCY_TELEMETRY_DIR`` overrides the directory
(smoke uses this to keep test events out of real logs). Collection is
manual: the office sends the files when triage time comes.

Failure posture — the one sanctioned inversion of the loud-failure mandate:
telemetry must never crash, block, or surface an error to the user. Any
problem silently drops the event; instrumentation that can break the
instrument is worse than none. Only ``instrument()`` and ``logEvent()`` are
called from app code, and neither can raise.
"""
import json
import os
import socket
import time
from functools import partial

from PySide6.QtWidgets import QTabWidget, QWidget

from version import VERSION

try:
    _HOST = socket.gethostname() or "unknown"
except Exception:
    _HOST = "unknown"


def _logPath() -> str:
    base = os.environ.get("MERCY_TELEMETRY_DIR")
    if not base:
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        base = os.path.join(local, "MERCY", "telemetry")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"usage-{_HOST}.jsonl")


def logEvent(event: str, screen: str = "") -> None:
    """Append one event line to the machine's usage log. Never raises."""
    try:
        line = json.dumps({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "host": _HOST,
            "ver": VERSION,
            "event": event,
            "screen": screen,
        })
        with open(_logPath(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # deliberate: drop the event, never the app


def _tabPath(tw: QTabWidget, index: int) -> str:
    """Full breadcrumb for a tab, e.g. ``Products/Mixtures``.

    Climbs ancestor QTabWidgets: at each one, the widget we climbed from is
    its page, so ``indexOf`` recovers the enclosing tab's label. A
    QTabWidget buried deeper inside a page (indexOf == -1) contributes no
    label but the climb continues.
    """
    parts = [tw.tabText(index)]
    child: QWidget = tw
    parent = tw.parentWidget()
    while parent is not None:
        if isinstance(parent, QTabWidget):
            i = parent.indexOf(child)
            if i >= 0:
                parts.append(parent.tabText(i))
            child = parent
        parent = parent.parentWidget()
    return "/".join(reversed(parts))


def _onTabChanged(tw: QTabWidget, index: int) -> None:
    try:
        if index >= 0:
            logEvent("tab", _tabPath(tw, index))
    except Exception:
        pass


def instrument(window: QWidget) -> None:
    """Wire tab-activation logging onto every QTabWidget under *window*.

    Called once from main.py after MainWindow construction — smoke's
    directly-constructed windows are NOT instrumented unless a check opts
    in, so offscreen test runs never pollute real logs. Never raises.
    """
    try:
        logEvent("launch")
        for tw in window.findChildren(QTabWidget):
            tw.currentChanged.connect(partial(_onTabChanged, tw))
    except Exception:
        pass
