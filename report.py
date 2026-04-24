from math import floor
import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF

from records import Database, ProductionRecord
from defaults import (
    PTO_ELIGIBILITY,
    PRODUCTION_ACTIONS, PRODUCTION_ACTION_TARGET, PRODUCTION_TARGET_UNIT,
)

# Step 19 trend-report knobs. Module-level so the team can flip modes without a
# signature change if the default doesn't match their gut. See MERGE_PLAN.md
# §13.6 for the decision on ratio-of-sums as default.
TREND_WINDOW_DAYS = 30
TREND_MIN_RANGE_DAYS = 30
# "ratioOfSums": sum(qty in window) / sum(hours in window). Matches Step 18's
# aggregation. Zero-production days contribute nothing to numerator or
# denominator and fall out naturally.
# "meanOfRates": mean of per-day rates (qty/hours), skipping days with no
# production so they don't drag the mean toward zero.
TREND_MODE = "ratioOfSums"

# Colorblind-friendly palette for trend lines (matplotlib's tab10 subset). The
# aggregate/"All shifts" line is always rendered last and gets the final color.
_TREND_LINE_COLORS = [
    colors.HexColor('#1f77b4'),  # blue
    colors.HexColor('#ff7f0e'),  # orange
    colors.HexColor('#2ca02c'),  # green
    colors.HexColor('#d62728'),  # red
    colors.HexColor('#9467bd'),  # purple
    colors.HexColor('#000000'),  # black
]

class PDFReport:
    def __init__(self, db: Database, path: str, margin: float = inch) -> None:
        self.db = db
        self.pdf = canvas.Canvas(path, pagesize=letter)
        self.lineSpace = 1.3
        self.calculateMargins(margin)
        self.pageNum = 1
        self.setFont("Times-Roman", 12)

    def calculateMargins(self, margin: float):
        self.margin = margin
        self.top = letter[1] - self.margin
        self.bottom = self.margin
        self.left = self.margin
        self.right = letter[0] - self.margin

    def setupPage(self):
        self.lastLine = self.top
    
    def nextPage(self):
        self.pdf.showPage()
        self.pageNum += 1
        self.setupPage()
    
    def setFont(self, font: str, size: int):
        self.pdf.setFont(font, size)
        self.font = font
        self.fontSize = size
    
    def skipLines(self, numLines):
        self.lastLine -= self.fontSize * self.lineSpace * numLines
    
    def drawText(self, text: str):
        self.pdf.drawString(self.left, self.lastLine - self.fontSize, text)
        self.skipLines(1)
    
    def drawTitle(self, text: str):
        oldFont = (self.font, self.fontSize)
        self.setFont("Times-Bold", 24)
        self.drawText(text)
        self.setFont(*oldFont)

    def drawSubtitle(self, text: str):
        oldFont = (self.font, self.fontSize)
        self.setFont("Times-Bold", 20)
        self.drawText(text)
        self.setFont(*oldFont)

    def drawSection(self, text: str):
        oldFont = (self.font, self.fontSize)
        self.setFont("Times-Bold", 18)
        self.drawText(text)
        self.setFont(*oldFont)

    def drawParagraph(self, text: str):
        maxWidth = self.right - self.left
        for paragraph in text.split("\n"):
            lines = self._wrapText(paragraph, maxWidth)
            for line in lines:
                if self.lastLine - self.fontSize < self.bottom:
                    self.nextPage()
                self.drawText(line)

    def drawSignatureLine(self, label: str):
        if self.lastLine - self.fontSize * self.lineSpace * 3 < self.bottom:
            self.nextPage()
        self.skipLines(2)
        labelWidth = stringWidth(label + "  ", self.font, self.fontSize)
        y = self.lastLine - self.fontSize
        self.pdf.drawString(self.left, y, label)
        self.pdf.line(self.left + labelWidth, y, self.right, y)
        self.skipLines(1)

    def _wrapText(self, text: str, maxWidth: float, font: str | None = None, fontSize: int | None = None) -> list[str]:
        font = font or self.font
        fontSize = fontSize or self.fontSize
        words = text.split()
        if len(words) == 0:
            return [""]
        lines = []
        currentLine = words[0]
        for word in words[1:]:
            testLine = currentLine + " " + word
            if stringWidth(testLine, font, fontSize) <= maxWidth:
                currentLine = testLine
            else:
                lines.append(currentLine)
                currentLine = word
        lines.append(currentLine)
        return lines

    def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None):
        hasHeader = headers is not None
        columns = len(widths) if widths is not None else len(headers) if hasHeader else len(data[0]) if len(data) > 0 else 1

        if widths == None:
            widths = [(self.right - self.left) / columns for i in range(columns)]

        totalWidth = 0
        for width in widths:
            totalWidth += width

        startX = self.left + ((self.right - self.left - totalWidth) / 2.0)
        xVals = [startX]
        for width in widths:
            xVals.append(xVals[-1] + width)

        padding = self.fontSize / 3
        lineHeight = self.fontSize * self.lineSpace

        # Phase A: Wrap all text and compute row heights
        # Each entry in rowInfo is (wrappedCells, rowHeight, isHeader)
        rowInfo: list[tuple[list[list[str]], float, bool]] = []

        if hasHeader:
            headerWrapped = []
            for i in range(columns):
                cellWidth = widths[i] - 2 * padding
                headerWrapped.append(self._wrapText(headers[i], cellWidth, "Times-Bold", self.fontSize))
            maxLines = max(len(lines) for lines in headerWrapped)
            rowInfo.append((headerWrapped, maxLines * lineHeight + padding, True))

        for dataRow in data:
            wrappedCells = []
            for i in range(columns):
                cellWidth = widths[i] - 2 * padding
                wrappedCells.append(self._wrapText(dataRow[i], cellWidth))
            maxLines = max(len(lines) for lines in wrappedCells)
            rowInfo.append((wrappedCells, maxLines * lineHeight + padding, False))

        # Phase B: Paginate by accumulating variable row heights
        availableHeight = self.lastLine - self.bottom
        usedHeight = 0
        rowsToDraw = 0
        for (wrappedCells, rowHeight, isHeader) in rowInfo:
            if usedHeight + rowHeight > availableHeight:
                break
            usedHeight += rowHeight
            rowsToDraw += 1

        if rowsToDraw == 0:
            return 0

        # Phase C: Build yVals and draw grid
        yVals = [self.lastLine]
        for i in range(rowsToDraw):
            yVals.append(yVals[-1] - rowInfo[i][1])

        self.pdf.grid(xVals, yVals)

        # Phase D: Draw wrapped text in cells
        drawn = 0
        for rowIdx in range(rowsToDraw):
            wrappedCells, rowHeight, isHeader = rowInfo[rowIdx]
            cellTop = yVals[rowIdx]

            if isHeader:
                oldFont = (self.font, self.fontSize)
                self.setFont("Times-Bold", self.fontSize)

                for colIdx in range(columns):
                    lines = wrappedCells[colIdx]
                    for lineIdx, line in enumerate(lines):
                        textY = cellTop - padding - self.fontSize - lineIdx * lineHeight
                        self.pdf.drawString(xVals[colIdx] + padding, textY, line)

                self.setFont(*oldFont)
            else:
                for colIdx in range(columns):
                    lines = wrappedCells[colIdx]
                    for lineIdx, line in enumerate(lines):
                        textY = cellTop - padding - self.fontSize - lineIdx * lineHeight
                        self.pdf.drawString(xVals[colIdx] + padding, textY, line)

                drawn += 1

        self.lastLine = yVals[rowsToDraw] - self.fontSize * self.lineSpace
        return drawn
    
    def globalsReport(self):
        globalKeys = self.db.globals.getGlobals()
        globalStrings = self.db.globals.getStrings()
        self.setupPage()
        self.drawTitle("TKG Production Report")
        self.skipLines(2)
        self.drawSection("Global Values")
        for glob in globalKeys:
            self.drawText(f"{globalStrings[glob][0]}: {getattr(self.db.globals, glob)} ({globalStrings[glob][1]})")
        self.nextPage()
        self.pdf.save()

    def mixReport(self, mixName):
        if mixName in self.db.mixtures:
            mix = self.db.mixtures[mixName]
            self.setupPage()
            self.drawTitle("TKG Production Report")
            self.skipLines(2)

            self.drawSection(f"{mixName} Mixture Composition")
            headers = ["Material", "Weight"]
            data = [[f"{mix.materials[i]}", f"{mix.weights[i]}"] for i in range(len(mix.materials))]
            self.drawTable(data, headers)

            self.drawTable([], ["Total", f"{mix.getBatchWeight()}"])

            self.drawSection(f"{mixName} Chemical Analysis")
            data = [
                ["SiO2", f"{mix.getProp("SiO2"):.4f}%"],
                ["Al2O3", f"{mix.getProp("Al2O3"):.4f}%"],
                ["Fe2O3", f"{mix.getProp("Fe2O3"):.4f}%"],
                ["TiO2", f"{mix.getProp("TiO2"):.4f}%"],
                ["Li2O", f"{mix.getProp("Li2O"):.4f}%"],
                ["P2O5", f"{mix.getProp("P2O5"):.4f}%"],
                ["Na2O", f"{mix.getProp("Na2O"):.4f}%"],
                ["CaO", f"{mix.getProp("CaO"):.4f}%"],
                ["K2O", f"{mix.getProp("K2O"):.4f}%"],
                ["MgO", f"{mix.getProp("MgO"):.4f}%"],
                ["Other", f"{mix.getProp("otherChem"):.4f}%"]
            ]
            self.drawTable(data)

            self.drawSection(f"{mixName} Sizing Analysis")
            headers = ["+50", "-50+100", "-100+200", "-200+325", "-325"]
            data = [[
                f"{mix.getProp("Plus50", False):.1f}%",
                f"{mix.getProp("Sub50Plus100", False):.1f}%",
                f"{mix.getProp("Sub100Plus200", False):.1f}%",
                f"{mix.getProp("Sub200Plus325", False):.1f}%",
                f"{mix.getProp("Sub325", False):.1f}%"
            ]]

            self.drawTable(data, headers)

            self.nextPage()
            self.pdf.save()

    def salesReport(self):
        parts = [self.db.parts[name] for name in self.db.parts.keys() if isinstance(self.db.parts[name].sales, int) and self.db.parts[name].sales > 0] # type: ignore
        data = []
        sales = 0
        total = 0
        totalLab = 0
        totalMatl = 0
        for part in parts:
            if part.sales is None:
                raise RuntimeError('part.sales is None')
            data.append([f"{part.name}", f"${part.getManufacturingCost():.4f}", f"{part.sales}", f"${part.sales * part.getGrossLaborCost():.2f}", f"${part.sales * part.getGrossMatlCost():.2f}", f"${part.sales * part.getManufacturingCost():.2f}"])
            sales += part.sales
            totalLab += part.sales * part.getGrossLaborCost()
            totalMatl += part.sales * part.getGrossMatlCost()
            total += part.sales * part.getManufacturingCost()
        while len(data) > 0:
            self.setupPage()
            self.drawTitle("TKG Production Report")
            self.skipLines(2)

            self.drawSection("Cost Analysis Report" if len(data) == len(parts) else "Sales (cont.)")
            headers = ["Part", "Man. Cost", "Sales", "Gross Lab.","Gross Mat.", "COGS"]
            drawn = self.drawTable(data, headers)

            if drawn == len(data):
                self.drawTable([], ["Total", "---", f"{sales}", f"${totalLab:.2f}", f"${totalMatl:.2f}", f"${total:.2f}"])
            
            data = data[drawn:]
            self.nextPage()
        self.pdf.save()

    def inventoryReport(self, currDate: datetime.date):
        if currDate not in self.db.inventories:
            raise RuntimeError('currDate not in self.db.inventories')
        dates = [date for date in self.db.inventories.keys() if date <= currDate]
        dates.sort(reverse=True)
        prevDate = dates[1] if len(dates) > 1 else None
        def processMaterials(date: datetime.date, data: list[list[str]] | None = None):
            currVal = 0
            origVal = 0
            materialRecs = [self.db.inventories[date].materials[name] for name in self.db.inventories[date].materials.keys()]
            for material in materialRecs:
                if material.name is None:
                    raise RuntimeError('material.name is None')
                if material.cost is None:
                    raise RuntimeError('material.cost is None')
                if material.amount is None:
                    raise RuntimeError('material.amount is None')
                currCost = self.db.materials[material.name].getCostPerLb() if material.name in self.db.materials else None
                if data is not None and material.amount > 0:
                    data.append([f"{material.name}", "N/A" if currCost is None else f"${currCost:.4f}", f"${material.cost:.4f}", f"{material.amount}", f"${material.cost * material.amount:.4f}"])
                if currCost is not None:
                    currVal += currCost * material.amount
                origVal += material.cost * material.amount
            return currVal, origVal
        
        def processPartsWIP(date: datetime.date, data: list[list[str]] | None = None):
            currVal = 0
            origVal = 0
            partRecs = [self.db.inventories[date].parts[name] for name in self.db.inventories[date].parts.keys()]
            for part in partRecs:
                if part.name is None:
                    raise RuntimeError('part.name is None')
                if part.cost is None:
                    raise RuntimeError('part.cost is None')
                if part.amount40 is None:
                    raise RuntimeError('part.amount40 is None')
                if part.amount60 is None:
                    raise RuntimeError('part.amount60 is None')
                if part.amount80 is None:
                    raise RuntimeError('part.amount80 is None')
                if part.amount100 is None:
                    raise RuntimeError('part.amount100 is None')
                currCost = self.db.parts[part.name].getManufacturingCost() if part.name in self.db.parts else None
                if data is not None and (part.amount40 + part.amount60 + part.amount80) > 0:
                    data.append([f"{part.name}", "N/A" if currCost is None else f"${currCost:.4f}", f"${part.cost:.4f}", f"{part.amount40}", f"{part.amount60}", f"{part.amount80}", f"${0.4 * part.cost * part.amount40 + 0.6 * part.cost * part.amount60 + 0.8 * part.cost * part.amount80:.4f}"])
                if currCost is not None:
                    currVal += 0.4 * currCost * part.amount40 + 0.6 * currCost * part.amount60 + 0.8 * currCost * part.amount80
                origVal += 0.4 * part.cost * part.amount40 + 0.6 * part.cost * part.amount60 + 0.8 * part.cost * part.amount80
            return currVal, origVal
        
        def processPartsCompleted(date: datetime.date, data: list[list[str]] | None = None):
            currVal = 0
            origVal = 0
            partRecs = [self.db.inventories[date].parts[name] for name in self.db.inventories[date].parts.keys()]
            for part in partRecs:
                if part.name is None:
                    raise RuntimeError('part.name is None')
                if part.cost is None:
                    raise RuntimeError('part.cost is None')
                if part.amount40 is None:
                    raise RuntimeError('part.amount40 is None')
                if part.amount60 is None:
                    raise RuntimeError('part.amount60 is None')
                if part.amount80 is None:
                    raise RuntimeError('part.amount80 is None')
                if part.amount100 is None:
                    raise RuntimeError('part.amount100 is None')
                currCost = self.db.parts[part.name].getManufacturingCost() if part.name in self.db.parts else None
                if data is not None and part.amount100 > 0:
                    data.append([f"{part.name}", "N/A" if currCost is None else f"${currCost:.4f}", f"${part.cost:.4f}", f"{part.amount100}", f"${part.cost * part.amount100:.4f}"])
                if currCost is not None:
                    currVal += currCost * part.amount100
                origVal += part.cost * part.amount100
            return currVal, origVal
        
        dataMatl = []
        dataPartWIP = []
        dataPartCompleted = []
        currValMatl_currDate, origValMatl_currDate = processMaterials(currDate, dataMatl)
        currValPartWIP_currDate, origValPartWIP_currDate = processPartsWIP(currDate, dataPartWIP)
        currValPartCompleted_currDate, origValPartCompleted_currDate = processPartsCompleted(currDate, dataPartCompleted)
        currValMatl_prevDate, origValMatl_prevDate = processMaterials(prevDate) if prevDate is not None else (0, 0)
        currValPartWIP_prevDate, origValPartWIP_prevDate = processPartsWIP(prevDate) if prevDate is not None else (0, 0)
        currValPartCompleted_prevDate, origValPartCompleted_prevDate = processPartsCompleted(prevDate) if prevDate is not None else (0, 0)

        dataDeltas = [
            ["Materials", f"${currValMatl_currDate:.2f}", f"${origValMatl_prevDate:.2f}" if prevDate is not None else "N/A", f"${currValMatl_currDate - origValMatl_prevDate:.2f}"],
            ["WIP Parts", f"${currValPartWIP_currDate:.2f}", f"${origValPartWIP_prevDate:.2f}" if prevDate is not None else "N/A", f"${currValPartWIP_currDate - origValPartWIP_prevDate:.2f}"],
            ["Completed Parts", f"${currValPartCompleted_currDate:.2f}", f"${origValPartCompleted_prevDate:.2f}" if prevDate is not None else "N/A", f"${currValPartCompleted_currDate - origValPartCompleted_prevDate:.2f}"]
        ]
        headersDelta = ["Category", "Current Value", f"{prevDate.isoformat() if prevDate is not None else "Prior"} Value", "Change"]
        self.setupPage()
        self.drawTitle(f"TKG Inventory Report for {currDate.isoformat()}")
        self.skipLines(2)

        self.drawSection("Inventory Overview")
        self.drawTable(dataDeltas, headersDelta)
        self.drawTable([], [
            "Total", f"${currValMatl_currDate + currValPartWIP_currDate + currValPartCompleted_currDate:.2f}",
            f"${origValMatl_prevDate + origValPartWIP_prevDate + origValPartCompleted_prevDate:.2f}" if prevDate is not None else "N/A",
            f"${(currValMatl_currDate + currValPartWIP_currDate + currValPartCompleted_currDate) - (origValMatl_prevDate + origValPartWIP_prevDate + origValPartCompleted_prevDate):.2f}"
            ])
        self.nextPage()

        dataMatl.sort()

        olen = len(dataMatl)
        while len(dataMatl) > 0:
            self.setupPage()
            self.drawTitle(f"TKG Inventory Report for {currDate.isoformat()}")
            self.skipLines(2)

            self.drawSection("Materials Inventory" if len(dataMatl) == olen else "Materials Inventory (cont.)")
            headers = ["Material", "Current Cost", "Original Cost", "Amount", "Value"]
            drawn = self.drawTable(dataMatl, headers)

            if drawn == len(dataMatl):
                self.drawTable([], ["Total", f"${currValMatl_currDate:.4f}", f"${origValMatl_currDate:.4f}", "---", "---"])
            
            dataMatl = dataMatl[drawn:]
            self.nextPage()
        
        dataPartWIP.sort()

        olen = len(dataPartWIP)
        while len(dataPartWIP) > 0:
            self.setupPage()
            self.drawTitle(f"TKG Inventory Report for {currDate.isoformat()}")
            self.skipLines(2)

            self.drawSection("WIP Parts Inventory" if len(dataPartWIP) == olen else "WIP Parts Inventory (cont.)")
            headers = ["Part", "Curr. Cost", "Orig. Cost", "Pressed", "Finished", "Fired", "Value"]
            drawn = self.drawTable(dataPartWIP, headers)

            if drawn == len(dataPartWIP):
                self.drawTable([], ["Total", f"${currValPartWIP_currDate:.4f}", f"${origValPartWIP_currDate:.4f}", "---", "---", "---", "---"])
            
            dataPartWIP = dataPartWIP[drawn:]
            self.nextPage()

        dataPartCompleted.sort()

        olen = len(dataPartCompleted)
        while len(dataPartCompleted) > 0:
            self.setupPage()
            self.drawTitle(f"TKG Inventory Report for {currDate.isoformat()}")
            self.skipLines(2)

            self.drawSection("Completed Parts Inventory" if len(dataPartCompleted) == olen else "Completed Parts Inventory (cont.)")
            headers = ["Part", "Curr. Cost", "Orig. Cost", "Completed", "Value"]
            drawn = self.drawTable(dataPartCompleted, headers)

            if drawn == len(dataPartCompleted):
                self.drawTable([], ["Total", f"${currValPartCompleted_currDate:.4f}", f"${origValPartCompleted_currDate:.4f}", "---", "---"])

            dataPartCompleted = dataPartCompleted[drawn:]
            self.nextPage()
        self.pdf.save()

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

    def _filterProduction(self, startDate: datetime.date, endDate: datetime.date,
                          action: str | None = None,
                          employeeId: int | None = None,
                          targetType: str | None = None,
                          targetName: str | None = None) -> list[ProductionRecord]:
        out = []
        for rec in self.db.production.values():
            if rec.date is None:
                continue
            if rec.date < startDate or rec.date > endDate:
                continue
            if action is not None and rec.action != action:
                continue
            if employeeId is not None and rec.employeeId != employeeId:
                continue
            if targetType is not None and rec.targetType != targetType:
                continue
            if targetName is not None and rec.targetName != targetName:
                continue
            out.append(rec)
        return out

    def _employeeName(self, employeeId) -> str:
        emp = self.db.employees.get(employeeId)
        if emp is None:
            return f"(missing #{employeeId})"
        last = (emp.lastName or "").upper()
        first = emp.firstName or ""
        return f"{last} {first} ({employeeId})"

    def productionSummaryReport(self, startDate: datetime.date, endDate: datetime.date):
        recs = self._filterProduction(startDate, endDate)

        grid: dict[tuple[int | None, str | None], tuple[float, float, float]] = {}
        empIds: set = set()
        for r in recs:
            key = (r.employeeId, r.action)
            q, s, h = grid.get(key, (0.0, 0.0, 0.0))
            grid[key] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)
            empIds.add(r.employeeId)

        def empSortKey(eid):
            emp = self.db.employees.get(eid)
            if emp is None:
                return (1, "", "", eid if eid is not None else 0)
            return (0, (emp.lastName or "").lower(), (emp.firstName or "").lower(), eid or 0)

        sortedIds = sorted(empIds, key=empSortKey)

        headers = ["Employee"] + [
            f"{a} ({PRODUCTION_TARGET_UNIT[PRODUCTION_ACTION_TARGET[a]]})"
            for a in PRODUCTION_ACTIONS
        ]

        def _format(q: float, s: float, h: float) -> str:
            if q == 0 and s == 0 and h == 0:
                return "—"
            extras = []
            if s > 0:
                extras.append(f"scrap: {s:g}")
            if h > 0:
                extras.append(f"{h:g}h")
            return f"{q:g} ({', '.join(extras)})" if extras else f"{q:g}"

        def cell(eid, action) -> str:
            q, s, h = grid.get((eid, action), (0.0, 0.0, 0.0))
            return _format(q, s, h)

        data = [[self._employeeName(eid)] + [cell(eid, a) for a in PRODUCTION_ACTIONS]
                for eid in sortedIds]

        totalsRow = ["Total"]
        for a in PRODUCTION_ACTIONS:
            tq = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[0] for eid in empIds)
            ts = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[1] for eid in empIds)
            th = sum(grid.get((eid, a), (0.0, 0.0, 0.0))[2] for eid in empIds)
            totalsRow.append(_format(tq, ts, th))

        olen = len(data)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle("TKG Production Summary")
            self.drawSubtitle(rangeText)
            self.skipLines(2)
            self.drawSection("Production by Employee")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle("TKG Production Summary")
                self.drawSubtitle(rangeText)
                self.skipLines(2)
                self.drawSection("Production by Employee" if len(data) == olen
                                 else "Production by Employee -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    self.drawTable([], totalsRow)
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionActionReport(self, action: str, startDate: datetime.date, endDate: datetime.date):
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')

        recs = self._filterProduction(startDate, endDate, action=action)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.targetName or "",
                                 r.employeeId if r.employeeId is not None else 0))

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        # Targetless actions (Tool Change) drop the target + scrap columns — both
        # are always empty/zero for those records and would just clutter the table.
        hasTarget = targetType != ""
        targetLabel = "Mixture" if targetType == "mix" else "Part"

        if hasTarget:
            headers = ["Date", "Shift", "Employee", targetLabel,
                       f"Quantity ({unit})", f"Scrap ({unit})", "Hours"]
            data = [[
                r.date.isoformat() if r.date else "",
                str(r.shift) if r.shift is not None else "",
                self._employeeName(r.employeeId),
                r.targetName or "",
                f"{r.quantity:g}" if r.quantity is not None else "",
                f"{r.scrapQuantity:g}",
                f"{r.hours:g}",
            ] for r in recs]
        else:
            headers = ["Date", "Shift", "Employee",
                       f"Quantity ({unit})", "Hours"]
            data = [[
                r.date.isoformat() if r.date else "",
                str(r.shift) if r.shift is not None else "",
                self._employeeName(r.employeeId),
                f"{r.quantity:g}" if r.quantity is not None else "",
                f"{r.hours:g}",
            ] for r in recs]
        olen = len(data)

        totalQ = sum((r.quantity or 0) for r in recs)
        totalS = sum(r.scrapQuantity for r in recs)
        totalH = sum(r.hours for r in recs)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle(f"TKG {action} Report")
            self.drawSubtitle(rangeText)
            self.skipLines(2)
            self.drawSection(f"{action} Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG {action} Report")
                self.drawSubtitle(rangeText)
                self.skipLines(2)
                self.drawSection(f"{action} Records" if len(data) == olen
                                 else f"{action} Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    if hasTarget:
                        self.drawTable([], ["", "", "", "Total",
                                            f"{totalQ:g}", f"{totalS:g}", f"{totalH:g}"])
                    else:
                        self.drawTable([], ["", "", "Total",
                                            f"{totalQ:g}", f"{totalH:g}"])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionTargetReport(self, targetType: str, targetName: str,
                               startDate: datetime.date, endDate: datetime.date):
        if targetType not in PRODUCTION_TARGET_UNIT:
            raise RuntimeError(f'unknown targetType {targetType!r}')

        recs = self._filterProduction(startDate, endDate,
                                      targetType=targetType, targetName=targetName)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.action or "",
                                 r.employeeId if r.employeeId is not None else 0))

        unit = PRODUCTION_TARGET_UNIT[targetType]
        targetLabel = "Mixture" if targetType == "mix" else "Part"

        headers = ["Date", "Shift", "Employee", "Action",
                   f"Quantity ({unit})", f"Scrap ({unit})", "Hours"]
        data = [[
            r.date.isoformat() if r.date else "",
            str(r.shift) if r.shift is not None else "",
            self._employeeName(r.employeeId),
            r.action or "",
            f"{r.quantity:g}" if r.quantity is not None else "",
            f"{r.scrapQuantity:g}",
            f"{r.hours:g}",
        ] for r in recs]
        olen = len(data)

        perAction: dict[str, tuple[float, float, float]] = {}
        for r in recs:
            q, s, h = perAction.get(r.action or "", (0.0, 0.0, 0.0))
            perAction[r.action or ""] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)

        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle(f"TKG Production Report: {targetName}")
            self.drawSubtitle(f"{targetLabel} ({rangeText})")
            self.skipLines(2)
            self.drawSection("Production Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle(f"TKG Production Report: {targetName}")
                self.drawSubtitle(f"{targetLabel} ({rangeText})")
                self.skipLines(2)
                self.drawSection("Production Records" if len(data) == olen
                                 else "Production Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    for a in PRODUCTION_ACTIONS:
                        if a in perAction:
                            q, s, h = perAction[a]
                            self.drawTable([], ["", "", "", f"Total {a}", f"{q:g}", f"{s:g}", f"{h:g}"])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionEmployeeReport(self, employeeId: int,
                                 startDate: datetime.date, endDate: datetime.date):
        if employeeId not in self.db.employees:
            raise RuntimeError(f'employeeId {employeeId} not in self.db.employees')

        recs = self._filterProduction(startDate, endDate, employeeId=employeeId)
        recs.sort(key=lambda r: (r.date, r.shift if r.shift is not None else 0,
                                 r.action or "", r.targetName or ""))

        headers = ["Date", "Shift", "Action", "Target", "Quantity", "Unit", "Scrap", "Hours"]
        data = [[
            r.date.isoformat() if r.date else "",
            str(r.shift) if r.shift is not None else "",
            r.action or "",
            r.targetName or "",
            f"{r.quantity:g}" if r.quantity is not None else "",
            PRODUCTION_TARGET_UNIT.get(r.targetType or "", ""),
            f"{r.scrapQuantity:g}",
            f"{r.hours:g}",
        ] for r in recs]
        olen = len(data)

        perAction: dict[str, tuple[float, float, float]] = {}
        for r in recs:
            q, s, h = perAction.get(r.action or "", (0.0, 0.0, 0.0))
            perAction[r.action or ""] = (q + (r.quantity or 0), s + r.scrapQuantity, h + r.hours)

        empName = self._employeeName(employeeId)
        rangeText = f"{startDate.isoformat()} through {endDate.isoformat()}"

        if olen == 0:
            self.setupPage()
            self.drawTitle("TKG Production Report")
            self.drawSubtitle(empName)
            self.skipLines(1)
            self.drawText(rangeText)
            self.skipLines(1)
            self.drawSection("Production Records")
            self.drawText("No production recorded in this range.")
            self.nextPage()
        else:
            while len(data) > 0:
                self.setupPage()
                self.drawTitle("TKG Production Report")
                self.drawSubtitle(empName)
                self.skipLines(1)
                self.drawText(rangeText)
                self.skipLines(1)
                self.drawSection("Production Records" if len(data) == olen
                                 else "Production Records -- Continued")
                drawn = self.drawTable(data, headers)
                if drawn == len(data):
                    for a in PRODUCTION_ACTIONS:
                        if a in perAction:
                            q, s, h = perAction[a]
                            unit = PRODUCTION_TARGET_UNIT[PRODUCTION_ACTION_TARGET[a]]
                            self.drawTable([], ["", "", f"Total {a}", "",
                                                f"{q:g}", unit, f"{s:g}", f"{h:g}"])
                data = data[drawn:]
                self.nextPage()
        self.pdf.save()

    def productionProductivityReport(self, action: str,
                                     targetName: str | None,
                                     shift: int | None,
                                     startDate: datetime.date,
                                     endDate: datetime.date):
        # Step 18: rate-per-hour drill-down feeding the costing code.
        # targetName is None for "all targets"; shift is None for "all shifts".
        # Tool Change has its own shape (no rate, no per-employee) and dispatches
        # to a helper below.
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')
        if action == "Tool Change":
            self._toolChangeProductivityReport(shift, startDate, endDate)
            return

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        allTargets = targetName is None
        allShifts = shift is None

        filterKwargs: dict = {"action": action}
        if not allTargets:
            filterKwargs["targetType"] = targetType
            filterKwargs["targetName"] = targetName
        recs = self._filterProduction(startDate, endDate, **filterKwargs)
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        perTarget: dict[str, tuple[float, float]] = {}
        perTargetEmp: dict[tuple[str, int | None], tuple[float, float]] = {}
        perShift: dict[int | None, tuple[float, float]] = {}
        totalQ = 0.0
        totalH = 0.0
        for r in recs:
            tn = r.targetName or ""
            q = r.quantity or 0
            h = r.hours
            cq, ch = perTarget.get(tn, (0.0, 0.0))
            perTarget[tn] = (cq + q, ch + h)
            key = (tn, r.employeeId)
            cq, ch = perTargetEmp.get(key, (0.0, 0.0))
            perTargetEmp[key] = (cq + q, ch + h)
            cq, ch = perShift.get(r.shift, (0.0, 0.0))
            perShift[r.shift] = (cq + q, ch + h)
            totalQ += q
            totalH += h

        title = f"TKG {action} Productivity"
        subtitleBits = []
        if not allTargets:
            subtitleBits.append(str(targetName))
        if not allShifts:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        def fmtRate(q: float, h: float) -> str:
            if h <= 0:
                return "—"
            return f"{q / h:.2f}"

        def fmtNum(x: float) -> str:
            return f"{x:g}"

        headersTarget = ["Target", f"Quantity ({unit})", "Hours", "Rate (per hr)"]
        headersEmp = ["Employee", f"Quantity ({unit})", "Hours", "Rate (per hr)"]
        headersShift = ["Shift", f"Quantity ({unit})", "Hours", "Rate (per hr)"]

        if len(recs) == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawText("No production recorded in this range.")
            self.nextPage()
            self.pdf.save()
            return

        def empSortKey(eid):
            emp = self.db.employees.get(eid)
            if emp is None:
                return (1, "", "", eid if eid is not None else 0)
            return (0, (emp.lastName or "").lower(),
                    (emp.firstName or "").lower(), eid or 0)

        def shiftSortKey(s):
            return (s is None, s or 0)

        def renderSection(sectionName: str, rows: list[list[str]],
                          headers: list[str],
                          totalsRow: list[str] | None = None):
            # Totals render as their own pure-header table after the main rows
            # so they come out bold — same pattern productionSummaryReport
            # uses to emphasize its "Total" row.
            olen = len(rows)
            while len(rows) > 0:
                self.setupPage()
                self.drawTitle(title)
                self.drawSubtitle(subtitle)
                self.skipLines(2)
                self.drawSection(sectionName if len(rows) == olen
                                 else f"{sectionName} -- Continued")
                drawn = self.drawTable(rows, headers)
                if drawn == len(rows) and totalsRow is not None:
                    self.drawTable([], totalsRow)
                rows = rows[drawn:]
                self.nextPage()

        def renderTargetDetail(tn: str):
            empsHere = sorted(
                {eid for (t, eid) in perTargetEmp if t == tn},
                key=empSortKey,
            )
            rows = []
            for eid in empsHere:
                eq, eh = perTargetEmp[(tn, eid)]
                rows.append([self._employeeName(eid),
                             fmtNum(eq), fmtNum(eh), fmtRate(eq, eh)])
            tq, th = perTarget[tn]
            totalsRow = ["Total", fmtNum(tq), fmtNum(th), fmtRate(tq, th)]
            renderSection(f"{action}: {tn}", rows, headersEmp, totalsRow)

        if allTargets:
            sortedTargets = sorted(perTarget.keys())
            summaryRows = []
            for tn in sortedTargets:
                tq, th = perTarget[tn]
                summaryRows.append([tn, fmtNum(tq), fmtNum(th), fmtRate(tq, th)])
            summaryTotals = ["Total", fmtNum(totalQ), fmtNum(totalH),
                             fmtRate(totalQ, totalH)]
            renderSection("Summary by Target", summaryRows, headersTarget,
                          summaryTotals)

            if allShifts:
                shiftRows = []
                for s in sorted(perShift.keys(), key=shiftSortKey):
                    sq, sh = perShift[s]
                    lbl = str(s) if s is not None else "(none)"
                    shiftRows.append([lbl, fmtNum(sq), fmtNum(sh), fmtRate(sq, sh)])
                shiftTotals = ["Total", fmtNum(totalQ), fmtNum(totalH),
                               fmtRate(totalQ, totalH)]
                renderSection("Overview by Shift", shiftRows, headersShift,
                              shiftTotals)

            for tn in sortedTargets:
                renderTargetDetail(tn)
        else:
            renderTargetDetail(targetName)

        self.pdf.save()

    def _toolChangeProductivityReport(self, shift: int | None,
                                      startDate: datetime.date,
                                      endDate: datetime.date):
        # Tool Change collapse: no rate/hr, no per-employee. Just total hours
        # per shift (or a single row when a shift is selected). The shift
        # selector stays active at the UI layer so "specific shift" is legal;
        # it just produces a one-row table.
        recs = self._filterProduction(startDate, endDate, action="Tool Change")
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        perShift: dict[int | None, float] = {}
        totalH = 0.0
        for r in recs:
            perShift[r.shift] = perShift.get(r.shift, 0.0) + r.hours
            totalH += r.hours

        title = "TKG Tool Change Productivity"
        subtitleBits = []
        if shift is not None:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        if len(recs) == 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawText("No production recorded in this range.")
            self.nextPage()
            self.pdf.save()
            return

        headers = ["Shift", "Total Hours"]
        rows: list[list[str]] = []
        totalsRow: list[str] | None = None
        if shift is None:
            for s in sorted(perShift.keys(),
                            key=lambda k: (k is None, k or 0)):
                lbl = str(s) if s is not None else "(none)"
                rows.append([lbl, f"{perShift[s]:g}"])
            totalsRow = ["Total", f"{totalH:g}"]
        else:
            # Specific-shift: the single row is already the total; no separate
            # totals row would add anything.
            rows.append([str(shift), f"{totalH:g}"])

        olen = len(rows)
        while len(rows) > 0:
            self.setupPage()
            self.drawTitle(title)
            self.drawSubtitle(subtitle)
            self.skipLines(2)
            self.drawSection("Hours by Shift" if len(rows) == olen
                             else "Hours by Shift -- Continued")
            drawn = self.drawTable(rows, headers)
            if drawn == len(rows) and totalsRow is not None:
                self.drawTable([], totalsRow)
            rows = rows[drawn:]
            self.nextPage()
        self.pdf.save()

    def productionTrendReport(self, action: str,
                              targetName: str | None,
                              shift: int | None,
                              startDate: datetime.date,
                              endDate: datetime.date):
        # Step 19: 30-day rolling-rate line chart. Graph-only; numbers for the
        # same window come from the Step 18 productivity report. Range is
        # validated to be at least TREND_MIN_RANGE_DAYS so the window always
        # has a meaningful span; the UI enforces this too, but the report is a
        # public entrypoint so we belt-and-suspender it.
        if action not in PRODUCTION_ACTIONS:
            raise RuntimeError(f'unknown action {action!r}')
        if (endDate - startDate).days < TREND_MIN_RANGE_DAYS - 1:
            raise RuntimeError(
                f'Trend reports require a date range of at least '
                f'{TREND_MIN_RANGE_DAYS} days.'
            )
        if action == "Tool Change":
            self._toolChangeTrendReport(shift, startDate, endDate)
            return

        targetType = PRODUCTION_ACTION_TARGET[action]
        unit = PRODUCTION_TARGET_UNIT[targetType]
        allTargets = targetName is None
        allShifts = shift is None

        # Only plot days whose full 30-day lookback fits inside the requested
        # range — reaching outside the range would mean partial windows and a
        # noisy leading edge (first 30 points climbing up to a steady state).
        # Per Matthew 2026-04-24: every datapoint must represent a full window.
        plotStart = startDate + datetime.timedelta(days=TREND_WINDOW_DAYS - 1)

        filterKwargs: dict = {"action": action}
        if not allTargets:
            filterKwargs["targetType"] = targetType
            filterKwargs["targetName"] = targetName
        recs = self._filterProduction(startDate, endDate, **filterKwargs)
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        title = f"TKG {action} Trend"
        subtitleBits = []
        if not allTargets:
            subtitleBits.append(str(targetName))
        if not allShifts:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        yLabel = f"Rate ({unit}/hr, 30-day avg)"

        if allTargets:
            # Leading aggregate chart across every target, then one chart per
            # target. Order: total first (team wants the fleet view up front),
            # then alphabetical by target name.
            aggSeries = self._buildTrendSeries(recs, plotStart, endDate,
                                               splitByShift=allShifts)
            self._drawTrendPage(title, subtitle, "All targets (aggregate)",
                                aggSeries, yLabel)
            targets = sorted({r.targetName for r in recs if r.targetName})
            for tn in targets:
                subset = [r for r in recs if r.targetName == tn]
                series = self._buildTrendSeries(subset, plotStart, endDate,
                                                splitByShift=allShifts)
                self._drawTrendPage(title, subtitle, f"Target: {tn}",
                                    series, yLabel)
        else:
            series = self._buildTrendSeries(recs, plotStart, endDate,
                                            splitByShift=allShifts)
            self._drawTrendPage(title, subtitle, f"Target: {targetName}",
                                series, yLabel)
        self.pdf.save()

    def _toolChangeTrendReport(self, shift: int | None,
                               startDate: datetime.date,
                               endDate: datetime.date):
        # Tool Change has no rate/hr — "time spent" is the metric. We plot the
        # 30-day rolling *sum* of hours so the y-axis reads as "hours spent on
        # tool changes in the preceding 30 days." This mirrors Step 18's Tool
        # Change collapse (which surfaces total hours by shift) and gives the
        # team a trend line they can compare month-over-month.
        plotStart = startDate + datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
        recs = self._filterProduction(startDate, endDate, action="Tool Change")
        if shift is not None:
            recs = [r for r in recs if r.shift == shift]

        title = "TKG Tool Change Trend"
        subtitleBits = []
        if shift is not None:
            subtitleBits.append(f"Shift {shift}")
        subtitleBits.append(f"{startDate.isoformat()} through {endDate.isoformat()}")
        subtitle = " — ".join(subtitleBits)

        series = self._buildToolChangeTrendSeries(
            recs, plotStart, endDate, splitByShift=(shift is None))
        self._drawTrendPage(title, subtitle, "Time spent",
                            series, "Hours (30-day total)")
        self.pdf.save()

    def _rollingRate(self, perDay: dict, startDate: datetime.date,
                     endDate: datetime.date, mode: str | None = None):
        # Given perDay: {date: (qty, hours)}, return [(date, rate_or_None), ...]
        # for every date in [startDate, endDate]. rate is None when the window
        # has no usable data (caller drops None points before plotting).
        mode = mode if mode is not None else TREND_MODE
        out: list[tuple[datetime.date, float | None]] = []
        d = startDate
        step = datetime.timedelta(days=1)
        while d <= endDate:
            windowStart = d - datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
            if mode == "ratioOfSums":
                sumQ = 0.0
                sumH = 0.0
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        q, h = perDay[wd]
                        sumQ += q
                        sumH += h
                    wd += step
                rate = (sumQ / sumH) if sumH > 0 else None
            elif mode == "meanOfRates":
                rates = []
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        q, h = perDay[wd]
                        if q > 0 and h > 0:
                            rates.append(q / h)
                    wd += step
                rate = (sum(rates) / len(rates)) if rates else None
            else:
                raise RuntimeError(f'unknown TREND_MODE {mode!r}')
            out.append((d, rate))
            d += step
        return out

    def _buildTrendSeries(self, recs, startDate, endDate, splitByShift):
        # Build [(label, [(date, y_or_None), ...]), ...] for non-Tool-Change
        # trends. When splitByShift is True, emit one series per shift plus
        # a final "All shifts" aggregate.
        def toPerDay(subset):
            perDay: dict[datetime.date, tuple[float, float]] = {}
            for r in subset:
                if r.date is None:
                    continue
                q, h = perDay.get(r.date, (0.0, 0.0))
                perDay[r.date] = (q + (r.quantity or 0), h + r.hours)
            return perDay

        if not splitByShift:
            return [("Rate", self._rollingRate(toPerDay(recs), startDate, endDate))]

        out = []
        shifts = sorted({r.shift for r in recs if r.shift is not None})
        for s in shifts:
            subset = [r for r in recs if r.shift == s]
            out.append((f"Shift {s}",
                        self._rollingRate(toPerDay(subset), startDate, endDate)))
        noneSubset = [r for r in recs if r.shift is None]
        if len(noneSubset) > 0:
            out.append(("Shift (none)",
                        self._rollingRate(toPerDay(noneSubset), startDate, endDate)))
        out.append(("All shifts",
                    self._rollingRate(toPerDay(recs), startDate, endDate)))
        return out

    def _buildToolChangeTrendSeries(self, recs, startDate, endDate, splitByShift):
        # Tool Change variant: 30-day rolling *sum* of hours instead of a rate.
        def toPerDay(subset):
            perDay: dict[datetime.date, float] = {}
            for r in subset:
                if r.date is None:
                    continue
                perDay[r.date] = perDay.get(r.date, 0.0) + r.hours
            return perDay

        def rollingSum(perDay):
            out = []
            d = startDate
            step = datetime.timedelta(days=1)
            while d <= endDate:
                windowStart = d - datetime.timedelta(days=TREND_WINDOW_DAYS - 1)
                total = 0.0
                wd = windowStart
                while wd <= d:
                    if wd in perDay:
                        total += perDay[wd]
                    wd += step
                out.append((d, total))
                d += step
            return out

        if not splitByShift:
            return [("Hours", rollingSum(toPerDay(recs)))]

        out = []
        shifts = sorted({r.shift for r in recs if r.shift is not None})
        for s in shifts:
            subset = [r for r in recs if r.shift == s]
            out.append((f"Shift {s}", rollingSum(toPerDay(subset))))
        noneSubset = [r for r in recs if r.shift is None]
        if len(noneSubset) > 0:
            out.append(("Shift (none)", rollingSum(toPerDay(noneSubset))))
        out.append(("All shifts", rollingSum(toPerDay(recs))))
        return out

    def _drawTrendPage(self, title: str, subtitle: str, sectionLabel: str,
                       series: list, yLabel: str):
        # One trend chart per page. Header matches the productivity report's
        # title/subtitle/section cadence so switching between the two reports
        # feels consistent.
        self.setupPage()
        self.drawTitle(title)
        self.drawSubtitle(subtitle)
        self.skipLines(1)
        self.drawSection(sectionLabel)

        # Drop series whose every point is None (e.g., a shift with no data in
        # the window). A series that's mostly data but has occasional None
        # points is kept; those None points are filtered out before plotting,
        # so the line connects across small gaps. Require >= 2 concrete points
        # so reportlab has a line to draw.
        cleaned = []
        anyConcrete = False
        for (label, pts) in series:
            concrete = [(d, y) for (d, y) in pts if y is not None]
            if len(concrete) > 0:
                anyConcrete = True
            if len(concrete) >= 2:
                cleaned.append((label, concrete))

        if len(cleaned) == 0:
            self.skipLines(1)
            if anyConcrete:
                # Data exists but the range leaves < 2 full-window datapoints
                # — i.e. the user picked the 30-day floor, which gives a
                # single plot point. Tell them plainly.
                self.drawText("Not enough data in this range to plot a trend line "
                              "(try a longer date range).")
            else:
                self.drawText("No production recorded in this range.")
            self.nextPage()
            return

        self.drawLinePlot(cleaned, yLabel)
        self.nextPage()

    def drawLinePlot(self, series: list, yLabel: str):
        # Renders one LinePlot + Legend inside a single Drawing placed at
        # self.lastLine. series is [(label, [(date, y), ...]), ...] with every
        # y already non-None and every series having >= 2 points.
        plotWidth = self.right - self.left
        plotHeight = 3.5 * inch

        drawing = Drawing(plotWidth, plotHeight)

        lp = LinePlot()
        lp.x = 55
        lp.y = 55
        lp.width = plotWidth - 180  # reserve space on the right for the legend
        lp.height = plotHeight - 85

        # x-axis in date ordinals so reportlab's numeric axis tick picker works.
        # labelTextFormat converts back to an ISO date for display.
        lp.data = [[(d.toordinal(), y) for (d, y) in pts]
                   for (_, pts) in series]

        for i in range(len(series)):
            color = _TREND_LINE_COLORS[i % len(_TREND_LINE_COLORS)]
            lp.lines[i].strokeColor = color
            lp.lines[i].strokeWidth = 1.2

        lp.xValueAxis.labelTextFormat = (
            lambda x: datetime.date.fromordinal(int(x)).isoformat()
        )
        lp.xValueAxis.labels.angle = 45
        lp.xValueAxis.labels.boxAnchor = 'e'
        lp.xValueAxis.labels.fontSize = 7
        lp.xValueAxis.visibleGrid = True
        lp.xValueAxis.gridStrokeColor = colors.lightgrey

        lp.yValueAxis.labels.fontSize = 8
        lp.yValueAxis.visibleGrid = True
        lp.yValueAxis.gridStrokeColor = colors.lightgrey

        drawing.add(lp)

        # Axis labels (non-rotated — keeps the helper simple and legible).
        drawing.add(String(lp.x + lp.width / 2, 8,
                           "Date", fontSize=9, textAnchor='middle'))
        drawing.add(String(10, lp.y + lp.height + 6,
                           yLabel, fontSize=9, textAnchor='start'))

        legend = Legend()
        legend.x = plotWidth - 110
        legend.y = lp.y + lp.height - 10
        legend.colorNamePairs = [
            (_TREND_LINE_COLORS[i % len(_TREND_LINE_COLORS)], series[i][0])
            for i in range(len(series))
        ]
        legend.fontSize = 8
        legend.deltay = 11
        legend.alignment = 'right'
        legend.columnMaximum = 10
        drawing.add(legend)

        renderPDF.draw(drawing, self.pdf, self.left, self.lastLine - plotHeight)
        self.lastLine -= plotHeight