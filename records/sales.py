# Sales subsystem record classes (spec §3, MERGE_PLAN §13.30). Aggregated into
# Database behind the records/ re-export shim, alongside the scheduling records
# (records/scheduling.py).

import datetime


def orderNumInitials(name):
    # Initials for an order-number prefix: first alphanumeric char of each
    # whitespace token, uppercased ("Acme Ceramics" -> "AC", "Insulator X1" ->
    # "IX"). Falls back to "X" so a blank/odd name still yields a usable prefix.
    tokens = [t for t in str(name).split() if t]
    initials = "".join(t[0] for t in tokens if t[0].isalnum()).upper()
    return initials or "X"


def formatOrderNum(client, part, digits):
    # Compose the suggested order number {clientInitials}-{partInitials}-{NNNNNN}.
    # `digits` is an int 0..999999, zero-padded to six. Authoritative format used
    # by both the Orders tab's auto-suggest and fuzz_db, so they never drift.
    return f"{orderNumInitials(client)}-{orderNumInitials(part)}-{digits:06d}"


class Client:
    # A customer that places orders (spec §3.5), keyed by its unique name. The
    # only other field is transportDays — typical shipment transit in *business
    # days* (a carrier's Mon–Fri shipping calendar excluding holidays, distinct
    # from the shop's shift workweek), one constant per client. The scheduler uses
    # it to back an order's ship-by date out of its due date
    # (ship-by = due − transportDays). A whole number of days; 0 is legal (a local
    # client shipped the same day it's due). Like the scheduling records, a flat
    # reference record with no `db` back-reference.
    def __init__(self, name, transportDays=0) -> None:
        self.name = name
        self.transportDays = transportDays

    def getTuple(self):
        return (self.name, self.transportDays)

    def fromTuple(self, values):
        self.name = values[0]
        self.transportDays = values[1]

    def __str__(self) -> str:
        return "({}, {})".format(self.name, self.transportDays)


class Order:
    # A shop order (spec §3.6): exactly one part for one client, keyed by a unique
    # orderNum (a free-text code, auto-suggested as {client}-{part}-{6 digits} but
    # user-editable). `client` and `part` are FK names into Database.clients /
    # Database.parts. `price` is the ORDER TOTAL, not per-unit (decision #6), so an
    # order's value is its price with no quantity multiply. `dueDate` is when the
    # customer needs the parts in hand; the scheduler backs out the ship-by date as
    # dueDate - client.transportDays. Flat reference record, no `db` back-ref.
    def __init__(self, orderNum, client="", part="", quantity=0, price=0.0, dueDate=None) -> None:
        self.orderNum = orderNum
        self.client = client
        self.part = part
        self.quantity = quantity
        self.price = price
        self.dueDate: datetime.date | None = dueDate

    def getTuple(self):
        return (self.orderNum, self.client, self.part, self.quantity, self.price,
                self.dueDate.isoformat() if self.dueDate is not None else None)

    def fromTuple(self, values):
        self.orderNum = values[0]
        self.client = values[1]
        self.part = values[2]
        self.quantity = values[3]
        self.price = values[4]
        self.dueDate = datetime.date.fromisoformat(values[5]) if values[5] is not None else None

    def __str__(self) -> str:
        due = self.dueDate.isoformat() if self.dueDate is not None else "?"
        return "({}, {}, {}, qty={}, ${}, due {})".format(
            self.orderNum, self.client, self.part, self.quantity, self.price, due)


class OrderStatus:
    # One order's dated status snapshots (spec §3.7). `snapshots` maps a date to
    # its (remainingToPress, remainingToShip) pair — the quantity still left to
    # press and still left to ship as of that date. The two are *independent*: one
    # feeds the scheduler (press), the other tracks fulfillment (ship). The latest
    # snapshot by date is the current state, so correcting a value just means adding
    # (or replacing) a newer-dated snapshot; an order with no snapshots simply has
    # no OrderStatus, and its outstanding-to-press defaults to the full ordered
    # quantity (spec §5.2). Persisted as one
    # (orderNum, date, remainingToPress, remainingToShip) row per snapshot in the
    # `order_status` table — the nested-relational shape, mirroring how PartPressPref
    # stores one (part, press, score) row per scored press. The tuple is an internal
    # storage detail; call sites go through the named accessors below. Like the other
    # sales records, a flat reference record with no `db` back-reference.
    def __init__(self, orderNum, snapshots=None) -> None:
        self.orderNum = orderNum
        # date -> (remainingToPress, remainingToShip)
        self.snapshots: dict[datetime.date, tuple[int, int]] = (
            dict(snapshots) if snapshots is not None else {})

    def setSnapshot(self, date, remainingToPress, remainingToShip) -> None:
        # Add or replace the snapshot for `date`. One snapshot per date
        # (UNIQUE(orderNum, date)), so re-setting an existing date overwrites it.
        self.snapshots[date] = (remainingToPress, remainingToShip)

    def removeSnapshot(self, date) -> None:
        self.snapshots.pop(date, None)

    def latestDate(self):
        # The most recent snapshot's date, or None if there are no snapshots yet.
        return max(self.snapshots) if self.snapshots else None

    def latest(self):
        # The most recent (remainingToPress, remainingToShip) pair (latest-by-date
        # wins, spec §3.7), or None if there are no snapshots yet.
        date = self.latestDate()
        return self.snapshots[date] if date is not None else None

    def remainingToPress(self):
        # Current quantity still to press (the scheduler's "outstanding to press"),
        # or None if no snapshot has been recorded yet (caller falls back to the
        # full ordered quantity per spec §5.2).
        latest = self.latest()
        return latest[0] if latest is not None else None

    def remainingToShip(self):
        # Current quantity still to ship, or None if no snapshot recorded yet.
        latest = self.latest()
        return latest[1] if latest is not None else None

    def isFulfilled(self) -> bool:
        # An order is fulfilled when its latest remaining-to-ship reaches 0
        # (spec §3.7). No snapshots => not yet fulfilled.
        ship = self.remainingToShip()
        return ship is not None and ship <= 0

    def getTuples(self):
        # One (orderNum, date, remainingToPress, remainingToShip) row per snapshot,
        # date-sorted — the persistence shape.
        return [(self.orderNum, date.isoformat(),
                 self.snapshots[date][0], self.snapshots[date][1])
                for date in sorted(self.snapshots)]

    def __str__(self) -> str:
        return "({}, {})".format(self.orderNum, sorted(self.snapshots.items()))
