# Production Scheduling subsystem record classes (spec §3, MERGE_PLAN §13.30).
# Aggregated into Database behind the records/ re-export shim.

# The three production shifts are fixed (matching Employee.shift, observances,
# and production — all of which use 1/2/3); nobody creates or deletes a shift.
SHIFTS = (1, 2, 3)

# Part-press preference scores run 1 (lowest) to 5 (highest); a missing
# (part, press) pair means *neutral*, not "cannot press here" (spec §3.4).
MIN_PRESS_SCORE = 1
MAX_PRESS_SCORE = 5


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


class PartPressPref:
    # One part's scored press preferences (spec §3.4). `scores` maps a press name
    # to its preference score (MIN_PRESS_SCORE..MAX_PRESS_SCORE); a press absent
    # from the dict is *neutral* (the missing-pair-is-neutral rule), so a part
    # with no scored presses simply has no PartPressPref. The score is a pure
    # assignment tiebreaker — it does not affect throughput in v1. Like the other
    # scheduling records, a flat reference record with no `db` back-reference.
    # Persisted as one (part, press, score) row per scored press in the
    # `part_press_pref` table — the nested-relational shape, mirroring how
    # ShiftWorkweek stores one (shift, weekday) row per working day.
    def __init__(self, part, scores=None) -> None:
        self.part = part
        self.scores: dict[str, int] = dict(scores) if scores is not None else {}

    def getScore(self, press):
        # The press's score, or None if neutral (no entry).
        return self.scores.get(press)

    def setScore(self, press, score) -> None:
        # Set or clear one press's score. A None / 0 score clears it back to
        # neutral (drops the entry), keeping `scores` free of neutral pairs so
        # the presence-row persistence stays in lockstep.
        if score is None or score == 0:
            self.scores.pop(press, None)
        else:
            self.scores[press] = score

    def getTuples(self):
        # One (part, press, score) row per scored press, press-name-sorted.
        return [(self.part, press, self.scores[press]) for press in sorted(self.scores)]

    def __str__(self) -> str:
        return "({}, {})".format(self.part, sorted(self.scores.items()))


class PresserPressPref:
    # One presser's scored press preferences (Step 65, MERGE_PLAN §13.44). The exact
    # twin of PartPressPref, but keyed by employeeId (FK -> employees.idNum / the
    # presser's PK) instead of part name: any presser can work any press but they
    # specialize, so `scores` maps a press name to a preference score
    # (MIN_PRESS_SCORE..MAX_PRESS_SCORE); a press absent from the dict is *neutral*
    # (the missing-pair-is-neutral rule), so a presser with no scored presses simply
    # has no PresserPressPref. Like part-press preference the score is a pure
    # assignment tiebreaker — it does not affect throughput in v1 (Step 66 consumes
    # it to staff pressers onto the already-decided press work). A flat reference
    # record with no `db` back-reference. Persisted as one (employeeId, press, score)
    # row per scored press in the `presser_press_pref` table — the nested-relational
    # shape, mirroring part_press_pref.
    def __init__(self, employeeId, scores=None) -> None:
        self.employeeId = employeeId
        self.scores: dict[str, int] = dict(scores) if scores is not None else {}

    def getScore(self, press):
        # The press's score, or None if neutral (no entry).
        return self.scores.get(press)

    def setScore(self, press, score) -> None:
        # Set or clear one press's score. A None / 0 score clears it back to
        # neutral (drops the entry), keeping `scores` free of neutral pairs so
        # the presence-row persistence stays in lockstep.
        if score is None or score == 0:
            self.scores.pop(press, None)
        else:
            self.scores[press] = score

    def getTuples(self):
        # One (employeeId, press, score) row per scored press, press-name-sorted.
        return [(self.employeeId, press, self.scores[press]) for press in sorted(self.scores)]

    def __str__(self) -> str:
        return "({}, {})".format(self.employeeId, sorted(self.scores.items()))


class PartTruck:
    # One part's parts-per-truck figure (Step 74a, MERGE_PLAN §13.46). Keyed by part
    # name (FK -> parts), `partsPerTruck` is how many finished pieces fill one truck.
    # It's a data-entry convenience consumed by the Order Status trucks-mode input
    # (Step 74b): a remaining-to-press / -ship figure entered in trucks is multiplied
    # by this to store pieces (everything stays stored + displayed in pieces). A part
    # with no figure simply has no PartTruck (missing = unset), so trucks-mode entry
    # is blocked until one is set. Structurally the scalar twin of Presser — a keyed
    # field plus one value column, not the nested-relational scores dict of
    # PartPressPref. Like the other scheduling records, a flat reference record with no
    # `db` back-reference. Persisted as one (part, partsPerTruck) row in the
    # `part_truck` table.
    def __init__(self, part, partsPerTruck=None) -> None:
        self.part = part
        self.partsPerTruck = partsPerTruck

    def getTuple(self):
        return (self.part, self.partsPerTruck)

    def fromTuple(self, values):
        self.part = values[0]
        self.partsPerTruck = values[1]

    def __str__(self) -> str:
        return "({}, {})".format(self.part, self.partsPerTruck)
