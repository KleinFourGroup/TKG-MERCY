import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from records.database import Database

LBS_PER_TON = 2000  # short ton

class Material:
    def __init__(self, name) -> None:
        self.name = name
        self.db: Database | None = None
        self.price = None
        self.freight = None
        self.SiO2 = None
        self.Al2O3 = None
        self.Fe2O3 = None
        self.TiO2 = None
        self.Li2O = None
        self.P2O5 = None
        self.Na2O = None
        self.CaO = None
        self.K2O = None
        self.MgO = None
        self.LOI = None
        self.Plus50 = None
        self.Sub50Plus100 = None
        self.Sub100Plus200 = None
        self.Sub200Plus325 = None
        self.Sub325 = None
        self.otherChem = None

    def setCost(self, price, freight):
        self.price = price
        self.freight = freight

    def setChems(self, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI) -> None:
        self.SiO2 = SiO2
        self.Al2O3 = Al2O3
        self.Fe2O3 = Fe2O3
        self.TiO2 = TiO2
        self.Li2O = Li2O
        self.P2O5 = P2O5
        self.Na2O = Na2O
        self.CaO = CaO
        self.K2O = K2O
        self.MgO = MgO
        self.LOI = LOI

    def setSizes(self, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325) -> None:
        self.Plus50 = Plus50
        self.Sub50Plus100 = Sub50Plus100
        self.Sub100Plus200 = Sub100Plus200
        self.Sub200Plus325 = Sub200Plus325
        self.Sub325 = Sub325

    def getCostPerLb(self):
        if self.price is None or self.freight is None:
            return None
        return (self.price + self.freight) / LBS_PER_TON

    def getTuple(self):
        return (
            self.name,
            self.price,
            self.freight,
            self.SiO2,
            self.Al2O3,
            self.Fe2O3,
            self.TiO2,
            self.Li2O,
            self.P2O5,
            self.Na2O,
            self.CaO,
            self.K2O,
            self.MgO,
            self.LOI,
            self.Plus50,
            self.Sub50Plus100,
            self.Sub100Plus200,
            self.Sub200Plus325,
            self.Sub325,
            self.otherChem
        )

    def fromTuple(self, vals):
        self.name = vals[0]
        self.setCost(*vals[1:3])
        self.setChems(*vals[3:14])
        self.setSizes(*vals[14:19])
        self.otherChem = vals[19] if len(vals) > 19 else 0

    def __str__(self) -> str:
        res = "({} | {} {} | {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {} | {} | {}, {}, {}, {}, {})".format(self.name,
                self.price, self.freight,
                 self.SiO2, self.Al2O3, self.Fe2O3, self.TiO2, self.Li2O, self.P2O5, self.Na2O, self.CaO, self.K2O, self.MgO, self.LOI, self.otherChem,
                 self.Plus50, self.Sub50Plus100, self.Sub100Plus200, self.Sub200Plus325, self.Sub325)
        return res

class Package:
    def __init__(self, name, kind, price) -> None:
        self.name = name
        self.db: Database | None = None
        self.kind = kind
        self.price = price
    def getTuple(self):
        return (
            self.name,
            self.kind,
            self.price
        )
    def fromTuple(self, values):
        self.name = values[0]
        self.kind = values[1]
        self.price = values[2]
    def __str__(self) -> str:
        res = "({} {} {})".format(self.name, self.kind, self.price)
        return res

class Mixture:
    def __init__(self, name, materials: list[str] = [], weights: list[int] = []) -> None:
        self.name = name
        self.db: Database | None = None
        self.materials = materials[:]
        self.weights = weights[:]
    def add(self, mat, wt):
        self.materials.append(mat)
        self.weights.append(wt)
    def getCost(self):
        if not (self.db is not None and self.db.materials is not None):
            raise RuntimeError('self.db is not None and self.db.materials is not None')
        cost = 0
        weight = 0
        for wt in self.weights:
            weight += wt
        for i in range(len(self.materials)):
            pct = self.weights[i] / weight
            costPerLb = self.db.materials[self.materials[i]].getCostPerLb()
            if costPerLb is None:
                raise RuntimeError('costPerLb is None')
            cost += pct * costPerLb
        return cost
    def getBatchWeight(self):
        weight = 0
        for wt in self.weights:
            weight += wt
        return weight
    def getProp(self, prop, LOI = True):
        if not (self.db is not None and self.db.materials is not None):
            raise RuntimeError('self.db is not None and self.db.materials is not None')
        ret = 0
        for i in range(len(self.materials)):
            matVal = getattr(self.db.materials[self.materials[i]], prop)
            if matVal is None:
                ret = None
                break
            pct = self.weights[i] / self.getBatchWeight()
            matLOI = self.db.materials[self.materials[i]].LOI
            if matLOI is None:
                raise RuntimeError('matLOI is None')
            ret += (pct * matVal / (1 - matLOI / 100)) if LOI else pct * matVal
        return ret

    def getTuple(self):
        return (self.name,)

    def fromTuple(self, values):
        self.name = values[0]
        self.materials = []
        self.weights = []

    def getComponentTuples(self):
        return [
            (self.name, self.materials[i], self.weights[i], i)
            for i in range(len(self.materials))
        ]

    def __str__(self) -> str:
        pairs = []
        for i in range(len(self.materials)):
            pair = "{}, {}".format(self.materials[i], self.weights[i])
            pairs.append(pair)
        res = "({} | {})".format(self.name, " | ".join(pairs))
        return res

class Globals:
    def __init__(self) -> None:
        self.gasCost = 0.0523
        self.batchingFactor = 1.167/1466.5
        self.laborCost = 19.25
        self.greenScrap = 2.6
        self.loading = 0.075
        self.inspection = 0.107
        self.manufacturingOverhead = 0.2404
        self.SGA = 0.5129

    def getGlobals(self):
        return [
            "gasCost",
            "batchingFactor",
            "laborCost",
            "greenScrap",
            "loading",
            "inspection",
            "manufacturingOverhead",
            "SGA"
        ]

    def getStrings(self):
        return {
            "gasCost": ("Gas cost", "$ / lb"),
            "batchingFactor": ("Batching time", "hrs / lb"),
            "laborCost": ("Labor", "$ / hr"),
            "greenScrap": ("Green scrap", "%" + " by weight"),
            "loading": ("Loading cost", "$ / pt"),
            "inspection": ("Inspection cost", "$ / pt"),
            "manufacturingOverhead": ("Manufacturing overhead", "$ / lb"),
            "SGA": ("SGA", "$ / lb"),
        }

class Part:
    def __init__(self, name) -> None:
        self.name = name
        self.db: Database | None = None
        self.weight: float | None = None
        self.mix = None
        self.pressing: float | None = None # pieces / hour
        self.turning: float | None = None # pieces / hour
        self.fireScrap = None
        self.box: str | None = None
        self.piecesPerBox: int | None = None
        self.pallet: str | None = None
        self.boxesPerPallet: int | None = None
        self.pad: list[str] | None = None
        self.padsPerBox: list[int] | None = None
        self.misc = []
        self.price: float | None = None
        self.sales = None

    def setProduction(self, weight, mix, pressing, turning, fireScrap, price):
        self.weight = weight
        self.mix = mix
        self.pressing = pressing
        self.turning = turning
        self.fireScrap = fireScrap
        self.price = price

    def setPackaging(self, box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc):
        self.box = box
        self.piecesPerBox = piecesPerBox
        self.pallet = pallet
        self.boxesPerPallet = boxesPerPallet
        self.pad = pad
        self.padsPerBox = padsPerBox
        self.misc.clear()
        self.misc.extend(misc)

    def getMixCost(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.weight is None:
            raise RuntimeError('self.weight is None')
        if self.mix is None:
            raise RuntimeError('self.mix is None')
        return self.weight * self.db.mixtures[self.mix].getCost()

    def getGasCost(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.weight is None:
            raise RuntimeError('self.weight is None')
        return self.weight * self.db.globals.gasCost

    def getMatlCost(self):
        return self.getMixCost() + self.getGasCost()

    def getBatchingTime(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.weight is None:
            raise RuntimeError('self.weight is None')
        return self.weight * self.db.globals.batchingFactor

    def getPressingTime(self):
        if self.pressing is None:
            raise RuntimeError('self.pressing is None')
        return 1 / self.pressing

    def getTurningTime(self):
        if self.turning is None:
            raise RuntimeError('self.turning is None')
        return 1 / self.turning

    def getLaborHours(self):
        return self.getBatchingTime() + self.getPressingTime() + self.getTurningTime()

    def getLaborCost(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        return self.getLaborHours() * self.db.globals.laborCost

    def getScrap(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.fireScrap is None:
            raise RuntimeError('self.fireScrap is None')
        # return self.greenScrap +self.fireScrap
        return (self.db.globals.greenScrap / 100) + self.fireScrap

    #
    def getGrossMatlCost(self):
        return self.getMatlCost() / (1 - self.getScrap())
    def getGrossLaborCost(self):
        return self.getLaborCost() / (1 - self.getScrap())
    def getGrossMatlLaborCost(self):
        return (self.getMatlCost() + self.getLaborCost()) / (1 - self.getScrap())

    def getPackagingCost(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.box is None:
            raise RuntimeError('self.box is None')
        if self.piecesPerBox is None:
            raise RuntimeError('self.piecesPerBox is None')
        if self.pad is None:
            raise RuntimeError('self.pad is None')
        if self.padsPerBox is None:
            raise RuntimeError('self.padsPerBox is None')
        if self.pallet is None:
            raise RuntimeError('self.pallet is None')
        if self.boxesPerPallet is None:
            raise RuntimeError('self.boxesPerPallet is None')
        boxCost = self.db.packaging[self.box].price
        padCost = 0
        for i in range(len(self.pad)):
            padCost += self.db.packaging[self.pad[i]].price * self.padsPerBox[i]
        palletCost = self.db.packaging[self.pallet].price
        perPalletCost = (boxCost + padCost) * self.boxesPerPallet + palletCost
        miscCost = 0
        for i in range(len(self.misc)):
            miscCost += self.db.packaging[self.misc[i]].price

        return perPalletCost / (self.piecesPerBox * self.boxesPerPallet) + miscCost

    def getVariableCost(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        return self.getGrossMatlLaborCost() + self.getPackagingCost() + self.db.globals.inspection + self.db.globals.loading

    def getManufacturingOverhead(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.weight is None:
            raise RuntimeError('self.weight is None')
        return self.weight * self.db.globals.manufacturingOverhead

    def getManufacturingCost(self):
        return self.getVariableCost() + self.getManufacturingOverhead()

    def getSGA(self):
        if self.db is None:
            raise RuntimeError('self.db is None')
        if self.weight is None:
            raise RuntimeError('self.weight is None')
        return self.weight * self.db.globals.SGA

    def getTotalCost(self):
        return self.getManufacturingCost() + self.getSGA()

    def getGM(self):
        return (self.price - self.getManufacturingCost()) / self.price

    def solveGM(self, target):
        return self.getManufacturingCost() / (1 - target)

    def getCM(self):
        return (self.price - self.getVariableCost()) / self.price

    def solveCM(self, target):
        return self.getVariableCost() / (1 - target)

    def getTuple(self):
        return (
            self.name,
            self.weight,
            self.mix,
            self.pressing,
            self.turning,
            self.fireScrap,
            self.box,
            self.piecesPerBox,
            self.pallet,
            self.boxesPerPallet,
            self.price,
            self.sales
        )

    def fromTuple(self, values):
        self.name = values[0]
        self.setProduction(values[1], values[2], values[3], values[4],
                           values[5], values[10])
        self.setPackaging(
            values[6], values[7], values[8], values[9],
            [], [], []
        )
        self.sales = values[11]

    def getPadTuples(self):
        pads = self.pad or []
        ppb = self.padsPerBox or []
        return [(self.name, pads[i], ppb[i], i) for i in range(len(pads))]

    def getMiscTuples(self):
        return [(self.name, self.misc[i], i) for i in range(len(self.misc))]

    def __str__(self) -> str:
        if self.fireScrap is None:
            raise RuntimeError('self.fireScrap is None')
        res = "({} | {}, {}, {}, {}, {}% | {}, {}, {}, {}, {}, {}, {} | {})".format(self.name,
                self.weight, self.mix, self.pressing, self.turning, 100 * self.fireScrap,
                self.box, self.piecesPerBox, self.pallet, self.boxesPerPallet, self.pad, self.padsPerBox, self.misc,
                self.price)
        return res

class MaterialInventoryRecord:
    def __init__(self) -> None:
        self.name: str | None = None
        self.date: datetime.date | None = None
        self.cost: float | None = None
        self.amount: float | None = None

    def setName(self, name: str):
        self.name = name

    def setDate(self, date: datetime.date):
        self.date = date

    def setInventory(self, cost: float, amount: float):
        self.cost = cost
        self.amount = amount

    def getTuple(self):
        if self.name is None:
            raise RuntimeError('self.name is None')
        if self.date is None:
            raise RuntimeError('self.date is None')
        if self.cost is None:
            raise RuntimeError('self.cost is None')
        if self.amount is None:
            raise RuntimeError('self.amount is None')
        return (
            self.name,
            self.date.isoformat(),
            self.cost,
            self.amount
        )

    def fromTuple(self, row: tuple[str, str, float, float]):
        self.setName(row[0])
        self.setDate(datetime.date.fromisoformat(row[1]))
        self.setInventory(row[2], row[3])

    def __str__(self):
        return f"({self.name}, {self.date} | {self.cost}, {self.amount})"

class PartInventoryRecord:
    def __init__(self) -> None:
        self.name: str | None = None
        self.date: datetime.date | None = None
        self.cost: float | None = None
        self.amount40: float | None = None
        self.amount60: float | None = None
        self.amount80: float | None = None
        self.amount100: float | None = None

    def setName(self, name: str):
        self.name = name

    def setDate(self, date: datetime.date):
        self.date = date

    def setInventory(self, cost: float, amount40: float, amount60: float, amount80: float, amount100: float):
        self.cost = cost
        self.amount40 = amount40
        self.amount60 = amount60
        self.amount80 = amount80
        self.amount100 = amount100

    def getTuple(self):
        if self.name is None:
            raise RuntimeError('self.name is None')
        if self.date is None:
            raise RuntimeError('self.date is None')
        if self.cost is None:
            raise RuntimeError('self.cost is None')
        if self.amount40 is None:
            raise RuntimeError('self.amount40 is None')
        if self.amount60 is None:
            raise RuntimeError('self.amount60 is None')
        if self.amount80 is None:
            raise RuntimeError('self.amount80 is None')
        if self.amount100 is None:
            raise RuntimeError('self.amount100 is None')
        return (
            self.name,
            self.date.isoformat(),
            self.cost,
            self.amount40,
            self.amount60,
            self.amount80,
            self.amount100
        )

    def fromTuple(self, row: tuple[str, str, float, float, float, float, float]):
        self.setName(row[0])
        self.setDate(datetime.date.fromisoformat(row[1]))
        self.setInventory(row[2], row[3], row[4], row[5], row[6])

    def __str__(self):
        return f"({self.name}, {self.date} | {self.cost}, {self.amount40}, {self.amount60}, {self.amount80}, {self.amount100})"

class Inventory:
    def __init__(self, date: datetime.date | None = None) -> None:
        self.date = date
        self.materials: dict[str, MaterialInventoryRecord] = {}
        self.parts: dict[str, PartInventoryRecord] = {}

    def updateMaterialRecord(self, oldName: str, newName: str):
        if oldName not in self.materials:
            raise RuntimeError('oldName not in self.materials')
        if not newName == oldName:
            materials = {newName if key == oldName else key:val for key, val in self.materials.items()}
            self.materials = materials
            self.materials[newName].setName(newName)

    def addMaterialRecord(self, materialRec: MaterialInventoryRecord):
        if materialRec.name is None:
            raise RuntimeError('materialRec.name is None')
        if self.date is None:
            raise RuntimeError('self.date is None')
        if not (self.date == materialRec.date):
            raise RuntimeError('self.date == materialRec.date')
        if materialRec.name in self.parts:
            raise RuntimeError('materialRec.name already in self.parts')

        self.materials[materialRec.name] = materialRec

    def delMaterialRecord(self, name: str):
        if name not in self.materials:
            raise RuntimeError('name not in self.materials')
        del self.materials[name]

    def updatePartRecord(self, oldName: str, newName: str):
        if oldName not in self.parts:
            raise RuntimeError('oldName not in self.parts')
        if not newName == oldName:
            parts = {newName if key == oldName else key:val for key, val in self.parts.items()}
            self.parts = parts
            self.parts[newName].setName(newName)

    def addPartRecord(self, partRec: PartInventoryRecord):
        if partRec.name is None:
            raise RuntimeError('partRec.name is None')
        if self.date is None:
            raise RuntimeError('self.date is None')
        if not (self.date == partRec.date):
            raise RuntimeError('self.date == partRec.date')
        if partRec.name in self.parts:
            raise RuntimeError('partRec.name already in self.parts')

        self.parts[partRec.name] = partRec

    def delPartRecord(self, name: str):
        if name not in self.parts:
            raise RuntimeError('name not in self.parts')
        del self.parts[name]

    def getMaterialTuples(self):
        ret = []
        for name in self.materials:
            ret.append(self.materials[name].getTuple())
        return ret

    def getPartTuples(self):
        ret = []
        for name in self.parts:
            ret.append(self.parts[name].getTuple())
        return ret
