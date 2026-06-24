# Production Scheduling subsystem record classes (spec §3, MERGE_PLAN §13.30).
# Aggregated into Database behind the records/ re-export shim. New scheduling
# record types (ShiftWorkweek, PartPressPref) land here in later steps.


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
