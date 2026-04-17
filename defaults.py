import datetime

TRAINING: list[str] = [
    "Orientation",
    "PPE",
    "Respiratory",
    "Lock Out/Tag Out",
    "Hearing Conservation",
    "Emergency Response",
    "Hazardous Communication",
    "Forklift"
]

REVIEW_DATES = [
    datetime.timedelta(days=30),
    datetime.timedelta(days=60),
    datetime.timedelta(days=90),
    datetime.timedelta(days=365)
]

POINT_VALS: dict[str, float] = {
    "Absence": 1,
    "Absence, no call": 2,
    "Tardy": 0.5,
    "Early departure": 0.5,
    "2+ hours missed": 1
}

HOLIDAYS: list[str] = [
    "New Years Day",
    "Presidents Day",
    "Memorial Day",
    "Independence Day",
    "Labor Day",
    "Thanksgiving",
    "Thanksgiving Morrow",
    "Christmas Eve",
    "Christmas Day",
    "New Years Eve"
]

PTO_ELIGIBILITY = 90