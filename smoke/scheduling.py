"""Step 51: deterministic checks for the production-scheduling primitives in
[`scheduling.py`](../scheduling.py) (algorithm addendum §2).

Each primitive gets a hand-built `Database` fixture with exactly the data it
reads, so expected values are exact — no Qt, no file I/O, no fuzz. A final
``scheduling_primitives_fuzz`` runs every primitive over a tiny fuzzed DB and
asserts only invariants (no crash, sane ranges), the Step-35 "render against
fuzzed data" spirit applied to logic instead of reports.
"""
import datetime


def _expect(errors: list[str], label: str, got, expected) -> None:
    if got != expected:
        errors.append(f"{label}: expected {expected!r}, got {got!r}")


def _findMonday() -> datetime.date:
    """A real Monday, found by walking forward from a fixed anchor — so the
    fixtures derive weekday-specific dates without hardcoding (and miscounting)
    a calendar weekday."""
    d = datetime.date(2026, 1, 5)
    while d.weekday() != 0:
        d += datetime.timedelta(days=1)
    return d


def scheduling_working_days() -> list[str]:
    """shiftWorksOn: workweek membership, weekend exclusion, shift-specific
    holiday closure, and the no-workweek-entry shift (never works)."""
    from records.database import emptyDB
    from records.employees import HolidayObservance
    import scheduling as S

    errors: list[str] = []
    db = emptyDB()
    monday = _findMonday()
    day = datetime.timedelta(days=1)
    friday = monday + 4 * day
    saturday = monday + 5 * day
    sunday = monday + 6 * day

    # Shifts 1 and 2 both work Mon-Fri; shift 3 has no workweek entry at all.
    for weekday in range(5):
        db.setShiftWorkday(1, weekday, True)
        db.setShiftWorkday(2, weekday, True)
    # Only shift 1 observes Independence Day, landed on a Friday (a working
    # weekday) so the closure is isolated from the weekend rule.
    db.holidays.setObservance(HolidayObservance("Independence Day", friday, 1))

    _expect(errors, "shift1 Monday", S.shiftWorksOn(db, 1, monday), True)
    _expect(errors, "shift1 Saturday (weekend)", S.shiftWorksOn(db, 1, saturday), False)
    _expect(errors, "shift1 Sunday (weekend)", S.shiftWorksOn(db, 1, sunday), False)
    _expect(errors, "shift1 holiday Friday (closed)", S.shiftWorksOn(db, 1, friday), False)
    # Shift 2 doesn't observe the holiday -> still open that Friday (proves the
    # observance check is per-shift, not global).
    _expect(errors, "shift2 holiday Friday (open, not observed)", S.shiftWorksOn(db, 2, friday), True)
    _expect(errors, "shift3 Monday (no workweek)", S.shiftWorksOn(db, 3, monday), False)
    return errors


def scheduling_presser_capacity() -> list[str]:
    """onPTO / pressersPresent / concurrentPresses / capacityHours: active-only,
    PTO-day removal (with CARRY sentinel skipped), idle presses (pressers <
    presses), the non-working-day zero, and top-by-hours lane selection when
    pressers > presses."""
    from records.database import emptyDB
    from records.employees import Employee, EmployeePTODB, EmployeePTORange
    from records.scheduling import Press, Presser
    import scheduling as S

    errors: list[str] = []
    db = emptyDB()
    monday = _findMonday()
    day = datetime.timedelta(days=1)
    tuesday = monday + day
    sunday = monday + 6 * day

    db.setShiftWorkday(1, 0, True)  # shift 1 works Mon
    db.setShiftWorkday(1, 1, True)  # ...and Tue
    db.setShiftWorkday(2, 0, True)  # shift 2 works Mon
    for name in ("P1", "P2", "P3"):
        db.addPress(Press(name))

    def addEmp(idn: int, shift: int, status: bool) -> None:
        e = Employee()
        e.idNum = idn
        e.lastName = "L"
        e.firstName = "F"
        e.shift = shift
        e.status = status
        db.addEmployee(e)

    addEmp(10, 1, True)
    addEmp(11, 1, True)
    addEmp(12, 2, True)
    addEmp(13, 1, False)  # inactive -> never present
    db.addPresser(Presser(10, 8.0))
    db.addPresser(Presser(11, 6.0))
    db.addPresser(Presser(12, 7.0))
    db.addPresser(Presser(13, 9.0))

    # Emp 11 is out on Monday only; a CARRY sentinel row must be ignored.
    pto = EmployeePTODB(11)
    pto.PTO[(monday, monday)] = EmployeePTORange(11, monday, monday, 8.0)
    jan1 = datetime.date(monday.year, 1, 1)
    pto.PTO[(jan1, "CARRY")] = EmployeePTORange(11, jan1, "CARRY", 0.0)
    db.PTO[11] = pto

    _expect(errors, "onPTO 11 Monday", S.onPTO(db, 11, monday), True)
    _expect(errors, "onPTO 11 Tuesday", S.onPTO(db, 11, tuesday), False)
    _expect(errors, "onPTO 10 Monday (no PTO db)", S.onPTO(db, 10, monday), False)

    _expect(errors, "present shift1 Monday",
            {p.employeeId for p in S.pressersPresent(db, 1, monday)}, {10})
    _expect(errors, "present shift1 Tuesday",
            {p.employeeId for p in S.pressersPresent(db, 1, tuesday)}, {10, 11})
    _expect(errors, "present shift2 Monday",
            {p.employeeId for p in S.pressersPresent(db, 2, monday)}, {12})

    _expect(errors, "concurrent shift1 Monday (idle presses)", S.concurrentPresses(db, 1, monday), 1)
    _expect(errors, "concurrent shift1 Tuesday", S.concurrentPresses(db, 1, tuesday), 2)
    _expect(errors, "concurrent shift1 Sunday (non-working)", S.concurrentPresses(db, 1, sunday), 0)

    _expect(errors, "capacity shift1 Monday", S.capacityHours(db, 1, monday), 8.0)
    _expect(errors, "capacity shift1 Tuesday", S.capacityHours(db, 1, tuesday), 14.0)
    _expect(errors, "capacity shift1 Sunday (non-working)", S.capacityHours(db, 1, sunday), 0.0)
    _expect(errors, "capacity shift2 Monday", S.capacityHours(db, 2, monday), 7.0)

    # Pressers > presses: one press, three present pressers -> one lane, taking
    # the highest hoursPerShift (9.0).
    db2 = emptyDB()
    db2.setShiftWorkday(1, 0, True)
    db2.addPress(Press("Only1"))
    for idn, hrs in ((20, 8.0), (21, 6.0), (22, 9.0)):
        e = Employee()
        e.idNum = idn
        e.lastName = "L"
        e.firstName = "F"
        e.shift = 1
        e.status = True
        db2.addEmployee(e)
        db2.addPresser(Presser(idn, hrs))
    _expect(errors, "concurrent pressers>presses", S.concurrentPresses(db2, 1, monday), 1)
    _expect(errors, "capacity pressers>presses (top-by-hours lane)",
            S.capacityHours(db2, 1, monday), 9.0)
    return errors


def scheduling_pressing_rate() -> list[str]:
    """pressingRate: empirical wins over fallback; thin history (< min hours)
    falls back; out-of-window records are excluded; no data and no Part.pressing
    yields None."""
    from records.database import emptyDB
    from records.products import Part
    from records.production import ProductionRecord
    import scheduling as S

    errors: list[str] = []
    db = emptyDB()
    today = datetime.date(2026, 6, 25)

    def mkpart(name: str, pressing) -> None:
        p = Part(name)
        p.setProduction(1.0, None, pressing, None, 0.05, 1.0)
        db.addPart(p)

    def addPressing(empId: int, part: str, qty: float, hours: float, ageDays: int) -> None:
        r = ProductionRecord()
        r.setRecord(empId, today - datetime.timedelta(days=ageDays), 1,
                    "Pressing", part, qty, 0, hours)
        db.production[r.key()] = r

    # Empirical (sum 300 qty / 10 hrs = 30) beats the Part.pressing fallback (5).
    mkpart("PartEmp", 5.0)
    addPressing(1, "PartEmp", 200.0, 8.0, 10)
    addPressing(2, "PartEmp", 100.0, 2.0, 12)
    _expect(errors, "rate empirical wins", S.pressingRate(db, "PartEmp", today), 30.0)

    # Thin history (1 hr < 4-hr minimum) -> fall back to Part.pressing (7).
    mkpart("PartThin", 7.0)
    addPressing(1, "PartThin", 50.0, 1.0, 5)
    _expect(errors, "rate thin history -> fallback", S.pressingRate(db, "PartThin", today), 7.0)

    # Window: an in-window record (rate 20) plus a huge record 200 days back that
    # must be excluded by the 180-day window.
    mkpart("PartWin", 99.0)
    addPressing(1, "PartWin", 400.0, 20.0, 10)
    addPressing(2, "PartWin", 99999.0, 1.0, 200)
    _expect(errors, "rate window excludes old", S.pressingRate(db, "PartWin", today), 20.0)

    # No history, no Part.pressing -> None (the order is infeasible, never silent).
    mkpart("PartNo", None)
    _expect(errors, "rate none available", S.pressingRate(db, "PartNo", today), None)
    return errors


def scheduling_scrap_inflation() -> list[str]:
    """requiredPressed: multiplicative inflation, the greenScrap percent->fraction
    conversion, missing fireScrap treated as 0, ceil rounding, and the >=100%
    clamp (no divide-by-zero)."""
    from records.database import emptyDB
    from records.products import Part
    import scheduling as S

    errors: list[str] = []
    db = emptyDB()

    def mkpart(name: str, fire) -> None:
        p = Part(name)
        p.setProduction(1.0, None, 5.0, None, fire, 1.0)
        db.addPart(p)

    mkpart("F0", 0.0)
    mkpart("F50", 0.5)
    mkpart("Fnone", None)
    mkpart("F10", 0.1)

    db.globals.greenScrap = 0.0
    _expect(errors, "scrap none", S.requiredPressed(db, "F0", 100), 100)
    _expect(errors, "scrap fire 50%", S.requiredPressed(db, "F50", 100), 200)
    _expect(errors, "scrap missing fire -> 0", S.requiredPressed(db, "Fnone", 100), 100)
    _expect(errors, "scrap ceil rounds up", S.requiredPressed(db, "F10", 10), 12)  # 10/0.9 = 11.11

    db.globals.greenScrap = 50.0  # 50% -> /0.5 (proves the percent conversion)
    _expect(errors, "scrap green 50%", S.requiredPressed(db, "F0", 100), 200)
    _expect(errors, "scrap green+fire 50%", S.requiredPressed(db, "F50", 100), 400)

    db.globals.greenScrap = 100.0  # clamped to 0.999 -> finite, no ZeroDivision
    _expect(errors, "scrap >=100% clamped", S.requiredPressed(db, "F0", 1), 1000)
    return errors


def scheduling_deadlines() -> list[str]:
    """subBusinessDays / shipBy / effectivePressBy: weekend skipping, the n<=0
    pass-through, transport back-out, missing-client and no-due-date handling,
    and the slack pull-in."""
    from records.database import emptyDB
    from records.sales import Client, Order
    import scheduling as S

    errors: list[str] = []
    monday = _findMonday()
    day = datetime.timedelta(days=1)
    friday = monday + 4 * day
    saturday = monday + 5 * day

    # 1 business day before Monday is the previous Friday (skips the weekend).
    _expect(errors, "subBiz Monday-1 -> prev Friday", S.subBusinessDays(monday, 1), monday - 3 * day)
    # 5 business days before Monday is the previous Monday.
    _expect(errors, "subBiz Monday-5 -> prev Monday", S.subBusinessDays(monday, 5), monday - 7 * day)
    # Within a week, no weekend crossed.
    _expect(errors, "subBiz Friday-1 -> Thursday", S.subBusinessDays(friday, 1), friday - day)
    # n<=0 returns the date unchanged, even on a weekend.
    _expect(errors, "subBiz n=0 on Saturday", S.subBusinessDays(saturday, 0), saturday)
    _expect(errors, "subBiz n=0 on Monday", S.subBusinessDays(monday, 0), monday)

    db = emptyDB()
    db.addClient(Client("ClientA", 1))  # 1 transport business day
    order = Order("O1", "ClientA", "PartA", 100, 50.0, monday)
    db.addOrder(order)
    _expect(errors, "shipBy (transport 1)", S.shipBy(db, order), monday - 3 * day)

    missingClient = Order("O2", "NoSuchClient", "PartA", 1, 1.0, monday)
    _expect(errors, "shipBy missing client -> transport 0", S.shipBy(db, missingClient), monday)

    noDue = Order("O3", "ClientA", "PartA", 1, 1.0, None)
    _expect(errors, "shipBy no due date -> None", S.shipBy(db, noDue), None)

    # ship-by (prev Friday) minus 2 slack business days = previous Wednesday.
    _expect(errors, "effectivePressBy (slack 2)", S.effectivePressBy(db, order), monday - 5 * day)
    _expect(errors, "effectivePressBy slack 0 == shipBy",
            S.effectivePressBy(db, order, slackBusinessDays=0), monday - 3 * day)
    _expect(errors, "effectivePressBy no due date -> None", S.effectivePressBy(db, noDue), None)
    return errors


def _addEmployee(db, idn: int, shift: int, status: bool = True) -> None:
    from records.employees import Employee
    e = Employee()
    e.idNum = idn
    e.lastName = "L"
    e.firstName = "F"
    e.shift = shift
    e.status = status
    db.addEmployee(e)


def _addPart(db, name: str, pressing, fire) -> None:
    from records.products import Part
    p = Part(name)
    p.setProduction(1.0, None, pressing, None, fire, 1.0)
    db.addPart(p)


def _rowTuples(result):
    return [(r.date, r.shift, r.press, r.part, r.quantity, r.hours) for r in result.rows]


def scheduling_scheduler() -> list[str]:
    """schedule(): the greedy EDF core (addendum §3-§4) on hand-built fixtures
    with exact expected output — front-loaded multi-day placement, the LATE flag
    + magnitude on a tight deadline, INFEASIBLE_NO_RATE on a rate-less part, the
    cold-start fallback warning, preference-ranked lane splitting (§3.4), the
    Step 66 greedy presser staffing (preference win, neutral tiebreak, preference
    beating the tiebreak), and determinism."""
    from records.database import emptyDB
    from records.scheduling import Press, Presser
    from records.sales import Client, Order
    import scheduling as S

    errors: list[str] = []
    monday = _findMonday()
    day = datetime.timedelta(days=1)
    tuesday = monday + day
    wednesday = monday + 2 * day
    friday = monday + 4 * day
    # transport 0 + slack 0 => effectivePressBy == dueDate, so the fixtures read
    # straight off the calendar.
    cfg = S.ScheduleConfig(slackBusinessDays=0)

    def base(part_pressing, part_fire, dueDate, qty=200, prefs=None, presses=("Press1",),
             pressers=((10, 8.0),)):
        db = emptyDB()
        for weekday in range(5):
            db.setShiftWorkday(1, weekday, True)
        for name in presses:
            db.addPress(Press(name))
        for idn, hrs in pressers:
            _addEmployee(db, idn, 1, True)
            db.addPresser(Presser(idn, hrs))
        _addPart(db, "P", part_pressing, part_fire)
        db.globals.greenScrap = 0.0
        db.addClient(Client("C", 0))
        db.addOrder(Order("O1", "C", "P", qty, 100.0, dueDate))
        for press, score in (prefs or {}).items():
            db.setPartPressScore("P", press, score)
        return db

    # --- A: ample deadline, one press/presser, 200 pcs @ 10/hr = 20 press-hrs over
    #        8/8/4 across Mon/Tue/Wed; finishes Wed, well before Friday -> no flags.
    dbA = base(10.0, 0.0, friday)
    rA = S.schedule(dbA, monday, cfg)
    _expect(errors, "A rows", _rowTuples(rA), [
        (monday, 1, "Press1", "P", 80.0, 8.0),
        (tuesday, 1, "Press1", "P", 80.0, 8.0),
        (wednesday, 1, "Press1", "P", 40.0, 4.0),
    ])
    _expect(errors, "A no flags", rA.flags, [])
    # P has a Part.pressing rate but no Pressing history -> cold-start fallback warning.
    _expect(errors, "A fallback warning",
            [(w.kind, w.part) for w in rA.warnings], [(S.WARN_FALLBACK_RATE, "P")])

    # --- B: same work, deadline Tuesday -> Wed's 4 press-hours land late.
    dbB = base(10.0, 0.0, tuesday)
    rB = S.schedule(dbB, monday, cfg)
    _expect(errors, "B rows (still fully placed)", _rowTuples(rB), _rowTuples(rA))
    _expect(errors, "B one flag", len(rB.flags), 1)
    if rB.flags:
        f = rB.flags[0]
        _expect(errors, "B LATE kind", f.kind, S.LATE)
        _expect(errors, "B LATE order", f.orderNum, "O1")
        _expect(errors, "B days late", f.daysLate, 1)        # Wed - Tue
        _expect(errors, "B pieces short at deadline", f.piecesShort, 40.0)

    # --- C: no empirical history AND no Part.pressing -> INFEASIBLE_NO_RATE, no rows.
    dbC = base(None, 0.0, friday)
    rC = S.schedule(dbC, monday, cfg)
    _expect(errors, "C no rows", rC.rows, [])
    _expect(errors, "C no-rate flag",
            [(f.kind, f.orderNum, f.part) for f in rC.flags],
            [(S.INFEASIBLE_NO_RATE, "O1", "P")])
    _expect(errors, "C no warnings (skipped before warn checks)", rC.warnings, [])

    # --- D: two presses, P prefers PB(5) over neutral PA(3); 100 pcs = 10 press-hrs
    #        on one Monday, capacity 16 -> PB fills first (8h), PA takes the rest (2h).
    dbD = base(10.0, 0.0, monday, qty=100, prefs={"PB": 5},
               presses=("PA", "PB"), pressers=((10, 8.0), (11, 8.0)))
    rD = S.schedule(dbD, monday, cfg)
    _expect(errors, "D preference-split rows", _rowTuples(rD), [
        (monday, 1, "PA", "P", 20.0, 2.0),
        (monday, 1, "PB", "P", 80.0, 8.0),
    ])
    _expect(errors, "D no flags", rD.flags, [])

    # --- E: 1000 pcs = 100 press-hrs but the horizon is capped at 3 days (24
    #        press-hrs) -> 76 press-hrs / 760 pcs can't fit: INFEASIBLE_NO_CAPACITY,
    #        and no LATE flag (NO_CAPACITY subsumes lateness).
    dbE = base(10.0, 0.0, friday, qty=1000)
    rE = S.schedule(dbE, monday, S.ScheduleConfig(slackBusinessDays=0, maxHorizonDays=2))
    _expect(errors, "E capped rows", len(rE.rows), 3)
    _expect(errors, "E no-capacity flag",
            [(f.kind, f.orderNum, f.piecesShort, f.shortHours) for f in rE.flags],
            [(S.INFEASIBLE_NO_CAPACITY, "O1", 760.0, 76.0)])

    # --- F: presser assignment (Step 66). Same two-press run as D (PA takes 2h,
    #        PB takes 8h); two present pressers — 10 prefers PA (5), 11 prefers
    #        PB (5). Greedy max-score staffs 10->PA and 11->PB, and the placed
    #        work (press/part/quantity/hours) is byte-identical to D — the presser
    #        pass only fills in who stands where.
    dbF = base(10.0, 0.0, monday, qty=100, prefs={"PB": 5},
               presses=("PA", "PB"), pressers=((10, 8.0), (11, 8.0)))
    dbF.setPresserPressScore(10, "PA", 5)
    dbF.setPresserPressScore(11, "PB", 5)
    rF = S.schedule(dbF, monday, cfg)
    _expect(errors, "F work unchanged by presser pass", _rowTuples(rF), [
        (monday, 1, "PA", "P", 20.0, 2.0),
        (monday, 1, "PB", "P", 80.0, 8.0),
    ])
    _expect(errors, "F presser assignment",
            [(r.press, r.presser) for r in rF.rows], [("PA", 10), ("PB", 11)])

    # --- G: all-neutral presser prefs -> the deterministic tiebreak staffs the
    #        lowest employeeId onto the alphabetically-first running press.
    dbG = base(10.0, 0.0, monday, qty=100, prefs={"PB": 5},
               presses=("PA", "PB"), pressers=((10, 8.0), (11, 8.0)))
    rG = S.schedule(dbG, monday, cfg)
    _expect(errors, "G neutral presser tiebreak",
            [(r.press, r.presser) for r in rG.rows], [("PA", 10), ("PB", 11)])

    # --- H: a strong preference overrides the neutral tiebreak — presser 11
    #        prefers PA (5) while everything else is neutral, so 11 takes PA and
    #        10 is left with PB (the inverse of G's id-order default).
    dbH = base(10.0, 0.0, monday, qty=100, prefs={"PB": 5},
               presses=("PA", "PB"), pressers=((10, 8.0), (11, 8.0)))
    dbH.setPresserPressScore(11, "PA", 5)
    rH = S.schedule(dbH, monday, cfg)
    _expect(errors, "H preference beats id tiebreak",
            [(r.press, r.presser) for r in rH.rows], [("PA", 11), ("PB", 10)])

    # --- Determinism: identical (db, today, config) -> identical result.
    _expect(errors, "deterministic", S.schedule(dbA, monday, cfg), rA)
    return errors


def scheduling_scheduler_fuzz() -> list[str]:
    """schedule() over a tiny seed=1 fuzzed DB, asserting the §4/§5 invariants:
    no crash, determinism (byte-identical on a re-run), every row on a working
    shift-day, per-(date,shift) placed press-hours never exceed capacity, every
    eligible order is accounted for (scheduled and/or flagged, never silently
    dropped), flag magnitudes are non-negative, and the Step 66 presser staffing
    (each running press staffed by one present, non-double-booked presser)."""
    import random
    from records.database import emptyDB
    import scheduling as S
    import fuzz_db as F

    errors: list[str] = []
    try:
        rng = random.Random(1)
        cfg = F.SCALES["tiny"]
        today = datetime.date(2026, 6, 25)
        db = emptyDB()

        materialNames = F.populateMaterials(db, rng, cfg["materials"])
        mixtureNames = F.populateMixtures(db, rng, cfg["mixtures"], materialNames)
        F.populatePackaging(db, rng, cfg["packaging"])
        packagingByKind = {k: [] for k in F.PACKAGING_POOL}
        for name in db.packaging:
            packagingByKind[db.packaging[name].kind].append(name)
        partNames = F.populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
        idNums = F.populateEmployees(db, rng, cfg["employees"], today)
        F.populatePTO(db, rng, idNums, today)
        F.populateHolidays(db, rng, today)
        F.populateProduction(db, rng, idNums, partNames, mixtureNames,
                             cfg["productionDays"], today)
        F.populatePresses(db, rng, cfg["presses"])
        F.populatePressers(db, rng, idNums, cfg["pressers"])
        F.populateShiftWorkweek(db, rng)
        pressNames = list(db.presses)
        F.populatePartPressPref(db, rng, partNames, pressNames)
        F.populatePresserPressPref(db, rng, list(db.pressers), pressNames)
        clientNames = F.populateClients(db, rng, cfg["clients"])
        orderNums = F.populateOrders(db, rng, clientNames, partNames, cfg["orders"], today)
        F.populateOrderStatus(db, rng, orderNums, today)

        result = S.schedule(db, today)

        # Determinism: a re-run is identical.
        if S.schedule(db, today) != result:
            errors.append("schedule not deterministic on identical (db, today)")

        # Every row lands on a working shift-day, on a real press, for a real part.
        for r in result.rows:
            if not S.shiftWorksOn(db, r.shift, r.date):
                errors.append(f"row on non-working shift-day: {r.date} shift={r.shift}")
            if r.press not in db.presses:
                errors.append(f"row on unknown press: {r.press}")
            if r.part not in db.parts:
                errors.append(f"row on unknown part: {r.part}")
            if r.hours < 0 or r.quantity < 0:
                errors.append(f"row with negative hours/qty: {r}")

        # Placed press-hours per (date, shift) never exceed that shift-day's capacity.
        byShiftDay: dict[tuple, float] = {}
        for r in result.rows:
            byShiftDay[(r.date, r.shift)] = byShiftDay.get((r.date, r.shift), 0.0) + r.hours
        for (d, shift), hours in byShiftDay.items():
            cap = S.capacityHours(db, shift, d)
            if hours > cap + 1e-6:
                errors.append(f"over capacity at {d} shift={shift}: {hours} > {cap}")

        # Every eligible order is accounted for: it has scheduled rows or a flag
        # (never silently dropped, §4). Build the eligible set the way the scheduler does.
        eligible = set()
        for num, order in db.orders.items():
            status = db.orderStatus.get(num)
            if status is not None and status.isFulfilled():
                continue
            if S.outstandingToPress(db, order) <= 0:
                continue
            eligible.add(num)
        scheduledParts = {r.part for r in result.rows}
        flaggedOrders = {f.orderNum for f in result.flags}
        for num in eligible:
            order = db.orders[num]
            if num not in flaggedOrders and order.part not in scheduledParts:
                errors.append(f"eligible order {num} neither scheduled nor flagged")

        # Flag magnitudes are non-negative; kinds are known.
        knownKinds = {S.LATE, S.INFEASIBLE_NO_CAPACITY, S.INFEASIBLE_NO_RATE}
        for f in result.flags:
            if f.kind not in knownKinds:
                errors.append(f"unknown flag kind: {f.kind}")
            if f.daysLate < 0 or f.piecesShort < 0 or f.shortHours < 0:
                errors.append(f"negative flag magnitude: {f}")

        # Step 66 presser staffing invariants. Per (date, shift): every running
        # press is staffed by exactly one present presser, all rows for the same
        # press share that presser, and no presser is double-booked across presses
        # that shift-day (surplus pressers simply go unassigned).
        presserByPress: dict[tuple, dict[str, int | None]] = {}
        for r in result.rows:
            key = (r.date, r.shift)
            byPress = presserByPress.setdefault(key, {})
            if r.press in byPress and byPress[r.press] != r.presser:
                errors.append(f"press {r.press} staffed by two pressers on {r.date} shift={r.shift}")
            byPress[r.press] = r.presser
        for (d, shift), byPress in presserByPress.items():
            presentIds = {p.employeeId for p in S.pressersPresent(db, shift, d)}
            seen: set[int] = set()
            for press, presser in byPress.items():
                if presser is None:
                    errors.append(f"running press {press} unstaffed on {d} shift={shift}")
                    continue
                if presser not in presentIds:
                    errors.append(f"presser {presser} not present on {d} shift={shift}")
                if presser in seen:
                    errors.append(f"presser {presser} double-booked on {d} shift={shift}")
                seen.add(presser)
    except Exception as e:  # noqa: BLE001 - a crash here is the failure we report
        errors.append(f"scheduler raised on fuzzed data: {e!r}")
    return errors


def scheduling_primitives_fuzz() -> list[str]:
    """Run every primitive over a tiny seed=1 fuzzed DB and assert invariants
    only — no crash, sane ranges, and the structural relations (non-working
    shift-days have zero capacity; scrap never shrinks a quantity; ship-by is on
    or before the due date; the press-by deadline is on or before ship-by)."""
    import random
    from records.database import emptyDB
    from records.scheduling import SHIFTS
    import scheduling as S
    import fuzz_db as F

    errors: list[str] = []
    try:
        rng = random.Random(1)
        cfg = F.SCALES["tiny"]
        today = datetime.date(2026, 6, 25)
        db = emptyDB()

        materialNames = F.populateMaterials(db, rng, cfg["materials"])
        mixtureNames = F.populateMixtures(db, rng, cfg["mixtures"], materialNames)
        F.populatePackaging(db, rng, cfg["packaging"])
        packagingByKind = {k: [] for k in F.PACKAGING_POOL}
        for name in db.packaging:
            packagingByKind[db.packaging[name].kind].append(name)
        partNames = F.populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
        idNums = F.populateEmployees(db, rng, cfg["employees"], today)
        F.populateReviews(db, rng, idNums, today)
        F.populateTraining(db, rng, idNums, today)
        F.populateAttendance(db, rng, idNums, today)
        F.populatePTO(db, rng, idNums, today)
        F.populateNotes(db, rng, idNums, today)
        F.populateHolidays(db, rng, today)
        F.populateProduction(db, rng, idNums, partNames, mixtureNames,
                             cfg["productionDays"], today)
        pressNames = F.populatePresses(db, rng, cfg["presses"])
        F.populatePressers(db, rng, idNums, cfg["pressers"])
        F.populateShiftWorkweek(db, rng)
        F.populatePartPressPref(db, rng, partNames, pressNames)
        clientNames = F.populateClients(db, rng, cfg["clients"])
        orderNums = F.populateOrders(db, rng, clientNames, partNames, cfg["orders"], today)
        F.populateOrderStatus(db, rng, orderNums, today)

        nPresses = len(db.presses)
        for offset in range(0, 21):
            d = today + datetime.timedelta(days=offset)
            for shift in SHIFTS:
                works = S.shiftWorksOn(db, shift, d)
                present = S.pressersPresent(db, shift, d)
                lanes = S.concurrentPresses(db, shift, d)
                hours = S.capacityHours(db, shift, d)
                if lanes < 0 or lanes > nPresses:
                    errors.append(f"concurrentPresses out of range: {lanes} (presses={nPresses}) shift={shift} {d}")
                expectedLanes = min(len(present), nPresses) if works else 0
                if lanes != expectedLanes:
                    errors.append(f"concurrentPresses {lanes} != min(present={len(present)}, presses={nPresses}) "
                                  f"or non-working zero, shift={shift} {d}")
                if hours < 0:
                    errors.append(f"capacityHours negative: {hours} shift={shift} {d}")
                if not works and (lanes != 0 or hours != 0.0):
                    errors.append(f"non-working shift-day has capacity: lanes={lanes} hours={hours} shift={shift} {d}")

        for part in partNames:
            rate = S.pressingRate(db, part, today)
            if rate is not None and rate <= 0:
                errors.append(f"pressingRate non-positive: {rate} part={part}")
            req = S.requiredPressed(db, part, 100)
            if req < 100:
                errors.append(f"requiredPressed shrank quantity: {req} < 100 part={part}")

        for num in orderNums:
            order = db.orders[num]
            ship = S.shipBy(db, order)
            press = S.effectivePressBy(db, order)
            if order.dueDate is not None:
                if ship is None or press is None:
                    errors.append(f"shipBy/effectivePressBy None for dated order {num}")
                    continue
                if ship > order.dueDate:
                    errors.append(f"shipBy {ship} after dueDate {order.dueDate} order={num}")
                if press > ship:
                    errors.append(f"effectivePressBy {press} after shipBy {ship} order={num}")

        for empId in idNums:
            S.onPTO(db, empId, today)  # must not raise
    except Exception as e:  # noqa: BLE001 - a crash here is the failure we report
        errors.append(f"primitive raised on fuzzed data: {e!r}")
    return errors
