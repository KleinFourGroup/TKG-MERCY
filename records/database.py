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
from records.scheduling import Press, Presser, ShiftWorkweek, PartPressPref, PresserPressPref
from records.sales import Client, Order, OrderStatus


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
                 production: dict[tuple, ProductionRecord],
                 presses: dict[str, Press],
                 pressers: dict[int, Presser],
                 shiftWorkweek: dict[int, ShiftWorkweek],
                 partPressPref: dict[str, PartPressPref],
                 presserPressPref: dict[int, PresserPressPref],
                 clients: dict[str, Client],
                 orders: dict[str, Order],
                 orderStatus: dict[str, OrderStatus]) -> None:
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
        self.presses = presses
        self.pressers = pressers
        self.shiftWorkweek = shiftWorkweek
        self.partPressPref = partPressPref
        self.presserPressPref = presserPressPref
        self.clients = clients
        self.orders = orders
        self.orderStatus = orderStatus
        for entry in self.materials:
            self.materials[entry].db = self
        for entry in self.mixtures:
            self.mixtures[entry].db = self
        for entry in self.packaging:
            self.packaging[entry].db = self
        for entry in self.parts:
            self.parts[entry].db = self

    def updatePart(self, entry, name):
        # Step 60: also require the original to still exist — a stale edit window
        # whose part was deleted from the tab would otherwise rekey to no `name`
        # key and KeyError on the line below; no-op the rename instead.
        if name != entry and entry in self.parts:
            parts = {name if key == entry else key:val for key, val in self.parts.items()}
            self.parts = parts
            self.parts[name].name = name
            # Propagate the rename to any order that references this part (Step 47),
            # the way updatePackaging fixes up parts.
            for order in self.orders.values():
                if order.part == entry:
                    order.part = name
            # Part-press preferences are keyed by part name (Step 48), so rekey the
            # entry and fix up the stored part on the record.
            if entry in self.partPressPref:
                pref = self.partPressPref.pop(entry)
                pref.part = name
                self.partPressPref[name] = pref

    def addPart(self, part: Part):
        if part.name in self.parts:
            raise RuntimeError('part.name already in self.parts')
        self.parts[part.name] = part
        part.db = self

    def delPart(self, name):
        if name not in self.parts:
            raise RuntimeError('name not in self.parts')
        # Refuse to delete a part an order still references (block-on-delete, like
        # delPackaging — Step 47). Production / inventory references intentionally
        # do NOT block; those historical records are meant to survive. Returns the
        # referencing order numbers (empty list = nothing referenced it, deleted).
        usedIn = [num for num, order in self.orders.items() if order.part == name]
        if len(usedIn) == 0:
            del self.parts[name]
            # Part-press preferences are config tied to a live part (unlike orders,
            # which block), so cascade-drop them when the part is deleted (Step 48) —
            # the same config-cascades-but-history-blocks split as delEmployee/pressers.
            self.partPressPref.pop(name, None)
        return usedIn

    def updatePackaging(self, entry, name):
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if name != entry and entry in self.packaging:
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
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if name != entry and entry in self.mixtures:
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
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if name != entry and entry in self.materials:
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
        # 4. Scheduling + production also reference the employee by id, but neither
        #    is an HR sub-DB so the loops above miss them: a Presser stores
        #    .employeeId (not .idNum), and production is keyed by rec.key() — a
        #    tuple that begins with employeeId, so a re-id changes the key, not just
        #    the field. A re-id keeps the employee alive (unlike delEmployee, where
        #    production is intentionally left as a (missing #id) tombstone), so both
        #    must follow the new id or they silently orphan.
        if oldID in self.pressers:
            self.pressers = {newID if key == oldID else key: val
                             for key, val in self.pressers.items()}
            self.pressers[newID].employeeId = newID
        # Presser-press preferences are keyed by employeeId too (Step 65), so a re-id
        # must move them with the presser or they silently orphan — same follow-the-id
        # rule as the pressers rekey just above.
        if oldID in self.presserPressPref:
            pref = self.presserPressPref.pop(oldID)
            pref.employeeId = newID
            self.presserPressPref[newID] = pref
        if any(rec.employeeId == oldID for rec in self.production.values()):
            for rec in self.production.values():
                if rec.employeeId == oldID:
                    rec.employeeId = newID
            # employeeId is part of the key, so rebuild the dict off the new keys.
            self.production = {rec.key(): rec for rec in self.production.values()}

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
        # A presser is current config tied 1:1 to a live employee (unlike the
        # historical production records, which intentionally survive), so drop the
        # presser record too if this employee was one. Optional — not every
        # employee is a presser — so this is a guarded delete, not a raise.
        if employeeID in self.pressers:
            del self.pressers[employeeID]
        # Presser-press preferences are keyed by employeeId (Step 65) and are presser
        # config, so drop them with the presser row — same cascade as the presser above.
        self.presserPressPref.pop(employeeID, None)

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

    # ---- Production Scheduling: presses ----------------------------------------------------

    def updatePress(self, entry, name):
        # Rekey the presses dict on rename, mirroring updatePackaging/updateMaterial.
        # Name-collision is rejected at the tab (PressEditWindow.readData).
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if name != entry and entry in self.presses:
            presses = {name if key == entry else key: val for key, val in self.presses.items()}
            self.presses = presses
            self.presses[name].name = name
            # Part-press preferences score presses by name (Step 48), so propagate
            # the rename into every part's score map (the entry, not the value).
            for pref in self.partPressPref.values():
                if entry in pref.scores:
                    pref.scores[name] = pref.scores.pop(entry)
            # Presser-press preferences score presses the same way (Step 65), so
            # propagate the rename into every presser's score map too.
            for presserPref in self.presserPressPref.values():
                if entry in presserPref.scores:
                    presserPref.scores[name] = presserPref.scores.pop(entry)

    def addPress(self, press: Press):
        if press.name in self.presses:
            raise RuntimeError('press.name already in self.presses')
        self.presses[press.name] = press

    def delPress(self, name):
        if name not in self.presses:
            raise RuntimeError('name not in self.presses')
        del self.presses[name]
        # Drop this press from every part's preference map (Step 48) — a deleted
        # press just becomes neutral everywhere (missing pair = neutral), and a
        # part left with no scored presses drops its now-empty PartPressPref so the
        # in-memory shape matches the persisted presence rows.
        for part in list(self.partPressPref):
            pref = self.partPressPref[part]
            pref.setScore(name, None)
            if not pref.scores:
                del self.partPressPref[part]
        # Same cascade for presser-press preferences (Step 65): a deleted press
        # drops out of every presser's map, and a presser left with no scored
        # presses drops its now-empty PresserPressPref so the in-memory shape
        # matches the persisted presence rows.
        for empId in list(self.presserPressPref):
            presserPref = self.presserPressPref[empId]
            presserPref.setScore(name, None)
            if not presserPref.scores:
                del self.presserPressPref[empId]

    # ---- Production Scheduling: part-press preference ------------------------------------

    def setPartPressScore(self, part, press, score):
        # Set or clear one (part, press) preference score, keeping self.partPressPref
        # in exact lockstep with the persisted presence rows: a part entry exists
        # only while it has >= 1 scored press, so a part scored all-neutral drops out
        # (and an empty DB has an empty dict — same shape as shiftWorkweek). Parts and
        # presses are created/deleted from their own tables, so there's no add/del
        # here; the nested editor just sets scores through this.
        if score is not None and score != 0:
            if part not in self.partPressPref:
                self.partPressPref[part] = PartPressPref(part)
            self.partPressPref[part].setScore(press, score)
        elif part in self.partPressPref:
            self.partPressPref[part].setScore(press, None)
            if not self.partPressPref[part].scores:
                del self.partPressPref[part]

    # ---- Production Scheduling: presser-press preference ---------------------------------

    def setPresserPressScore(self, employeeId, press, score):
        # Set or clear one (presser, press) preference score — the exact twin of
        # setPartPressScore but keyed by employeeId. Keeps self.presserPressPref in
        # lockstep with the persisted presence rows: a presser entry exists only while
        # it has >= 1 scored press, so a presser scored all-neutral drops out (and an
        # empty DB has an empty dict). Pressers are created/deleted from their own
        # table, so there's no add/del here; the grid tab just sets scores through this.
        if score is not None and score != 0:
            if employeeId not in self.presserPressPref:
                self.presserPressPref[employeeId] = PresserPressPref(employeeId)
            self.presserPressPref[employeeId].setScore(press, score)
        elif employeeId in self.presserPressPref:
            self.presserPressPref[employeeId].setScore(press, None)
            if not self.presserPressPref[employeeId].scores:
                del self.presserPressPref[employeeId]

    # ---- Production Scheduling: pressers ---------------------------------------------------

    def updatePresser(self, oldId, newId):
        # Rekey the pressers dict when the presser is reassigned to a different
        # employee, mirroring updateEmployee's rekey. employeeId is the PK; the
        # hoursPerShift field is set directly on the record by the edit window.
        # A new-id collision is rejected at the tab (PresserEditWindow.readData).
        # Guarded against a stale original id — a presser deleted or reassigned
        # while an Edit window stayed open — the way updateEmployee is (Step 60
        # class): a missing oldId makes the rekey a no-op rather than a KeyError on
        # `self.pressers[newId]` (crash_fuzz-found; the last updateX helper that
        # still assumed its original key was present).
        if newId == oldId:
            return
        if oldId in self.pressers:
            self.pressers = {newId if key == oldId else key: val
                             for key, val in self.pressers.items()}
            self.pressers[newId].employeeId = newId
        # Presser-press preferences are keyed by employeeId (Step 65), exactly
        # like pressers, so rekey the entry and fix up the stored id — the same
        # follow-the-presser rule used everywhere pressers is rekeyed. No
        # collision: the tab rejects reassigning to an existing presser, so newId
        # has no pre-existing preference row.
        if oldId in self.presserPressPref:
            pref = self.presserPressPref.pop(oldId)
            pref.employeeId = newId
            self.presserPressPref[newId] = pref

    def addPresser(self, presser: Presser):
        if presser.employeeId in self.pressers:
            raise RuntimeError('presser.employeeId already in self.pressers')
        self.pressers[presser.employeeId] = presser

    def delPresser(self, employeeId):
        if employeeId not in self.pressers:
            raise RuntimeError('employeeId not in self.pressers')
        del self.pressers[employeeId]
        # Presser-press preferences are config tied 1:1 to a live presser (Step 65),
        # so cascade-drop them when the presser is deleted — the same
        # config-cascades pattern as delPart dropping a part's partPressPref.
        self.presserPressPref.pop(employeeId, None)

    # ---- Production Scheduling: shift workweek ---------------------------------------------

    def setShiftWorkday(self, shift, weekday, working):
        # Toggle one (shift, weekday) working day. Keeps self.shiftWorkweek in
        # exact lockstep with the persisted presence rows: a shift entry exists
        # only while it has >= 1 working day, so an all-cleared shift drops out
        # (and an empty DB has an empty dict — same shape as presses/pressers).
        # Shifts aren't created/deleted, so there's no add/del; the grid tab just
        # flips cells through here.
        if working:
            if shift not in self.shiftWorkweek:
                self.shiftWorkweek[shift] = ShiftWorkweek(shift)
            self.shiftWorkweek[shift].setDay(weekday, True)
        elif shift in self.shiftWorkweek:
            self.shiftWorkweek[shift].setDay(weekday, False)
            if not self.shiftWorkweek[shift].days:
                del self.shiftWorkweek[shift]

    # ---- Sales: clients --------------------------------------------------------------------

    def updateClient(self, entry, name):
        # Rekey the clients dict on rename, mirroring updatePackaging/updateMaterial.
        # The transportDays field is set directly on the record by the edit window.
        # Name-collision is rejected at the tab (ClientEditWindow.readData).
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if name != entry and entry in self.clients:
            clients = {name if key == entry else key: val for key, val in self.clients.items()}
            self.clients = clients
            self.clients[name].name = name
            # Propagate the rename to any order that references this client (Step 47).
            for order in self.orders.values():
                if order.client == entry:
                    order.client = name

    def addClient(self, client: Client):
        if client.name in self.clients:
            raise RuntimeError('client.name already in self.clients')
        self.clients[client.name] = client

    def delClient(self, name):
        if name not in self.clients:
            raise RuntimeError('name not in self.clients')
        # Refuse to delete a client an order still references (block-on-delete, like
        # delPackaging — Step 47). Returns the referencing order numbers (empty
        # list = nothing referenced it, deleted).
        usedIn = [num for num, order in self.orders.items() if order.client == name]
        if len(usedIn) == 0:
            del self.clients[name]
        return usedIn

    # ---- Sales: orders ---------------------------------------------------------------------

    def updateOrder(self, oldNum, newNum):
        # Rekey the orders dict when the order number changes (orderNum is the PK),
        # mirroring updateEmployee's rekey. The client / part / quantity / price /
        # dueDate fields are set directly on the record by the edit window. A
        # new-number collision is rejected at the tab (OrderEditWindow.readData).
        # Step 60: no-op if the original is gone (stale window) so the rekey can't KeyError.
        if newNum != oldNum and oldNum in self.orders:
            orders = {newNum if key == oldNum else key: val for key, val in self.orders.items()}
            self.orders = orders
            self.orders[newNum].orderNum = newNum
            # Order status snapshots are keyed by order number (Step 49), so rekey
            # the entry and fix up the stored orderNum on the record.
            if oldNum in self.orderStatus:
                status = self.orderStatus.pop(oldNum)
                status.orderNum = newNum
                self.orderStatus[newNum] = status

    def addOrder(self, order: Order):
        if order.orderNum in self.orders:
            raise RuntimeError('order.orderNum already in self.orders')
        self.orders[order.orderNum] = order

    def delOrder(self, orderNum):
        if orderNum not in self.orders:
            raise RuntimeError('orderNum not in self.orders')
        del self.orders[orderNum]
        # Order status snapshots are config tied to a live order (Step 49), so
        # cascade-drop them when the order is deleted — the same config-cascades
        # pattern as delPart dropping a part's partPressPref.
        self.orderStatus.pop(orderNum, None)

    # ---- Sales: order status (dated snapshots) ---------------------------------------------

    def setOrderSnapshot(self, orderNum, date, remainingToPress, remainingToShip):
        # Add or replace one dated status snapshot for an order, keeping
        # self.orderStatus in exact lockstep with the persisted rows: an order entry
        # exists only while it has >= 1 snapshot (an empty DB has an empty dict —
        # same shape as partPressPref / shiftWorkweek). Orders are created/deleted
        # from their own table, so there's no add/del here; the nested editor sets
        # snapshots through this.
        if orderNum not in self.orderStatus:
            self.orderStatus[orderNum] = OrderStatus(orderNum)
        self.orderStatus[orderNum].setSnapshot(date, remainingToPress, remainingToShip)

    def removeOrderSnapshot(self, orderNum, date):
        # Drop one dated snapshot; if it was the order's last, drop the now-empty
        # OrderStatus so the in-memory shape matches the persisted presence rows.
        if orderNum in self.orderStatus:
            self.orderStatus[orderNum].removeSnapshot(date)
            if not self.orderStatus[orderNum].snapshots:
                del self.orderStatus[orderNum]

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
        {},          # production
        {},          # presses
        {},          # pressers
        {},          # shiftWorkweek
        {},          # partPressPref
        {},          # presserPressPref
        {},          # clients
        {},          # orders
        {}           # orderStatus
    )
