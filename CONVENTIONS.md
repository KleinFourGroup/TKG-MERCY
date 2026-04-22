# MERCY — Dev conventions and gotchas

*Live working notes for MERCY development. Split out of `MERGE_PLAN.md` §12.4 on 2026-04-22 so conventions + gotchas have a home that doesn't require grepping the plan. Short and scannable; extend as new items surface. For project state and step-by-step history see `MERGE_PLAN.md` and `plan_archive/`.*

---

## Baseline workflow

- **Run `smoke.py` at the start and end of any invasive step.** The eleven checks in `smoke.py` are the always-on regression net. Start-of-step confirms you're building on a clean base; end-of-step confirms you didn't break anything before you commit. Offscreen, fast (~few seconds total), so there's no excuse to skip it.
- **Keep `fuzz_db.py` in sync as `records.py` / the schema evolves.** When a new record type lands or an existing one gains fields, update the fuzz generator so it continues to produce fully-populated DBs. Cataloged in `MERGE_PLAN.md` §13.8 as landed, but the tool is a live dependency of any report-stress or migration-rehearsal work — let it rot and the generated DBs quietly diverge from the real schema.

## Gotchas

- **Headless `Employee` construction.** `Employee.shift` is an `int` and `Employee.fullTime` is a separate `bool`. Set them as two fields (`e.shift = 1; e.fullTime = True`) or use `setJob(role, shift, fullTime)`. **Do not** pre-format the compound string (`e.shift = "1|1"`) — `Employee.getTuple()` re-appends `|{fullTime}` unconditionally and you'll end up with `"1|1|1"` on disk, which the migration path won't recognize as a legal shape.
- **Offscreen Qt needs a `QApplication`.** Any throwaway `./Scripts/python.exe -c '...'` that touches a Qt widget (including `MainWindow()`) must construct `QApplication([])` first. Otherwise Qt aborts silently during widget construction and bash reports exit 127 — which *looks* like "command not found" and sends you hunting for the wrong bug. `smoke.py` handles this for you; standalone probes need the boilerplate.

## Testing

Manual GUI testing on Matthew's Windows machine is the acceptance bar for anything user-facing. Headless sanity checks run from the repo-local venv as `./Scripts/python.exe smoke.py` (sets `QT_QPA_PLATFORM=offscreen` internally). See [`plan_archive/test_conventions.md`](plan_archive/test_conventions.md) for the historical breakdown of each smoke check and when it landed.
