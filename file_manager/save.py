import datetime
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from app import MainWindow


class SaveMixin:
    # saveFile orchestration + the long _saveFileBody that walks every table.
    # Operates on `self.dbFile`, `self.filePath`, and `self.mainApp.db` set up by
    # the composed FileManager.

    if TYPE_CHECKING:
        # Attributes provided by the composed FileManager (see file_manager/__init__.py).
        dbFile: sqlite3.Connection | None
        filePath: str | None
        mainApp: MainWindow

    def saveFile(self):
        if self.filePath is None or self.dbFile is None:
            raise RuntimeError('self.filePath is not None and self.dbFile is not None')
        # Atomic save: the body below runs as a single SQLite transaction.
        # Any exception rolls the entire save back, leaving the DB file
        # unchanged (§3.4 of MERGE_PLAN.md).
        try:
            self._saveFileBody()
        except Exception:
            self.dbFile.rollback()
            raise
        self.dbFile.commit()

    def _saveFileBody(self):
        db = self.mainApp.db

        # --- globals (ANIKA cost parameters; db_version is preserved separately) ---
        logging.info(f"Saving globals to {self.filePath}")
        for name in db.globals.getGlobals():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO globals VALUES (?, ?)", (name, getattr(db.globals, name)))
                logging.info(f" * Saving {name} = {getattr(db.globals, name)}")
            except Exception as e:
                logging.error(f" * Error saving {name} = {getattr(db.globals, name)}: {repr(e)}")

        def clearOld(dbName, currDict):
            if self.dbFile is None:
                raise RuntimeError('self.dbFile is None')
            res = self.dbFile.execute(f"SELECT name FROM {dbName}")
            deleted = [vals for vals in res.fetchall() if not vals[0] in currDict]
            if len(deleted) > 0:
                try:
                    self.dbFile.executemany(f"DELETE FROM {dbName} WHERE name=?", deleted)
                    logging.info(f" * Deleting old entries {", ".join([f"{name[0]}" for name in deleted])}")
                except Exception as e:
                    logging.error(f" * Error deleting old entries {", ".join([f"{name[0]}" for name in deleted])}: {repr(e)}")

        # --- ANIKA: materials / mixtures / packaging / parts / inventories ---

        logging.info(f"Saving materials to {self.filePath}")
        for name in db.materials:
            vals = db.materials[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("materials", db.materials)

        logging.info(f"Saving mixtures to {self.filePath}")
        for name in db.mixtures:
            vals = db.mixtures[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO mixtures VALUES (?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("mixtures", db.mixtures)

        logging.info(f"Saving mixture components to {self.filePath}")
        # Strategy: for each in-memory mixture, wipe its child rows and re-insert. Then
        # orphan-clean any child rows whose mixture parent no longer exists.
        for name in db.mixtures:
            self.dbFile.execute("DELETE FROM mixture_components WHERE mixture=?", (name,))
            for vals in db.mixtures[name].getComponentTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO mixture_components VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT mixture, material FROM mixture_components")
        orphans = [row for row in res.fetchall() if row[0] not in db.mixtures]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM mixture_components WHERE (mixture, material)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan components {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan components {orphans}: {repr(e)}")

        logging.info(f"Saving packaging to {self.filePath}")
        for name in db.packaging:
            vals = db.packaging[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO packaging VALUES (?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("packaging", db.packaging)

        logging.info(f"Saving parts to {self.filePath}")
        for name in db.parts:
            vals = db.parts[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")
        clearOld("parts", db.parts)

        logging.info(f"Saving part pads to {self.filePath}")
        for name in db.parts:
            self.dbFile.execute("DELETE FROM part_pads WHERE part=?", (name,))
            for vals in db.parts[name].getPadTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO part_pads VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT part, pad FROM part_pads")
        orphans = [row for row in res.fetchall() if row[0] not in db.parts]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM part_pads WHERE (part, pad)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan part pads {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan part pads {orphans}: {repr(e)}")

        logging.info(f"Saving part misc to {self.filePath}")
        for name in db.parts:
            self.dbFile.execute("DELETE FROM part_misc WHERE part=?", (name,))
            for vals in db.parts[name].getMiscTuples():
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO part_misc VALUES (?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")
        res = self.dbFile.execute("SELECT part, item FROM part_misc")
        orphans = [row for row in res.fetchall() if row[0] not in db.parts]
        if len(orphans) > 0:
            try:
                self.dbFile.executemany("DELETE FROM part_misc WHERE (part, item)=(?, ?)", orphans)
                logging.info(f" * Deleting orphan part misc {orphans}")
            except Exception as e:
                logging.error(f" * Error deleting orphan part misc {orphans}: {repr(e)}")

        logging.info(f"Saving materials inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getMaterialTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO materialInventory VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM materialInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].materials]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM materialInventory WHERE (name, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving parts inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getPartTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO partInventory VALUES (?, ?, ?, ?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT name, date FROM partInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].parts]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM partInventory WHERE (name, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        # --- BECKY: employees / reviews / training / attendance / PTO / notes / holidays / observances ---

        logging.info(f"Saving employees to {self.filePath}")
        for idNum in db.employees:
            vals = db.employees[idNum].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum FROM employees")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.employees]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM employees WHERE idNum=?", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"{idNum[0]}" for idNum in deleted])}: {repr(e)}")

        logging.info(f"Saving reviews to {self.filePath}")
        for idNum in db.reviews:
            valsList = db.reviews[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO reviews VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM reviews")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.reviews or not datetime.date.fromisoformat(vals[1]) in db.reviews[vals[0]].reviews]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM reviews WHERE (idNum, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving training to {self.filePath}")
        for idNum in db.training:
            valsList = db.training[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO training VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, training, date FROM training")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.training or not vals[1] in db.training[vals[0]].training or not datetime.date.fromisoformat(vals[2]) in db.training[vals[0]].training[vals[1]]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM training WHERE (idNum, training, date)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving attendance to {self.filePath}")
        for idNum in db.attendance:
            valsList = db.attendance[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO attendance VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date FROM attendance")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.attendance or not datetime.date.fromisoformat(vals[1]) in db.attendance[vals[0]].points]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM attendance WHERE (idNum, date)=(?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving PTO to {self.filePath}")
        for idNum in db.PTO:
            valsList = db.PTO[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO PTO VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, start, end FROM PTO")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.PTO or not (datetime.date.fromisoformat(vals[1]), vals[2] if vals[2] in ["CARRY", "CASH", "DROP"] else datetime.date.fromisoformat(vals[2])) in db.PTO[vals[0]].PTO]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM PTO WHERE (idNum, start, end)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[1]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving notes to {self.filePath}")
        for idNum in db.notes:
            valsList = db.notes[idNum].getTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?)", vals)
                    logging.info(f" * Saving {vals}")
                except Exception as e:
                    logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT idNum, date, time FROM notes")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.notes or not (datetime.date.fromisoformat(vals[1]), vals[2]) in db.notes[vals[0]].notes]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM notes WHERE (idNum, date, time)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]}, {vals[2]})" for vals in deleted])}: {repr(e)}")

        logging.info(f"Saving holidays to {self.filePath}")
        for vals in db.holidays.getDefaultTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO holidays VALUES (?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday FROM holidays")
        deleted = [vals for vals in res.fetchall() if not vals[0] in db.holidays.defaults]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM holidays WHERE holiday=?", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"{holiday[0]}" for holiday in deleted])}: {repr(e)}")

        logging.info(f"Saving observances to {self.filePath}")
        for vals in db.holidays.getObservanceTuples():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO observances VALUES (?, ?, ?)", vals)
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(f"SELECT holiday, shift, date FROM observances")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[2]).year in db.holidays.observances or
                                                      not vals[0] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year] or
                                                      not vals[1] in db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]] or
                                                      not db.holidays.observances[datetime.date.fromisoformat(vals[2]).year][vals[0]][vals[1]].date.isoformat() == vals[2]]
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(f"DELETE FROM observances WHERE (holiday, shift, date)=(?, ?, ?)", deleted)
                logging.info(f" * Deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {", ".join([f"({observance[0]}, {observance[1]}, {observance[2]})" for observance in deleted])}: {repr(e)}")

        # --- MERCY: production ---
        # The `id` column is an AUTOINCREMENT surrogate key — don't try to supply it from
        # in-memory state. Insert on the UNIQUE(employeeId, date, shift, targetType,
        # targetName, action) natural key; SQLite will keep or assign `id` as needed.
        logging.info(f"Saving production to {self.filePath}")
        for key, rec in db.production.items():
            vals = rec.getTuple()
            try:
                self.dbFile.execute(
                    "INSERT OR REPLACE INTO production"
                    "(employeeId, date, shift, targetType, targetName, action, quantity, scrapQuantity, hours) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    vals
                )
                logging.info(f" * Saving {vals}")
            except Exception as e:
                logging.error(f" * Error saving {vals}: {repr(e)}")

        res = self.dbFile.execute(
            "SELECT employeeId, date, shift, targetType, targetName, action FROM production"
        )
        deleted = []
        for row in res.fetchall():
            emp, dateStr, shift, tType, tName, action = row
            memKey = (emp, datetime.date.fromisoformat(dateStr), shift, tType, tName, action)
            if memKey not in db.production:
                deleted.append(row)
        if len(deleted) > 0:
            try:
                self.dbFile.executemany(
                    "DELETE FROM production WHERE "
                    "(employeeId, date, shift, targetType, targetName, action)=(?, ?, ?, ?, ?, ?)",
                    deleted
                )
                logging.info(f" * Deleting old entries {deleted}")
            except Exception as e:
                logging.error(f" * Error deleting old entries {deleted}: {repr(e)}")
