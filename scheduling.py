"""Production-scheduling primitives (Step 51 / plan §13.30).

Pure, deterministic logic over a `Database` — the stable foundation the
swappable scheduler core (Step 52) sits on (algorithm addendum §10). Nothing
here touches Qt, the filesystem, or any persisted state, so every helper is
covered by a deterministic check in `smoke/scheduling.py`.

Not to be confused with `records/scheduling.py`, which holds the *record
classes* (Press / Presser / ShiftWorkweek / PartPressPref). This module is the
*math* over them, fixed by the algorithm design round
([`plan_archive/prod-sched-algorithm.md`](plan_archive/prod-sched-algorithm.md))
§2: working days, presser capacity, pressing rate, scrap inflation, and the
effective press-by deadline.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from records.scheduling import SHIFTS

if TYPE_CHECKING:
    from records.database import Database
    from records.sales import Order
    from records.scheduling import Presser

# Tunable scheduling constants (addendum §6). Module-level for v1 — the stateless
# report means no schema / Globals field. Step 52's schedule(db, T, config) seam
# will lift these onto a config object so the policy stays swappable (§10).
SLACK_BUSINESS_DAYS = 2   # effective-deadline pull-in, in business days (§8.2)
RATE_WINDOW_DAYS = 180    # trailing window for the empirical pressing rate (§8.4)
RATE_MIN_HOURS = 4.0      # "enough history" bar before trusting empirical (§8.4)
MAX_HORIZON_DAYS = 365    # hard cap on the scheduler's forward walk (§6, §3.2)

# Midpoint of the 1..5 PartPressPref scale: a part with no scored preference for a
# press ranks as neutral (decision #5), between an explicit avoid (1-2) and prefer
# (4-5). Used only as a press-assignment tiebreaker — never a throughput effect.
NEUTRAL_PRESS_SCORE = 3

# Float dust guard for the press-hours math (§3.3): treat residual demand at or
# below this as fully placed.
EPS = 1e-9


def shiftWorksOn(db: Database, shift: int, d: datetime.date) -> bool:
    """Addendum §2.1: shift `shift` works on date `d` iff `d`'s weekday is in the
    shift's workweek AND `d` is not a holiday this shift observes. A shift with no
    ShiftWorkweek entry (no working days configured) never works. Observances are
    shift-specific, so the holiday check is per `shift`."""
    workweek = db.shiftWorkweek.get(shift)
    if workweek is None or not workweek.worksOn(d.weekday()):
        return False
    for holiday in db.holidays.getHolidays(d.year):
        if db.holidays.getObservance(d.year, holiday, shift) == d:
            return False
    return True


def onPTO(db: Database, employeeId: int, d: datetime.date) -> bool:
    """Addendum §2.2: True iff `d` falls within any of the employee's dated PTO
    ranges. Coarse (spec §4) — a single overlapping day removes the whole shift.
    The CARRY / CASH / DROP sentinel rows (`end` is a str, not a date) are
    year-end PTO accounting, not absences, so they're skipped."""
    ptoDb = db.PTO.get(employeeId)
    if ptoDb is None:
        return False
    for rng in ptoDb.PTO.values():
        end = rng.end
        if isinstance(end, datetime.date) and rng.start is not None and rng.start <= d <= end:
            return True
    return False


def pressersPresent(db: Database, shift: int, d: datetime.date) -> list[Presser]:
    """Addendum §2.2: the active pressers assigned to `shift` (via Employee.shift)
    who aren't out on PTO on `d`. A presser whose employee is missing or inactive
    is excluded — re-id / delete cascade pressers (Steps 56/59), so an orphan is a
    data anomaly we skip rather than crash the schedule over."""
    present: list[Presser] = []
    for empId, presser in db.pressers.items():
        emp = db.employees.get(empId)
        if emp is None or not emp.status or emp.shift != shift:
            continue
        if onPTO(db, empId, d):
            continue
        present.append(presser)
    return present


def concurrentPresses(db: Database, shift: int, d: datetime.date) -> int:
    """Addendum §2.6: how many presses can run at once on `shift`/`d` =
    min(pressers present, presses). 0 on a non-working shift-day. Surplus presses
    sit idle when pressers < presses (normal); surplus pressers idle in the rarer
    pressers > presses direction."""
    if not shiftWorksOn(db, shift, d):
        return 0
    return min(len(pressersPresent(db, shift, d)), len(db.presses))


def capacityHours(db: Database, shift: int, d: datetime.date) -> float:
    """Addendum §2.6: total press-hours available on `shift`/`d`. Each running
    press (a lane) delivers one presser's hoursPerShift; the lane count is
    min(pressers present, presses). When pressers > presses the highest-hours
    pressers take the lanes (maximizes capacity — pressers are interchangeable).
    0.0 on a non-working shift-day or with no presses / no pressers present."""
    if not shiftWorksOn(db, shift, d):
        return 0.0
    present = pressersPresent(db, shift, d)
    lanes = min(len(present), len(db.presses))
    if lanes == 0:
        return 0.0
    hours = sorted((p.hoursPerShift for p in present), reverse=True)
    return float(sum(hours[:lanes]))


def empiricalPressingRate(db: Database, part: str, today: datetime.date,
                          windowDays: int = RATE_WINDOW_DAYS,
                          minHours: float = RATE_MIN_HOURS) -> float | None:
    """The empirical half of `pressingRate` (addendum §2.3): trailing-window
    sum(quantity)/sum(hours) over `Pressing` production records for `part`, or
    None when the history is thinner than `minHours` (or has no pressed pieces).
    Split out so the scheduler can tell whether a part's rate is empirically
    grounded or is riding the Part.pressing cold-start fallback (a soft §4
    warning) without recomputing."""
    totalQ = 0.0
    totalH = 0.0
    for rec in db.production.values():
        if rec.action != "Pressing" or rec.targetName != part:
            continue
        if rec.date is None or rec.hours <= 0:
            continue
        age = (today - rec.date).days
        if 0 <= age <= windowDays:
            totalH += rec.hours
            totalQ += rec.quantity or 0
    if totalH >= minHours and totalQ > 0:
        return totalQ / totalH
    return None


def pressingRate(db: Database, part: str, today: datetime.date,
                 windowDays: int = RATE_WINDOW_DAYS,
                 minHours: float = RATE_MIN_HOURS) -> float | None:
    """Addendum §2.3: per-part pieces/hour. The empirical rate
    (`empiricalPressingRate`) when history is thick enough, falling back to
    Part.pressing otherwise, and None when neither is available (the order is
    then infeasible per §4 — never silently skipped)."""
    empirical = empiricalPressingRate(db, part, today, windowDays, minHours)
    if empirical is not None:
        return empirical
    part_obj = db.parts.get(part)
    if part_obj is not None and part_obj.pressing is not None and part_obj.pressing > 0:
        return part_obj.pressing
    return None


def requiredPressed(db: Database, part: str, outstanding: float) -> int:
    """Addendum §2.4: `outstanding` pieces inflated for scrap, **multiplicatively**
    (decision #7): outstanding / (1 − green) / (1 − fire), rounded up. `green` is
    the global greenScrap (a *percent* → /100); `fire` is the part's fireScrap
    (already a fraction; missing → 0, a data gap the report surfaces). Deliberately
    NOT Part.getScrap(), which combines scrap *additively* for costing — a
    different question. Scrap fractions are clamped below 1 so impossible
    (≥100%) scrap yields an absurd-but-finite quantity (visibly wrong) instead of
    a divide-by-zero crash."""
    green = min(max(db.globals.greenScrap / 100.0, 0.0), 0.999)
    part_obj = db.parts.get(part)
    rawFire = part_obj.fireScrap if (part_obj is not None and part_obj.fireScrap is not None) else 0.0
    fire = min(max(rawFire, 0.0), 0.999)
    return math.ceil(outstanding / (1.0 - green) / (1.0 - fire))


def subBusinessDays(d: datetime.date, n: int) -> datetime.date:
    """Step back `n` business days (Mon–Fri) from `d`, skipping weekends. v1 has
    no shipping-holiday calendar (decision §8.3) — the shift-specific observances
    are shop closures, the wrong list — so only Sat/Sun are skipped. n ≤ 0 returns
    `d` unchanged (0 transport days = a local client shipped the day it's due)."""
    result = d
    remaining = n
    while remaining > 0:
        result -= datetime.timedelta(days=1)
        if result.weekday() < 5:  # Mon(0)..Fri(4)
            remaining -= 1
    return result


def shipBy(db: Database, order: Order) -> datetime.date | None:
    """Addendum §2.5 / spec §3.6: the date the parts must leave the shop =
    due date − the client's transport business days. None if the order has no due
    date."""
    if order.dueDate is None:
        return None
    client = db.clients.get(order.client)
    transport = client.transportDays if client is not None else 0
    return subBusinessDays(order.dueDate, transport)


def effectivePressBy(db: Database, order: Order,
                     slackBusinessDays: int = SLACK_BUSINESS_DAYS) -> datetime.date | None:
    """Addendum §2.5: the hard press-by deadline = ship-by − `slackBusinessDays`.
    The slack is a tunable pull-in giving margin for error (default 2 business
    days, §8.2). None if the order has no due date."""
    ship = shipBy(db, order)
    if ship is None:
        return None
    return subBusinessDays(ship, slackBusinessDays)


# ---------------------------------------------------------------------------
# Step 52: scheduler core (addendum §3 sequencing/allocation/assignment + §4
# infeasibility). The whole scheduler is reached through the single `schedule`
# seam (§10) returning a plain `ScheduleResult`, so the report (Step 53) and any
# smoke check consume the result, never the algorithm's internals — swapping the
# greedy heuristic for a better optimizer touches nothing downstream.
# ---------------------------------------------------------------------------

# Flag kinds (addendum §4). LATE and the two INFEASIBLE_* are mutually exclusive
# per order; NO_CAPACITY subsumes lateness (it never fit, so reporting the
# residual is the actionable number).
LATE = "LATE"
INFEASIBLE_NO_CAPACITY = "INFEASIBLE_NO_CAPACITY"
INFEASIBLE_NO_RATE = "INFEASIBLE_NO_RATE"

# Soft warning kinds (addendum §4): the schedule is still emitted, but the
# numbers should be trusted appropriately.
WARN_FALLBACK_RATE = "FALLBACK_RATE"
WARN_MISSING_FIRESCRAP = "MISSING_FIRESCRAP"

# Presser-assignment policy (Step 66, §13.44). "preference" is the only v1
# heuristic: staff the present pressers onto the running presses by presser->press
# preference (greedy max-score). "balanced" / rotation-weighted policies are
# reserved behind this config seam (addendum §10 provisional pattern) but
# unimplemented — an unrecognized policy raises rather than silently mis-staffing.
PRESSER_ASSIGNMENT_PREFERENCE = "preference"


@dataclass(frozen=True)
class ScheduleConfig:
    """The §6 tunables on one object (addendum §10) so policy stays a parameter
    change, not surgery. Defaults are the module constants the primitives use."""
    slackBusinessDays: int = SLACK_BUSINESS_DAYS
    rateWindowDays: int = RATE_WINDOW_DAYS
    rateMinHours: float = RATE_MIN_HOURS
    maxHorizonDays: int = MAX_HORIZON_DAYS
    # Step 66: a presser with no scored preference for a press ranks as this
    # neutral midpoint (the presser twin of NEUTRAL_PRESS_SCORE). Only a staffing
    # tiebreaker — never a throughput effect.
    presserNeutralScore: int = NEUTRAL_PRESS_SCORE
    # Step 66: which heuristic staffs pressers onto presses (see
    # PRESSER_ASSIGNMENT_PREFERENCE). Other policies are reserved (§10).
    presserAssignment: str = PRESSER_ASSIGNMENT_PREFERENCE


@dataclass(frozen=True)
class ScheduleRow:
    """One cell of the schedule (addendum §3.5): press `part` on `press` during
    `shift` on `date`, targeting `quantity` pieces over `hours` press-hours,
    staffed by `presser` (an employeeId, or None when no present presser was
    assignable — never in practice, since a running press always has a present
    presser to staff it). Step 66 adds `presser` as a secondary, preference-only
    assignment layered on *after* the press/part decision: it never changes what
    runs or which presses run, only who stands where."""
    date: datetime.date
    shift: int
    press: str
    part: str
    quantity: float
    hours: float
    presser: int | None = None


@dataclass(frozen=True)
class OrderFlag:
    """A flagged order (addendum §4), carrying its magnitude. Which fields are
    meaningful depends on `kind`:
      LATE                   -> daysLate (calendar days completion is past the
                                effective press-by) + piecesShort (pieces still
                                unplaced as of the deadline).
      INFEASIBLE_NO_CAPACITY -> shortHours / piecesShort the horizon couldn't
                                absorb.
      INFEASIBLE_NO_RATE     -> none (the part name is the data gap to fix)."""
    orderNum: str
    part: str
    kind: str
    daysLate: int = 0
    piecesShort: float = 0.0
    shortHours: float = 0.0


@dataclass(frozen=True)
class ScheduleWarning:
    """A soft, non-blocking warning about a part (addendum §4): a cold-start
    fallback rate, or a missing fireScrap. Deduplicated per (kind, part)."""
    kind: str
    part: str


@dataclass(frozen=True)
class ScheduleResult:
    """Everything the report (Step 53) and smoke need: the schedule rows, the
    flagged orders, the soft warnings, and the generation anchor `today`. The
    whole subsystem is stateless (spec §5.1) — this is recomputed on demand."""
    today: datetime.date
    rows: list[ScheduleRow]
    flags: list[OrderFlag]
    warnings: list[ScheduleWarning]


def outstandingToPress(db: Database, order: Order) -> int:
    """Addendum §1: the order's outstanding-to-press = its latest OrderStatus
    `remainingToPress` snapshot, falling back to the full ordered quantity when
    no snapshot exists yet (spec §5.2)."""
    status = db.orderStatus.get(order.orderNum)
    if status is not None:
        remaining = status.remainingToPress()
        if remaining is not None:
            return remaining
    return order.quantity


def _eligibleOrders(db: Database, config: ScheduleConfig) -> list[Order]:
    """Addendum §1 order eligibility, then §3.1 sequencing. An order enters the
    scheduler iff it has press work left (outstanding-to-press > 0) and isn't
    already fulfilled (remaining-to-ship 0). Eligible orders are sorted by
    (effectivePressBy, -price, orderNum): EDF first, order total breaks deadline
    ties to favor revenue (decisions #5/#6), orderNum makes it fully
    deterministic (§5). Orders with no due date have no deadline, so they sort
    after all dated orders and can never be flagged late."""
    eligible: list[Order] = []
    for order in db.orders.values():
        status = db.orderStatus.get(order.orderNum)
        if status is not None and status.isFulfilled():
            continue
        if outstandingToPress(db, order) <= 0:
            continue
        eligible.append(order)

    def sortKey(order: Order):
        deadline = effectivePressBy(db, order, config.slackBusinessDays)
        return (deadline is None, deadline or datetime.date.max, -order.price, order.orderNum)

    return sorted(eligible, key=sortKey)


def _prefScore(db: Database, part: str, press: str) -> int:
    """The part's preference score for a press, with a missing pair treated as
    the neutral midpoint (addendum §3.4 / decision #5)."""
    pref = db.partPressPref.get(part)
    if pref is None:
        return NEUTRAL_PRESS_SCORE
    score = pref.getScore(press)
    return score if score is not None else NEUTRAL_PRESS_SCORE


def _presserPrefScore(db: Database, employeeId: int, press: str, neutral: int) -> int:
    """A presser's preference score for a press, with a missing pair treated as
    `neutral` (Step 66 / §13.44) — the presser twin of `_prefScore`. The neutral
    midpoint is passed in from ScheduleConfig.presserNeutralScore rather than read
    from a module constant, so the staffing policy stays tunable behind the
    schedule() seam."""
    pref = db.presserPressPref.get(employeeId)
    if pref is None:
        return neutral
    score = pref.getScore(press)
    return score if score is not None else neutral


@dataclass
class _Lane:
    """One running press lane during press assignment: a press name plus the
    press-hours still free on it (one presser's hoursPerShift, drawn down as
    parts are pinned). Mutable, internal to `_assignLanes`."""
    press: str
    remaining: float


def _assignLanes(db: Database, shift: int, d: datetime.date,
                 placedByPart: dict[str, float], rates: dict[str, float]) -> list[ScheduleRow]:
    """Addendum §3.4: pin a shift-day's pooled (part -> press-hours) work onto
    specific press lanes, producing the (date, shift, press, part) rows.

    The lanes are the `min(present, presses)` running presses (§2.6), each with
    one presser's hoursPerShift as its budget; the budgets are the top-by-hours
    presser shifts (matching capacityHours). The presses chosen to run are the
    ones the pressed parts most prefer (highest aggregate PartPressPref score,
    press name breaking ties), paired largest-budget-first. Each part's hours are
    then placed onto lanes preferring that part's score, largest parts first,
    splitting across lanes when one lane's remaining budget is too small. This
    only decides *which lane* runs work — whether it fits was settled in §3.3
    against the pooled hours — so it never drops a piece."""
    present = pressersPresent(db, shift, d)
    lanesCount = min(len(present), len(db.presses))
    if lanesCount == 0:
        return []
    budgets = sorted((p.hoursPerShift for p in present), reverse=True)[:lanesCount]
    pressNames = sorted(db.presses.keys())

    def aggScore(press: str) -> int:
        return sum(_prefScore(db, part, press) for part in placedByPart)

    chosen = sorted(pressNames, key=lambda press: (-aggScore(press), press))[:lanesCount]
    lanes = [_Lane(press, budget) for press, budget in zip(chosen, budgets)]

    # part -> {press -> hours}
    assigned: dict[str, dict[str, float]] = {}
    for part in sorted(placedByPart, key=lambda p: (-placedByPart[p], p)):
        hoursLeft = placedByPart[part]
        while hoursLeft > EPS:
            open_lanes = [lane for lane in lanes if lane.remaining > EPS]
            if not open_lanes:
                break  # §3.3 guarantees total placed <= sum(budgets), so unreachable
            lane = min(open_lanes,
                       key=lambda lane: (-_prefScore(db, part, lane.press),
                                         -lane.remaining, lane.press))
            take = min(hoursLeft, lane.remaining)
            assigned.setdefault(part, {})
            assigned[part][lane.press] = assigned[part].get(lane.press, 0.0) + take
            lane.remaining -= take
            hoursLeft -= take

    rows: list[ScheduleRow] = []
    for part, byPress in assigned.items():
        rate = rates[part]
        for press, hours in byPress.items():
            rows.append(ScheduleRow(d, shift, press, part, hours * rate, hours))
    return rows


def _assignPressers(db: Database, shift: int, d: datetime.date,
                    rows: list[ScheduleRow], config: ScheduleConfig) -> list[ScheduleRow]:
    """Step 66 (§13.44): staff the present pressers onto the running presses of a
    shift-day — a pass secondary to the press/part decision `_assignLanes` already
    made, run once per (date, shift) over that shift-day's rows.

    Greedy max-score matching (decision 2026-07-02): score every
    (running press, present presser) pair by the presser's press preference
    (`_presserPrefScore`, missing = config.presserNeutralScore), then assign
    top-down — highest score first, press name then employeeId breaking ties —
    skipping any press or presser already taken. Each running press ends up with
    exactly one present presser; when pressers outnumber presses the surplus stay
    unassigned that shift (the rarer direction — normally pressers <= presses, so
    nobody is starved). This never changes whether or what runs, only who stands
    where: no row is added, dropped, or re-quantified — only its `presser` field
    is filled in (the rows are frozen, so it rebuilds them via `replace`)."""
    if config.presserAssignment != PRESSER_ASSIGNMENT_PREFERENCE:
        raise NotImplementedError(
            f"presserAssignment={config.presserAssignment!r} is reserved but not "
            "implemented; only 'preference' is available in v1.")
    runningPresses = sorted({r.press for r in rows})
    presserIds = sorted(p.employeeId for p in pressersPresent(db, shift, d))

    # All (press, presser) pairs, best score first; ties broken deterministically
    # by press name then employeeId so a re-run staffs the same crew identically
    # (§5 determinism).
    pairs = sorted(
        ((press, empId) for press in runningPresses for empId in presserIds),
        key=lambda pe: (-_presserPrefScore(db, pe[1], pe[0], config.presserNeutralScore),
                        pe[0], pe[1]))
    pressToPresser: dict[str, int] = {}
    takenPressers: set[int] = set()
    for press, empId in pairs:
        if press in pressToPresser or empId in takenPressers:
            continue
        pressToPresser[press] = empId
        takenPressers.add(empId)

    return [replace(r, presser=pressToPresser.get(r.press)) for r in rows]


def schedule(db: Database, today: datetime.date | None = None,
             config: ScheduleConfig | None = None) -> ScheduleResult:
    """Addendum §3-§4: the greedy earliest-deadline-first, front-loaded scheduler.

    Walks eligible orders by urgency (§3.1) and places each one's scrap-inflated
    press demand into the earliest available shift-day capacity (§3.3), front to
    back from `today`. An order that can't finish before its effective press-by
    keeps getting placed into later working shift-days and is flagged LATE; one
    that can't fit even by the horizon is flagged INFEASIBLE_NO_CAPACITY; a part
    with no usable rate is flagged INFEASIBLE_NO_RATE. Nothing is ever silently
    dropped (§4 never-drop). A second pass pins each shift-day's pooled work onto
    specific press lanes (§3.4), then a third staffs the present pressers onto
    those lanes by presser->press preference (Step 66, secondary to the press
    decision). Deterministic given (db, today, config)."""
    if today is None:
        today = datetime.date.today()
    if config is None:
        config = ScheduleConfig()

    flags: list[OrderFlag] = []
    warnings: set[ScheduleWarning] = set()
    rates: dict[str, float] = {}
    # (date, shift) -> {part -> press-hours placed}
    placed: dict[tuple[datetime.date, int], dict[str, float]] = {}
    # (date, shift) -> remaining press-hours, computed lazily from capacityHours.
    remaining: dict[tuple[datetime.date, int], float] = {}

    def remainingHours(d: datetime.date, shift: int) -> float:
        key = (d, shift)
        if key not in remaining:
            remaining[key] = capacityHours(db, shift, d)
        return remaining[key]

    for order in _eligibleOrders(db, config):
        part = order.part
        rate = pressingRate(db, part, today, config.rateWindowDays, config.rateMinHours)
        if rate is None:
            flags.append(OrderFlag(order.orderNum, part, INFEASIBLE_NO_RATE))
            continue
        # Soft warnings: a cold-start fallback rate, and a missing fireScrap
        # (under-pressing a genuinely-scrapping part is the made-visible cost).
        if empiricalPressingRate(db, part, today, config.rateWindowDays,
                                 config.rateMinHours) is None:
            warnings.add(ScheduleWarning(WARN_FALLBACK_RATE, part))
        part_obj = db.parts.get(part)
        if part_obj is not None and part_obj.fireScrap is None:
            warnings.add(ScheduleWarning(WARN_MISSING_FIRESCRAP, part))

        needHours = requiredPressed(db, part, outstandingToPress(db, order)) / rate
        deadline = effectivePressBy(db, order, config.slackBusinessDays)
        lateRecorded = False
        piecesShortAtDeadline = 0.0
        completion: datetime.date | None = None

        for offset in range(config.maxHorizonDays + 1):
            if needHours <= EPS:
                break
            d = today + datetime.timedelta(days=offset)
            for shift in SHIFTS:
                if needHours <= EPS:
                    break
                # Crossed the deadline with work still to place -> LATE; capture
                # the pieces that will land late (everything not yet placed on or
                # before the deadline) before placing any of it.
                if deadline is not None and d > deadline and not lateRecorded:
                    lateRecorded = True
                    piecesShortAtDeadline = needHours * rate
                avail = remainingHours(d, shift)
                if avail <= EPS:
                    continue
                take = min(needHours, avail)
                cell = placed.setdefault((d, shift), {})
                cell[part] = cell.get(part, 0.0) + take
                remaining[(d, shift)] = avail - take
                rates[part] = rate
                needHours -= take
                completion = d

        if needHours > EPS:
            # Hit the horizon with demand unplaced — capacity, not just lateness.
            flags.append(OrderFlag(order.orderNum, part, INFEASIBLE_NO_CAPACITY,
                                   piecesShort=needHours * rate, shortHours=needHours))
        elif lateRecorded and completion is not None and deadline is not None:
            flags.append(OrderFlag(order.orderNum, part, LATE,
                                   daysLate=(completion - deadline).days,
                                   piecesShort=piecesShortAtDeadline))

    rows: list[ScheduleRow] = []
    for (d, shift), placedByPart in placed.items():
        laneRows = _assignLanes(db, shift, d, placedByPart, rates)
        # Step 66: staff pressers onto the lanes this shift-day just fixed
        # (secondary to the part-preference lane decision, which stays untouched).
        rows.extend(_assignPressers(db, shift, d, laneRows, config))

    rows.sort(key=lambda r: (r.date, r.shift, r.press, r.part))
    flags.sort(key=lambda f: (f.kind, f.orderNum))
    sortedWarnings = sorted(warnings, key=lambda w: (w.kind, w.part))
    return ScheduleResult(today, rows, flags, sortedWarnings)


# ---------------------------------------------------------------------------
# Step 67: report-view helpers (§13.44). Pure, deterministic operations over a
# computed ScheduleResult — the per-shift / date-range variants and the
# date/shift-grouped layout are *view slices* of an already-computed schedule,
# never a re-run of the scheduler (shortening the horizon would corrupt
# placement and misflag capacity). Shared by schedule_tab.py and
# report/scheduling.py so the on-screen table and the PDF read identically.
# ---------------------------------------------------------------------------

# Abbreviated weekday names indexed by date.weekday() (Mon=0). A fixed table,
# not strftime("%a"), so the group headings are locale-independent / deterministic.
_GROUP_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def filterSchedule(result: ScheduleResult, shift: int | None = None,
                   start: datetime.date | None = None,
                   end: datetime.date | None = None) -> ScheduleResult:
    """A view slice of a computed schedule for the Step 67 per-shift / date-range
    report variants: keep only rows matching `shift` (when given) and falling in
    [`start`, `end`] inclusive (each bound open when None). Flags and warnings are
    order-level / dateless, so they pass through **unfiltered** — a filtered view
    must never hide a late or infeasible order (design call 2026-07-02). Slices
    the result, never re-runs the scheduler, so `today` is preserved."""
    rows = [r for r in result.rows
            if (shift is None or r.shift == shift)
            and (start is None or r.date >= start)
            and (end is None or r.date <= end)]
    return ScheduleResult(result.today, rows, result.flags, result.warnings)


def groupScheduleRows(
        rows: list[ScheduleRow]) -> list[tuple[tuple[datetime.date, int], list[ScheduleRow]]]:
    """Group schedule rows into ordered (date, shift) buckets for the grouped
    report/tab layout (Step 67), where Date and Shift move from repeated columns
    into a group heading. Assumes `rows` is sorted by (date, shift, ...) the way
    `schedule()` emits them (and `filterSchedule` preserves), so equal keys are
    contiguous and the buckets come out chronologically."""
    groups: list[tuple[tuple[datetime.date, int], list[ScheduleRow]]] = []
    for r in rows:
        key = (r.date, r.shift)
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(r)
    return groups


def scheduleGroupHeading(d: datetime.date, shift: int) -> str:
    """The subheading for one (date, shift) group (Step 67): weekday + ISO date +
    shift, e.g. 'Mon 2026-07-06 — Shift 1'. Used verbatim by both the on-screen
    group labels and the PDF subheadings so they stay identical."""
    return f"{_GROUP_WEEKDAYS[d.weekday()]} {d.isoformat()} — Shift {shift}"


def scheduleFilterDescription(shift: int | None, start: datetime.date | None,
                              end: datetime.date | None) -> str:
    """A human-readable description of an active filter (Step 67) for the status
    line and the filtered-PDF subtitle, e.g. 'Shift 3, 2026-07-06 to 2026-07-08'
    or 'All shifts'. A date bound shown as '…' when open-ended."""
    parts = [f"Shift {shift}" if shift is not None else "All shifts"]
    if start is not None or end is not None:
        lo = start.isoformat() if start is not None else "…"
        hi = end.isoformat() if end is not None else "…"
        parts.append(f"{lo} to {hi}")
    return ", ".join(parts)
