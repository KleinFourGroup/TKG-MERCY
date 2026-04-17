import sqlite3
import datetime
from utils import listToString, stringToList, stringToB64, stringFromB64
import defaults

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
        assert(not date == None)
        self.anniversary = date

    def setName(self, lastName: str, firstName: str):
        assert(not lastName == None)
        assert(not firstName == None)
        self.lastName = lastName
        self.firstName = firstName

    def setID(self, num: int):
        assert(not num == None)
        assert(num >= 0)
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
        assert(not self.anniversary == None)
        return (
            self.idNum,
            self.lastName,
            self.firstName,
            self.anniversary.isoformat(),
            self.role,
            f"{self.shift}|{1 if self.fullTime else 0}",
            self.addressLine1,
            self.addressLine2,
            self.addressCity,
            self.addressState,
            self.addressZip,
            self.addressTel,
            self.addressEmail,
            1 if self.status else 0
        )

    def fromTuple(self, row: tuple[int, str, str, str, str, int | str, str, str, str, str, str, str, str, int]):
        self.setID(row[0])
        self.setName(row[1], row[2])
        self.setAnniversary(datetime.date.fromisoformat(row[3]))
        if isinstance(row[5], int):
            self.setJob(row[4], row[5], True)
        else:
            jobArgs = row[5].split("|")
            assert(len(jobArgs) == 2)
            self.setJob(row[4], int(jobArgs[0]), jobArgs[1] == "1")
        self.setAddress(row[6], row[7], row[8], row[9], row[10], row[11], row[12])
        self.setStatus(not row[13] == 0)

class EmployeeReview:
    def __init__(self, idNum: int | None = None, date: datetime.date | None = None, nextReview: datetime.date | None = None, details: str = "") -> None:
        assert(idNum == None or idNum >= 0)
        self.idNum: int | None = idNum
        self.date: datetime.date | None = date
        self.nextReview: datetime.date | None = nextReview
        self.details: str = details

    def setID(self, num: int):
        assert(not num == None)
        assert(num >= 0)
        self.idNum = num

    def getTuple(self):
        return (
            self.idNum,
            "" if self.date == None else self.date.isoformat(),
            "" if self.nextReview == None else self.nextReview.isoformat(),
            stringToB64(self.details)
        )

    def fromTuple(self, row: tuple[int, str, str, str]):
        self.setID(row[0])
        self.date = None if row[1] == "" else datetime.date.fromisoformat(row[1])
        self.nextReview = None if row[2] == "" else datetime.date.fromisoformat(row[2])
        self.details = stringFromB64(row[3])

class EmployeeTrainingDate:
    def __init__(self, idNum: int | None = None, training: str | None = None, date: datetime.date | None = None, comment: str = "") -> None:
        self.idNum: int | None = idNum
        self.training: str | None = training
        self.date: datetime.date | None = date
        self.comment: str = comment

    def setID(self, num: int):
        assert(not num == None)
        assert(num >= 0)
        self.idNum = num

    def setTraining(self, training: str):
        assert(self.training == None)
        self.training = training

    def setDate(self, date: datetime.date):
        self.date = date

    def getTuple(self):
        assert(not self.date == None)
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
        assert(not num == None)
        assert(num >= 0)
        self.employee = num

    def setDate(self, start: datetime.date, end: datetime.date | str):
        assert(not start == None)
        assert(not end == None)
        if isinstance(end, datetime.date):
            assert(start <= end)
        else:
            assert(end in ["CARRY", "CASH", "DROP"])
        self.start = start
        self.end = end

    def setHours(self, hours: float):
        assert(not hours == None)
        assert(hours > 0)
        self.hours = hours

    def getTuple(self):
        assert(not self.start == None)
        assert(not self.end == None)
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
        assert(not num == None)
        assert(num >= 0)
        self.idNum = num

    def getTuple(self):
        assert(not self.date == None)
        assert(not self.time == None)
        return (
            self.idNum,
            self.date.isoformat(),
            self.time,
            stringToB64(self.details)
        )

    def fromTuple(self, row: tuple[int, str, str, str]):
        self.setID(row[0])
        self.date = datetime.date.fromisoformat(row[1])
        self.time = row[2]
        self.details = stringFromB64(row[3])

class EmployeePoint:
    def __init__(self, idNum: int | None = None, date: datetime.date | None = None, reason: str | None = None, value: float = 0) -> None:
        self.idNum: int | None = idNum
        self.date: datetime.date | None = date
        self.reason: str | None = reason
        self.value: float = value

    def setEmployee(self, num: int):
        assert(not num == None)
        assert(num >= 0)
        self.idNum = num

    def setDate(self, date: datetime.date):
        assert(not date == None)
        self.date = date

    def setReason(self, reason: str, value: float):
        self.reason = reason
        if reason in defaults.POINT_VALS:
            assert(value == defaults.POINT_VALS[reason])
        self.value = value

    def getTuple(self):
        assert(not self.date == None)
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
        assert(holiday in defaults.HOLIDAYS)
        self.holiday = holiday

    def setDate(self, date: datetime.date, shift: int):
        assert(not date == None)
        self.date = date
        self.shift = shift

    def getTuple(self):
        assert(not self.date == None)
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
            assert(self.idNum == self.reviews[date].idNum)
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
                assert(self.idNum == self.training[train][date].idNum)
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
                print(f"{diff} days from {currDate.isoformat()} to {nextDate.isoformat()}, deducting {credit} points from a total of {sumPt}!")
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
            assert(self.idNum == self.points[date].idNum)
            ret.append(self.points[date].getTuple())
        return ret

class EmployeeNotesDB:
    def __init__(self, idNum: int) -> None:
        self.idNum: int = idNum
        self.notes: dict[tuple[datetime.date, str], EmployeeNote] = {}

    def getTuples(self):
        ret = []
        for key in self.notes:
            assert(self.idNum == self.notes[key].idNum)
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
                assert(dates[1].year == year)
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
        assert(count <= 1)
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
        assert(count <= 1)
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
            assert(self.idNum == self.PTO[dateRange].employee)
            ret.append(self.PTO[dateRange].getTuple())
        return ret

class ObservancesDB:
    def __init__(self) -> None:
        self.defaults: dict[str, int] = {}
        self.observances: dict[int, dict[str, dict[int, HolidayObservance]]] = {}

    def setDefault(self, holiday: str, month: int):
        assert(1 <= month and month <= 12)
        self.defaults[holiday] = month

    def getDefault(self, holiday: str):
        if not holiday in self.defaults:
            return 1
        else:
            return self.defaults[holiday]

    def setObservance(self, holiday: HolidayObservance):
        assert(not holiday.date == None)
        assert(not holiday.holiday == None)
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

class Database:
    def __init__(self,
                 globals: Globals,
                 materials: dict[str, Material],
                 mixtures: dict[str, Mixture],
                 packaging: dict[str, Package],
                 parts: dict[str, Part],
                 inventories: dict[datetime.date, Inventory],
                 employees: dict[int, Employee] | None = None,
                 reviews: dict[int, EmployeeReviewsDB] | None = None,
                 training: dict[int, EmployeeTrainingDB] | None = None,
                 attendance: dict[int, EmployeePointsDB] | None = None,
                 PTO: dict[int, EmployeePTODB] | None = None,
                 notes: dict[int, EmployeeNotesDB] | None = None,
                 holidays: ObservancesDB | None = None) -> None:
        self.globals = globals
        self.materials = materials
        self.mixtures = mixtures
        self.packaging = packaging
        self.parts = parts
        self.inventories = inventories
        self.employees = employees if employees is not None else {}
        self.reviews = reviews if reviews is not None else {}
        self.training = training if training is not None else {}
        self.attendance = attendance if attendance is not None else {}
        self.PTO = PTO if PTO is not None else {}
        self.notes = notes if notes is not None else {}
        self.holidays = holidays if holidays is not None else ObservancesDB()
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
    
    def addEmployee(self, employee: Employee):
        assert(not employee.idNum in self.employees)
        assert(not employee.idNum == None)
        self.employees[employee.idNum] = employee

    def updateEmployee(self, oldID, newID):
        if not oldID == newID:
            emloyees = {newID if key == oldID else key:val for key, val in self.employees.items()}
            self.employees = emloyees
            self.employees[newID].idNum = newID
            # TODO: replacement logic for other DBs
            if oldID in self.reviews:
                reviews = {newID if key == oldID else key:val for key, val in self.reviews.items()}
                self.reviews = reviews
                self.reviews[newID].idNum = newID
            if oldID in self.notes:
                notes = {newID if key == oldID else key:val for key, val in self.notes.items()}
                self.notes = notes
                self.notes[newID].idNum = newID

    def delEmployee(self, employeeID: int):
        assert(employeeID in self.employees)
        del self.employees[employeeID]
        assert(employeeID in self.reviews)
        del self.reviews[employeeID]
        assert(employeeID in self.training)
        del self.training[employeeID]
        assert(employeeID in self.attendance)
        del self.attendance[employeeID]
        assert(employeeID in self.PTO)
        del self.PTO[employeeID]
        assert(employeeID in self.notes)
        del self.notes[employeeID]

    def addEmployeeReviews(self, employeeReviews: EmployeeReviewsDB):
        assert(not employeeReviews.idNum in self.reviews)
        self.reviews[employeeReviews.idNum] = employeeReviews

    def addEmployeeTraining(self, employeeTraining: EmployeeTrainingDB):
        assert(not employeeTraining.idNum in self.training)
        self.training[employeeTraining.idNum] = employeeTraining

    def addEmployeePoints(self, employeePoints: EmployeePointsDB):
        assert(not employeePoints.idNum in self.attendance)
        self.attendance[employeePoints.idNum] = employeePoints

    def addEmployeePTO(self, employeePTO: EmployeePTODB):
        assert(not employeePTO.idNum in self.PTO)
        self.PTO[employeePTO.idNum] = employeePTO

    def addEmployeeNotes(self, employeeNotes: EmployeeNotesDB):
        assert(not employeeNotes.idNum in self.notes)
        self.notes[employeeNotes.idNum] = employeeNotes

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
    return Database(
        Globals(), {}, {}, {}, {}, {},
        {}, {}, {}, {}, {}, {},
        ObservancesDB()
    )