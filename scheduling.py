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
from typing import TYPE_CHECKING

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


def pressingRate(db: Database, part: str, today: datetime.date,
                 windowDays: int = RATE_WINDOW_DAYS,
                 minHours: float = RATE_MIN_HOURS) -> float | None:
    """Addendum §2.3: per-part pieces/hour. Empirical sum(quantity)/sum(hours)
    over `Pressing` production records for `part` within the trailing `windowDays`
    (the same ratio the productivity reports use), falling back to Part.pressing
    when history is thinner than `minHours`, and None when neither is available
    (the order is then infeasible per §4 — never silently skipped)."""
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
