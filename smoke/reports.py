"""PDF report rendering checks for the production-family reports
(Step 12) and the three productivity-family reports (Steps 18, 19, 24)."""
import os
import sys
import tempfile
from datetime import date as datetime_date


def production_report() -> list[str]:
    """Step 12: generate each production report and assert files are non-empty.

    Seeds one employee + three records (one per action), then exercises:
      - productionSummaryReport (multi-employee grid path with the totals row)
      - productionActionReport  (single-action filter)
      - productionTargetReport  (single-part filter, both totals + per-action)
      - productionEmployeeReport (single-employee, mixed-action totals)
      - empty-range path (no records in window) — should still render a page.
    Doesn't parse PDF content; success is generation without exception + non-empty file.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord, Employee
    from report import PDFReport

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPaths: list[str] = []
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        emp = Employee()
        emp.idNum = 101
        emp.lastName = "Smith"
        emp.firstName = "Alice"
        emp.shift = 1
        emp.fullTime = True
        emp.status = True
        emp.anniversary = datetime_date(2020, 1, 1)
        w.db.employees[emp.idNum] = emp

        d = datetime_date(2026, 4, 15)
        # Hours nonzero so the Step 26 rate columns are exercised; the Tool
        # Change record exercises the rate-suppressed path (no rate cell on
        # targetless actions).
        for spec in [(d, 1, "Batching", "MixA", 7.5, 0, 1.5),
                     (d, 2, "Pressing", "PartA", 250.0, 3, 8.0),
                     (d, 3, "Finishing", "PartB", 125.5, 0, 6.5),
                     (d, 1, "Tool Change", "", 0, 0, 4.0)]:
            r = ProductionRecord()
            r.setRecord(emp.idNum, *spec)
            w.db.production[r.key()] = r

        start = datetime_date(2026, 4, 1)
        end = datetime_date(2026, 4, 30)
        emptyStart = datetime_date(2030, 1, 1)
        emptyEnd = datetime_date(2030, 1, 31)

        reports = [
            ("summary", lambda p: p.productionSummaryReport(start, end)),
            ("action",  lambda p: p.productionActionReport("Pressing", start, end)),
            ("target",  lambda p: p.productionTargetReport("part", "PartA", start, end)),
            ("employee", lambda p: p.productionEmployeeReport(emp.idNum, start, end)),
            ("empty",   lambda p: p.productionSummaryReport(emptyStart, emptyEnd)),
        ]
        pdf = None
        for name, fn in reports:
            tmpPdf = tempfile.NamedTemporaryFile(suffix=f"-{name}.pdf", delete=False)
            tmpPdf.close()
            pdfPaths.append(tmpPdf.name)
            try:
                pdf = PDFReport(w.db, tmpPdf.name)
                fn(pdf)
            except Exception as e:
                errors.append(f"report {name} raised: {e!r}")
                continue
            if not os.path.exists(tmpPdf.name) or os.path.getsize(tmpPdf.name) == 0:
                errors.append(f"report {name} produced empty/missing file")

        # Step 26: spot-check the rate helper directly. PDFReport methods are
        # otherwise opaque (output is PDF binary), so this asserts the
        # formatting contract that the report tables rely on.
        if pdf is not None:
            if pdf._fmtRate(100, 4) != "25.00":
                errors.append(
                    f"_fmtRate(100, 4) returned {pdf._fmtRate(100, 4)!r}, expected '25.00'")
            if pdf._fmtRate(100, 0) != "—":
                errors.append(
                    f"_fmtRate(100, 0) returned {pdf._fmtRate(100, 0)!r}, expected '—'")
            if pdf._fmtRate(0, 8) != "0.00":
                errors.append(
                    f"_fmtRate(0, 8) returned {pdf._fmtRate(0, 8)!r}, expected '0.00'")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        for p in pdfPaths:
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors


def production_productivity_report() -> list[str]:
    """Step 18: productivity report covers all four layout cases + Tool Change.

    Seeds two employees and production records that span two targets and two
    shifts so the aggregation paths have something to sum, then exercises the
    productivity report in the four shape combinations:
      - specific target + specific shift
      - specific target + all shifts
      - all targets    + specific shift
      - all targets    + all shifts        (adds the by-shift overview table)
    Tool Change gets its own two variants (specific shift, all shifts) since
    its collapse skips rate/hr and per-employee entirely. The empty-range
    path is exercised too — both non-Tool-Change and Tool Change.
    Doesn't parse PDF content; success is generation without exception + a
    non-empty file in each case.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord, Employee
    from report import PDFReport

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPaths: list[str] = []
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        for idNum, first in [(101, "Alice"), (102, "Bob")]:
            emp = Employee()
            emp.idNum = idNum
            emp.lastName = "Smith" if idNum == 101 else "Jones"
            emp.firstName = first
            emp.shift = 1
            emp.fullTime = True
            emp.status = True
            emp.anniversary = datetime_date(2020, 1, 1)
            w.db.employees[emp.idNum] = emp

        d1 = datetime_date(2026, 4, 15)
        d2 = datetime_date(2026, 4, 16)
        # (employeeId, date, shift, action, targetName, quantity, scrap, hours)
        seed = [
            (101, d1, 1, "Pressing", "PartA", 250.0, 3, 4.0),
            (101, d1, 2, "Pressing", "PartB", 100.0, 0, 2.5),
            (102, d1, 1, "Pressing", "PartA",  80.0, 1, 1.5),
            (102, d2, 2, "Pressing", "PartB", 140.0, 0, 3.0),
            (101, d1, 1, "Tool Change", "",      2.0, 0, 0.5),
            (102, d1, 2, "Tool Change", "",      1.0, 0, 0.75),
            (101, d2, 3, "Tool Change", "",      3.0, 0, 1.25),
        ]
        for eid, date, shift, action, target, qty, scrap, hours in seed:
            r = ProductionRecord()
            r.setRecord(eid, date, shift, action, target, qty, scrap, hours)
            w.db.production[r.key()] = r

        start = datetime_date(2026, 4, 1)
        end = datetime_date(2026, 4, 30)
        emptyStart = datetime_date(2030, 1, 1)
        emptyEnd = datetime_date(2030, 1, 31)

        reports = [
            ("productivity-specific-specific",
             lambda p: p.productionProductivityReport("Pressing", "PartA", 1, start, end)),
            ("productivity-specific-allshifts",
             lambda p: p.productionProductivityReport("Pressing", "PartA", None, start, end)),
            ("productivity-alltargets-specific",
             lambda p: p.productionProductivityReport("Pressing", None, 2, start, end)),
            ("productivity-alltargets-allshifts",
             lambda p: p.productionProductivityReport("Pressing", None, None, start, end)),
            ("productivity-toolchange-specific",
             lambda p: p.productionProductivityReport("Tool Change", None, 2, start, end)),
            ("productivity-toolchange-allshifts",
             lambda p: p.productionProductivityReport("Tool Change", None, None, start, end)),
            ("productivity-empty",
             lambda p: p.productionProductivityReport("Pressing", None, None, emptyStart, emptyEnd)),
            ("productivity-toolchange-empty",
             lambda p: p.productionProductivityReport("Tool Change", None, None, emptyStart, emptyEnd)),
        ]
        for name, fn in reports:
            tmpPdf = tempfile.NamedTemporaryFile(suffix=f"-{name}.pdf", delete=False)
            tmpPdf.close()
            pdfPaths.append(tmpPdf.name)
            try:
                pdf = PDFReport(w.db, tmpPdf.name)
                fn(pdf)
            except Exception as e:
                errors.append(f"report {name} raised: {e!r}")
                continue
            if not os.path.exists(tmpPdf.name) or os.path.getsize(tmpPdf.name) == 0:
                errors.append(f"report {name} produced empty/missing file")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        for p in pdfPaths:
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors


def production_employee_productivity_report() -> list[str]:
    """Step 24: per-employee productivity report covers all four selection
    combos (action specific|all × employee specific|all) + Tool Change.

    Seeds two employees and production records covering multiple actions,
    targets, and shifts so each aggregation path has content. Exercises:
      - specific action + specific employee  (Case A)
      - specific action + all employees      (Case C)
      - all actions    + specific employee   (Case B)
      - all actions    + all employees       (Case D, the deepest layout)
      - Tool Change    + specific employee
      - Tool Change    + all employees
      - empty range (no records)
    Doesn't parse PDF content; success is generation without exception +
    non-empty file.
    """
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord, Employee
    from report import PDFReport

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPaths: list[str] = []
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        # Two employees so the all-employees aggregate has multiple rows.
        ids = []
        for idNum, last, first in [(201, "Smith", "Alice"),
                                   (202, "Jones", "Bob")]:
            emp = Employee()
            emp.idNum = idNum
            emp.lastName = last
            emp.firstName = first
            emp.shift = 1
            emp.fullTime = True
            emp.status = True
            emp.anniversary = datetime_date(2020, 1, 1)
            w.db.employees[emp.idNum] = emp
            ids.append(idNum)

        d = datetime_date(2026, 4, 15)
        # Spans multiple actions / targets / shifts per employee so the
        # per-target detail and the cross-action overview both have data.
        # Tool Change records exercise the rate-suppressed path; the second
        # employee's missing Batching action exercises the case where an
        # employee's per-action breakdown is sparse.
        records = [
            (ids[0], d, 1, "Batching",   "MixA",  7.5,  0, 1.5),
            (ids[0], d, 1, "Pressing",   "PartA", 250., 3, 8.0),
            (ids[0], d, 2, "Finishing",  "PartB", 125.5, 0, 6.5),
            (ids[0], d, 1, "Tool Change", "",     0,    0, 4.0),
            (ids[1], d, 2, "Pressing",   "PartA", 180., 1, 6.0),
            (ids[1], d, 2, "Finishing",  "PartA", 200., 2, 7.0),
            (ids[1], d, 3, "Tool Change", "",     0,    0, 2.0),
        ]
        for spec in records:
            r = ProductionRecord()
            r.setRecord(*spec)
            w.db.production[r.key()] = r

        start = datetime_date(2026, 4, 1)
        end = datetime_date(2026, 4, 30)
        emptyStart = datetime_date(2030, 1, 1)
        emptyEnd = datetime_date(2030, 1, 31)
        e0 = ids[0]

        reports = [
            ("emp-prod-specific-action-specific-emp",
             lambda p: p.productionEmployeeProductivityReport("Pressing", e0, start, end)),
            ("emp-prod-specific-action-all-emps",
             lambda p: p.productionEmployeeProductivityReport("Pressing", None, start, end)),
            ("emp-prod-all-actions-specific-emp",
             lambda p: p.productionEmployeeProductivityReport(None, e0, start, end)),
            ("emp-prod-all-actions-all-emps",
             lambda p: p.productionEmployeeProductivityReport(None, None, start, end)),
            ("emp-prod-toolchange-specific-emp",
             lambda p: p.productionEmployeeProductivityReport("Tool Change", e0, start, end)),
            ("emp-prod-toolchange-all-emps",
             lambda p: p.productionEmployeeProductivityReport("Tool Change", None, start, end)),
            ("emp-prod-empty-range",
             lambda p: p.productionEmployeeProductivityReport(None, None, emptyStart, emptyEnd)),
        ]
        for name, fn in reports:
            tmpPdf = tempfile.NamedTemporaryFile(suffix=f"-{name}.pdf", delete=False)
            tmpPdf.close()
            pdfPaths.append(tmpPdf.name)
            try:
                pdf = PDFReport(w.db, tmpPdf.name)
                fn(pdf)
            except Exception as e:
                errors.append(f"report {name} raised: {e!r}")
                continue
            if not os.path.exists(tmpPdf.name) or os.path.getsize(tmpPdf.name) == 0:
                errors.append(f"report {name} produced empty/missing file")
    finally:
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        for p in pdfPaths:
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors


def production_trend_report() -> list[str]:
    """Step 19: trend report covers all four layout cases + Tool Change + both
    rolling modes, and rejects ranges shorter than 30 days.

    Seeds two employees across two shifts with ~90 days of production so the
    30-day rolling window always has data to chew on. Exercises the trend
    report in the four shape combinations, plus Tool Change's two variants,
    plus a run with TREND_MODE flipped to "meanOfRates". Finally confirms a
    sub-30-day range raises RuntimeError and an all-empty range still produces
    a valid PDF ("No production recorded").
    """
    # Step 33 split: TREND_MODE lives in `report.production`, not `report`
    # itself, so the mode-swap below has to mutate the submodule binding.
    import report.production as R
    from PySide6.QtWidgets import QApplication
    from app import MainWindow
    from records import ProductionRecord, Employee
    from report import PDFReport

    errors = []
    app = QApplication.instance() or QApplication(sys.argv)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    pdfPaths: list[str] = []
    savedMode = R.TREND_MODE
    w = None
    try:
        w = MainWindow()
        if not w.fileManager.setFile(tmp.name):
            errors.append("setFile returned False on fresh empty DB")
            return errors

        for idNum, first, shift in [(101, "Alice", 1), (102, "Bob", 2)]:
            emp = Employee()
            emp.idNum = idNum
            emp.lastName = "Smith" if idNum == 101 else "Jones"
            emp.firstName = first
            emp.shift = shift
            emp.fullTime = True
            emp.status = True
            emp.anniversary = datetime_date(2020, 1, 1)
            w.db.employees[emp.idNum] = emp

        base = datetime_date(2026, 1, 1)
        import random
        import datetime as _dt
        rnd = random.Random(42)
        for day in range(90):
            d = base + _dt.timedelta(days=day)
            for eid, shift in [(101, 1), (102, 2)]:
                for target in ("PartA", "PartB"):
                    r = ProductionRecord()
                    r.setRecord(eid, d, shift, "Pressing", target,
                                100.0 + rnd.random() * 50.0, 0, 2.0)
                    w.db.production[r.key()] = r
                r = ProductionRecord()
                r.setRecord(eid, d, shift, "Tool Change", "", 1.0, 0, 0.3)
                w.db.production[r.key()] = r

        start = datetime_date(2026, 1, 1)
        end = datetime_date(2026, 3, 31)
        shortStart = datetime_date(2026, 1, 1)
        shortEnd = datetime_date(2026, 1, 15)  # 15 days — must reject
        emptyStart = datetime_date(2030, 1, 1)
        emptyEnd = datetime_date(2030, 3, 1)  # 60 days of nothing

        reports = [
            ("trend-specific-specific",
             lambda p: p.productionTrendReport("Pressing", "PartA", 1, start, end)),
            ("trend-specific-allshifts",
             lambda p: p.productionTrendReport("Pressing", "PartA", None, start, end)),
            ("trend-alltargets-specific",
             lambda p: p.productionTrendReport("Pressing", None, 1, start, end)),
            ("trend-alltargets-allshifts",
             lambda p: p.productionTrendReport("Pressing", None, None, start, end)),
            ("trend-toolchange-specific",
             lambda p: p.productionTrendReport("Tool Change", None, 1, start, end)),
            ("trend-toolchange-allshifts",
             lambda p: p.productionTrendReport("Tool Change", None, None, start, end)),
            ("trend-empty",
             lambda p: p.productionTrendReport("Pressing", None, None, emptyStart, emptyEnd)),
        ]
        for name, fn in reports:
            tmpPdf = tempfile.NamedTemporaryFile(suffix=f"-{name}.pdf", delete=False)
            tmpPdf.close()
            pdfPaths.append(tmpPdf.name)
            try:
                pdf = PDFReport(w.db, tmpPdf.name)
                fn(pdf)
            except Exception as e:
                errors.append(f"report {name} raised: {e!r}")
                continue
            if not os.path.exists(tmpPdf.name) or os.path.getsize(tmpPdf.name) == 0:
                errors.append(f"report {name} produced empty/missing file")

        # Flip the rolling-average mode and re-run the richest layout to make
        # sure meanOfRates path doesn't crash either.
        R.TREND_MODE = "meanOfRates"
        tmpPdf = tempfile.NamedTemporaryFile(suffix="-trend-meanofrates.pdf", delete=False)
        tmpPdf.close()
        pdfPaths.append(tmpPdf.name)
        try:
            pdf = PDFReport(w.db, tmpPdf.name)
            pdf.productionTrendReport("Pressing", None, None, start, end)
        except Exception as e:
            errors.append(f"meanOfRates mode raised: {e!r}")
        else:
            if os.path.getsize(tmpPdf.name) == 0:
                errors.append("meanOfRates mode produced empty file")
        R.TREND_MODE = savedMode

        # Sub-30-day range must be rejected by the report itself (belt and
        # suspenders — the UI also blocks it).
        tmpPdf = tempfile.NamedTemporaryFile(suffix="-trend-short.pdf", delete=False)
        tmpPdf.close()
        pdfPaths.append(tmpPdf.name)
        pdf = PDFReport(w.db, tmpPdf.name)
        raised = False
        try:
            pdf.productionTrendReport("Pressing", None, None, shortStart, shortEnd)
        except RuntimeError:
            raised = True
        if not raised:
            errors.append("sub-30-day range did not raise RuntimeError")

        # Unknown action must also raise.
        tmpPdf = tempfile.NamedTemporaryFile(suffix="-trend-bogus.pdf", delete=False)
        tmpPdf.close()
        pdfPaths.append(tmpPdf.name)
        pdf = PDFReport(w.db, tmpPdf.name)
        raised = False
        try:
            pdf.productionTrendReport("NotARealAction", None, None, start, end)
        except RuntimeError:
            raised = True
        if not raised:
            errors.append("unknown action did not raise RuntimeError")
    finally:
        R.TREND_MODE = savedMode
        if w is not None and w.fileManager.dbFile is not None:
            w.fileManager.dbFile.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(tmp.name + suffix)
            except OSError:
                pass
        for p in pdfPaths:
            try:
                os.unlink(p)
            except OSError:
                pass
    return errors
