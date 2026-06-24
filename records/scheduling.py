# Production Scheduling subsystem record classes (spec §3, MERGE_PLAN §13.30).
# Aggregated into Database behind the records/ re-export shim. New scheduling
# record types (Presser, ShiftWorkweek, PartPressPref) land here in later steps.


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
