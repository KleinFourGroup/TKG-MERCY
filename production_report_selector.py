from PySide6.QtWidgets import QWidget, QLabel, QComboBox

from app import MainWindow
from defaults import PRODUCTION_ACTIONS, PRODUCTION_ACTION_TARGET
from utils import widgetFromList


def _employeeLabel(emp):
    return f"{emp.lastName.upper()} {emp.firstName} ({emp.idNum})"


class ProductionReportSelector(QWidget):
    # Five-combo selector cluster used by ProductionReportWindow across all
    # seven report modes (Production Summary, Per Action, Per Target,
    # Per Employee, Productivity, Employee Productivity, Trend). Owns the
    # action / targetType / targetName / shift / employee combos plus the
    # visibility, rebuild-on-mode-change, and default-selection logic that
    # used to live inline on the report window.
    #
    # Lifecycle: parent constructs once, calls setMode(reportType) on every
    # report-type change, then reads resolved values via the getter
    # properties at click time inside generate().

    def __init__(self, mainApp: MainWindow,
                 initialEmployeeId: int | None = None):
        super().__init__()
        self.mainApp = mainApp
        self._currentMode: str | None = None

        self.actionBox = QComboBox()
        self.actionBox.setEditable(False)
        self.actionBox.currentTextChanged.connect(self._onActionChanged)
        self._rebuildActionBox(includeAll=False)

        self.targetTypeBox = QComboBox()
        self.targetTypeBox.setEditable(False)
        self.targetTypeBox.addItem("Mixture", userData="mix")
        self.targetTypeBox.addItem("Part", userData="part")
        self.targetTypeBox.currentIndexChanged.connect(self._onTargetTypeChanged)

        self.targetNameBox = QComboBox()
        self.targetNameBox.setEditable(False)

        # "All shifts" maps to None so generate()'s dispatch can branch
        # without sentinel strings.
        self.shiftBox = QComboBox()
        self.shiftBox.setEditable(False)
        self.shiftBox.addItem("All shifts", userData=None)
        self.shiftBox.addItem("1", userData=1)
        self.shiftBox.addItem("2", userData=2)
        self.shiftBox.addItem("3", userData=3)

        self.employeeBox = QComboBox()
        self.employeeBox.setEditable(False)
        self._rebuildEmployeeBox(includeAll=False)
        if initialEmployeeId is not None:
            for i in range(self.employeeBox.count()):
                if self.employeeBox.itemData(i) == initialEmployeeId:
                    self.employeeBox.setCurrentIndex(i)
                    break

        self.actionLabel = QLabel("Action:")
        self.targetTypeLabel = QLabel("Target type:")
        self.targetNameLabel = QLabel("Target:")
        self.shiftLabel = QLabel("Shift:")
        self.employeeLabel = QLabel("Employee:")

        widgetFromList(self, [
            [self.actionLabel, self.actionBox],
            [self.targetTypeLabel, self.targetTypeBox],
            [self.targetNameLabel, self.targetNameBox],
            [self.shiftLabel, self.shiftBox],
            [self.employeeLabel, self.employeeBox],
        ])

        # Seed Per Target's initial target-name list (Mixture is index 0).
        self._onTargetTypeChanged(self.targetTypeBox.currentIndex())

    # ---- public API ---------------------------------------------------------

    def setMode(self, reportType: str):
        # Apply visibility, rebuild combos, set initial defaults for the
        # given report mode. Called by the parent dialog on every
        # report-type-combo change.
        self._currentMode = reportType
        isProdLike = (reportType == "Productivity") or (reportType == "Trend")
        isEmpProd = (reportType == "Employee Productivity")
        showAction = (reportType == "Per Action") or isProdLike or isEmpProd
        showTargetType = (reportType == "Per Target")
        showTargetName = (reportType == "Per Target") or isProdLike
        showEmployee = (reportType == "Per Employee") or isEmpProd
        showShift = isProdLike
        for w in (self.actionLabel, self.actionBox):
            w.setVisible(showAction)
        for w in (self.targetTypeLabel, self.targetTypeBox):
            w.setVisible(showTargetType)
        for w in (self.targetNameLabel, self.targetNameBox):
            w.setVisible(showTargetName)
        for w in (self.shiftLabel, self.shiftBox):
            w.setVisible(showShift)
        for w in (self.employeeLabel, self.employeeBox):
            w.setVisible(showEmployee)
        # Action + employee boxes carry an extra "All" entry only for
        # Employee Productivity. Rebuild on every mode switch so the other
        # modes (which require a specific selection) can't see it.
        self._rebuildActionBox(includeAll=isEmpProd)
        self._rebuildEmployeeBox(includeAll=isEmpProd)
        # Repopulate targetNameBox for the mode we're entering — each mode
        # fills it differently (Per Target plain names; Productivity / Trend
        # add "All" and follow the action).
        if isProdLike:
            self._rebuildProductivityTargets()
            self._applyProductivityVisibility()
        elif reportType == "Per Target":
            self._onTargetTypeChanged(self.targetTypeBox.currentIndex())

    # ---- resolved-value properties -----------------------------------------

    @property
    def action(self) -> str | None:
        # currentData() of the action combo: a specific action string, or
        # None for the "All actions" sentinel (only present in Employee
        # Productivity mode).
        return self.actionBox.currentData()

    @property
    def actionText(self) -> str:
        # currentText() of the action combo. Returns the literal "All actions"
        # in Employee Productivity mode when the sentinel entry is selected;
        # used by the parent's _defaultPrefix to slug the filename.
        return self.actionBox.currentText()

    @property
    def targetType(self) -> str | None:
        # currentData() of the targetType combo: "mix" or "part". Only the
        # Per Target mode reads this — productivity-like modes derive the
        # target type from the selected action via PRODUCTION_ACTION_TARGET.
        return self.targetTypeBox.currentData()

    @property
    def targetName(self) -> str | None:
        # Mode-dependent read-out so the parent doesn't have to branch:
        #   Per Target          -> currentText() (always a specific name).
        #   Productivity/Trend  -> currentData() (None for the "All" entry).
        #   Tool Change action  -> None regardless of combo state (the row
        #                          is hidden in that case).
        if self._currentMode in ("Productivity", "Trend"):
            if self.actionText == "Tool Change":
                return None
            return self.targetNameBox.currentData()
        return self.targetNameBox.currentText()

    @property
    def targetNameText(self) -> str:
        # currentText() of the target combo, unconditional. Used by the
        # parent's _defaultPrefix for slugging.
        return self.targetNameBox.currentText()

    @property
    def shift(self) -> int | None:
        return self.shiftBox.currentData()

    @property
    def employeeId(self) -> int | None:
        return self.employeeBox.currentData()

    # ---- internal: combo rebuild + change handlers --------------------------

    def _onActionChanged(self, _text: str):
        if self._currentMode in ("Productivity", "Trend"):
            self._rebuildProductivityTargets()
            self._applyProductivityVisibility()

    def _onTargetTypeChanged(self, _idx: int):
        # Only the "Per Target" report uses the explicit targetType selector;
        # in Productivity / Trend modes the target list is driven by the
        # action instead (see _rebuildProductivityTargets).
        if self._currentMode in ("Productivity", "Trend"):
            return
        targetType = self.targetTypeBox.currentData()
        self.targetNameBox.clear()
        if targetType == "mix":
            self.targetNameBox.addItems(sorted(self.mainApp.db.mixtures.keys()))
        elif targetType == "part":
            self.targetNameBox.addItems(sorted(self.mainApp.db.parts.keys()))

    def _rebuildProductivityTargets(self):
        # Populates targetNameBox with an "All" entry + every mix/part of the
        # action's target type. Tool Change is targetless and clears the box.
        # Shared between the Productivity and Trend reports — the selector
        # shape is identical.
        action = self.actionBox.currentText()
        targetType = PRODUCTION_ACTION_TARGET.get(action, "")
        self.targetNameBox.clear()
        if targetType == "":
            return
        self.targetNameBox.addItem("All", userData=None)
        if targetType == "mix":
            names = sorted(self.mainApp.db.mixtures.keys())
        else:
            names = sorted(self.mainApp.db.parts.keys())
        for n in names:
            self.targetNameBox.addItem(n, userData=n)

    def _applyProductivityVisibility(self):
        # Tool Change has no target, so hide the target row when that action
        # is selected even in Productivity / Trend mode.
        action = self.actionBox.currentText()
        hasTarget = PRODUCTION_ACTION_TARGET.get(action, "") != ""
        for w in (self.targetNameLabel, self.targetNameBox):
            w.setVisible(hasTarget)

    def _rebuildActionBox(self, includeAll: bool):
        # The "All actions" entry is only meaningful for the Step 24 Employee
        # Productivity report; other modes (Per Action, Productivity, Trend)
        # require a specific action. Rebuild on every type change so a stale
        # "All actions" selection can't leak into a mode that doesn't accept
        # it. In Employee-Productivity (includeAll=True) we default to the
        # "All" entry rather than restoring the prior specific action — the
        # broader report is what users want first; specific action is one
        # click away. In other modes we restore the prior selection so
        # re-entering the mode lands you back where you were.
        self.actionBox.blockSignals(True)
        if includeAll:
            self.actionBox.clear()
            self.actionBox.addItem("All actions", userData=None)
            for a in PRODUCTION_ACTIONS:
                self.actionBox.addItem(a, userData=a)
            self.actionBox.setCurrentIndex(0)
        else:
            prev = self.actionBox.currentData()
            self.actionBox.clear()
            for a in PRODUCTION_ACTIONS:
                self.actionBox.addItem(a, userData=a)
            for i in range(self.actionBox.count()):
                if self.actionBox.itemData(i) == prev:
                    self.actionBox.setCurrentIndex(i)
                    break
        self.actionBox.blockSignals(False)

    def _rebuildEmployeeBox(self, includeAll: bool):
        # Mirror of _rebuildActionBox: the "All employees" entry is only
        # valid in Employee Productivity mode. Per Employee requires a
        # specific id. Same default-to-All-on-entry / restore-prev-otherwise
        # rationale.
        self.employeeBox.blockSignals(True)
        emps = list(self.mainApp.db.employees.values())
        emps.sort(key=lambda e: (0 if e.status else 1,
                                 (e.lastName or "").lower(),
                                 (e.firstName or "").lower()))
        if includeAll:
            self.employeeBox.clear()
            self.employeeBox.addItem("All employees", userData=None)
            for emp in emps:
                suffix = "" if emp.status else " [inactive]"
                self.employeeBox.addItem(_employeeLabel(emp) + suffix,
                                         userData=emp.idNum)
            self.employeeBox.setCurrentIndex(0)
        else:
            prev = self.employeeBox.currentData()
            self.employeeBox.clear()
            for emp in emps:
                suffix = "" if emp.status else " [inactive]"
                self.employeeBox.addItem(_employeeLabel(emp) + suffix,
                                         userData=emp.idNum)
            for i in range(self.employeeBox.count()):
                if self.employeeBox.itemData(i) == prev:
                    self.employeeBox.setCurrentIndex(i)
                    break
        self.employeeBox.blockSignals(False)
