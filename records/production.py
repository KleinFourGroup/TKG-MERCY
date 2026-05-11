import datetime
import defaults

class ProductionRecord:
    # One shift-level entry: a specific employee performed a specific action
    # against a specific part or mix on a specific day. Units are implied by
    # targetType via defaults.PRODUCTION_TARGET_UNIT.
    def __init__(self) -> None:
        self.employeeId: int | None = None
        self.date: datetime.date | None = None
        self.shift: int | None = None
        self.targetType: str | None = None  # "part" or "mix"
        self.targetName: str | None = None
        self.action: str | None = None
        self.quantity: float | None = None
        self.scrapQuantity: float = 0
        self.hours: float = 0

    def setRecord(self, employeeId: int, date: datetime.date, shift: int,
                  action: str, targetName: str,
                  quantity: float, scrapQuantity: float = 0, hours: float = 0):
        # Action picks targetType: Batching->mix, Pressing/Finishing->part,
        # Tool Change->"" (no target — scrap is also fixed at 0).
        if action not in defaults.PRODUCTION_ACTIONS:
            raise RuntimeError(f'action {action!r} not in PRODUCTION_ACTIONS')
        self.employeeId = employeeId
        self.date = date
        self.shift = shift
        self.action = action
        self.targetType = defaults.PRODUCTION_ACTION_TARGET[action]
        # For targetless actions, coerce targetName/scrap to the canonical empty-state
        # values so the natural UNIQUE key doesn't get polluted by stray UI text.
        if self.targetType == "":
            self.targetName = ""
            self.scrapQuantity = 0
        else:
            self.targetName = targetName
            self.scrapQuantity = scrapQuantity
        self.quantity = quantity
        self.hours = hours

    def key(self):
        # Matches the UNIQUE constraint on the production table.
        return (self.employeeId, self.date, self.shift,
                self.targetType, self.targetName, self.action)

    def getTuple(self):
        if self.date is None:
            raise RuntimeError('self.date is None')
        return (
            self.employeeId,
            self.date.isoformat(),
            self.shift,
            self.targetType,
            self.targetName,
            self.action,
            self.quantity,
            self.scrapQuantity,
            self.hours,
        )

    def fromTuple(self, row: tuple[int, str, int, str, str, str, float, float, float]):
        action = row[5]
        if action not in defaults.PRODUCTION_ACTIONS:
            raise RuntimeError(f'action {action!r} not in PRODUCTION_ACTIONS')
        expectedType = defaults.PRODUCTION_ACTION_TARGET[action]
        if row[3] != expectedType:
            raise RuntimeError(
                f'targetType {row[3]!r} inconsistent with action {action!r} '
                f'(expected {expectedType!r})'
            )
        self.employeeId = row[0]
        self.date = datetime.date.fromisoformat(row[1])
        self.shift = row[2]
        self.targetType = row[3]
        self.targetName = row[4]
        self.action = action
        self.quantity = row[6]
        self.scrapQuantity = row[7] if row[7] is not None else 0
        self.hours = row[8] if row[8] is not None else 0

    def __str__(self) -> str:
        dateStr = self.date.isoformat() if self.date is not None else "?"
        return (f"({self.employeeId} {dateStr} s{self.shift} {self.action} "
                f"{self.targetName} [{self.targetType}] "
                f"{self.quantity} scrap={self.scrapQuantity} hours={self.hours})")
