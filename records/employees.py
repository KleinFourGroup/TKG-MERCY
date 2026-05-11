import datetime
import defaults

class Employee:
    def __init__(self) -> None:
        self.idNum: int | None = None
        self.lastName: str | None = None
        self.firstName: str | None = None
        self.anniversary: datetime.date | None = None

        self.role: str | None = None
        self.shift: int | None = None
        self.fullTime: bool = True

        self.addressLine1: str | None = None
        self.addressLine2: str | None = None
        self.addressCity: str | None = None
        self.addressState: str | None = None
        self.addressZip: str | None = None
        self.addressTel: str | None = None
        self.addressEmail: str | None = None

        self.status: bool = True

    def setAnniversary(self, date: datetime.date):
        if date is None:
            raise RuntimeError('date is None')
        self.anniversary = date

    def setName(self, lastName: str, firstName: str):
        if lastName is None:
            raise RuntimeError('lastName is None')
        if firstName is None:
            raise RuntimeError('firstName is None')
        self.lastName = lastName
        self.firstName = firstName

    def setID(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.idNum = num

    def setJob(self, role: str, shift: int, fullTime: bool):
        self.role = role
        self.shift = shift
        self.fullTime = fullTime

    def setAddress(self, addressLine1: str, addressLine2: str, addressCity: str, addressState: str, addressZip: str, addressTel: str, addressEmail: str):
        self.addressLine1 = addressLine1
        self.addressLine2 = addressLine2
        self.addressCity = addressCity
        self.addressState = addressState
        self.addressZip = addressZip
        self.addressTel = addressTel
        self.addressEmail = addressEmail

    def setStatus(self, active: bool = False):
        self.status = active

    def getTuple(self):
        if self.anniversary is None:
            raise RuntimeError('self.anniversary is None')
        return (
            self.idNum,
            self.lastName,
            self.firstName,
            self.anniversary.isoformat(),
            self.role,
            self.shift,
            1 if self.fullTime else 0,
            self.addressLine1,
            self.addressLine2,
            self.addressCity,
            self.addressState,
            self.addressZip,
            self.addressTel,
            self.addressEmail,
            1 if self.status else 0
        )

    def fromTuple(self, row: tuple[int, str, str, str, str, int, int, str, str, str, str, str, str, str, int]):
        self.setID(row[0])
        self.setName(row[1], row[2])
        self.setAnniversary(datetime.date.fromisoformat(row[3]))
        self.setJob(row[4], row[5], row[6] == 1)
        self.setAddress(row[7], row[8], row[9], row[10], row[11], row[12], row[13])
        self.setStatus(not row[14] == 0)

class EmployeeReview:
    def __init__(self, idNum: int | None = None, date: datetime.date | None = None, nextReview: datetime.date | None = None, details: str = "") -> None:
        if not (idNum is None or idNum >= 0):
            raise RuntimeError('idNum is None or idNum >= 0')
        self.idNum: int | None = idNum
        self.date: datetime.date | None = date
        self.nextReview: datetime.date | None = nextReview
        self.details: str = details

    def setID(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.idNum = num

    def getTuple(self):
        return (
            self.idNum,
            "" if self.date is None else self.date.isoformat(),
            "" if self.nextReview is None else self.nextReview.isoformat(),
            self.details
        )

    def fromTuple(self, row: tuple[int, str, str, str]):
        self.setID(row[0])
        self.date = None if row[1] == "" else datetime.date.fromisoformat(row[1])
        self.nextReview = None if row[2] == "" else datetime.date.fromisoformat(row[2])
        self.details = row[3] if row[3] is not None else ""

class EmployeeTrainingDate:
    def __init__(self, idNum: int | None = None, training: str | None = None, date: datetime.date | None = None, comment: str = "") -> None:
        self.idNum: int | None = idNum
        self.training: str | None = training
        self.date: datetime.date | None = date
        self.comment: str = comment

    def setID(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.idNum = num

    def setTraining(self, training: str):
        if self.training is not None:
            raise RuntimeError('self.training is not None')
        self.training = training

    def setDate(self, date: datetime.date):
        self.date = date

    def getTuple(self):
        if self.date is None:
            raise RuntimeError('self.date is None')
        return (
            self.idNum,
            self.training,
            self.date.isoformat(),
            self.comment
        )

    def fromTuple(self, row: tuple[int, str, str, str]):
        self.setID(row[0])
        self.setTraining(row[1])
        self.date = datetime.date.fromisoformat(row[2])
        self.comment = row[3]

class EmployeePTORange:
    def __init__(self, idNum: int | None = None, start: datetime.date | None = None, end: datetime.date | str | None = None, hours: float = 0) -> None:
        self.employee: int | None = idNum
        self.start: datetime.date | None = start
        self.end: datetime.date | str | None = end
        self.hours: float = hours

    def setEmployee(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.employee = num

    def setDate(self, start: datetime.date, end: datetime.date | str):
        if start is None:
            raise RuntimeError('start is None')
        if end is None:
            raise RuntimeError('end is None')
        if isinstance(end, datetime.date):
            if not (start <= end):
                raise RuntimeError('start <= end')
        else:
            if end not in ["CARRY", "CASH", "DROP"]:
                raise RuntimeError('end not in ["CARRY", "CASH", "DROP"]')
        self.start = start
        self.end = end

    def setHours(self, hours: float):
        if hours is None:
            raise RuntimeError('hours is None')
        if not (hours > 0):
            raise RuntimeError('hours > 0')
        self.hours = hours

    def getTuple(self):
        if self.start is None:
            raise RuntimeError('self.start is None')
        if self.end is None:
            raise RuntimeError('self.end is None')
        return (
            self.employee,
            self.start.isoformat(),
            self.end.isoformat() if isinstance(self.end, datetime.date) else self.end,
            self.hours
        )

    def fromTuple(self, row: tuple[int, str, str, float]):
        self.setEmployee(row[0])
        if row[2] in ["CARRY", "CASH", "DROP"]:
            self.setDate(datetime.date.fromisoformat(row[1]), row[2])
        else:
            self.setDate(datetime.date.fromisoformat(row[1]), datetime.date.fromisoformat(row[2]))
        self.setHours(row[3])

class EmployeeNote:
    def __init__(self, idNum: int | None = None, date: datetime.date | None = None, time: str | None = None, details: str = "") -> None:
        self.idNum: int | None = idNum
        self.date: datetime.date | None = date
        self.time: str | None = time
        self.details: str = details

    def setID(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.idNum = num

    def getTuple(self):
        if self.date is None:
            raise RuntimeError('self.date is None')
        if self.time is None:
            raise RuntimeError('self.time is None')
        return (
            self.idNum,
            self.date.isoformat(),
            self.time,
            self.details
        )

    def fromTuple(self, row: tuple[int, str, str, str]):
        self.setID(row[0])
        self.date = datetime.date.fromisoformat(row[1])
        self.time = row[2]
        self.details = row[3] if row[3] is not None else ""

class EmployeePoint:
    def __init__(self, idNum: int | None = None, date: datetime.date | None = None, reason: str | None = None, value: float = 0) -> None:
        self.idNum: int | None = idNum
        self.date: datetime.date | None = date
        self.reason: str | None = reason
        self.value: float = value

    def setEmployee(self, num: int):
        if num is None:
            raise RuntimeError('num is None')
        if not (num >= 0):
            raise RuntimeError('num >= 0')
        self.idNum = num

    def setDate(self, date: datetime.date):
        if date is None:
            raise RuntimeError('date is None')
        self.date = date

    def setReason(self, reason: str, value: float):
        self.reason = reason
        if reason in defaults.POINT_VALS:
            if not (value == defaults.POINT_VALS[reason]):
                raise RuntimeError('value == defaults.POINT_VALS[reason]')
        self.value = value

    def getTuple(self):
        if self.date is None:
            raise RuntimeError('self.date is None')
        return (
            self.idNum,
            self.date.isoformat(),
            self.reason,
            self.value
        )

    def fromTuple(self, row: tuple[int, str, str, float]):
        self.setEmployee(row[0])
        self.setDate(datetime.date.fromisoformat(row[1]))
        self.setReason(row[2], row[3])

class HolidayObservance:
    def __init__(self, holiday: str | None = None, date: datetime.date | None = None, shift: int = 1) -> None:
        self.holiday: str | None = holiday
        self.date: datetime.date | None = date
        self.shift: int = shift

    def setHoliday(self, holiday: str):
        if holiday not in defaults.HOLIDAYS:
            raise RuntimeError('holiday not in defaults.HOLIDAYS')
        self.holiday = holiday

    def setDate(self, date: datetime.date, shift: int):
        if date is None:
            raise RuntimeError('date is None')
        self.date = date
        self.shift = shift

    def getTuple(self):
        if self.date is None:
            raise RuntimeError('self.date is None')
        return (
            self.holiday,
            self.shift,
            self.date.isoformat()
        )

    def fromTuple(self, row: tuple[str, int, str]):
        self.setHoliday(row[0])
        self.setDate(datetime.date.fromisoformat(row[2]), row[1])

class EmployeeReviewsDB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.reviews: dict[datetime.date, EmployeeReview] = {}

    def lastReview(self):
        keys = list(self.reviews.keys())
        keys.sort()
        if len(keys) == 0:
            return None
        else:
            return self.reviews[keys[-1]]

    def getTuples(self):
        ret = []
        for date in self.reviews:
            if not (self.idNum == self.reviews[date].idNum):
                raise RuntimeError('self.idNum == self.reviews[date].idNum')
            ret.append(self.reviews[date].getTuple())
        return ret

class EmployeeTrainingDB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.training: dict[str, dict[datetime.date, EmployeeTrainingDate]] = {}
        for key in defaults.TRAINING:
            self.training[key] = {}

    def getTuples(self):
        ret = []
        for train in self.training:
            for date in self.training[train]:
                if not (self.idNum == self.training[train][date].idNum):
                    raise RuntimeError('self.idNum == self.training[train][date].idNum')
                ret.append(self.training[train][date].getTuple())
        return ret

class EmployeePointsDB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.points: dict[datetime.date, EmployeePoint] = {}

    def currentPoints(self, today: datetime.date):
        dates = list(self.points.keys())
        dates.sort()
        def filterDates(date: datetime.date):
            diff = (today - date).days
            val = self.points[date].value
            return diff <= 365 and val > 0
        validDates = list(filter(filterDates, dates))
        validDates.append(today) # won't ever be plugged into self.points
        sumPt = 0
        if len(validDates) > 1:
            for ind in range(len(validDates) - 1):
                currDate = validDates[ind]
                nextDate = validDates[ind + 1]
                sumPt += self.points[currDate].value
                diff = (nextDate - currDate).days
                credit = (diff - 1) // 90
                sumPt = max(sumPt - credit, 0)
        return sumPt

    def currentPointsList(self, today: datetime.date):
        dates = list(self.points.keys())
        dates.sort()
        def filterDates(date: datetime.date):
            diff = (today - date).days
            val = self.points[date].value
            return diff <= 365 and val > 0
        validDates = list(filter(filterDates, dates))
        validDates.append(today) # won't ever be plugged into self.points
        resPts: list[EmployeePoint] = []
        if len(validDates) > 1:
            for ind in range(len(validDates) - 1):
                currDate = validDates[ind]
                nextDate = validDates[ind + 1]
                resPts.append(self.points[currDate])
                diff = (nextDate - currDate).days
                credit = (diff - 1) // 90
                for i in range(credit):
                    autoDeduct = EmployeePoint(self.idNum, currDate + datetime.timedelta(days=(i + 1)*90), "Automatic deduction", -1)
                    resPts.append(autoDeduct)
        return resPts

    def getTuples(self):
        ret = []
        for date in self.points:
            if not (self.idNum == self.points[date].idNum):
                raise RuntimeError('self.idNum == self.points[date].idNum')
            ret.append(self.points[date].getTuple())
        return ret

class EmployeeNotesDB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.notes: dict[tuple[datetime.date, str], EmployeeNote] = {}

    def getTuples(self):
        ret = []
        for key in self.notes:
            if not (self.idNum == self.notes[key].idNum):
                raise RuntimeError('self.idNum == self.notes[key].idNum')
            ret.append(self.notes[key].getTuple())
        return ret

class EmployeePTODB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.PTO: dict[tuple[datetime.date, datetime.date|str], EmployeePTORange] = {}

    def getUsedHours(self, year: int):
        total = 0
        for dates in self.PTO:
            if dates[0].year == year and isinstance(dates[1], datetime.date):
                if not (dates[1].year == year):
                    raise RuntimeError('dates[1].year == year')
                total += self.PTO[dates].hours
        return total

    def getAvailableBaseHours(self, aniversary: datetime.date, year: int):
        # 6 mos - 40 hrs
        # 1 Year - 40 hrs
        # 2 years - 80 hrs
        # 3 - years - 88 hrs
        # 4 years - 96 hrs
        # 5 years - 104 hrs
        # 6 years - 112 hrs
        # 7 years - 120 hrs
        # > 7 years - 120 hours
        tenure = year - aniversary.year
        if tenure < 0:
            return 0
        elif tenure <= 1:
            return 40
        else:
            return min(120, 80 + (tenure - 2) * 8)

    def getCarryType(self, year: int):
        count = 0
        ret = None
        for dates in self.PTO:
            if dates[0].year == year:
                if dates[1] == "CARRY" or dates[1] == "CASH" or dates[1] == "DROP":
                    count += 1
                    ret = dates[1]
        if not (count <= 1):
            raise RuntimeError('count <= 1')
        return ret

    def clearCarry(self, year: int):
        toClear = []
        for dates in self.PTO:
            if dates[0].year == year and dates[1] == "CARRY" or dates[1] == "CASH" or dates[1] == "DROP":
                    toClear.append(dates)
        for dates in toClear:
            del self.PTO[dates]

    def getCarryHours(self, year: int):
        count = 0
        ret = 0
        for dates in self.PTO:
            if dates[0].year == year:
                if dates[1] == "CARRY":
                    count += 1
                    ret = self.PTO[dates].hours
                elif dates[1] == "CASH" or dates[1] == "DROP":
                    count += 1
                    ret = 0
        if not (count <= 1):
            raise RuntimeError('count <= 1')
        return ret

    def getQuarterHours(self, aniversary: datetime.date, attendance: EmployeePointsDB, today: datetime.date):
        # NEED WAY MORE DETAIL
        year = today.year
        counts = [0 for i in range(4)]
        for date in attendance.points:
            if (date.year == year or date.year == year - 1) and attendance.points[date].value > 0:
                if date.year == year - 1 and date.month > 9:
                    counts[0] += 1
                elif date.year == year and date.month <= 3:
                    counts[1] += 1
                elif date.year == year and date.month <= 6:
                    counts[2] += 1
                elif date.year == year  and date.month <= 9:
                    counts[3] += 1
        bonuses = 0
        if aniversary < datetime.date(year=year-1, month=10, day=1) and today > datetime.date(year=year-1, month=12, day=31) and counts[0] == 0:
            bonuses += 4
        if aniversary < datetime.date(year=year, month=1, day=1) and today > datetime.date(year=year, month=3, day=31) and counts[1] == 0:
            bonuses += 4
        if aniversary < datetime.date(year=year, month=4, day=1) and today > datetime.date(year=year, month=6, day=30) and counts[2] == 0:
            bonuses += 4
        if aniversary < datetime.date(year=year, month=7, day=1) and today > datetime.date(year=year, month=9, day=30) and counts[3] == 0:
            bonuses += 4
        return bonuses

    def getAvailableHours(self, aniversary: datetime.date, attendance: EmployeePointsDB, today: datetime.date):
        year = today.year
        base = self.getAvailableBaseHours(aniversary, year)
        carry = self.getCarryHours(year)
        bonuses = self.getQuarterHours(aniversary, attendance, today)
        return base + carry + bonuses

    def getTuples(self):
        ret = []
        for dateRange in self.PTO:
            if not (self.idNum == self.PTO[dateRange].employee):
                raise RuntimeError('self.idNum == self.PTO[dateRange].employee')
            ret.append(self.PTO[dateRange].getTuple())
        return ret

class ObservancesDB:
    def __init__(self) -> None:
        self.defaults: dict[str, int] = {}
        self.observances: dict[int, dict[str, dict[int, HolidayObservance]]] = {}

    def setDefault(self, holiday: str, month: int):
        if not (1 <= month and month <= 12):
            raise RuntimeError('1 <= month and month <= 12')
        self.defaults[holiday] = month

    def getDefault(self, holiday: str):
        if not holiday in self.defaults:
            return 1
        else:
            return self.defaults[holiday]

    def setObservance(self, holiday: HolidayObservance):
        if holiday.date is None:
            raise RuntimeError('holiday.date is None')
        if holiday.holiday is None:
            raise RuntimeError('holiday.holiday is None')
        year = holiday.date.year
        if not year in self.observances:
            self.observances[year] = {}
        if not holiday.holiday in self.observances[year]:
            self.observances[year][holiday.holiday] = {}
        self.observances[year][holiday.holiday][holiday.shift] = holiday

    def getObservance(self, year: int, holiday: str, shift: int):
        if not year in self.observances:
            return None
        elif not holiday in self.observances[year]:
            return None
        elif not shift in self.observances[year][holiday]:
            return None
        else:
            return self.observances[year][holiday][shift].date

    def delObservance(self, year: int, holiday: str, shift: int):
        if year in self.observances and holiday in self.observances[year] and shift in self.observances[year][holiday]:
            del self.observances[year][holiday][shift]
            if len(self.observances[year][holiday].keys()) == 0:
                del self.observances[year][holiday]
            if len(self.observances[year].keys()) == 0:
                del self.observances[year]

    def getHolidays(self, year: int):
        if not year in self.observances:
            return list(self.defaults.keys())
        else:
            used = list(self.observances[year].keys())
            for holiday in self.defaults:
                if not holiday in self.observances[year]:
                    used.append(holiday)
            return used

    def getDefaultTuples(self):
        rets = []
        for holiday in self.defaults:
            month = self.defaults[holiday]
            rets.append((holiday, month))
        return rets

    def getObservanceTuples(self):
        rets = []
        for year in self.observances:
            for holiday in self.observances[year]:
                for shift in self.observances[year][holiday]:
                    rets.append(self.observances[year][holiday][shift].getTuple())
        return rets
