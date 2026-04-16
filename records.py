import sqlite3
import datetime
from utils import listToString, stringToList

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
        if self.price == None or self.freight == None:
            return None
        return (self.price + self.freight) / 2000 #2200?
    
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
        assert(self.db is not None and self.db.materials is not None)
        cost = 0
        weight = 0
        for wt in self.weights:
            weight += wt
        for i in range(len(self.materials)):
            pct = self.weights[i] / weight
            costPerLb = self.db.materials[self.materials[i]].getCostPerLb()
            assert(costPerLb is not None)
            cost += pct * costPerLb
        return cost
    def getBatchWeight(self):
        weight = 0
        for wt in self.weights:
            weight += wt
        return weight
    def getProp(self, prop, LOI = True):
        assert(self.db is not None and self.db.materials is not None)
        ret = 0
        for i in range(len(self.materials)):
            matVal = getattr(self.db.materials[self.materials[i]], prop)
            if matVal == None:
                ret = None
                break
            pct = self.weights[i] / self.getBatchWeight()
            matLOI = self.db.materials[self.materials[i]].LOI
            assert(matLOI is not None)
            ret += (pct * matVal / (1 - matLOI / 100)) if LOI else pct * matVal
        return ret
    
    def getTuple(self):
        return (
            self.name,
            listToString(self.materials, str),
            listToString(self.weights, float)
        )
    
    def fromTuple(self, values):
        self.name = values[0]
        self.materials = stringToList(values[1], str)
        self.weights = stringToList(values[2], float)

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
    
class ImportedPart:
    def __init__(self, name) -> None:
        self.name = name
        self.db: Database | None = None
        self.weight: float | None = None
        self.boardQty: int | None = None
        self.mix: str | None = None
        self.pressing: int | None = None # trucks / shift
        self.turning: float | None = None # hours / truck
        self.loading: float | None = None # hours / truck
        self.unloading: float | None = None # hours / truck
        self.inspection = None # pieces / hour
        self.scrap: float | None = None
        self.box: str | None = None
        self.piecesPerBox: int | None = None
        self.pallet: str | None = None
        self.boxesPerPallet: int | None = None
        self.pad: list[str] | None = None
        self.padsPerBox: list[int] | None = None
        self.misc = []
        self.price: float | None = None

    def setProduction(self, weight, boardQty, mix, pressing, turning, loading, unloading, inspection, scrap, price):
        self.weight = weight
        self.boardQty = boardQty
        self.mix = mix
        self.pressing = pressing
        self.turning = turning
        self.loading = loading
        self.unloading = unloading
        self.inspection = inspection
        self.scrap = scrap
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
        assert(self.db is not None)
        assert(self.weight is not None)
        assert(self.mix is not None)
        return self.weight * self.db.mixtures[self.mix].getCost()
    
    def getGasCost(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.gasCost
    
    def getMatlCost(self):
        return self.getMixCost() + self.getGasCost()
    
    def getBatchingTime(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.batchingFactor
    
    def getPressingTime(self):
        assert(self.pressing is not None)
        assert(self.boardQty is not None)
        return 8 / (18 * self.pressing * self.boardQty)
    
    def getTurningTime(self):
        assert(self.turning is not None)
        assert(self.boardQty is not None)
        return self.turning / (18 * self.boardQty)
    
    def getLoadingTime(self):
        assert(self.loading is not None)
        assert(self.boardQty is not None)
        return self.loading / (18 * self.boardQty)
    
    def getUnloadingTime(self):
        assert(self.unloading is not None)
        assert(self.boardQty is not None)
        return self.unloading / (18 * self.boardQty)
    
    def getInspectionTime(self):
        assert(self.inspection is not None)
        return 1 / self.inspection
    
    def getLaborHours(self):
        return self.getBatchingTime() + self.getPressingTime() + self.getTurningTime() + self.getLoadingTime() + self.getUnloadingTime() + self.getInspectionTime()
    
    def getLaborCost(self):
        assert(self.db is not None)
        return self.getLaborHours() * self.db.globals.laborCost
    
    def getGrossMatlLaborCost(self):
        assert(self.scrap is not None)
        return (self.getMatlCost() + self.getLaborCost()) / (1 - self.scrap)
    
    def getPackagingCost(self):
        assert(self.db is not None)
        assert(self.box is not None)
        assert(self.pad is not None)
        assert(self.padsPerBox is not None)
        assert(self.pallet is not None)
        assert(self.piecesPerBox is not None)
        assert(self.boxesPerPallet is not None)
        boxCost = self.db.packaging[self.box].price
        padCost = 0
        padStrs = []
        for i in range(len(self.pad)):
            padStrs.append("{} ({}) * {}".format(self.db.packaging[self.pad[i]].price , self.pad[i], self.padsPerBox[i]))
            padCost += self.db.packaging[self.pad[i]].price * self.padsPerBox[i]
        palletCost = self.db.packaging[self.pallet].price
        perPalletCost = (boxCost + padCost) * self.boxesPerPallet + palletCost
        miscCost = 0
        for i in range(len(self.misc)):
            miscCost += self.db.packaging[self.misc[i]].price

        return perPalletCost / (self.piecesPerBox * self.boxesPerPallet) + miscCost
    
    def getManufacturingOverhead(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.manufacturingOverhead
    
    def getManufacturingCost(self):
        return self.getGrossMatlLaborCost() + self.getPackagingCost() + self.getManufacturingOverhead()
    
    def getSGA(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.SGA
    
    def getTotalCost(self):
        return self.getManufacturingCost() + self.getSGA()
    
    def getVariableCost(self):
        return self.getGrossMatlLaborCost() + self.getPackagingCost()
    
    def getGM(self):
        return (self.price - self.getManufacturingCost()) / self.price
    
    def getCM(self):
        return (self.price - self.getVariableCost()) / self.price
    
    def getProductivity(self):
        assert(self.weight is not None)
        assert(self.scrap is not None)
        return self.weight * (1 - self.scrap) / self.getLaborHours()
    
    def convert(self):
        assert(self.boardQty is not None)
        assert(self.pressing is not None)
        assert(self.turning is not None)
        assert(self.loading is not None)
        assert(self.unloading is not None)
        res = Part(self.name)
        res.setProduction(self.weight, self.mix,
                          self.pressing * 18 * self.boardQty / 8, 18 * self.boardQty / self.turning, 18 * self.boardQty / self.loading, 18 * self.boardQty / self.unloading,
                          self.inspection, 0, self.scrap, self.price)
        res.setPackaging(self.box, self.piecesPerBox, self.pallet, self.boxesPerPallet, self.pad, self.padsPerBox, self.misc)
        res.sales = 0
        return res

    def __str__(self) -> str:
        res = "({} | {}, {}, {}, {}, {}, {}, {}, {}, {} | {}, {}, {}, {}, {}, {}, {} | {})".format(self.name,
                self.weight, self.boardQty, self.mix, self.pressing, self.turning, self.loading, self.unloading, self.inspection, self.scrap,
                self.box, self.piecesPerBox, self.pallet, self.boxesPerPallet, self.pad, self.padsPerBox, self.misc,
                self.price)
        return res
    
class Part:
    def __init__(self, name) -> None:
        self.name = name
        self.db: Database | None = None
        self.weight: float | None = None
        self.mix = None
        self.pressing: float | None = None # pieces / hour
        self.turning: float | None = None # pieces / hour
        self.loading: float | None = None # pieces / hour
        self.unloading: float | None = None # pieces / hour
        self.inspection: float | None = None # pieces / hour
        self.greenScrap = None
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

    def setProduction(self, weight, mix, pressing, turning, loading, unloading, inspection, greenScrap, fireScrap, price):
        self.weight = weight
        self.mix = mix
        self.pressing = pressing
        self.turning = turning
        self.loading = loading
        self.unloading = unloading
        self.inspection = inspection
        self.greenScrap = greenScrap
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
        assert(self.db is not None)
        assert(self.weight is not None)
        assert(self.mix is not None)
        return self.weight * self.db.mixtures[self.mix].getCost()
    
    def getGasCost(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.gasCost
    
    def getMatlCost(self):
        return self.getMixCost() + self.getGasCost()
    
    def getBatchingTime(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.batchingFactor
    
    def getPressingTime(self):
        assert(self.pressing is not None)
        return 1 / self.pressing
    
    def getTurningTime(self):
        assert(self.turning is not None)
        return 1 / self.turning
    
    def getLaborHours(self):
        return self.getBatchingTime() + self.getPressingTime() + self.getTurningTime()
    
    def getLaborCost(self):
        assert(self.db is not None)
        return self.getLaborHours() * self.db.globals.laborCost
    
    def getScrap(self):
        assert(self.db is not None)
        assert(self.fireScrap is not None)
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
        assert(self.db is not None)
        assert(self.box is not None)
        assert(self.piecesPerBox is not None)
        assert(self.pad is not None)
        assert(self.padsPerBox is not None)
        assert(self.pallet is not None)
        assert(self.boxesPerPallet is not None)
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
        assert(self.db is not None)
        return self.getGrossMatlLaborCost() + self.getPackagingCost() + self.db.globals.inspection + self.db.globals.loading
    
    def getManufacturingOverhead(self):
        assert(self.db is not None)
        assert(self.weight is not None)
        return self.weight * self.db.globals.manufacturingOverhead
    
    def getManufacturingCost(self):
        return self.getVariableCost() + self.getManufacturingOverhead()
    
    def getSGA(self):
        assert(self.db is not None)
        assert(self.weight is not None)
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
    
    def getProductivity(self):
        return self.weight * (1 - self.getScrap()) / self.getLaborHours()
    
    def getTuple(self):
            return (
                self.name,
                self.weight,
                self.mix,
                self.pressing,
                self.turning,
                self.loading,
                self.unloading,
                self.inspection,
                self.greenScrap,
                self.fireScrap,
                self.box,
                self.piecesPerBox,
                self.pallet,
                self.boxesPerPallet,
                listToString(self.pad, str),
                listToString(self.padsPerBox, int),
                listToString(self.misc, str),
                self.price,
                self.sales
            )
    
    def fromTuple(self, values):
        self.name = values[0]
        prod = list(values[1:10])
        prod.append(values[17])
        self.setProduction(*prod)
        self.setPackaging(
            values[10],
            values[11],
            values[12],
            values[13],
            stringToList(values[14], str),
            stringToList(values[15], int),
            stringToList(values[16], str)
        )
        self.sales = values[18]

    def __str__(self) -> str:
        assert(self.fireScrap is not None)
        res = "({} | {}, {}, {}, {}, {}, {}, {}, {}% + {}% | {}, {}, {}, {}, {}, {}, {} | {})".format(self.name,
                self.weight, self.mix, self.pressing, self.turning, f"UNUSED: {self.loading}", f"UNUSED: {self.unloading}", f"UNUSED: {self.inspection}", f"UNUSED: {self.greenScrap}", 100 * self.fireScrap,
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
        assert(self.name is not None)
        assert(self.date is not None)
        assert(self.cost is not None)
        assert(self.amount is not None)
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
        assert(self.name is not None)
        assert(self.date is not None)
        assert(self.cost is not None)
        assert(self.amount40 is not None)
        assert(self.amount60 is not None)
        assert(self.amount80 is not None)
        assert(self.amount100 is not None)
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
        assert(oldName in self.materials)
        if not newName == oldName:
            materials = {newName if key == oldName else key:val for key, val in self.materials.items()}
            self.materials = materials
            self.materials[newName].setName(newName)
    
    def addMaterialRecord(self, materialRec: MaterialInventoryRecord):
        assert(materialRec.name is not None)
        assert(self.date is not None)
        assert(self.date == materialRec.date)
        assert(not materialRec.name in self.parts)

        self.materials[materialRec.name] = materialRec
    
    def delMaterialRecord(self, name: str):
        assert(name in self.materials)
        del self.materials[name]
    
    def updatePartRecord(self, oldName: str, newName: str):
        assert(oldName in self.parts)
        if not newName == oldName:
            parts = {newName if key == oldName else key:val for key, val in self.parts.items()}
            self.parts = parts
            self.parts[newName].setName(newName)
    
    def addPartRecord(self, partRec: PartInventoryRecord):
        assert(partRec.name is not None)
        assert(self.date is not None)
        assert(self.date == partRec.date)
        assert(not partRec.name in self.parts)

        self.parts[partRec.name] = partRec
    
    def delPartRecord(self, name: str):
        assert(name in self.parts)
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

class Database:
    def __init__(self, globals: Globals, materials: dict[str, Material], mixtures: dict[str, Mixture], packaging: dict[str, Package], parts: dict[str, Part], inventories: dict[datetime.date, Inventory]) -> None:
        self.globals = globals
        self.materials = materials
        self.mixtures = mixtures
        self.packaging = packaging
        self.parts = parts
        self.inventories = inventories
        for entry in self.materials:
            self.materials[entry].db = self
        for entry in self.mixtures:
            self.mixtures[entry].db = self
        for entry in self.packaging:
            self.packaging[entry].db = self
        for entry in self.parts:
            self.parts[entry].db = self
        self.toWrite: dict[str, list[str]] = {
            # "globals": self.globals.getGlobals(),
            "materials": list(self.materials.keys()),
            "mixtures": list(self.mixtures.keys()),
            "packaging": list(self.packaging.keys()),
            "parts": list(self.parts.keys())
        }
    
    def updatePart(self, entry, name):
        if not name == entry:
            parts = {name if key == entry else key:val for key, val in self.parts.items()}
            self.parts = parts
            self.parts[name].name = name
    
    def addPart(self, part: Part):
        assert(not part.name in self.parts)
        self.parts[part.name] = part
        part.db = self
    
    def delPart(self, name):
        assert(name in self.parts)
        del self.parts[name]
    
    def updatePackaging(self, entry, name):
        if not name == entry:
            packaging = {name if key == entry else key:val for key, val in self.packaging.items()}
            self.packaging = packaging
            self.packaging[name].name = name
            for pname in self.parts:
                part = self.parts[pname]
                if part.box == entry:
                    part.box = name
                if part.pallet == entry:
                    part.pallet = name
                assert(part.pad is not None)
                for i in range(len(part.pad)):
                    if part.pad[i] == entry:
                        part.pad[i] = name
                for i in range(len(part.misc)):
                    if part.misc[i] == entry:
                        part.misc[i] = name
    
    def addPackaging(self, item: Package):
        assert(not item.name in self.packaging)
        self.packaging[item.name] = item
        item.db = self
    
    def delPackaging(self, name):
        assert(name in self.packaging)
        usedIn = []
        for pname in self.parts:
            used = False
            part = self.parts[pname]
            used = used or part.box == name
            used = used or part.pallet == name
            assert(part.pad is not None)
            for i in range(len(part.pad)):
                used = used or part.pad[i] == name
            for i in range(len(part.misc)):
                used = used or part.misc[i] == name
            if used:
                usedIn.append(pname)
        if len(usedIn) == 0:
            del self.packaging[name]
        return usedIn
    
    def updateMixture(self, entry, name):
        if not name == entry:
            mixtures = {name if key == entry else key:val for key, val in self.mixtures.items()}
            self.mixtures = mixtures
            self.mixtures[name].name = name
            for pname in self.parts:
                part = self.parts[pname]
                if part.mix == entry:
                    part.mix = name
    
    def addMixture(self, mixture: Mixture):
        assert(not mixture.name in self.mixtures)
        self.mixtures[mixture.name] = mixture
        mixture.db = self

    def delMixture(self, name):
        assert(name in self.mixtures)
        usedIn = []
        for pname in self.parts:
            used = False
            part = self.parts[pname]
            used = used or part.mix == name
            if used:
                usedIn.append(pname)
        if len(usedIn) == 0:
            del self.mixtures[name]
        return usedIn
    
    def updateMaterial(self, entry, name):
        if not name == entry:
            materials = {name if key == entry else key:val for key, val in self.materials.items()}
            self.materials = materials
            self.materials[name].name = name
            for mname in self.mixtures:
                mix = self.mixtures[mname]
                for i in range(len(mix.materials)):
                    if mix.materials[i] == entry:
                        mix.materials[i] = name
    
    def addMaterial(self, material: Material):
        assert(not material.name in self.materials)
        self.materials[material.name] = material
        material.db = self
    
    def delMaterial(self, name):
        assert(name in self.materials)
        usedIn = []
        for mname in self.mixtures:
            mix = self.mixtures[mname]
            used = False
            for i in range(len(mix.materials)):
                used = used or mix.materials[i] == name
            if used:
                usedIn.append(mname)
        if len(usedIn) == 0:
            del self.materials[name]
        return usedIn
    
    def updateInventory(self, oldDate: datetime.date, date: datetime.date):
        assert(oldDate in self.inventories)
        assert(not date in self.inventories)
        inventory = self.inventories[oldDate]
        for material, record in inventory.materials.items():
            record.setDate(date)
        for part, record in inventory.parts.items():
            record.setDate(date)
        del self.inventories[oldDate]
        self.inventories[date] = inventory
    
    def addInventory(self, date: datetime.date):
        assert(not date in self.inventories)
        self.inventories[date] = Inventory(date)
    
    def delInventory(self, date: datetime.date):
        assert(date in self.inventories)
        del self.inventories[date]
    
    def updateMaterialInventory(self, date: datetime.date, oldName: str, newName: str):
        assert(date in self.inventories)
        self.inventories[date].updateMaterialRecord(oldName, newName)
    
    def addMaterialInventory(self, materialRec: MaterialInventoryRecord):
        assert(materialRec.date is not None)
        if not materialRec.date in self.inventories:
            self.addInventory(materialRec.date)
        self.inventories[materialRec.date].addMaterialRecord(materialRec)
    
    def delMaterialInventory(self, date: datetime.date, name: str):
        assert(date in self.inventories)
        self.inventories[date].delMaterialRecord(name)
    
    def updatePartInventory(self, date: datetime.date, oldName: str, newName: str):
        assert(date in self.inventories)
        self.inventories[date].updatePartRecord(oldName, newName)
    
    def addPartInventory(self, partRec: PartInventoryRecord):
        assert(partRec.date is not None)
        if not partRec.date in self.inventories:
            self.addInventory(partRec.date)
        self.inventories[partRec.date].addPartRecord(partRec)
    
    def delPartInventory(self, date: datetime.date, name: str):
        assert(date in self.inventories)
        self.inventories[date].delPartRecord(name)
    
    def materialCosts(self):
        for entry in self.materials:
            cost = self.materials[entry].getCostPerLb()
            if not cost == None:
                print("{} {}".format(self.materials[entry].name, cost))
    
    def mixtureCosts(self):
        for entry in self.mixtures:
            print("{} {}".format(self.mixtures[entry].name, self.mixtures[entry].getCost()))
    
    def partCosts(self):
        for entry in self.parts:
            part = self.parts[entry]
            print("{} | {:.4f} {:.4f} -> {:.4f} {:.4f} {:.4f} -> {:.4f} {:.4f} -> {:.4f} | {:.4f} | {:.2f}% {:.2f}% {:.4f} | {:.4f}".format(part.name, part.getMatlCost(),  part.getLaborCost(),
                                          part.getGrossMatlLaborCost(), part.getPackagingCost(), part.getManufacturingOverhead(),
                                          part.getManufacturingCost(), part.getSGA(),
                                          part.getTotalCost(), part.price,
                                          100 * part.getGM(), 100 * part.getCM(), part.getVariableCost(),
                                          part.getProductivity()))


    def __str__(self) -> str:
        res = []
        res.append("--- Materials ---")
        for entry in self.materials:
            res.append(str(self.materials[entry]))
        res.append("--- Mixes ---")
        for entry in self.mixtures:
            res.append(str(self.mixtures[entry]))
        res.append("--- Packaging ---")
        for entry in self.packaging:
            res.append(str(self.packaging[entry]))
        res.append("--- Parts ---")
        for entry in self.parts:
            res.append(str(self.parts[entry]))
        return "\n".join(res)
    
def emptyDB():
    return Database(Globals(), {}, {}, {}, {}, {})