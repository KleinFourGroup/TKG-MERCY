# Production Scheduling subsystem record classes (spec §3, MERGE_PLAN §13.30).
# Aggregated into Database behind the records/ re-export shim. New scheduling
# record types (PartPressPref) land here in later steps.

# The three production shifts are fixed (matching Employee.shift, observances,
# and production — all of which use 1/2/3); nobody creates or deletes a shift.
SHIFTS = (1, 2, 3)


class Press:
    # A press on the shop floor, keyed by its unique name (spec §3.3). A flat
    # reference record: nothing is computed from a Press, so it carries no `db`
    # back-reference — it's just a name the scheduler assigns pressing work to.
    def __init__(self, name) -> None:
        self.name = name

    def getTuple(self):
        return (self.name,)

    def fromTuple(self, values):
        self.name = values[0]

    def __str__(self) -> str:
        return "({})".format(self.name)


class Presser:
    # An employee who presses, plus their per-shift press capacity (spec §3.1).
    # Keyed by employeeId (FK -> employees.idNum) — an "is-a-presser" flag plus a
    # capacity number layered onto an existing employee. The presser's shift comes
    # from Employee.shift (one shift per employee), so it isn't stored here. Like
    # Press, a flat reference record with no `db` back-reference.
    def __init__(self, employeeId, hoursPerShift=0.0) -> None:
        self.employeeId = employeeId
        self.hoursPerShift = hoursPerShift

    def getTuple(self):
        return (self.employeeId, self.hoursPerShift)

    def fromTuple(self, values):
        self.employeeId = values[0]
        self.hoursPerShift = values[1]

    def __str__(self) -> str:
        return "({}, {})".format(self.employeeId, self.hoursPerShift)


class ShiftWorkweek:
    # Which weekdays a single shift normally works (spec §3.2). Presence-based:
    # `days` holds the weekday integers the shift works (Mon=0..Sun=6, matching
    # date.weekday() so Step 51's shift-works-on-date helper can compare directly);
    # a weekday's absence means the shift is off that day. One ShiftWorkweek per
    # shift, and the three shifts are fixed (see SHIFTS). Stable over time — no
    # effective-dating in v1. Like Press/Presser, a flat reference record with no
    # `db` back-reference. Persisted as one (shift, weekday) row per working day in
    # the `shift_workweek` table, so a shift with no working days has no rows.
    def __init__(self, shift, days=None) -> None:
        self.shift = shift
        self.days: set[int] = set(days) if days is not None else set()

    def worksOn(self, weekday) -> bool:
        return weekday in self.days

    def setDay(self, weekday, working) -> None:
        if working:
            self.days.add(weekday)
        else:
            self.days.discard(weekday)

    def getTuples(self):
        # One (shift, weekday) presence row per working day, weekday-sorted.
        return [(self.shift, weekday) for weekday in sorted(self.days)]

    def __str__(self) -> str:
        return "({}, {})".format(self.shift, sorted(self.days))
