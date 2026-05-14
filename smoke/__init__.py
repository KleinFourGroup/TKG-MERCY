"""smoke/ — repo-wide regression checks. Importing this package sets the
QT_QPA_PLATFORM=offscreen environment variable so check functions that
construct Qt widgets work without a display.

Run the full battery via ``./Scripts/python.exe -m smoke``. Individual
check functions can also be imported and called directly."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from smoke.records import (
    compile_all, empty_roundtrip,
    production_roundtrip, production_tool_change_roundtrip,
    production_quantity_validation,
)
from smoke.migrations import (
    legacy_anika_migration, legacy_becky_migration, legacy_merge,
    mercy_v3_to_v4_migration,
)
from smoke.reports import (
    production_report, production_productivity_report,
    production_employee_productivity_report, production_trend_report,
    product_employee_reports,
)
from smoke.ui import (
    production_refresh_on_delete, production_batch_roundtrip,
    qsettings_reopen, close_confirm,
)

__all__ = [
    "compile_all", "empty_roundtrip",
    "production_roundtrip", "production_tool_change_roundtrip",
    "production_quantity_validation",
    "legacy_anika_migration", "legacy_becky_migration", "legacy_merge",
    "mercy_v3_to_v4_migration",
    "production_report", "production_productivity_report",
    "production_employee_productivity_report", "production_trend_report",
    "product_employee_reports",
    "production_refresh_on_delete", "production_batch_roundtrip",
    "qsettings_reopen", "close_confirm",
]
