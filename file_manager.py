import sqlite3
import datetime

from app import MainWindow
from records import Material, Mixture, Package, Part, MaterialInventoryRecord, PartInventoryRecord

class FileManager:
    def __init__(self, mainApp: MainWindow) -> None:
        self.mainApp = mainApp
        self.filePath = None
        self.dbFile = None

    def initFile(self):
        assert(not self.filePath == None)
        try:
            self.dbFile = sqlite3.connect(self.filePath)
            res = self.dbFile.execute("SELECT name FROM sqlite_master")
            tables = [row[0] for row in res.fetchall()]
            if len(tables) > 14:
                print(f"Initialization error: too many tables in {self.filePath}.  Found:")
                for tab in tables:
                    print(f" * {tab}")
                self.dbFile.close()
                return False
            elif len(tables) < 10 and len(tables) > 0:
                print(f"Initialization error: too few tables in {self.filePath}.  Found:")
                for tab in tables:
                    print(f" * {tab}")
                self.dbFile.close()
                return False
            
            if len(tables) == 0:
                self.dbFile.execute("CREATE TABLE globals(name PRIMARY KEY, value)")
                self.dbFile.execute("CREATE TABLE materials(name PRIMARY KEY, cost, freight, SiO2, Al2O3, Fe2O3, TiO2, Li2O, P2O5, Na2O, CaO, K2O, MgO, LOI, Plus50, Sub50Plus100, Sub100Plus200, Sub200Plus325, Sub325, otherChem)")
                self.dbFile.execute("CREATE TABLE mixtures(name PRIMARY KEY, materials, weights)")
                self.dbFile.execute("CREATE TABLE packaging(name PRIMARY KEY, kind, cost)")
                self.dbFile.execute("CREATE TABLE parts(name PRIMARY KEY, weight, mix, pressing, turning, loading, unloading, inspection, greenScrap, fireScrap, box, piecesPerBox, pallet, boxesPerPallet, pad, padsPerBox, misc, price, sales)")
                self.dbFile.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
                self.dbFile.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
                self.dbFile.commit()
                return True
            elif len(tables) == 10 and "globals" in tables and "materials" in tables and "mixtures" in tables and "packaging" in tables and "parts" in tables:
                self.dbFile.execute("CREATE TABLE materialInventory(name, date, cost, amount, UNIQUE(name, date))")
                self.dbFile.execute("CREATE TABLE partInventory(name, date, cost, amount40, amount60, amount80, amount100, UNIQUE(name, date))")
                self.dbFile.commit()
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                    self.dbFile.commit()
                return True
            elif len(tables) == 14 and "globals" in tables and "materials" in tables and "mixtures" in tables and "packaging" in tables and "parts" in tables and "materialInventory" in tables and "partInventory" in tables:
                cols = [row[1] for row in self.dbFile.execute("PRAGMA table_info(materials)").fetchall()]
                if 'otherChem' not in cols:
                    self.dbFile.execute("ALTER TABLE materials ADD COLUMN otherChem DEFAULT 0")
                    self.dbFile.commit()
                return True
            else:
                print(f"Initialization error: wrong tables in {self.filePath}")
                self.dbFile.close()
                return False
        except Exception as e:
            print(f"Initialization error: {repr(e)}")
            assert(self.dbFile is not None)
            self.dbFile.close()
            return False

    def saveFile(self):
        assert((not self.filePath == None) and (not self.dbFile == None))
        db = self.mainApp.db
        print(f"Saving globals to {self.filePath}")
        for name in db.globals.getGlobals():
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO globals VALUES (?, ?)", (name, getattr(db.globals, name)))
                print(f" * Saving {name} = {getattr(db.globals, name)}")
            except Exception as e:
                print(f" * Error saving {name} = {getattr(db.globals, name)}: {repr(e)}")
        self.dbFile.commit()

        def clearOld(dbName, currDict):
            assert(self.dbFile is not None)
            res = self.dbFile.execute(f"SELECT name FROM {dbName}")
            deleted = [vals for vals in res.fetchall() if not vals[0] in currDict]
            if len(deleted) > 0:
                try:
                    res.executemany(f"DELETE FROM {dbName} WHERE name=?", deleted)
                    print(f" * Deleting old entries {", ".join([f"{name[0]}" for name in deleted])}")
                except Exception as e:
                    print(f" * Error deleting old entries {", ".join([f"{name[0]}" for name in deleted])}: {repr(e)}")
            self.dbFile.commit()

        print(f"Saving materials to {self.filePath}")
        for name in db.materials:
            vals = db.materials[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()
        clearOld("materials", db.materials)

        print(f"Saving mixtures to {self.filePath}")
        for name in db.mixtures:
            vals = db.mixtures[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO mixtures VALUES (?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()
        clearOld("mixtures", db.mixtures)

        print(f"Saving packaging to {self.filePath}")
        for name in db.packaging:
            vals = db.packaging[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO packaging VALUES (?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()
        clearOld("packaging", db.packaging)

        print(f"Saving parts to {self.filePath}")
        for name in db.parts:
            vals = db.parts[name].getTuple()
            try:
                self.dbFile.execute("INSERT OR REPLACE INTO parts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", vals)
                print(f" * Saving {vals}")
            except Exception as e:
                print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()
        clearOld("parts", db.parts)

        print(f"Saving materials inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getMaterialTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO materialInventory VALUES (?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()

        res = self.dbFile.execute(f"SELECT name, date FROM materialInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].materials]
        if len(deleted) > 0:
            try:
                res.executemany(f"DELETE FROM materialInventory WHERE (name, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")
        self.dbFile.commit()
        
        print(f"Saving parts inventories to {self.filePath}")
        for date in db.inventories:
            valsList = db.inventories[date].getPartTuples()
            for vals in valsList:
                try:
                    self.dbFile.execute("INSERT OR REPLACE INTO partInventory VALUES (?, ?, ?, ?, ?, ?, ?)", vals)
                    print(f" * Saving {vals}")
                except Exception as e:
                    print(f" * Error saving {vals}: {repr(e)}")
        self.dbFile.commit()

        res = self.dbFile.execute(f"SELECT name, date FROM partInventory")
        deleted = [vals for vals in res.fetchall() if not datetime.date.fromisoformat(vals[1]) in db.inventories or not vals[0] in db.inventories[datetime.date.fromisoformat(vals[1])].parts]
        if len(deleted) > 0:
            try:
                res.executemany(f"DELETE FROM partInventory WHERE (name, date)=(?, ?)", deleted)
                print(f" * Deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}")
            except Exception as e:
                print(f" * Error deleting old entries {", ".join([f"({vals[0]}, {vals[1]})" for vals in deleted])}: {repr(e)}")
        self.dbFile.commit()

    def loadFile(self):
        assert((not self.filePath == None) and (not self.dbFile == None))
        from records import emptyDB
        self.mainApp.db = emptyDB()
        db = self.mainApp.db
        print(f"Loading globals from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM globals")
        for pair in res.fetchall():
            name, val = pair
            setattr(db.globals, name, val)
            print(f" * Loaded {name} = {val}")

        print(f"Loading materials from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materials")
        for values in res.fetchall():
            material = Material("ERROR")
            material.fromTuple(values)
            db.materials[material.name] = material
            material.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {material}")

        print(f"Loading mixtures from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM mixtures")
        for values in res.fetchall():
            mixture = Mixture("ERROR")
            mixture.fromTuple(values)
            db.mixtures[mixture.name] = mixture
            mixture.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {mixture}")

        print(f"Loading packaging from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM packaging")
        for values in res.fetchall():
            package = Package("ERROR", None, None)
            package.fromTuple(values)
            db.packaging[package.name] = package
            package.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {package}")

        print(f"Loading parts from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM parts")
        for values in res.fetchall():
            part = Part("ERROR")
            part.fromTuple(values)
            db.parts[part.name] = part
            part.db = db
            print(f" * Loaded {values}")
            print(f" --> Loaded {part}")

        print(f"Loading material inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM materialInventory")
        for values in res.fetchall():
            rec = MaterialInventoryRecord()
            rec.fromTuple(values)
            db.addMaterialInventory(rec)
            print(f" * Loaded {values}")
            print(f" --> Loaded {rec}")

        print(f"Loading part inventories from {self.filePath}")
        res = self.dbFile.execute("SELECT * FROM partInventory")
        for values in res.fetchall():
            rec = PartInventoryRecord()
            rec.fromTuple(values)
            db.addPartInventory(rec)
            print(f" * Loaded {values}")
            print(f" --> Loaded {rec}")

    def setFile(self, filePath):
        oldPath = self.filePath
        oldConn = self.dbFile
        self.filePath = filePath
        success = self.initFile()
        if success:
            if not oldConn == None:
                oldConn.close()
        else:
            print(f"Failed to initialize {filePath}")
            self.filePath = oldPath
            self.dbFile = oldConn
        return success