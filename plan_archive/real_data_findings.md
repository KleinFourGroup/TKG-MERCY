# MERCY — Step 13 real-data drill findings

*Split out of `MERGE_PLAN.md` §12.5 on 2026-04-22 to keep the active plan doc lean. Content below is preserved verbatim from the plan at split time — stale cross-references (including relative `§12.x` pointers and "Step N above/below" language) are left intact since historical accuracy matters more than polish. For current project state, see `MERGE_PLAN.md`.*

---


**What ran.** A throwaway driver (`step13_real_data.py`, not committed) executed five drills offscreen against copies of two real legacy files the team handed over — `legancyanika.db` (v1 ANIKA, no `db_version` stamp, detected via table shape) and `legacybecky.db` (v2 BECKY). Sources were hashed before and after; both were byte-identical afterward. All five drills passed; the summary below is retained so future regressions can be compared against known-good numbers.

**Check 1a — legacy ANIKA migration.**
- Pre: 7 tables, version `None`, counts `{materials:49, mixtures:10, parts:141, packaging:51, materialInventory:31, partInventory:57, globals:8}`.
- Post: 19 tables, `db_version=3`, all MERCY tables present. Base64 compound decode produced `mixture_components=71, part_pads=148, part_misc=281`. Row counts for `mixtures` and `parts` unchanged (10/10, 141/141). One `.db.bak-*` sibling written, matching §8 expectation. Save/reload roundtrip preserved counts.

**Check 1b — legacy BECKY migration.**
- Pre: 9 tables, `db_version=2`, counts `{employees:29, training:188, attendance:135, PTO:85, reviews:1, notes:3, holidays:10, observances:30}`.
- Post: 19 tables, `db_version=3`. `employees` columns split into `shift` + `fullTime` per §3.3. Base64 decode applied to `reviews.details` / `notes.details`. **Orphan sweep found zero orphans** in this file — the `updateEmployee` pre-7a bug evidently never corrupted it. Good for the release, bad for code coverage: the orphan-sweep code path is exercised only by synthetic fixtures in `smoke.py::legacy_becky_migration`. If a later BECKY file does have orphans, watch for the correct count drop and the info-level log line.
- One `.bak` sibling written. Save/reload roundtrip preserved employee count (29/29). Source byte-identical.

**Check 1c — merge.**
- ANIKA copy opened first (141 parts), then BECKY copy imported via `importOtherDb`. Merge plan reported **zero collisions** (the two real files share no keys — ANIKA identifies by string name, BECKY by `idNum`). Post-merge: 141 parts + 29 employees + 29 review-collections carried through. Save/reload preserved everything. BECKY temp copy SHA-256 identical before and after `importOtherDb` — **Step 10's "source file untouched" guarantee holds on real data**.

**Check 2a — backup/restore drill.**
- Migrated a real ANIKA copy to MERCY format, truncated the live file to 0 bytes, copied the `.bak-*` sibling back into place, reopened in a fresh `MainWindow`. The restored file is pre-migration, so MERCY re-ran the ANIKA v1→v3 migration on it (creating a second `.bak`), and loaded successfully with `parts=141` intact. Recovery path works end-to-end.

**Check 2b — atomic-save drill.**
- Opened a fully-migrated file, deleted an in-memory part (`1046-FS4`), monkey-patched `_saveFileBody` to run the real body and then raise `RuntimeError` before `saveFile`'s outer `commit()`. On-disk row counts (`parts`, `mixtures`, `materials`, `mixture_components`, `part_pads`) were byte-identical before and after the attempted save — Step 7a's try/rollback/commit wrapper is rolling back correctly against a real-file connection, not just the hand-crafted fixtures.

**What Step 13 did NOT cover.** Three items from the original Step 13 pick-up notes didn't fire and are left for future steps or dropped as low priority:
- **Production tracking + reports against real production data** (original check 3). Deferred — the team hasn't started logging production yet. Covered in practice once they do; no code work needed now.
- **Report sanity-check loop with the team** (original check 4). The team's first-look feedback instead surfaced three feature asks, now tracked as §13.
- **Cross-platform sanity** (original check 5). Windows-only shop; dropped.

**Performance notes.** The v2→v3 BECKY migration's per-row `UPDATE` on `reviews.details` / `notes.details` ran instantaneously on the real 29-employee file (1 review, 3 notes). The §12.5-original-hypothesis about large-file slowness did not materialize at this file size — but the drill didn't push into hundreds of reviews/notes either, so the "swap to a `CASE`-expression single `UPDATE`" fallback remains a live option if the team's next snapshot is substantially bigger.

**Regression hooks for future sessions.** The synthetic `smoke.py` checks (`legacy_anika_migration`, `legacy_becky_migration`, `legacy_merge`, production roundtrip + report) cover the same code paths as the drills above on fixture data — they are the durable safety net. The throwaway driver was deliberately not promoted to `smoke.py` because it depends on files that are gitignored and specific to Matthew's machine; committing it would either break for anyone else running `smoke.py` or force those files into the tree.

