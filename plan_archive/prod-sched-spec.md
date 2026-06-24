# MERCY Feature Spec: Production Scheduling

A new subsystem for MERCY that tracks parts orders and produces a **Production
Schedule Report** — which parts should be pressed, on which presses, on which
shifts, on which days, to meet outstanding order deadlines.

**Status: approved by the team 2026-06-24.** Implementation is tracked as
Steps 42–54 in [`MERGE_PLAN.md`](../MERGE_PLAN.md) §13.30; this document is the
authoritative reference for the build.

All open questions from the review rounds have been answered by the team. This
document is in two parts: a **Resolved Decisions** log, and the **spec** beneath
(which folds those decisions in).

---

## Part 1 — Resolved Decisions

Decisions from two review rounds (the first resolved the bulk of the model; the
second closed the final eight questions). Recorded here as the authoritative
decision log for when this becomes a dev plan.

| # | Question | Decision |
|---|----------|----------|
| 1 | One part per order, or multi-line orders? | **One part per order.** These are *shop orders* — each is already a single line item. Entering full customer orders that auto-decompose into shop orders is a future goal, out of scope for v1. |
| 2 | One presser per press? | **Yes, one presser per press.** Some shifts have **fewer pressers than presses**, so the scheduler must accommodate **idle presses** — concurrent presses are capped by pressers present, not press count. |
| 3 | Does press score affect throughput? | **No — preference only for v1.** The 1–5 score is an assignment tiebreaker, not a rate multiplier. (Per-press rates would need press recorded on production entries; revisit later.) |
| 4 | Order status: cumulative or incremental? | **Neither — entries record *total remaining*.** Two separate fields per snapshot: quantity *still left* to **press** and quantity *still left* to **ship**, each as of its date. |
| 5 | Value tiebreak: price or margin? | **Price.** The goal is to maximize revenue. |
| 6 | Is `price` unit or total? | **Order total**, not per-unit. So an order's value *is* its price — no `quantity × price` needed. |
| 7 | Scrap-inflation formula? | **Confirmed:** `pressed = N / (1 − greenScrap) / (1 − fireScrap)`, global `greenScrap` and per-part `fireScrap`. |
| 8 | Transport time units / granularity? | **Business days, one constant per client.** |
| — | Pressing rate source | Empirical (from production records), per-part; `Part.pressing` is the cold-start fallback. |
| — | Output granularity | Shift-level quotas per press — `(date, shift, press, part) → quantity`; no named pressers. |
| — | Scope | Pressing only (no batching/finishing scheduling, no live inventory integration). |
| — | Deadlines | Hard unless impossible; late orders flagged explicitly. |
| — | Slack | A tunable pull-in applied to every effective deadline. |
| — | PTO | Applied coarsely (a PTO day removes that presser's full shift). |
| — | Report | On-screen regenerable table + PDF export; stateless; horizon = until all outstanding orders placed. |

---

## Part 2 — Spec

### 1. Overview & goal

Production Scheduling tracks customer **orders** for parts and produces a
**Production Schedule Report**: a per-`(day, shift, press, part)` set of pressing
quotas chosen so that outstanding orders are pressed in time to ship by their
due dates. It introduces several new databases, and will require a dedicated
**UI design round** and **algorithm design round** before the scheduler itself
is built.

### 2. Scope & non-goals (v1)

**In scope:** tracking the reference data (pressers, presses, shift workweeks,
part-press preferences, clients, orders, order status) and generating the
pressing schedule.

**Explicitly out of scope for v1:**

- **Full customer orders.** Orders here are *shop orders* — each is already a
  single part/line item. Auto-decomposing a multi-part customer order into shop
  orders is a future goal.
- **Batching and finishing scheduling** — only pressing. We assume batching and
  finishing keep up and are not the bottleneck.
- **Inventory integration.** MERCY's monthly inventory records aren't updated
  frequently enough to be a trustworthy stock source yet. Existing finished-goods
  stock that satisfies an order is instead represented by entering an initial
  **remaining-to-press** below the ordered quantity (see §3.7 / §4). Live
  `partInventory` draw-down is a future goal.
- **Per-presser assignment.** The schedule assigns quotas to presses at the
  *shift* level; the crew self-assigns. Pressers are interchangeable.
- **Press downtime / maintenance** — all presses are assumed available on every
  working shift.
- **Presser↔part / presser↔press capability matrices** — every presser can run
  every press and press every part.
- **Multi-shift pressers** — each presser works exactly one shift (reuses
  `Employee.shift`).
- **Effective-dated workweeks** — the shift workweek is stable over time.
- **Partial-day PTO precision** — PTO is applied coarsely (§4).
- **Per-press pressing rates** — rates are per-part only.

### 3. New databases

#### 3.1 Pressers
Which employees can press, and their press capacity.

- **Employee** — unique key; FK to `employees.idNum`.
- **Hours per shift pressed** — a near-constant per presser.

The presser's shift comes from `Employee.shift` (an employee works one shift),
not stored here. This is effectively an "is-a-presser" flag plus a capacity
number layered onto an existing employee.

#### 3.2 Shift Workweek
Which days of the week each of the three shifts normally works. Stable over time
(no effective-dating in v1). Combined with the existing holiday/observance data
(§4), this defines whether a given shift works on a given date.

#### 3.3 Press
A flat list of presses on the shop floor. Each has a unique **name**. All
presses are assumed available on every working shift in v1.

#### 3.4 Part-Press Preference
Maps each part to a scored list of presses, score 1 (lowest) to 5 (highest).
Internally `(part, press, score)` with `UNIQUE(part, press)`.

- **Every part can be pressed on every press.** A missing `(part, press)` entry
  means *neutral* preference, not "cannot press here."
- The score is a pure **assignment preference / tiebreaker** — it does not affect
  throughput in v1.

Editing this is a *nested* relational editor (one part → many scored presses),
like the existing mixtures / part-pads editors.

#### 3.5 Client
- **Name** — unique (enforced as the key, matching app convention).
- **Transport time** — typical shipment transit, in **business days**, one
  constant per client. *(Business days = standard Mon–Fri shipping calendar
  excluding holidays — a carrier convention, distinct from the shop's shift
  workweek.)*

#### 3.6 Order (shop order)
- **Order number** — unique key.
- **Client** — FK to Client.
- **Part** — FK to Part (exactly one part per shop order).
- **Quantity**
- **Price** — the **order total** (not per-unit).
- **Due date** — the date the customer needs the parts **in hand**. The ship-by
  date is therefore `due date − client transport time`.

#### 3.7 Order Status
Tracks remaining work against an order over time. Each entry is a dated snapshot
of what is **still left**, not what's been completed:

- **Quantity remaining to press, as of a given date**
- **Quantity remaining to ship, as of a given date**

These are two independent fields — one feeds the scheduler (press), one tracks
fulfillment (ship). The latest snapshot (by date) is the current state;
correcting a value just means adding a newer snapshot. An order is **fulfilled**
when quantity remaining to ship reaches 0. Existing on-hand stock is represented
by an initial remaining-to-press that's already below the ordered quantity.

Like Part-Press Preference, this is a nested editor (one order → many dated
snapshots).

### 4. Reused existing data

The scheduler leans on data MERCY already has — no new tables for these:

- **Working days** — the existing `holidays` / `observances` tables are already
  shift-specific and per-year. A shift works on a date iff the date's weekday is
  in that shift's workweek (§3.2) **and** the date is not a holiday observed by
  that shift.
- **PTO** — existing PTO ranges reduce presser capacity, applied **coarsely**:
  any day overlapping a presser's PTO range removes that presser's full shift of
  capacity that day. (PTO is stored as a date range + total hours, so finer
  per-day modeling isn't possible without schema work; revisit only if it
  matters.)
- **Pressing rates** — derived **empirically** from the existing `production`
  records (the productivity reports already compute `sum(quantity)/sum(hours)`
  per part). `Part.pressing` (a long-standing pieces/hour guesstimate) is the
  **fallback** for parts without enough history; the empirical data is meant to
  refine it over time. Rates are **per-part**, not per-press.
- **Scrap** — per-part `fireScrap` and global `greenScrap` inflate required
  pressing quantity: `pressed = N / (1 − greenScrap) / (1 − fireScrap)`.
- **Presser shift** — `Employee.shift`.
- **Existing stock** — represented as a reduced initial remaining-to-press on
  the order (§3.7), not read from `partInventory`.

### 5. The Production Schedule Report

#### 5.1 Output
A table of pressing quotas at `(date, shift, press, part) → target quantity`
granularity. Specific employees are **not** named.

- **Format:** an on-screen, regenerable table with a **PDF export** (matching the
  existing report convention).
- **State:** stateless — regenerated on demand from current orders/status; not
  persisted or hand-editable in v1.
- **Horizon:** projects until all currently-outstanding orders are placed.

#### 5.2 Definitions

- **Outstanding to press** = the order's latest *remaining-to-press* status
  snapshot (or the full ordered quantity if none recorded yet). No subtraction
  needed — the status entry *is* the outstanding amount.
- **Effective press-by date** = `due date − transport (business days) − slack`.
  Any post-press finishing lead time is folded into the slack constant for v1
  (since finishing isn't scheduled).
- **Required pressed quantity** = outstanding inflated for scrap (§4).
- **Shift/day capacity** — on each working day, the number of presses that can
  run simultaneously on a shift is `min(pressers present that shift, total
  presses)`. When pressers < presses the surplus presses sit **idle** — this is
  normal and the scheduler must handle it. Each running press contributes
  `hours-per-shift × per-part pressing rate` parts.

#### 5.3 Constraints & objectives

**Hard constraints:**
1. Each order's required production is pressed by its effective press-by date —
   *unless impossible*, in which case the order is flagged (§5.4).
2. Production is only scheduled on days a shift actually works (workweek +
   holidays).
3. Concurrent presses on a shift never exceed `min(pressers present, presses)`,
   and per-shift volume never exceeds the resulting capacity (presser DB + PTO).

**Soft objectives / tiebreakers (in order):**
1. **Order sequencing** — schedule earliest effective-deadline first; break ties
   by **order price** (the order total — maximizing revenue).
2. **Press assignment** — among feasible presses, prefer the higher-scored press
   for that part (preference only, no rate effect in v1).

A tunable **slack** constant pulls every effective deadline earlier, giving
margin for error.

#### 5.4 Infeasibility
When capacity cannot meet all deadlines, the report must **explicitly flag which
orders will be late and by how much** — never emit a plausible-but-impossible
plan. (Consistent with MERCY's standing principle that failures must be apparent
to the user.)

### 6. Algorithm

Optimal scheduling here is almost certainly NP-hard, so we target a **"good
enough"** heuristic — likely greedy earliest-deadline-first with
preference-weighted press assignment and the slack buffer. The concrete algorithm
is a **separate design round** once this model is approved; this spec only fixes
the model so that round is well-posed.

#### 6.1 Notes for the algorithm round
- **Idle presses are expected.** On shifts where pressers < presses, the
  scheduler chooses *which* presses to run (preferring high-scored presses for
  the parts being made) and leaves the rest idle. Capacity is bounded by
  presser-hours, not press count.
- Empirical rates have a cold-start problem (no history → `Part.pressing`
  fallback); the heuristic must handle both.
- Remaining-to-press status keeps the scheduler's input uniform: it only ever
  sees "outstanding to press," with existing stock already netted out (§3.7).

### 7. UI

- The current **Production** tab is renamed **"Production and Scheduling."**
- New databases use the standard table view with **New / Edit / Delete /
  Generate Report** buttons, with refreshes wired in — except the two *nested*
  editors (Part-Press Preference, Order Status), which need a sub-editor like the
  mixtures / part-pads pattern.
- Proposed sub-tab grouping under "Production and Scheduling" (to be finalized in the
  UI design round):
  - **Daily Entry / Reports** — existing production tracking.
  - **Sales** — Clients, Orders, Order Status.
  - **Scheduling config** — Pressers, Presses, Shift Workweek, Part-Press
    Preference.
  - **Schedule** — the Production Schedule Report.

### 8. Build / process notes

Not stakeholder questions — flagged so the eventual roadmap accounts for them:

- ~7 new tables ⇒ a `db_version` migration bump, with backup + WAL + atomic-save
  handling per existing convention.
- `fuzz_db.py` must be extended to populate every new table, and `smoke/` checks
  added (new CRUD tabs, the nested editors, and a render check for the schedule
  report).
- Two design rounds precede implementation: **UI layout** and **scheduling
  algorithm**.
