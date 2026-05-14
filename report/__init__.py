# PDFReport composed from per-domain mixins (Step 33). External imports —
# `from report import PDFReport` — keep working unchanged because the class
# is exported here.
#
# Eventual goal (Matthew, 2026-05-13): split production.py further so each
# report lives in its own file once the team has finalized the layouts.
# Tracked in MERGE_PLAN.md §13.21.

from .core import PDFReportCore
from .products import ProductReportsMixin
from .employees import EmployeeReportsMixin
from .production import ProductionReportsMixin


class PDFReport(
    ProductReportsMixin,
    EmployeeReportsMixin,
    ProductionReportsMixin,
    PDFReportCore,
):
    pass


__all__ = ["PDFReport"]
