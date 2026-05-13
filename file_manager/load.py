import logging

from records.products import Material, Mixture, Package, Part, MaterialInventoryRecord, PartInventoryRecord
from records.employees import (
    Employee, EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB, EmployeePTODB, EmployeeNotesDB,
    EmployeeReview, EmployeeTrainingDate, EmployeePoint, EmployeePTORange, EmployeeNote, HolidayObservance,
)
from records.production import ProductionRecord


class LoadMixin:
    # loadFile + the _loadIntoDb worker that pours every table into a Database.
    # Operates on `self.dbFile`, `self.filePath`, and `self.mainApp.db` set up by
    # the composed FileManager. _loadIntoDb is called with an explicit db so the
    # importer can populate a throwaway emptyDB without clobbering self.mainApp.db.

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
