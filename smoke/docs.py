"""Doc-consistency checks — the Step 85 answer to "every doc rot we found
was one fact stated twice, with one copy updated".

The single-source rule (HANDOFF § The doc system) says a live fact lives in
exactly one doc and everything else points at it. That was a convention you
had to *remember*; these checks make it structural. Text-only — no imports
of app code, so it's the cheapest check in the battery."""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Live docs that must not restate the smoke baseline. WORKLOG.md is exempt:
# its entries quote the count *as of that step* on purpose, and that history
# is correct precisely because it does not track the current number.
_LIVE_DOCS = ("CLAUDE.md", "CONVENTIONS.md", "MERGE_PLAN.md", "README.md",
              "ROADMAP.md")

_BASELINE_ROW = re.compile(r"^\|\s*\*\*Smoke baseline\*\*\s*\|(.*)$", re.M)
_PASS_COUNT = re.compile(r"(\d+)\s*PASS")


def _read(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as f:
        return f.read()


def docs_single_source() -> list[str]:
    """Assert the three facts the docs state in exactly one place each:

      1. HANDOFF.md's Cursor smoke baseline == the number of registered
         checks in ``smoke.CHECKS``. Adding a check without updating the
         Cursor (or vice versa) fails here.
      2. No other live doc restates a smoke count. WORKLOG.md is exempt --
         its per-step counts are frozen history, not the live fact.
      3. No step number has both a WORKLOG ``## Step N`` entry and a
         ROADMAP ``### Step N`` entry -- i.e. nothing that shipped is still
         listed as planned. This is the landing-commit lifecycle from
         HANDOFF § The doc system, machine-checked.

    Reads the docs as text and imports ``CHECKS`` lazily (importing it at
    module scope would be circular -- ``smoke/__init__.py`` imports this
    module before it defines the registry)."""
    from smoke import CHECKS

    errors = []
    handoff = _read("HANDOFF.md")

    row = _BASELINE_ROW.search(handoff)
    if row is None:
        errors.append("HANDOFF.md: no `| **Smoke baseline** |` row found in the Cursor")
    else:
        stated = _PASS_COUNT.search(row.group(1))
        if stated is None:
            errors.append(f"HANDOFF.md: Smoke baseline row states no `N PASS` count: {row.group(1).strip()!r}")
        elif int(stated.group(1)) != len(CHECKS):
            errors.append(
                f"HANDOFF.md Cursor says {stated.group(1)} PASS but smoke.CHECKS "
                f"registers {len(CHECKS)} checks — update the Cursor's Smoke baseline row"
            )

    extra = _PASS_COUNT.findall(handoff)
    if len(extra) > 1:
        errors.append(
            f"HANDOFF.md states a smoke count {len(extra)} times ({', '.join(extra)}) — "
            "the baseline is quoted in the Cursor row and nowhere else"
        )

    for name in _LIVE_DOCS:
        found = _PASS_COUNT.findall(_read(name))
        if found:
            errors.append(
                f"{name} restates the smoke baseline ({', '.join(found)} PASS) — "
                "it lives only in HANDOFF.md's Cursor; point at it instead"
            )

    shipped = set(re.findall(r"^##\s+Step\s+(\d+)", _read("WORKLOG.md"), re.M))
    planned = set(re.findall(r"^###\s+Step\s+(\d+)", _read("ROADMAP.md"), re.M))
    for num in sorted(shipped & planned, key=int):
        errors.append(
            f"Step {num} has a WORKLOG entry (shipped) but is still in ROADMAP as planned — "
            "the landing commit deletes the ROADMAP entry"
        )

    return errors
