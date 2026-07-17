# ROADMAP — planned work

Forward-looking only; **this file shrinks as work lands.** Each planned step carries its scoping essay here; when it ships, the essay is replaced by a WORKLOG as-built entry and deleted from this file (the essay's still-useful parts move with it). Live status: the 🧭 Cursor in [HANDOFF.md](HANDOFF.md). One step = one commit.

## The overhaul block — Steps 85–87 (planned 2026-07-16)

Origin: Matthew, post-release — *"the codebase has a lot of weird edge cases that really need to be cleaned up."* Do these as **separate steps, not a cleanup mega-commit** (the reasoning that split option D out of Step 81), smoke green at every step. Step 84 (the doc split) was the block's first member and has landed.

### Step 85 — machine-enforce the single-source facts

Every doc rot found on 2026-07-16 was *one fact stated twice, one copy updated* — including the fix itself, which shipped `71` in one place and `72` in another before a second cold read caught it. A smoke check asserting **"the smoke-baseline count in HANDOFF.md's Cursor == the number of registered checks"** makes the single-source convention structural instead of remembered. Extends naturally (e.g. no ROADMAP entry for a step the Cursor says landed). Cheap; the same move as Step 81 itself.

### Step 86 — make illegal record states unrepresentable

*The* root of the "weird edge cases". `Material("Clay")` leaves `Plus50 = None` and the table formatter crashes; `Mixture` needs a `db` back-ref that **only** `addMixture()` sets, so `getCost()` raises on a raw dict insert. Every consumer must defend, the defenses are inconsistent, and this single root produced **three** separate incidents on 2026-07-16 alone (the smoke-fixture bug, a probe crash, and the whole `addX()`-vs-dict-insert convention). Fix direction: required constructor args and one validating way in. Highest leverage of the cleanup.

### Step 87 — mutation-path + boilerplate sweep

Absorbs the former Step 83 `EditWindow` base class, **rescoped to "every mutation path", not `*EditWindow`** — the Step 81 follow-up proved the naming convention is *not* the set (`PartsMarginsWindow` mutates `part.price` outside it). Folds in two smaller chores found the same day: name the anonymous widget fields (`mainLayout[2][1]` — brittle; broke two probes), and collapse the refresh method-name zoo (`refreshTable`/`refresh`/`refreshTab`/`refreshPicker`/…), the only reason `_refreshAllTabs` needs an adapter.

The `EditWindow` shape (from the Step 81 split-out, was §13.53): a thin base owning the `__init__` preamble (`super().__init__(mainApp, Qt.WindowType.Window)` / `WA_DeleteOnClose` / `self.mainApp`) and a `commit(isNew)` that calls the subclass's `readData(isNew)` and on success does `refreshAllViews()` + success message + `close()`; each window drops its hand-written pair (~140 lines of duplicated boilerplate across 20 windows). Known outliers to handle individually: [holidays_tab.py](holidays_tab.py) (no-arg `readData` on a `selectButton`) and [production_tab.py](production_tab.py) (`if self.readData(True):` with its own message + the separate `ProductionBatchDialog._save()` path). **Honest limits, re-read before starting:** a subclass that skips `super().__init__` or wires a button straight to `readData` is silently outside the mechanism, and Step 81 already made the forgotten-call failure *loud* — so the real payoff is boilerplate deletion, not safety. Weigh against a 20-window × (update + create) manual sweep; smoke can't reach the message-box commit gate.

## Unnumbered

- **A `/handoff` skill** — codify the cold-read audit that worked on 2026-07-16: spawn a subagent that follows CLAUDE.md's onboarding *cold* and adversarially audits docs against code. It found a shipped inventory bug and four rebuild traps in one pass. Should be a command, not an improvisation.

## Blocked on real data / field feedback (no code until unblocked)

- **Validate the greedy scheduler against real order data.** The greedy EDF core is explicitly *provisional* (algorithm addendum §10). Real orders + presses now exist (69 orders / 5 presses in the current real DB) and Matthew has eyeballed a real-order schedule, but a genuine verdict still needs: (1) real die placement (`Press.currentPart` is unset on every real press — the encouraging 2026-07-16 look ran on a *manually entered, team-sanity-checked* seed, not floor state); (2) a real `dieChangeHours` (below); (3) **the team deploying a schedule**, so there's observed-vs-predicted to compare. Until (3), any "validation" is a plausibility eyeball. Swapping the allocator happens behind the unchanged `schedule(db, today, config)` seam.
- **Step 80's floor gate (unmet).** Generate a schedule on the real DB with real `currentPart` values and eyeball that dies stop hopping — the exact symptom that motivated the die-tracking work. Step 80's "landed" = code + synthetic-seed drills only.
- **⏸ `dieChangeHours` (Matthew, 2026-07-16):** *"I'll set a change cost once I get some proper feedback from the team."* **Do not invent a value.** One-line `ScheduleConfig` change when the number arrives: a literal (e.g. 10 min = `10/60`) or the reserved `empiricalDieChangeHours(db, today)` helper (avg Tool Change record hours, needs ≥3 in the trailing window — reserved, not built). Until then the scheduler runs at 0.0 = pure hysteresis, completion dates unaffected. Also the input the validation item above needs, and the lever that suppresses sliver die-swaps (22-minute tails) automatically.
- **Presser `"balanced"` / rotation-weighted assignment.** Reserved `presserAssignment` policy seam (Step 66) with a `NotImplementedError` guard; build the spread-the-work variant only if real production weeks show pure-preference reshuffling annoys the crew.

## Waiting on team input (small; one commit each)

- **In-cell edit-trigger feel** (Step 64 grids): ships at double-click / click-selected-cell (+ F2); Matthew leans single-click-opens but flagged his taste differs from the team's. One-line switch to `AllEditTriggers` in `PrefGrid.__init__` if they want it.
- **Trend (graph) variant of the per-employee productivity report.** Step 24 shipped table-only; reuses the existing trend machinery. Wants a team "yes, we'd use it."
- **About / Diagnostics panel** (re-scoped 2026-07-02 from the dropped "App Info" tab): show what the title bar doesn't — the open DB's `db_version` (read `MERCY_DB_VERSION`, don't hardcode), full build id, DB path / `QSettings` location. Build only if the team hits support friction.
- **Proper dirty-tracking + never-saved-data close gate.** The confirm-on-close dialog prompts whenever a file is loaded; a real version flags per-mutation, clears on save/load, prompts only when dirty, and closes the `filePath is None` silent-discard edge. Deferred per Matthew 2026-04-24 ("most don't save until the very end anyway"); revisit if the always-prompt nag becomes painful.

## Cosmetic — likely skip

- `file_manager/load.py` bundled `from records import (...)` → per-method imports (the last Step 28.1 leftover). Judged cosmetic-only; do it only if that file is being touched anyway.
