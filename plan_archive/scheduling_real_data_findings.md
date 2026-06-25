# MERCY — Step 54 Production Scheduling real-data drill findings

*Companion to [`real_data_findings.md`](real_data_findings.md) (the original Step 13
drill). Records the Step 54 end-to-end verification of the Production Scheduling
subsystem (Steps 42–53) against a real in-use MERCY DB, the way Step 13 verified the
original merge against real legacy ANIKA + BECKY files. For current project state
see [`../MERGE_PLAN.md`](../MERGE_PLAN.md); the durable regression net is the
synthetic smoke checks named at the bottom.*

---

**What ran.** A throwaway driver (`step54_real_data.py`, not committed — it depends
on a machine-specific file) executed offscreen against a **copy** of
`Mercy DB 6-1-26.db`, the latest real db file from before the scheduling feature
block (Matthew's home DB directory). The original was SHA-256 hashed before and
after and was **byte-identical** afterward — the drill only ever opened the copy.
The team has no real order/client/press data yet (per the algorithm addendum's
standing note), so the sales/scheduling tables were populated with fuzzed data on
top of the real costing/HR/production data; all assertions passed.

**Pre-migration state (real v4 DB).**
- `db_version=4`, 19 tables (none of the 7 scheduling/sales tables present — exactly
  a pre-Step-43 file).
- Real data: `materials:50, mixtures:15, parts:165, employees:48, production:296,
  packaging:51, materialInventory:93, partInventory:302, reviews:1, training:252,
  attendance:210, PTO:156, notes:1, holidays:10, observances:60`.

**Check 1 — v4 → v11 additive migration chain.**
- Post: `db_version=11`; all 7 tables (`presses`, `pressers`, `shift_workweek`,
  `part_press_pref`, `clients`, `orders`, `order_status`) created and **empty**.
- Pre-existing costing/HR/production counts **identical** before and after — the
  additive chain touched no existing data.
- **No `.bak` sibling written** — confirms the migrate.py claim that the v4→v11
  additive migrations (unlike the destructive ANIKA v1→v2 / BECKY v2→v3 ones) need
  no backup. This invariant had been asserted nowhere until now.
- In-memory load reconstructed all collections; the Mixture→Material cost chain
  computed cleanly on the real mixtures.

**Check 2 — scheduling/sales populate + save/reload roundtrip.**
- Populated on the migrated DB against the real employees/parts: 4 presses,
  4 pressers, 5 clients, 12 orders (fuzzed, due-dated around today), 12 order-status
  snapshots, 70 part-press preference rows.
- save → reload into a fresh `MainWindow`: every scheduling/sales collection and the
  296 production records roundtripped row-for-row.

**Check 3 — scheduler + report end-to-end on the migrated DB.**
- `schedule(db, today)` produced **32 schedule rows, 0 late/infeasible flags, 6 soft
  warnings**. Every row landed on a real working shift-day / real press / real part;
  every eligible order was scheduled or flagged (never silently dropped, §4).
- The 6 warnings are genuine real-data findings: real parts with `fireScrap` unset
  and/or no recent pressing history (cold-start `Part.pressing` fallback rate). This
  is the soft-warning surface doing its job on real data, not a defect — the team
  will dial in `fireScrap` and accumulate pressing history over time.
- `scheduleReport` rendered a valid PDF (`%PDF-`) against the migrated+reloaded DB.

**What this drill did NOT cover.**
- **Real order/client/press data** — none exists yet, so orders were fuzzed. When the
  team starts entering real orders, a re-run against them is worth doing (no code
  work needed — the same driver, re-pointed). The 6 cold-start warnings will shrink
  as real pressing history accrues.
- **Backup/restore of a *destructive* migration in the scheduling era** — the v4→v11
  chain is purely additive, so there is no destructive-migration backup to restore
  here. Step 13's check 2a already drilled the destructive ANIKA/BECKY restore path;
  Step 54's atomic-save rollback (check below) covers the save side.

**Regression hooks (the durable, committed net).** Two new synthetic smoke checks
cover the same code paths on fixture data, so the drill above doesn't need its
machine-specific file to stay green:
- `smoke/migrations.py::mercy_v4_to_v11_end_to_end` — builds a realistic v11 DB,
  downgrades it on disk to a v4 shape, replays v4→v11, asserts the no-backup
  invariant and data preservation, populates scheduling/sales, roundtrips, and runs
  `schedule()` + `scheduleReport`.
- `smoke/migrations.py::scheduling_save_rollback` — Step 13's atomic-save drill
  (check 2b), re-run now that `_saveFileBody` writes the 7 new tables: an injected
  mid-save failure rolls back, leaving the on-disk scheduling/sales tables
  byte-identical and a sentinel press off disk.
