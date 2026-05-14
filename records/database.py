import datetime

from records.products import (
    Globals, Material, Mixture, Package, Part, Inventory,
    MaterialInventoryRecord, PartInventoryRecord,
)
from records.employees import (
    Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB,
    EmployeePTODB, EmployeeNotesDB, ObservancesDB,
)
from records.production import ProductionRecord


class Database:
    def __init__(self,
                 globals: Globals,
                 materials: dict[str, Material],
                 mixtures: dict[str, Mixture],
                 packaging: dict[str, Package],
                 parts: dict[str, Part],
                 inventories: dict[datetime.date, Inventory],
                 employees: dict[int, Employee],
                 reviews: dict[int, EmployeeReviewsDB],
                 training: dict[int, EmployeeTrainingDB],
                 attendance: dict[int, EmployeePointsDB],
                 PTO: dict[int, EmployeePTODB],
                 notes: dict[int, EmployeeNotesDB],
                 holidays: ObservancesDB,
                 production: dict[tuple, ProductionRecord]) -> None:
        self.globals = globals
        self.materials = materials
        self.mixtures = mixtures
        self.packaging = packaging
        self.parts = parts
        self.inventories = inventories
        self.employees = employees
        self.reviews = reviews
        self.training = training
        self.attendance = attendance
        self.PTO = PTO
        self.notes = notes
        self.holidays = holidays
        self.production = production
        for entry in self.materials:
            self.materials[entry].db = self
        for entry in self.mixtures:
            self.mixtures[entry].db = self
        for entry in self.packaging:
            self.packaging[entry].db = self
        for entry in self.parts:
            self.parts[entry].db = self

    def updatePart(self, entry, name):
        if not name == entry:
            parts = {name if key == entry else key:val for key, val in self.parts.items()}
            self.parts = parts
            self.parts[name].name = name

    def addPart(self, part: Part):
        if part.name in self.parts:
            raise RuntimeError('part.name already in self.parts')
        self.parts[part.name] = part
        part.db = self

    def delPart(self, name):
        if name not in self.parts:
            raise RuntimeError('name not in self.parts')
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
                if part.pad is None:
                    raise RuntimeError('part.pad is None')
                for i in range(len(part.pad)):
                    if part.pad[i] == entry:
                        part.pad[i] = name
                for i in range(len(part.misc)):
                    if part.misc[i] == entry:
                        part.misc[i] = name

    def addPackaging(self, item: Package):
        if item.name in self.packaging:
            raise RuntimeError('item.name already in self.packaging')
        self.packaging[item.name] = item
        item.db = self

    def delPackaging(self, name):
        if name not in self.packaging:
            raise RuntimeError('name not in self.packaging')
        usedIn = []
        for pname in self.parts:
            used = False
            part = self.parts[pname]
            used = used or part.box == name
            used = used or part.pallet == name
            if part.pad is None:
                raise RuntimeError('part.pad is None')
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
        if mixture.name in self.mixtures:
            raise RuntimeError('mixture.name already in self.mixtures')
        self.mixtures[mixture.name] = mixture
        mixture.db = self

    def delMixture(self, name):
        if name not in self.mixtures:
            raise RuntimeError('name not in self.mixtures')
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
        if material.name in self.materials:
            raise RuntimeError('material.name already in self.materials')
        self.materials[material.name] = material
        material.db = self

    def delMaterial(self, name):
        if name not in self.materials:
            raise RuntimeError('name not in self.materials')
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
        if oldDate not in self.inventories:
            raise RuntimeError('oldDate not in self.inventories')
        if date in self.inventories:
            raise RuntimeError('date already in self.inventories')
        inventory = self.inventories[oldDate]
        for material, record in inventory.materials.items():
            record.setDate(date)
        for part, record in inventory.parts.items():
            record.setDate(date)
        del self.inventories[oldDate]
        self.inventories[date] = inventory

    def addInventory(self, date: datetime.date):
        if date in self.inventories:
            raise RuntimeError('date already in self.inventories')
        self.inventories[date] = Inventory(date)

    def delInventory(self, date: datetime.date):
        if date not in self.inventories:
            raise RuntimeError('date not in self.inventories')
        del self.inventories[date]

    def addMaterialInventory(self, materialRec: MaterialInventoryRecord):
        if materialRec.date is None:
            raise RuntimeError('materialRec.date is None')
        if not materialRec.date in self.inventories:
            self.addInventory(materialRec.date)
        self.inventories[materialRec.date].addMaterialRecord(materialRec)

    def addPartInventory(self, partRec: PartInventoryRecord):
        if partRec.date is None:
            raise RuntimeError('partRec.date is None')
        if not partRec.date in self.inventories:
            self.addInventory(partRec.date)
        self.inventories[partRec.date].addPartRecord(partRec)

    def addEmployee(self, employee: Employee):
        if employee.idNum in self.employees:
            raise RuntimeError('employee.idNum already in self.employees')
        if employee.idNum is None:
            raise RuntimeError('employee.idNum is None')
        self.employees[employee.idNum] = employee

    def updateEmployee(self, oldID, newID):
        if oldID == newID:
            return
        # 1. Rekey every employee-indexed collection that contains oldID.
        for name in ("employees", "reviews", "training", "attendance", "PTO", "notes"):
            coll = getattr(self, name)
            if oldID in coll:
                setattr(self, name, {newID if key == oldID else key: val for key, val in coll.items()})
        # 2. Update the stored id on the employee and each sub-DB wrapper.
        if newID in self.employees:
            self.employees[newID].idNum = newID
        for name in ("reviews", "training", "attendance", "PTO", "notes"):
            coll = getattr(self, name)
            if newID in coll:
                coll[newID].idNum = newID
        # 3. Propagate to each child record so per-record consistency holds.
        #    (EmployeePTORange uses `.employee` instead of `.idNum`.)
        if newID in self.reviews:
            for rec in self.reviews[newID].reviews.values():
                rec.idNum = newID
        if newID in self.training:
            for byDate in self.training[newID].training.values():
                for rec in byDate.values():
                    rec.idNum = newID
        if newID in self.attendance:
            for rec in self.attendance[newID].points.values():
                rec.idNum = newID
        if newID in self.PTO:
            for rec in self.PTO[newID].PTO.values():
                rec.employee = newID
        if newID in self.notes:
            for rec in self.notes[newID].notes.values():
                rec.idNum = newID

    def delEmployee(self, employeeID: int):
        if employeeID not in self.employees:
            raise RuntimeError('employeeID not in self.employees')
        del self.employees[employeeID]
        if employeeID not in self.reviews:
            raise RuntimeError('employeeID not in self.reviews')
        del self.reviews[employeeID]
        if employeeID not in self.training:
            raise RuntimeError('employeeID not in self.training')
        del self.training[employeeID]
        if employeeID not in self.attendance:
            raise RuntimeError('employeeID not in self.attendance')
        del self.attendance[employeeID]
        if employeeID not in self.PTO:
            raise RuntimeError('employeeID not in self.PTO')
        del self.PTO[employeeID]
        if employeeID not in self.notes:
            raise RuntimeError('employeeID not in self.notes')
        del self.notes[employeeID]

    def addEmployeeReviews(self, employeeReviews: EmployeeReviewsDB):
        if employeeReviews.idNum in self.reviews:
            raise RuntimeError('employeeReviews.idNum already in self.reviews')
        self.reviews[employeeReviews.idNum] = employeeReviews

    def addEmployeeTraining(self, employeeTraining: EmployeeTrainingDB):
        if employeeTraining.idNum in self.training:
            raise RuntimeError('employeeTraining.idNum already in self.training')
        self.training[employeeTraining.idNum] = employeeTraining

    def addEmployeePoints(self, employeePoints: EmployeePointsDB):
        if employeePoints.idNum in self.attendance:
            raise RuntimeError('employeePoints.idNum already in self.attendance')
        self.attendance[employeePoints.idNum] = employeePoints

    def addEmployeePTO(self, employeePTO: EmployeePTODB):
        if employeePTO.idNum in self.PTO:
            raise RuntimeError('employeePTO.idNum already in self.PTO')
        self.PTO[employeePTO.idNum] = employeePTO

    def addEmployeeNotes(self, employeeNotes: EmployeeNotesDB):
        if employeeNotes.idNum in self.notes:
            raise RuntimeError('employeeNotes.idNum already in self.notes')
        self.notes[employeeNotes.idNum] = employeeNotes

    # ---- mergeFrom -------------------------------------------------------------------------

    def planMergeFrom(self, other: "Database") -> dict:
        # Inspect-only: report what a mergeFrom(other) would import and which keys already
        # exist on self. Used by the importer UI to build a confirmation summary and to
        # abort without side effects if anything collides.
        incoming = {
            "materials": sorted(other.materials.keys()),
            "mixtures": sorted(other.mixtures.keys()),
            "packaging": sorted(other.packaging.keys()),
            "parts": sorted(other.parts.keys()),
            "employees": sorted(other.employees.keys()),
            "holidays": sorted(other.holidays.defaults.keys()),
        }
        # Inventories collide at the (date, name) grain. Walk both sides.
        matInv = []
        partInv = []
        for date, inv in other.inventories.items():
            for name in inv.materials:
                matInv.append((date.isoformat(), name))
            for name in inv.parts:
                partInv.append((date.isoformat(), name))
        incoming["materialInventory"] = sorted(matInv)
        incoming["partInventory"] = sorted(partInv)
        # Observances collide at (year, holiday, shift).
        obs = []
        for year, byHoliday in other.holidays.observances.items():
            for holiday, byShift in byHoliday.items():
                for shift in byShift:
                    obs.append((year, holiday, shift))
        incoming["observances"] = sorted(obs)

        collisions = {
            "materials": [n for n in incoming["materials"] if n in self.materials],
            "mixtures": [n for n in incoming["mixtures"] if n in self.mixtures],
            "packaging": [n for n in incoming["packaging"] if n in self.packaging],
            "parts": [n for n in incoming["parts"] if n in self.parts],
            "employees": [i for i in incoming["employees"] if i in self.employees],
            "holidays": [h for h in incoming["holidays"] if h in self.holidays.defaults],
        }
        matInvCol = []
        partInvCol = []
        for (dateStr, name) in incoming["materialInventory"]:
            d = datetime.date.fromisoformat(dateStr)
            if d in self.inventories and name in self.inventories[d].materials:
                matInvCol.append((dateStr, name))
        for (dateStr, name) in incoming["partInventory"]:
            d = datetime.date.fromisoformat(dateStr)
            if d in self.inventories and name in self.inventories[d].parts:
                partInvCol.append((dateStr, name))
        collisions["materialInventory"] = matInvCol
        collisions["partInventory"] = partInvCol
        obsCol = []
        for (year, holiday, shift) in incoming["observances"]:
            if (year in self.holidays.observances
                and holiday in self.holidays.observances[year]
                and shift in self.holidays.observances[year][holiday]):
                obsCol.append((year, holiday, shift))
        collisions["observances"] = obsCol

        return {"incoming": incoming, "collisions": collisions}

    def mergeFrom(self, other: "Database"):
        # Copy every non-overlapping entry from `other` into self. Globals and the
        # production table are intentionally skipped: the open DB's ANIKA cost
        # parameters win (§8.5), and production is always empty in legacy files.
        # Caller is responsible for checking planMergeFrom(other)["collisions"] first —
        # mergeFrom assumes no collisions and will raise if any exist.
        plan = self.planMergeFrom(other)
        for key, vals in plan["collisions"].items():
            if vals:
                raise RuntimeError(f'mergeFrom collision on {key}: {vals}')

        # --- ANIKA products ---
        for name, obj in other.materials.items():
            self.materials[name] = obj
            obj.db = self
        for name, obj in other.mixtures.items():
            self.mixtures[name] = obj
            obj.db = self
        for name, obj in other.packaging.items():
            self.packaging[name] = obj
            obj.db = self
        for name, obj in other.parts.items():
            self.parts[name] = obj
            obj.db = self

        # --- inventories: reparent each MaterialInventoryRecord / PartInventoryRecord
        #     onto the already-open DB's per-date Inventory (creating the date if new). ---
        for date, inv in other.inventories.items():
            for rec in inv.materials.values():
                self.addMaterialInventory(rec)
            for rec in inv.parts.values():
                self.addPartInventory(rec)

        # --- BECKY employees + the five per-employee sub-DBs ---
        for idNum, emp in other.employees.items():
            self.employees[idNum] = emp
            self.reviews[idNum] = other.reviews[idNum]
            self.training[idNum] = other.training[idNum]
            self.attendance[idNum] = other.attendance[idNum]
            self.PTO[idNum] = other.PTO[idNum]
            self.notes[idNum] = other.notes[idNum]

        # --- holidays defaults + observances ---
        for holiday, month in other.holidays.defaults.items():
            self.holidays.defaults[holiday] = month
        for year, byHoliday in other.holidays.observances.items():
            if year not in self.holidays.observances:
                self.holidays.observances[year] = {}
            for holiday, byShift in byHoliday.items():
                if holiday not in self.holidays.observances[year]:
                    self.holidays.observances[year][holiday] = {}
                for shift, obs in byShift.items():
                    self.holidays.observances[year][holiday][shift] = obs

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
        ObservancesDB(),
        {}
    )
