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
