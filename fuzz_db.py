"""
Generate a MERCY DB populated with plausible fake data across every record type.

Useful for:
  - Exercising reports (and future report designs) with realistic volume
  - Sanity-checking schema migrations at scale
  - Producing demoable DBs to hand around internally

The fuzzer writes through the real `FileManager.saveFile()` pipeline, so the
resulting DB is indistinguishable from one the running app would produce.
Determinism: pass ``--seed N`` for reproducible output.

Usage:
    ./Scripts/python.exe fuzz_db.py                          # 'medium' into fuzz.db
    ./Scripts/python.exe fuzz_db.py -o demo.db -s large --seed 7
    ./Scripts/python.exe fuzz_db.py -s tiny -o smoke_fixture.db --seed 1

Scales (roughly):
    tiny    — 3 parts, 3 employees, 5 days production
    small   — 6 parts, 6 employees, 30 days production
    medium  — 20 parts, 15 employees, 90 days production  (default)
    large   — 60 parts, 40 employees, 180 days production

Not intended for committing generated DBs; fuzz*.db is gitignored.
"""
import argparse
import datetime
import os
import random
import sys

# Importing app.py pulls in Qt. MainWindow() fails silently without a QApplication
# when QT_QPA_PLATFORM=offscreen, so set that + create a QApplication up front.
# See memory: feedback_offscreen_qt.md
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import defaults  # noqa: E402
from app import MainWindow  # noqa: E402
from records import (  # noqa: E402
    Material, Mixture, Package, Part,
    MaterialInventoryRecord, PartInventoryRecord, Inventory,
    Employee, EmployeeReview, EmployeeTrainingDate, EmployeePoint,
    EmployeePTORange, EmployeeNote, HolidayObservance,
    EmployeeReviewsDB, EmployeeTrainingDB, EmployeePointsDB,
    EmployeePTODB, EmployeeNotesDB,
    ProductionRecord,
)


# ---- scale knobs ------------------------------------------------------------

SCALES = {
    "tiny":   dict(materials=4,  mixtures=2,  packaging=5,  parts=3,
                   employees=3,  inventorySnapshots=1, productionDays=5),
    "small":  dict(materials=6,  mixtures=3,  packaging=6,  parts=6,
                   employees=6,  inventorySnapshots=2, productionDays=30),
    "medium": dict(materials=12, mixtures=5,  packaging=10, parts=20,
                   employees=15, inventorySnapshots=2, productionDays=90),
    "large":  dict(materials=25, mixtures=10, packaging=18, parts=60,
                   employees=40, inventorySnapshots=4, productionDays=180),
}


# ---- name pools (fake but plausible) ----------------------------------------

FIRST_NAMES = [
    "Alex", "Blair", "Casey", "Dana", "Evan", "Frankie", "Gale", "Harper",
    "Indy", "Jules", "Kai", "Logan", "Morgan", "Nico", "Ollie", "Parker",
    "Quinn", "Riley", "Sage", "Taylor", "Umber", "Vic", "Wren", "Xan",
    "Yael", "Zion", "Ash", "Bryn", "Cam", "Devon", "Ellis", "Finn",
    "Gray", "Hollis", "Ira", "Jamie", "Kendall", "Lane", "Marley", "Noel",
]
LAST_NAMES = [
    "Adler", "Bishop", "Carter", "Dawson", "Ellis", "Fletcher", "Greene",
    "Hoyt", "Ingram", "Jansen", "Kerr", "Lowry", "Mercer", "Nash", "Ortiz",
    "Park", "Quinn", "Rao", "Sloan", "Tully", "Underwood", "Vance", "Walsh",
    "Xiang", "Yates", "Zimmer",
]
ROLES = [
    "Presser", "Finisher", "Batcher", "Shift Lead", "Quality Inspector",
    "Materials Handler", "Maintenance", "Shipping Clerk",
]
STATES = ["OH", "PA", "IN", "MI", "KY"]
CITIES = ["Springfield", "Fairview", "Franklin", "Clayton", "Greenville",
          "Jackson", "Milford", "Oakland", "Riverside", "Salem"]
STREETS = ["Main St", "Oak Ave", "Pine Rd", "Maple Dr", "Elm Ct",
           "Washington Blvd", "Cedar Ln"]

MATERIAL_POOL = [
    "Feldspar A", "Feldspar B", "Silica 200", "Silica 325",
    "Kaolin Light", "Kaolin Heavy", "Ball Clay", "Nepheline",
    "Dolomite", "Talc", "Lithium Spar", "Zirconium Oxide",
    "Tin Oxide", "Iron Oxide", "Aluminum Oxide", "Calcium Carb",
    "Magnesium Carb", "Sodium Ash", "Potash", "Quartz Fine",
    "Quartz Coarse", "Bone Ash", "Bentonite", "Frit Base", "Frit Lead-free",
]
MIX_POOL = [
    "Standard White", "Standard Cream", "High-Strength A", "High-Strength B",
    "Low-Fire", "Engine Body", "Refractory 1", "Refractory 2",
    "Porcelain Mix", "Stoneware Mix", "Kiln Shelf Mix", "Sanitary Ware",
]
PACKAGING_POOL = {
    "box":    ["Box 12x10", "Box 18x12", "Box 24x16", "Heavy Crate"],
    "pallet": ["Pallet 48x40", "Pallet 42x42", "Half Pallet"],
    "pad":    ["Corrugate Pad", "Foam Pad A", "Foam Pad B", "Cardboard Divider"],
    "misc":   ["Strapping", "Stretch Wrap", "Edge Protector", "Label Set"],
}
PART_PREFIX = ["Insulator", "Bushing", "Body", "Ring", "Cap", "Disc", "Tube", "Sleeve"]
PART_SUFFIX = ["X1", "X2", "Premium", "Standard", "HT", "LT", "500", "700", "A", "B"]

TRAININGS = defaults.TRAINING[:]
POINT_REASONS = list(defaults.POINT_VALS.keys())

NOTE_PHRASES = [
    "Arrived to find line already running", "Covered for late teammate",
    "Coached on PPE", "Discussed goals for Q review",
    "Clarified batch-sheet procedure", "Praised for spotting defect",
    "Reviewed new finishing spec", "Mentioned interest in forklift certification",
]
REVIEW_DETAILS = [
    "Meeting expectations. Focus next quarter on consistency on finish line.",
    "Strong performer; flagged for cross-training opportunities.",
    "Needs improvement on timeliness; action plan discussed.",
    "New hire orientation review, no concerns.",
    "Exceeded targets; recommended for shift lead consideration.",
]

# Default month for each holiday (used for observance placement).
HOLIDAY_MONTHS = {
    "New Years Day":       1,
    "Presidents Day":      2,
    "Memorial Day":        5,
    "Independence Day":    7,
    "Labor Day":           9,
    "Thanksgiving":       11,
    "Thanksgiving Morrow": 11,
    "Christmas Eve":      12,
    "Christmas Day":      12,
    "New Years Eve":      12,
}


# ---- helpers ----------------------------------------------------------------

def pickUnique(rng: random.Random, pool: list[str], count: int) -> list[str]:
    """Return `count` unique names; synthesizes suffixed names if the pool is too small."""
    if count <= len(pool):
        return rng.sample(pool, count)
    picks = list(pool)
    i = 1
    while len(picks) < count:
        picks.append(f"{pool[i % len(pool)]} {i}")
        i += 1
    return picks


# ---- population: ANIKA side --------------------------------------------------

def populateMaterials(db, rng, n):
    names = pickUnique(rng, MATERIAL_POOL, n)
    for name in names:
        m = Material(name)
        m.setCost(round(rng.uniform(50, 600), 2), round(rng.uniform(20, 80), 2))
        m.setChems(*[round(rng.uniform(0, 12), 2) for _ in range(11)])
        m.setSizes(*[round(rng.uniform(0, 25), 2) for _ in range(5)])
        m.otherChem = round(rng.uniform(0, 5), 2)
        db.addMaterial(m)
    return names


def populateMixtures(db, rng, n, materialNames):
    names = pickUnique(rng, MIX_POOL, n)
    for name in names:
        mix = Mixture(name)
        count = min(rng.randint(2, 4), len(materialNames))
        for mat in rng.sample(materialNames, count):
            mix.add(mat, rng.randint(10, 200))
        db.addMixture(mix)
    return names


def populatePackaging(db, rng, n):
    # Guarantee at least one of each kind, then fill the rest randomly.
    picks: list[tuple[str, str]] = []
    for kind, pool in PACKAGING_POOL.items():
        picks.append((rng.choice(pool), kind))
    remaining = []
    for kind, pool in PACKAGING_POOL.items():
        for name in pool:
            if (name, kind) not in picks:
                remaining.append((name, kind))
    rng.shuffle(remaining)
    while len(picks) < n and remaining:
        picks.append(remaining.pop())

    names = []
    for name, kind in picks:
        pkg = Package(name, kind, round(rng.uniform(0.10, 15.0), 2))
        db.addPackaging(pkg)
        names.append(name)
    return names


def populateParts(db, rng, n, mixtureNames, packagingByKind):
    names = []
    used = set()
    # Defensive cap: if we somehow can't generate n unique names from the pool
    # combinatorics (prefix × suffix = 80), stop gracefully.
    maxAttempts = n * 5
    attempts = 0
    while len(names) < n and attempts < maxAttempts:
        attempts += 1
        name = f"{rng.choice(PART_PREFIX)} {rng.choice(PART_SUFFIX)}"
        if name in used:
            continue
        used.add(name)

        p = Part(name)
        p.setProduction(
            weight=round(rng.uniform(0.25, 12), 2),
            mix=rng.choice(mixtureNames),
            pressing=round(rng.uniform(8, 80), 1),
            turning=round(rng.uniform(10, 100), 1),
            fireScrap=round(rng.uniform(0.005, 0.06), 4),
            price=round(rng.uniform(1.50, 45), 2),
        )
        numPads = rng.randint(0, min(2, len(packagingByKind["pad"])))
        pads = rng.sample(packagingByKind["pad"], numPads) if numPads else []
        padsPerBox = [rng.randint(1, 6) for _ in pads]
        numMisc = rng.randint(0, min(2, len(packagingByKind["misc"])))
        misc = rng.sample(packagingByKind["misc"], numMisc) if numMisc else []
        p.setPackaging(
            box=rng.choice(packagingByKind["box"]),
            piecesPerBox=rng.randint(4, 40),
            pallet=rng.choice(packagingByKind["pallet"]),
            boxesPerPallet=rng.randint(12, 64),
            pad=pads,
            padsPerBox=padsPerBox,
            misc=misc,
        )
        p.sales = rng.randint(500, 20000)
        db.addPart(p)
        names.append(name)
    return names


def populateInventory(db, rng, n, materialNames, partNames, today):
    # n snapshots stepping 30–90 days backward from today.
    date = today
    for _ in range(n):
        inv = Inventory(date)
        # Snapshot ~half the materials and ~half the parts each pass.
        for mat in rng.sample(materialNames, max(1, len(materialNames) // 2)):
            rec = MaterialInventoryRecord()
            rec.setName(mat)
            rec.setDate(date)
            rec.setInventory(round(rng.uniform(200, 1000), 2),
                             round(rng.uniform(500, 20000), 1))
            inv.addMaterialRecord(rec)
        for part in rng.sample(partNames, max(1, len(partNames) // 2)):
            rec = PartInventoryRecord()
            rec.setName(part)
            rec.setDate(date)
            rec.setInventory(
                round(rng.uniform(1, 50), 2),
                rng.randint(0, 200), rng.randint(0, 200),
                rng.randint(0, 200), rng.randint(0, 200),
            )
            inv.addPartRecord(rec)
        db.inventories[date] = inv
        date = date - datetime.timedelta(days=rng.randint(30, 90))


# ---- population: BECKY side --------------------------------------------------

def populateEmployees(db, rng, n, today):
    idNums = []
    usedIds = set()
    usedNames = set()
    while len(idNums) < n:
        idNum = rng.randint(1001, 9999)
        if idNum in usedIds:
            continue
        last = rng.choice(LAST_NAMES)
        first = rng.choice(FIRST_NAMES)
        if (first, last) in usedNames:
            continue
        usedIds.add(idNum)
        usedNames.add((first, last))

        emp = Employee()
        emp.setID(idNum)
        emp.setName(last, first)
        years = rng.choice([0, 0, 1, 1, 2, 3, 5, 8, 12])
        annivYear = today.year - years
        emp.setAnniversary(datetime.date(
            annivYear, rng.randint(1, 12), rng.randint(1, 28)
        ))
        emp.setJob(rng.choice(ROLES), rng.choice([1, 2, 3]), rng.random() > 0.1)
        emp.setAddress(
            f"{rng.randint(100, 9999)} {rng.choice(STREETS)}",
            "" if rng.random() > 0.2 else f"Apt {rng.randint(1, 40)}",
            rng.choice(CITIES),
            rng.choice(STATES),
            f"{rng.randint(10000, 99999)}",
            f"({rng.randint(200, 899)}) {rng.randint(200, 899)}-{rng.randint(1000, 9999)}",
            f"{first.lower()}.{last.lower()}@example.com",
        )
        emp.setStatus(rng.random() > 0.15)

        db.employees[idNum] = emp
        db.reviews[idNum] = EmployeeReviewsDB(idNum)
        db.training[idNum] = EmployeeTrainingDB(idNum)
        db.attendance[idNum] = EmployeePointsDB(idNum)
        db.PTO[idNum] = EmployeePTODB(idNum)
        db.notes[idNum] = EmployeeNotesDB(idNum)
        idNums.append(idNum)
    return idNums


def populateReviews(db, rng, idNums, today):
    for idNum in idNums:
        numReviews = rng.randint(0, 3)
        seen = set()
        for _ in range(numReviews):
            date = today - datetime.timedelta(days=rng.randint(30, 1095))
            if date in seen:
                continue
            seen.add(date)
            nxt = date + datetime.timedelta(days=rng.choice([90, 180, 365]))
            db.reviews[idNum].reviews[date] = EmployeeReview(
                idNum, date, nxt, rng.choice(REVIEW_DETAILS)
            )


def populateTraining(db, rng, idNums, today):
    for idNum in idNums:
        picked = rng.sample(TRAININGS, min(rng.randint(2, 5), len(TRAININGS)))
        for t in picked:
            date = today - datetime.timedelta(days=rng.randint(60, 730))
            td = EmployeeTrainingDate(idNum, t, date,
                                      rng.choice(["", "Passed", "Refresher", ""]))
            db.training[idNum].training[t][date] = td


def populateAttendance(db, rng, idNums, today):
    for idNum in idNums:
        n = rng.choice([0, 0, 1, 2, 3, 5, 8, 12])
        seen = set()
        for _ in range(n):
            date = today - datetime.timedelta(days=rng.randint(1, 365))
            if date in seen:
                continue
            seen.add(date)
            reason = rng.choice(POINT_REASONS)
            db.attendance[idNum].points[date] = EmployeePoint(
                idNum, date, reason, defaults.POINT_VALS[reason]
            )


def populatePTO(db, rng, idNums, today):
    for idNum in idNums:
        n = rng.randint(0, 4)
        seen = set()
        for _ in range(n):
            start = today - datetime.timedelta(days=rng.randint(0, 300))
            if rng.random() < 0.85:
                length = rng.randint(1, 5)
                end = start + datetime.timedelta(days=length)
                hours = 8 * length
            else:
                # CARRY/CASH/DROP are anchored to start of year per the model.
                end = rng.choice(["CARRY", "CASH", "DROP"])
                hours = rng.randint(8, 40)
                start = datetime.date(today.year, 1, 1)
            if (start, end) in seen:
                continue
            seen.add((start, end))
            db.PTO[idNum].PTO[(start, end)] = EmployeePTORange(idNum, start, end, hours)


def populateNotes(db, rng, idNums, today):
    for idNum in idNums:
        n = rng.randint(0, 3)
        seen = set()
        for _ in range(n):
            date = today - datetime.timedelta(days=rng.randint(0, 365))
            timeStr = f"{rng.randint(6, 18):02d}:{rng.choice([0, 15, 30, 45]):02d}"
            key = (date, timeStr)
            if key in seen:
                continue
            seen.add(key)
            db.notes[idNum].notes[key] = EmployeeNote(
                idNum, date, timeStr, rng.choice(NOTE_PHRASES)
            )


def populateHolidays(db, rng, today):
    for h in defaults.HOLIDAYS:
        db.holidays.setDefault(h, HOLIDAY_MONTHS.get(h, 1))
    # Observances for this year + next, all three shifts.
    for year in [today.year, today.year + 1]:
        for h in defaults.HOLIDAYS:
            month = HOLIDAY_MONTHS.get(h, 1)
            obsDate = datetime.date(year, month, rng.randint(1, 28))
            for shift in [1, 2, 3]:
                db.holidays.setObservance(HolidayObservance(h, obsDate, shift))


# ---- population: MERCY production --------------------------------------------

def populateProduction(db, rng, idNums, partNames, mixtureNames, days, today):
    """
    Scatter production records across the last `days` days. For each employee
    on each day, 0-3 records split across the three actions (Batching on mixes,
    Pressing/Finishing on parts). UNIQUE(employee, date, shift, type, name, action).
    """
    actions = defaults.PRODUCTION_ACTIONS
    usedKeys = set()
    count = 0
    for dayOffset in range(days):
        date = today - datetime.timedelta(days=dayOffset)
        # Sparser weekend coverage.
        if date.weekday() >= 5 and rng.random() < 0.7:
            continue
        for idNum in idNums:
            if rng.random() < 0.15:  # ~15% off-day
                continue
            shift = rng.choice([1, 2, 3])
            for _ in range(rng.randint(1, 3)):
                action = rng.choice(actions)
                targetType = defaults.PRODUCTION_ACTION_TARGET[action]
                target = rng.choice(mixtureNames if targetType == "mix" else partNames)
                key = (idNum, date, shift, targetType, target, action)
                if key in usedKeys:
                    continue
                usedKeys.add(key)

                if action == "Batching":
                    qty = rng.randint(1, 6)          # drops
                    hours = round(rng.uniform(0.5, 4), 1)
                else:
                    qty = rng.randint(10, 200)       # parts
                    hours = round(rng.uniform(1, 8), 1)
                scrap = 0 if rng.random() < 0.6 else rng.randint(0, 5)

                rec = ProductionRecord()
                rec.setRecord(idNum, date, shift, action, target, qty, scrap, hours)
                db.production[key] = rec
                count += 1
    return count


# ---- entry ------------------------------------------------------------------

def build(output: str, seed: int | None, scale: str):
    rng = random.Random(seed)
    cfg = SCALES[scale]
    today = datetime.date.today()

    # Wipe existing target so FileManager.setFile takes the 'empty' path
    # (creates the full unified schema + stamps current db_version).
    if os.path.exists(output):
        os.remove(output)

    _app = QApplication.instance() or QApplication(sys.argv[:1])
    w = MainWindow()
    db = w.db

    print(f"seed={seed!r}  scale={scale}  output={output}")
    materialNames = populateMaterials(db, rng, cfg["materials"])
    print(f"  materials: {len(materialNames)}")
    mixtureNames = populateMixtures(db, rng, cfg["mixtures"], materialNames)
    print(f"  mixtures:  {len(mixtureNames)}")
    populatePackaging(db, rng, cfg["packaging"])
    packagingByKind = {k: [] for k in PACKAGING_POOL}
    for name in db.packaging:
        packagingByKind[db.packaging[name].kind].append(name)
    print(f"  packaging: {len(db.packaging)}  ({ {k: len(v) for k, v in packagingByKind.items()} })")
    partNames = populateParts(db, rng, cfg["parts"], mixtureNames, packagingByKind)
    print(f"  parts:     {len(partNames)}")

    idNums = populateEmployees(db, rng, cfg["employees"], today)
    print(f"  employees: {len(idNums)}")
    populateReviews(db, rng, idNums, today)
    populateTraining(db, rng, idNums, today)
    populateAttendance(db, rng, idNums, today)
    populatePTO(db, rng, idNums, today)
    populateNotes(db, rng, idNums, today)
    populateHolidays(db, rng, today)

    populateInventory(db, rng, cfg["inventorySnapshots"], materialNames, partNames, today)
    print(f"  inventory: {len(db.inventories)} snapshots")

    nprod = populateProduction(db, rng, idNums, partNames, mixtureNames,
                               cfg["productionDays"], today)
    print(f"  production: {nprod} records over {cfg['productionDays']} days")

    if not w.fileManager.setFile(output):
        print(f"ERROR: setFile returned False for {output}", file=sys.stderr)
        sys.exit(1)
    w.fileManager.saveFile()
    if w.fileManager.dbFile is not None:
        w.fileManager.dbFile.close()
    print(f"wrote {output}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-o", "--output", default="fuzz.db",
                    help="output DB path (default: fuzz.db)")
    ap.add_argument("-s", "--scale", default="medium", choices=list(SCALES),
                    help="scale preset (default: medium)")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for reproducible output")
    args = ap.parse_args()
    build(args.output, args.seed, args.scale)


if __name__ == "__main__":
    main()
