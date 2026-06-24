# Sales subsystem record classes (spec §3, MERGE_PLAN §13.30). Aggregated into
# Database behind the records/ re-export shim, alongside the scheduling records
# (records/scheduling.py). The remaining sales record type (OrderStatus) lands
# here in Step 49.

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
