# Sales subsystem record classes (spec §3, MERGE_PLAN §13.30). Aggregated into
# Database behind the records/ re-export shim, alongside the scheduling records
# (records/scheduling.py). The remaining sales record types (Order, OrderStatus)
# land here in Steps 47 / 49.


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
