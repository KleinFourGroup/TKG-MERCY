import datetime
from typing import TYPE_CHECKING

from reportlab.lib.units import inch

from defaults import PTO_ELIGIBILITY

if TYPE_CHECKING:
    from records import Database
    from reportlab.pdfgen import canvas


class EmployeeReportsMixin:
    # Employee-domain PDF reports: attendance points, PTO summary, notes/incidents
    # roster, single-incident form (with signature line), and active-employee
    # roster. All five build on the primitives in PDFReportCore — see
    # report/__init__.py for the composition.

    if TYPE_CHECKING:
        # Attributes + helpers provided by PDFReportCore (composed in last).
        db: Database
        pdf: canvas.Canvas
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSubtitle(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawParagraph(self, text: str) -> None: ...
        def drawSignatureLine(self, label: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

    def employeePointsReport(self, id):
        if id in self.db.employees:
            employee = self.db.employees[id]
            points = self.db.attendance[id]
            if employee.lastName is None:
                raise RuntimeError('employee.lastName is None')

            headers = ["Date", "Points", "Reason"]
            data = [[
                "{}".format(entry.date.isoformat() if entry.date is not None else "ERROR"),
                "{}".format(entry.value),
                "{}".format(entry.reason)

            ] for entry in points.currentPointsList(datetime.date.today())]
            olen = len(data)

            if len(data) == 0:
                self.setupPage()
                self.drawTitle(f"TKG Attendance Report ({datetime.date.today().isoformat()})")
                self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
                self.skipLines(2)

                self.drawSection(f"Attendance Details")

                self.drawTable([], ["Total", f"{points.currentPoints(datetime.date.today())}", ""])
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG Attendance Report ({datetime.date.today().isoformat()})")
                self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
                self.skipLines(2)

                self.drawSection(f"Attendance Details{" -- Continued" if not len(data) == olen else ""}")
                drawn = self.drawTable(data, headers)

                if drawn == len(data):
                    self.drawTable([], ["Total", f"{points.currentPoints(datetime.date.today())}", ""])

                data = data[drawn:]
                self.nextPage()
            self.pdf.save()

    def employeePTOReport(self, id):
        if id in self.db.employees:
            employee = self.db.employees[id]
            PTO = self.db.PTO[id]
            if employee.lastName is None:
                raise RuntimeError('employee.lastName is None')
            if employee.anniversary is None:
                raise RuntimeError('employee.anniversary is None')

            today = datetime.date.today()

            headers = ["Start", "End", "Hours"]
            data = [[
                "{}".format(PTO.PTO[entry].start.isoformat()), # type: ignore
                "{}".format(PTO.PTO[entry].end.isoformat() if isinstance(PTO.PTO[entry].end, datetime.date) else PTO.PTO[entry].end), # type: ignore
                "{}{}".format("" if isinstance(PTO.PTO[entry].end, datetime.date) else "", PTO.PTO[entry].hours)

            ] for entry in PTO.PTO if isinstance(PTO.PTO[entry].end, datetime.date) and PTO.PTO[entry].end.year == today.year]
            data.sort(key=lambda row: (row[0], row[1]))
            olen = len(data)

            unusedType = PTO.getCarryType(datetime.date.today().year)

            status = "None"
            if unusedType == "CARRY":
                status = "Carried over"
            elif unusedType == "CASH":
                status = "Cashed out"
            elif unusedType == "DROP":
                status = "Dropped"

            self.setupPage()
            self.drawTitle(f"TKG PTO Report ({datetime.date.today().isoformat()})")
            self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
            self.skipLines(2)

            self.drawSection(f"PTO Overview")
            self.drawText(f"PTO hours in {datetime.date.today().year}: {PTO.getAvailableHours(employee.anniversary, self.db.attendance[id], today)}{"" if (today - employee.anniversary).days >= PTO_ELIGIBILITY else f" (available {(employee.anniversary + datetime.timedelta(days=PTO_ELIGIBILITY)).isoformat()})"}")
            self.drawText(f"Base PTO in {datetime.date.today().year}: {PTO.getAvailableBaseHours(employee.anniversary, today.year)}")
            self.drawText(f"PTO attendance bonus in {datetime.date.today().year}: {PTO.getQuarterHours(employee.anniversary, self.db.attendance[id], today)}")
            self.drawText(f"PTO carryover from {datetime.date.today().year - 1}: {PTO.getCarryHours(today.year)} ({status})")
            self.skipLines(1)
            self.drawText(f"PTO used in {datetime.date.today().year}: {PTO.getUsedHours(today.year)}")
            self.skipLines(1)
            self.drawText(f"PTO remaining in {datetime.date.today().year}: {PTO.getAvailableHours(employee.anniversary, self.db.attendance[id], today) - PTO.getUsedHours(today.year)}")
            self.skipLines(2)

            if len(data) == 0:
                self.drawSection(f"PTO Details")

                self.drawTable([], ["Total Used", "", f"{PTO.getUsedHours(today.year)}"])
            while len(data) > 0:
                if not len(data) == olen:
                    self.setupPage()
                    self.drawTitle(f"TKG PTO Report ({datetime.date.today().isoformat()})")
                    self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
                    self.skipLines(2)

                self.drawSection(f"PTO Details{" -- Continued" if not len(data) == olen else ""}")
                drawn = self.drawTable(data, headers)

                if drawn == len(data):
                    self.drawTable([], ["Total Used", "", f"{PTO.getUsedHours(today.year)}"])

                data = data[drawn:]
                self.nextPage()
            self.pdf.save()

    def employeeNotesReport(self, id):
        if id in self.db.employees:
            employee = self.db.employees[id]
            notesDB = self.db.notes[id]
            if employee.lastName is None:
                raise RuntimeError('employee.lastName is None')

            today = datetime.date.today()
            headers = ["Date", "Time", "Details"]
            widths = [1.2 * inch, 0.8 * inch, 4.5 * inch]
            data = [[
                "{}".format(note.date.isoformat()),
                "{}".format(note.time),
                "{}".format(note.details)
            ] for note in notesDB.notes.values() if (today - note.date).days <= 365]
            data.sort(key=lambda row: (row[0], row[1]))
            olen = len(data)

            if len(data) == 0:
                self.setupPage()
                self.drawTitle(f"TKG Notes and Incidents Report ({today.isoformat()})")
                self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
                self.skipLines(2)

                self.drawSection(f"Notes & Incidents (Past Year)")

                self.drawTable([], ["Total Notes", f"{olen}", ""], widths)
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG Notes and Incidents Report ({today.isoformat()})")
                self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
                self.skipLines(2)

                self.drawSection(f"Notes and Incidents (Past Year){" -- Continued" if not len(data) == olen else ""}")
                drawn = self.drawTable(data, headers, widths)

                if drawn == len(data):
                    self.drawTable([], ["Total Notes", f"{olen}", ""], widths)

                data = data[drawn:]
                self.nextPage()
            self.pdf.save()

    def employeeIncidentReport(self, id, date, time):
        if id in self.db.employees:
            employee = self.db.employees[id]
            note = self.db.notes[id].notes[(date, time)]
            if employee.lastName is None:
                raise RuntimeError('employee.lastName is None')

            self.setupPage()
            self.drawTitle(f"TKG Incident Report")
            self.drawSubtitle(f"{employee.lastName.upper()} {employee.firstName} ({id})")
            self.skipLines(1)

            self.drawSection("Incident Details")
            self.drawText(f"Date: {note.date.isoformat()}")
            self.drawText(f"Time: {note.time}")
            self.skipLines(1)

            self.drawParagraph(note.details)
            self.skipLines(2)

            self.drawSignatureLine("Employee Signature:")
            self.drawSignatureLine("Date:")

            self.pdf.save()

    def employeeActiveReport(self):
        headers = ["ID", "Name", "Points", "Remaining PTO"]
        data = [[
            "{}".format(id),
            "{} {}".format(self.db.employees[id].lastName.upper(), self.db.employees[id].firstName), # type: ignore
            "{}".format(self.db.attendance[id].currentPoints(datetime.date.today())),
            "{}".format(self.db.PTO[id].getAvailableHours(self.db.employees[id].anniversary, self.db.attendance[id], datetime.date.today()) - self.db.PTO[id].getUsedHours(datetime.date.today().year) if self.db.employees[id].fullTime else "N/A") # type: ignore
        ] for id in self.db.employees if self.db.employees[id].status]
        olen = len(data)

        if len(data) == 0:
            self.setupPage()
            self.drawTitle(f"TKG Active Employees Report ({datetime.date.today().isoformat()})")
            self.skipLines(2)

            self.drawSection(f"Details")

            self.drawTable([], ["Total Employees", f"{olen}"])
        while len(data) > 0:
            self.setupPage()
            self.drawTitle(f"TKG Active Employees Report ({datetime.date.today().isoformat()})")
            self.skipLines(2)

            self.drawSection(f"Details{" -- Continued" if not len(data) == olen else ""}")
            drawn = self.drawTable(data, headers)

            if drawn == len(data):
                self.drawTable([], ["Total Employees", f"{olen}"])

            data = data[drawn:]
            self.nextPage()
        self.pdf.save()
