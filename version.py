"""Derive the app version from git at import time, with a build-time fallback.

Strategy:
  1. Running from source: shell out to ``git describe --tags --always --dirty``.
     This is the authoritative answer on dev machines — no file to keep in sync.
  2. Running frozen by PyInstaller: .git isn't bundled, so fall back to
     ``_version.py``, which ``main.spec`` writes at build time from the same
     ``git describe`` call. Frozen exes carry a fixed version string.
  3. Neither available (git missing in dev with no prior build): ``"dev-unknown"``.

Tags with a leading ``v`` (e.g. ``v1.0rc3``) get that prefix stripped so the
displayed VERSION stays consistent with the pre-automation string format.
"""
import os
import subprocess
import sys


def _gitDescribe() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=here,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    if not tag:
        return None
    return tag[1:] if tag.startswith("v") else tag


def getVersion() -> str:
    # PyInstaller sets sys.frozen; the source tree (and .git) isn't present
    # inside the frozen exe, so skip the git call entirely.
    if not getattr(sys, "frozen", False):
        tag = _gitDescribe()
        if tag:
            return tag
    try:
        from _version import VERSION  # type: ignore[import-not-found]
        return VERSION
    except ImportError:
        return "dev-unknown"


VERSION = getVersion()
