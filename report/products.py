import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from records import Database
    from reportlab.pdfgen import canvas


class ProductReportsMixin:
    # Product-domain PDF reports: globals (cost parameters), mixture composition
    # + chemistry, sales-vs-cost analysis, and inventory snapshots. All four
    # build on the primitives in PDFReportCore — see report/__init__.py for the
    # composition.

    if TYPE_CHECKING:
        # Attributes + helpers provided by PDFReportCore (composed in last).
        db: Database
        pdf: canvas.Canvas
        def setupPage(self) -> None: ...
        def nextPage(self) -> None: ...
        def skipLines(self, numLines) -> None: ...
        def drawText(self, text: str) -> None: ...
        def drawTitle(self, text: str) -> None: ...
        def drawSection(self, text: str) -> None: ...
        def drawTable(self, data: list[list[str]], headers: list[str] | None = None, widths: list[float] | None = None) -> int: ...

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
        _, origValMatl_prevDate = processMaterials(prevDate) if prevDate is not None else (0, 0)
        _, origValPartWIP_prevDate = processPartsWIP(prevDate) if prevDate is not None else (0, 0)
        _, origValPartCompleted_prevDate = processPartsCompleted(prevDate) if prevDate is not None else (0, 0)

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
