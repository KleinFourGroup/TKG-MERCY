from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from records import Database


class PDFReportCore:
    # Owns the canvas + page geometry + the drawing primitives every domain
    # report builds on (drawTitle / drawTable / drawText / etc.). Composed into
    # PDFReport last so the per-domain mixins can lean on these without having
    # to redefine them. See report/__init__.py for the composition.

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

        if widths is None:
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
