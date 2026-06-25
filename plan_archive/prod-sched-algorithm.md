# MERCY Algorithm Design Round — Production Scheduler

**Step 50 addendum to [`prod-sched-spec.md`](prod-sched-spec.md).** The spec fixed
the *model* (data, definitions, constraints); this addendum fixes the *heuristic*
— order sequencing, the capacity / idle-press model, the rate / scrap / deadline
math, press assignment, and infeasibility handling — so that the scheduler
(Step 52) and its primitives (Step 51) are well-posed. It writes **no code**; it
is the reviewable artifact for the second design gate the spec calls for (§6,
§8).

**Status: APPROVED by the team 2026-06-25.** §8 records the six review decisions
(front-load, 2-business-day slack, weekends-only transport, and the three lighter
calls); the rest stood as proposed. This doc is now the authoritative reference
for Steps 51–53. A standing directive from review threads through the build: the
greedy heuristic is **provisional** until it runs against real order data — keep
it easy to rip out (§10).

Grounded throughout in the records that actually shipped in Steps 43–49
([`records/scheduling.py`](../records/scheduling.py),
[`records/sales.py`](../records/sales.py)) and the reused costing / HR data
([`records/products.py`](../records/products.py),
[`records/employees.py`](../records/employees.py),
[`records/production.py`](../records/production.py)).

---

## 1. Inputs — exactly what the scheduler reads

All reads are off the in-memory `Database`; the report is **stateless** (spec
§5.1), recomputed on demand from the current DB. "Today" `T` is the generation
date (the anchor; see §3.2). Field names below are the shipped ones.

| Source | Field(s) used | Notes |
|--------|---------------|-------|
| `Order` | `orderNum`, `client`, `part`, `quantity`, `price`, `dueDate` | `price` is the **order total** (decision #6) — the value tiebreak uses it directly, no `qty×price`. |
| `OrderStatus` | `remainingToPress()` (latest snapshot) | The scheduler's **outstanding-to-press**. Falls back to `Order.quantity` when no snapshot exists (spec §5.2). `remainingToShip()` / `isFulfilled()` are fulfillment-only — the scheduler ignores them except to **skip** fulfilled orders. |
| `Client` | `transportDays` | Business days; backs out ship-by from due (§2.5). |
| `Part` | `pressing` (pieces/hr, fallback rate), `fireScrap` (fraction) | `pressing` may be `None`/0; `fireScrap` may be `None` (§2.3, §2.4). |
| `Globals` | `greenScrap` | Stored as a **percent** (default 2.6 → fraction 0.026). Global, not per-part. |
| `production` | `quantity`, `hours` where `action=="Pressing"`, `targetType=="part"`, `targetName==part` | Empirical rate basis (§2.3) — the same `sum(qty)/sum(hours)` the productivity reports already use ([`report/production.py`](../report/production.py), "ratioOfSums"). |
| `Press` | `name` | The flat set of press lanes the schedule assigns to. |
| `Presser` | `employeeId`, `hoursPerShift` | Shift comes from `Employee.shift`, not stored on the presser. |
| `ShiftWorkweek` | `worksOn(weekday)` | Per shift 1/2/3; weekday absent ⇒ shift off that day. |
| `ObservancesDB` | `getObservance(year, holiday, shift)` | Shift-specific shop-closure dates (§2.1). |
| `EmployeePTODB` / `EmployeePTORange` | `start`, `end`, `hours` | Coarse day-overlap removes a presser's whole shift (§2.2). |
| `PartPressPref` | `getScore(press)` | 1–5; absent ⇒ neutral. Assignment tiebreaker only — **no** throughput effect (decision #3). |

**Order eligibility.** An order enters the scheduler iff its outstanding-to-press
> 0 **and** it is not fulfilled (`remainingToShip == 0`). Orders with no remaining
press work, or already shipped, are dropped silently (they need no schedule).

---

## 2. Derived quantities — the math (→ Step 51 primitives)

Each of these is a pure, deterministic helper with its own `smoke/` check
(Step 51's testable milestone). They take the `db` and explicit dates so they
stay testable headless.

### 2.1 Does shift *s* work on date *d*?

```
shiftWorksOn(db, s, d):
    if not db.shiftWorkweek[s].worksOn(d.weekday()):   # Mon=0..Sun=6
        return False
    # any holiday this shift observes on d closes the shift
    for holiday in db.observances.getHolidays(d.year):
        if db.observances.getObservance(d.year, holiday, s) == d:
            return False
    return True
```

Weekday convention matches `date.weekday()` deliberately — `ShiftWorkweek.days`
already stores Mon=0..Sun=6 (see its docstring). Observances are **shift-specific**
(one shift can work a day another has off), so the holiday check is per `s`.

### 2.2 Pressers present on shift *s*, date *d*

```
pressersPresent(db, s, d):
    return [ p for p in db.pressers.values()
             if db.employees[p.employeeId].shift == s
             and db.employees[p.employeeId].status            # active only
             and not onPTO(db, p.employeeId, d) ]
```

`onPTO` = `d` falls within any of the presser's dated PTO ranges (the
`CARRY`/`CASH`/`DROP` sentinel rows are year-end accounting, not absences, and are
skipped). **Coarse** per spec §4: any overlap removes the *whole* shift's
capacity for that presser that day — PTO hours aren't prorated (the schema
stores a range + a lump `hours`, so finer modeling isn't possible without schema
work). Inactive employees are excluded (a presser row can outlive an employee's
active status).

### 2.3 Per-part pressing rate (empirical, with cold-start fallback)

```
pressingRate(db, part, T):
    recs = [ r for r in db.production
             if r.action=="Pressing" and r.targetName==part
             and r.hours and r.hours > 0
             and 0 <= (T - r.date).days <= RATE_WINDOW_DAYS ]
    H = sum(r.hours for r in recs); Q = sum(r.quantity or 0 for r in recs)
    if H >= RATE_MIN_HOURS and Q > 0:
        return Q / H                      # empirical pieces/hour
    if db.parts[part].pressing and db.parts[part].pressing > 0:
        return db.parts[part].pressing    # Part.pressing cold-start fallback
    return None                            # no rate -> order is infeasible (§4)
```

- **Empirical first, fallback second** (spec §4): trailing-window `sum(qty)/sum(hours)`
  over `Pressing` records, matching the productivity report exactly; `Part.pressing`
  only when history is too thin.
- `RATE_WINDOW_DAYS` (proposed **180**) bounds recency so a part's rate tracks its
  *current* tooling/crew, not ancient runs. `RATE_MIN_HOURS` (proposed **4.0**,
  ≈ half a shift) is the "enough history" bar below which we don't trust the
  empirical average and fall back. Both tunable (§6); both flagged in §8.
- **No rate at all** (no history, `Part.pressing` unset/0) ⇒ the part can't be
  scheduled ⇒ the order is flagged infeasible with reason *"no pressing rate"*
  (§4), never silently skipped.

### 2.4 Scrap inflation (required pressed quantity)

Per decision #7, **multiplicative**:

```
requiredPressed(db, part, outstanding):
    g = db.globals.greenScrap / 100      # percent -> fraction
    f = db.parts[part].fireScrap or 0    # already a fraction; None -> 0 (+warn)
    return ceil( outstanding / (1 - g) / (1 - f) )
```

- `greenScrap` is a **percent** in the data (default 2.6); `fireScrap` is already a
  fraction. Mixing those up would be a 100× error, hence the explicit `/100`.
- **Deliberate divergence flag.** This is *not* `Part.getScrap()`.
  `Part.getScrap()` combines scrap **additively** (`greenScrap/100 + fireScrap`)
  for the *costing* gross-up; decision #7 fixed the *yield* model as multiplicative.
  The scheduler computes `g`/`f` itself and must **not** be "simplified" to reuse
  `getScrap()` — they answer different questions and differ numerically.
- **Missing `fireScrap`** is treated as 0 (no inflation) with a soft per-part
  warning surfaced on the report, rather than crashing — visible degradation over
  a hard stop, per the dual-mandate ([`feedback_failure_mandate`]). Under-pressing
  a part whose scrap is genuinely nonzero is the cost, and it's made visible.
- `ceil` because you press whole pieces and rounding down would systematically
  under-deliver.

### 2.5 Effective press-by date

```
shipBy(db, order)      = subBusinessDays(order.dueDate, db.clients[order.client].transportDays)
effectivePressBy(...)  = subBusinessDays(shipBy, SLACK_BUSINESS_DAYS)
```

- **ship-by = due − transport** (spec §3.6): the parts must leave the shop this
  many *business days* before they're due in-hand.
- **effective press-by = ship-by − slack**: a tunable global pull-in giving margin
  for error and absorbing un-scheduled finishing lead time (spec §5.3). Default
  **2 business days** — a deliberate buffer against the known noise in the
  cold-start rate data; the team dials it in once real performance is visible
  (§8.2).
- **`subBusinessDays`** steps backward over Mon–Fri. **v1 simplification (flagged,
  §8): weekends only — no holiday calendar.** MERCY's `observances` are
  *shift-specific shop closures*, not the carrier's shipping holidays, so reusing
  them here would be wrong; and there's no federal-holiday table in the data.
  Holiday-aware transport is a future refinement. Slack is also counted in
  business days for consistency with transport.
- The resulting `effectivePressBy` is a **calendar date** — a hard deadline the
  press work must finish on or before. Press *capacity*, separately, exists only
  on shop working shift-days (§2.1); the two calendars are intentionally distinct.

### 2.6 Shift-day capacity (the press-hours / idle-press model)

The unit of capacity is **press-hours**, because parts press at different rates —
a fixed "parts per shift" number can't be shared across parts, but hours can.

For shift `s` on a working date `d`:

```
present = pressersPresent(db, s, d)              # §2.2
nPresses = len(db.presses)
lanes    = present sorted by hoursPerShift desc, take first min(len(present), nPresses)
capacityHours(s, d) = sum(p.hoursPerShift for p in lanes)
```

- **One presser ⇄ one press** (decision #2). The number of presses that can run
  at once is `min(pressers present, presses)` — the **lanes**.
- **Idle presses are normal** (decision #2): when `present < nPresses`, the surplus
  presses sit idle; capacity is bounded by **presser-hours**, not press count.
- **Pressers > presses** (the rarer direction): only `nPresses` can run; we keep
  the highest-`hoursPerShift` pressers as lanes (maximizes capacity; interchangeable
  pressers make the choice immaterial to feasibility). Flagged in §8.
- A lane delivers its presser's `hoursPerShift` of press time. Pressing part `P`
  consumes `requiredPressed_P / rate_P` press-hours, drawn from the shift-day's
  pooled `capacityHours` during sequencing (§3.3) and pinned to specific press
  lanes during assignment (§3.4).

---

## 3. The heuristic — scheduler core (→ Step 52)

Greedy **earliest-deadline-first, front-loaded**: walk orders by urgency and place
each order's press demand into the earliest available shift-day capacity. This is
the spec's stated approach (§6) and the slack-pulls-the-deadline-earlier framing
(§5.3) implies front-loading. Front-loading is also the robust choice — finishing
ahead of the (already slack-adjusted) deadline protects against capacity surprises.
Front-load was confirmed at review (§8.1) over the just-in-time alternative; it is
a **policy**, isolated behind the scheduler seam (§10) so a future "front-load
less" tweak stays a localized change.

### 3.1 Order sequencing

```
sort eligible orders by (effectivePressBy, -price, orderNum)
```

EDF primary; **price** (order total) breaks deadline ties to maximize revenue
(decisions #5/#6); `orderNum` breaks the remainder so the schedule is fully
deterministic (§5). This realizes soft objective #1.

### 3.2 Timeline & horizon

- **Anchor.** Scheduling starts at `T` (today / generation date). Capacity in the
  past doesn't exist; the first placeable shift-day is `T` itself if a shift works
  then, else the next working shift-day.
- **Horizon.** Walk shift-days forward lazily as demand requires; the natural stop
  is when every eligible order is placed (spec §5.1, "until all outstanding orders
  are placed"). A hard cap `MAX_HORIZON_DAYS` (proposed **365**, §6) bounds the
  walk so a pathological/under-capacity DB can't loop unbounded — hitting it means
  remaining demand is reported infeasible (§4), never dropped.
- Capacity per `(d, s)` is computed lazily by §2.6 and memoized; a running
  `remainingHours[(d, s)]` is decremented as demand is placed.

### 3.3 Allocation loop

```
for order in sequenced_orders:
    P    = order.part
    rate = pressingRate(db, P, T)
    if rate is None:
        flag(order, INFEASIBLE_NO_RATE); continue
    need = requiredPressed(db, P, outstandingToPress(order)) / rate   # press-hours
    # walk working shift-days from T forward, earliest first
    for (d, s) in workingShiftDays(from=T):
        if d > effectivePressBy(order) and order not yet flagged late:
            flag(order, LATE, since=d)        # crossed the deadline, still placing
        take = min(need, remainingHours[(d, s)])
        if take > 0:
            place(d, s, P, hours=take, qty=take*rate)   # provisional; lane-pinned in §3.4
            remainingHours[(d, s)] -= take
            need -= take
        if need <= EPS: break
    if need > EPS:
        flag(order, INFEASIBLE_NO_CAPACITY, shortHours=need)   # hit MAX_HORIZON
```

- **Front-loaded EDF**: most-urgent order fills the earliest capacity first; later
  orders take what's left. An order that can't fit before its `effectivePressBy`
  because earlier-deadline orders consumed the capacity keeps getting placed into
  *later* working shift-days and is **flagged late** — never dropped (spec §5.4,
  hard-unless-impossible).
- One order's demand may **span multiple shift-days and shifts**; intra-day there's
  no ordering significance (deadlines are date-granular), so all working shifts of
  a day are equally early.
- `EPS` guards float dust from the hours math.

### 3.4 Press assignment (soft objective #2)

The loop above pools capacity per shift-day; a second pass pins each shift-day's
placed `(part → hours)` onto specific **press lanes** (§2.6), producing the
`(date, shift, press, part) → quantity` output:

```
for each (d, s) with placed work:
    lanes = the running presses for (d,s), each with a presser's hoursPerShift budget
    for each placed (part, hours), in descending requiredPressed order:
        assign onto lanes preferring higher PartPressPref score for that part,
        splitting across lanes when one lane's remaining budget is too small
```

- **Preference, not capability** (decision #3, spec §3.4): every press can press
  every part; the score only orders the choice. **Neutral (absent) preference ⇒
  treated as the midpoint 3** for ranking, so "no opinion" sits between an explicit
  *avoid* (1–2) and an explicit *prefer* (4–5). Ties (equal score) break by press
  name, for determinism. Flagged in §8.
- A part may land on **multiple presses** in one shift (its hours split across
  lanes) and a press may carry **multiple parts** in one shift (sequential within
  the shift) — both are first-class in the `(date, shift, press, part)` output.
- Assignment is best-effort bin-packing; it never changes *whether* the work fits
  (that was decided in §3.3 against the pooled hours), only *which lane* runs it.

### 3.5 Output

- **Schedule rows:** `(date, shift, press, part) → target quantity` (spec §5.1).
  No named pressers — the crew self-assigns (spec §2, non-goal).
- **Late / at-risk list:** every flagged order with its reason and magnitude (§4).

---

## 4. Infeasibility — never a plausible-but-impossible plan

Per spec §5.4 and the standing failure principle, the report **explicitly flags**
shortfalls instead of emitting a clean-looking impossible schedule. Three flag
kinds, each carrying its magnitude:

| Flag | Trigger | Magnitude reported |
|------|---------|--------------------|
| `LATE` | Order placed, but some of it lands **after** its `effectivePressBy`. | **Days late** = (completion date − effectivePressBy) and **pieces short at deadline** = qty still unplaced as of the deadline. |
| `INFEASIBLE_NO_CAPACITY` | Demand still unplaced at `MAX_HORIZON_DAYS`. | **Press-hours short** (and pieces) that no horizon day could absorb. |
| `INFEASIBLE_NO_RATE` | No empirical history **and** no `Part.pressing`. | The part name — a data gap to fix, not a capacity problem. |

Soft, non-blocking **warnings** (schedule still emitted): a part with `fireScrap`
unset (§2.4), or a part scheduled entirely on the `Part.pressing` cold-start
fallback (rate not yet empirically grounded). These surface on the report so the
numbers are trusted appropriately.

**Never-drop rule:** flagged orders are still fully scheduled (LATE keeps placing
past the deadline; NO_CAPACITY reports the residual). The plan always accounts for
100% of eligible demand — late, but visible.

---

## 5. Determinism & statelessness

- **Stateless** (spec §5.1): nothing persisted; regenerated from current
  orders/status each time. No new tables, no `db_version` bump for the scheduler
  itself.
- **Deterministic:** given the same DB and the same `T`, the schedule is
  byte-identical. Every sort has a total tiebreak (`orderNum`, press `name`); no
  RNG, no dict-iteration-order dependence. This is what makes a `smoke/` invariant
  check possible against `fuzz_db` data (Step 52 milestone).
- `T` is an explicit parameter (defaulting to today), so smoke can pin a date and
  assert exact output — the same headless-testability discipline the rest of the
  suite uses.

---

## 6. Tunable constants

v1 keeps these as **module-level constants** in the new scheduling logic module
(Step 51), not schema/`Globals` fields — consistent with the stateless-report
decision and avoiding a migration. The Schedule report dialog (Step 53) may expose
**horizon** (and possibly **slack**) as on-screen controls; promoting any of these
to persisted, user-editable `Globals` is deferred until the field asks for it.

| Constant | Proposed default | Meaning | §8? |
|----------|------------------|---------|-----|
| `SLACK_BUSINESS_DAYS` | 2 | Pull-in applied to every effective deadline. | yes |
| `RATE_WINDOW_DAYS` | 180 | Trailing window for the empirical rate. | yes |
| `RATE_MIN_HOURS` | 4.0 | "Enough history" bar before trusting empirical. | yes |
| `MAX_HORIZON_DAYS` | 365 | Hard cap on the forward walk (infeasibility backstop). | no |

---

## 7. Worked micro-example (sanity check)

One part `P`, two presses, shift 1 works Mon–Fri, two pressers on shift 1 each
`hoursPerShift = 8`. `rate_P = 10 pcs/hr`. Order: 1500 pcs, `greenScrap = 2.6%`,
`fireScrap = 5%`, client `transportDays = 3`, due Fri the 19th, `SLACK = 2`.

- ship-by = 19th − 3 business days = **14th** (Mon). press-by = 14th − 2 = **12th**
  (Thu).
- requiredPressed = 1500 / (1−0.026) / (1−0.05) = 1500 / 0.974 / 0.95 ≈ **1621** pcs
  → 1621 / 10 = **162.1 press-hours**.
- Shift-1 capacity = 2 lanes × 8 = **16 press-hours/day** → 160 pcs/day.
- 162.1 / 16 ≈ **10.2 working days** of shift-1. Starting the 1st, the 12th is the
  8th working day (~128 press-hrs) — short by ~34 hrs ⇒ order flagged **LATE**,
  finishing ~2 working days past press-by, ~544 pcs short at the deadline. Exactly
  the kind of "visible, quantified" miss §4 requires.

(Illustrative — confirms the units compose; not a test fixture.)

---

## 8. Resolved decisions (team review, 2026-06-25)

All six review questions are answered; the answers are folded into the sections
above. Recorded here as the decision log (mirroring the spec's Part 1).

1. **Schedule timing → front-load.** EDF, press as early as capacity allows in
   deadline order, over the just-in-time alternative. (§3)
2. **Slack → 2 business days.** A unilateral pull-in to absorb the known noise in
   the cold-start rate data; the team will dial it in against real performance once
   they see how the schedule behaves. Counted in business days, for consistency with
   transport. (§2.5, §6)
3. **Transport business days → weekends-only (no holidays) for v1.** No carrier
   shipping-holiday calendar exists, and the shift-specific `observances` are the
   wrong list (shop closures, not shipping holidays). Holiday-aware transport is a
   future refinement. (§2.5)
4. **Empirical rate → 180-day window, 4-hour minimum history.** Confirmed defaults;
   tunable as the field reveals how fast rates drift. (§2.3, §6)
5. **Neutral press preference → midpoint (3).** "No opinion" ranks between an
   explicit *avoid* (1–2) and an explicit *prefer* (4–5). (§3.4)
6. **Pressers > presses → keep the highest-`hoursPerShift` pressers as lanes.**
   Fine for the rare over-staffed shift. (§2.6)

---

## 9. Mapping to the build (Steps 51–53)

- **Step 51 — primitives (pure logic, smoke-checked):** §2.1 `shiftWorksOn`,
  §2.2 `pressersPresent`/`onPTO`, §2.3 `pressingRate`, §2.4 `requiredPressed`,
  §2.5 `subBusinessDays`/`shipBy`/`effectivePressBy`, §2.6 `capacityHours`. Each
  lands with a deterministic `smoke/` check; these are exactly Step 51's listed
  helpers.
- **Step 52 — scheduler core:** §3 (sequencing, timeline, allocation, assignment) +
  §4 (infeasibility). Emits the §3.5 output. smoke asserts the invariants of §5
  (determinism) and §4 (every eligible order accounted for; nothing on a non-working
  day; per-shift volume ≤ capacity) against `fuzz_db` data. If §3 proves large at
  review, split it sub-step-style (sequencing+capacity walk, then assignment) — the
  primitives are already carved into Step 51 to keep the core small.
- **Step 53 — report:** a `report/scheduling.py` mixin composed into `PDFReport`
  (the Step 33 pattern): on-screen regenerable table + horizon control + an explicit
  late-orders section + reportlab PDF export. Manual UI gate (plan §13.30).

`fuzz_db.py` already populates every scheduling/sales table (Steps 43–49); Step 52
will want it to also generate enough `Pressing` production history that
`pressingRate` exercises the empirical path, not only the fallback.

---

## 10. Replaceability — the greedy core is provisional

Standing directive from review: until the schedule runs against **real order data**
(not yet in hand), we won't know whether greedy EDF is good enough or whether the
shop needs a more optimal allocator, a less front-loaded policy, or a different
objective. So Step 52 keeps the heuristic **easy to rip out**:

- **One seam.** The whole scheduler is reached through a single entry point —
  `schedule(db, T, config) -> ScheduleResult` — returning a plain result (schedule
  rows + flag list, §3.5 / §4). The report (Step 53) and any smoke check consume
  that *result*, never the algorithm's internals, so swapping the allocator touches
  nothing downstream.
- **Stable foundation, swappable strategy.** The §2 primitives (capacity, rates,
  deadlines, working days) are inputs *any* algorithm needs — they stay put. Only
  §3.1 sequencing + §3.3 allocation + the front-load policy are the "greedy" part,
  isolated so an ILP / CP-SAT solver, a less-front-loading variant, or a different
  objective drops in behind the same seam.
- **Policy via config, not edits.** The §6 tunables (slack, window, horizon) ride a
  `config` object rather than literals scattered through the loop, so "front-load
  less" / "more slack" is a parameter change, not surgery.
- **No persistence to migrate around it** (§5): the scheduler is stateless, so
  replacing it is pure logic — no schema, no data migration, no `db_version` bump.

Ship a working, honest greedy schedule now; trade it up cheaply once the real
numbers say what "good enough" actually is.
