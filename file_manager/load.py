import logging
from typing import TYPE_CHECKING

from records.products import Material, Mixture, Package, Part, MaterialInventoryRecord, PartInventoryRecord
from records.employees import (
    Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB,
    EmployeeReview, EmployeeTrainingDate, EmployeePoint, EmployeePTORange, EmployeeNote, HolidayObservance,
)
from records.production import ProductionRecord
from records.scheduling import Press, Presser, ShiftWorkweek, PartPressPref, PresserPressPref, PartTruck
from records.sales import Client, Order
import datetime

if TYPE_CHECKING:
    import sqlite3
    from app import MainWindow


class LoadMixin:
    # loadFile + the _loadIntoDb worker that pours every table into a Database.
    # Operates on `self.dbFile`, `self.filePath`, and `self.mainApp.db` set up by
    # the composed FileManager. _loadIntoDb is called with an explicit db so the
    # importer can populate a throwaway emptyDB without clobbering self.mainApp.db.

    if TYPE_CHECKING:
        # Attributes provided by the composed FileManager (see file_manager/__init__.py).
        # Declared here so Pylance can resolve `self.dbFile`/etc. on mixin methods.
        dbFile: sqlite3.Connection | None
        filePath: str | None
        mainApp: MainWindow

    def loadFile(self):
        if self.filePath is None or self.dbFile is None:
            raise RuntimeError('self.filePath is not None and self.dbFile is not None')
        from records import emptyDB
        self.mainApp.db = emptyDB()
        self._loadIntoDb(self.mainApp.db)

    def _loadIntoDb(self, db):
        # Read every table from self.dbFile into the provided Database. Split out from
        # loadFile so the importer can populate a throwaway `emptyDB()` without
        # clobbering self.mainApp.db.
        if self.filePath is None or self.dbFile is None:
            raise RuntimeError('self.filePath is not None and self.dbFile is not None')

        # --- globals (ANIKA cost parameters; ignore db_version on the load side) ---
        logging.info(f"Loading globals from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM globals")
        for pair in res.fetchall():
            name, val = pair
            if name == "db_version":
                logging.info(f" * (ignored on load) {name} = {val}")
                continue
            setattr(db.globals, name, val)
            logging.info(f" * Loaded {name} = {val}")

        # --- ANIKA data ---

        logging.info(f"Loading materials from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materials")
        for values in res.fetchall():
            material = Material("ERROR")
            material.fromTuple(values)
            db.materials[material.name] = material
            material.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {material}")

        logging.info(f"Loading mixtures from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM mixtures")
        for values in res.fetchall():
            mixture = Mixture("ERROR")
            mixture.fromTuple(values)
            db.mixtures[mixture.name] = mixture
            mixture.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {mixture}")

        logging.info(f"Loading mixture components from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT mixture, material, weight, sort_order FROM mixture_components "
            "ORDER BY mixture, sort_order"
        )
        for (mixtureName, material, weight, _sort) in res.fetchall():
            if mixtureName not in db.mixtures:
                raise RuntimeError(f'mixture_components row references missing mixture {mixtureName!r}')
            db.mixtures[mixtureName].add(material, weight)
            logging.info(f" * Loaded component ({mixtureName}, {material}, {weight})")

        logging.info(f"Loading packaging from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM packaging")
        for values in res.fetchall():
            package = Package("ERROR", None, None)
            package.fromTuple(values)
            db.packaging[package.name] = package
            package.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {package}")

        logging.info(f"Loading parts from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM parts")
        for values in res.fetchall():
            part = Part("ERROR")
            part.fromTuple(values)
            db.parts[part.name] = part
            part.db = db
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {part}")

        logging.info(f"Loading part pads from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT part, pad, padsPerBox, sort_order FROM part_pads "
            "ORDER BY part, sort_order"
        )
        for (partName, pad, padsPerBox, _sort) in res.fetchall():
            if partName not in db.parts:
                raise RuntimeError(f'part_pads row references missing part {partName!r}')
            if db.parts[partName].pad is None:
                db.parts[partName].pad = []
            if db.parts[partName].padsPerBox is None:
                db.parts[partName].padsPerBox = []
            db.parts[partName].pad.append(pad)
            db.parts[partName].padsPerBox.append(padsPerBox)
            logging.info(f" * Loaded pad ({partName}, {pad}, {padsPerBox})")

        logging.info(f"Loading part misc from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT part, item, sort_order FROM part_misc "
            "ORDER BY part, sort_order"
        )
        for (partName, item, _sort) in res.fetchall():
            if partName not in db.parts:
                raise RuntimeError(f'part_misc row references missing part {partName!r}')
            db.parts[partName].misc.append(item)
            logging.info(f" * Loaded misc ({partName}, {item})")

        logging.info(f"Loading material inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materialInventory")
        for values in res.fetchall():
            rec = MaterialInventoryRecord()
            rec.fromTuple(values)
            db.addMaterialInventory(rec)
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {rec}")

        logging.info(f"Loading part inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM partInventory")
        for values in res.fetchall():
            rec = PartInventoryRecord()
            rec.fromTuple(values)
            db.addPartInventory(rec)
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded {rec}")

        # --- BECKY data ---

        logging.info(f"Loading employees from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM employees")
        for values in res.fetchall():
            employee = Employee()
            employee.fromTuple(values)
            assert employee.idNum is not None, "Employee.fromTuple should set idNum"

            db.addEmployee(employee)
            reviews = EmployeeReviewsDB(employee.idNum)
            db.addEmployeeReviews(reviews)
            training = EmployeeTrainingDB(employee.idNum)
            db.addEmployeeTraining(training)
            points = EmployeePointsDB(employee.idNum)
            db.addEmployeePoints(points)
            PTO = EmployeePTODB(employee.idNum)
            db.addEmployeePTO(PTO)
            notes = EmployeeNotesDB(employee.idNum)
            db.addEmployeeNotes(notes)

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded employee {employee.idNum}")

        logging.info(f"Loading reviews from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM reviews")
        for values in res.fetchall():
            review = EmployeeReview()
            review.fromTuple(values)

            if review.idNum not in db.reviews:
                raise RuntimeError('review.idNum not in db.reviews')
            db.reviews[review.idNum].reviews[review.date] = review

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded review ({review.idNum}, {review.date})")

        logging.info(f"Loading training from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM training")
        for values in res.fetchall():
            training = EmployeeTrainingDate()
            training.fromTuple(values)

            if training.idNum not in db.training:
                raise RuntimeError('training.idNum not in db.training')
            if not training.training in db.training[training.idNum].training:
                db.training[training.idNum].training[training.training] = {}
            db.training[training.idNum].training[training.training][training.date] = training

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded training ({training.idNum}, {training.training}, {training.date})")

        logging.info(f"Loading attendance from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM attendance")
        for values in res.fetchall():
            point = EmployeePoint()
            point.fromTuple(values)

            if point.idNum not in db.attendance:
                raise RuntimeError('point.idNum not in db.attendance')
            db.attendance[point.idNum].points[point.date] = point

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded point ({point.idNum}, {point.date})")

        logging.info(f"Loading PTO from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM PTO")
        for values in res.fetchall():
            pto = EmployeePTORange()
            pto.fromTuple(values)

            if pto.employee not in db.PTO:
                raise RuntimeError('pto.employee not in db.PTO')
            db.PTO[pto.employee].PTO[(pto.start, pto.end)] = pto

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded point ({pto.employee}, {pto.start}, {pto.end})")

        logging.info(f"Loading notes from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM notes")
        for values in res.fetchall():
            note = EmployeeNote()
            note.fromTuple(values)

            if note.idNum not in db.notes:
                raise RuntimeError('note.idNum not in db.notes')
            db.notes[note.idNum].notes[(note.date, note.time)] = note

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded note ({note.idNum}, {note.date}, {note.time})")

        logging.info(f"Loading holidays from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM holidays")
        for values in res.fetchall():
            holiday = values[0]
            month = values[1]

            db.holidays.defaults[holiday] = month

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded holiday {holiday}")

        logging.info(f"Loading observances from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM observances")
        for values in res.fetchall():
            observance = HolidayObservance()
            observance.fromTuple(values)
            assert observance.date is not None, "HolidayObservance.fromTuple should set date"

            db.holidays.setObservance(observance)

            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded observance ({observance.holiday}, {observance.date.isoformat()}, {observance.shift})")

        # --- MERCY: production ---
        logging.info(f"Loading production from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours "
            "FROM production"
        )
        for values in res.fetchall():
            rec = ProductionRecord()
            rec.fromTuple(values)
            db.production[rec.key()] = rec
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded production {rec}")

        # --- Production Scheduling: presses ---
        logging.info(f"Loading presses from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM presses")
        for values in res.fetchall():
            press = Press("ERROR")
            press.fromTuple(values)
            db.presses[press.name] = press
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded press {press}")

        # --- Production Scheduling: pressers ---
        logging.info(f"Loading pressers from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM pressers")
        for values in res.fetchall():
            presser = Presser(-1)
            presser.fromTuple(values)
            db.pressers[presser.employeeId] = presser
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded presser {presser}")

        # --- Production Scheduling: shift workweek ---
        # Each (shift, weekday) row is one working day; rebuild the per-shift
        # ShiftWorkweek on demand so a shift with no rows simply has no entry.
        logging.info(f"Loading shift workweek from {self.filePath}")
        res = self.dbFile.execute("SELECT shift, weekday FROM shift_workweek")
        for (shift, weekday) in res.fetchall():
            if shift not in db.shiftWorkweek:
                db.shiftWorkweek[shift] = ShiftWorkweek(shift)
            db.shiftWorkweek[shift].days.add(weekday)
            logging.info(f" * Loaded workweek ({shift}, {weekday})")

        # --- Sales: clients ---
        logging.info(f"Loading clients from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM clients")
        for values in res.fetchall():
            client = Client("ERROR")
            client.fromTuple(values)
            db.clients[client.name] = client
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded client {client}")

        # --- Sales: orders ---
        logging.info(f"Loading orders from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM orders")
        for values in res.fetchall():
            order = Order("ERROR")
            order.fromTuple(values)
            db.orders[order.orderNum] = order
            logging.info(f" * Loaded {values}")
            logging.info(f" --> Loaded order {order}")

        # --- Production Scheduling: part-press preference ---
        # Each (part, press, score) row is one scored press; rebuild the per-part
        # PartPressPref on demand so a part with no rows simply has no entry.
        logging.info(f"Loading part-press preferences from {self.filePath}")
        res = self.dbFile.execute("SELECT part, press, score FROM part_press_pref ORDER BY part, press")
        for (part, press, score) in res.fetchall():
            if part not in db.partPressPref:
                db.partPressPref[part] = PartPressPref(part)
            db.partPressPref[part].setScore(press, score)
            logging.info(f" * Loaded part-press preference ({part}, {press}, {score})")

        # --- Production Scheduling: presser-press preference ---
        # Each (employeeId, press, score) row is one scored press (Step 65); rebuild
        # the per-presser PresserPressPref on demand so a presser with no rows simply
        # has no entry — the presser twin of part_press_pref above.
        logging.info(f"Loading presser-press preferences from {self.filePath}")
        res = self.dbFile.execute("SELECT employeeId, press, score FROM presser_press_pref ORDER BY employeeId, press")
        for (employeeId, press, score) in res.fetchall():
            if employeeId not in db.presserPressPref:
                db.presserPressPref[employeeId] = PresserPressPref(employeeId)
            db.presserPressPref[employeeId].setScore(press, score)
            logging.info(f" * Loaded presser-press preference ({employeeId}, {press}, {score})")

        # --- Production Scheduling: parts per truck ---
        # Each (part, partsPerTruck) row is one part's truck size (Step 74a); a part
        # with no row simply has no entry (missing = unset).
        logging.info(f"Loading parts per truck from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM part_truck")
        for values in res.fetchall():
            truck = PartTruck("ERROR")
            truck.fromTuple(values)
            db.partTruck[truck.part] = truck
            logging.info(f" * Loaded parts per truck {values}")

        # --- Sales: order status ---
        # Each (orderNum, date, remainingToPress, remainingToShip) row is one dated
        # snapshot; setOrderSnapshot rebuilds the per-order OrderStatus on demand so
        # an order with no rows simply has no entry.
        logging.info(f"Loading order status from {self.filePath}")
        res = self.dbFile.execute(
            "SELECT orderNum, date, remainingToPress, remainingToShip FROM order_status "
            "ORDER BY orderNum, date"
        )
        for (orderNum, date, remainingToPress, remainingToShip) in res.fetchall():
            db.setOrderSnapshot(orderNum, datetime.date.fromisoformat(date),
                                remainingToPress, remainingToShip)
            logging.info(f" * Loaded order status ({orderNum}, {date}, {remainingToPress}, {remainingToShip})")
