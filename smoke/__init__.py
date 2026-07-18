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
    production_quantity_validation, mixture_full_loi_material,
)
from smoke.migrations import (
    legacy_anika_migration, legacy_becky_migration, legacy_merge,
    mercy_v3_to_v4_migration, mercy_v4_to_v5_migration, mercy_v5_to_v6_migration,
    mercy_v6_to_v7_migration, mercy_v7_to_v8_migration, mercy_v8_to_v9_migration,
    mercy_v9_to_v10_migration, mercy_v10_to_v11_migration,
    mercy_v11_to_v12_migration, mercy_v12_to_v13_migration,
    mercy_v13_to_v14_migration,
    mercy_v4_to_v14_end_to_end, scheduling_save_rollback,
)
from smoke.reports import (
    production_report, production_productivity_report,
    production_employee_productivity_report, production_trend_report,
    product_employee_reports, schedule_report, order_status_report,
)
from smoke.ui import (
    production_refresh_on_delete, inventory_edit_missing_date, production_batch_roundtrip,
    materials_impossible_loi_rejected,
    qsettings_reopen, file_dialog_dir_memory, close_confirm,
    parts_tab_crud, employees_tab_crud, presses_tab_crud, pressers_tab_crud,
    shift_workweek_roundtrip, part_press_pref_crud, presser_press_pref_crud,
    part_truck_crud,
    clients_tab_crud, orders_tab_crud,
    order_status_crud, order_status_trucks_entry, order_report_window_generates,
    schedule_tab_generates,
    employee_detail_populates, reviews_dialog_roundtrip,
    training_dialog_roundtrip, points_dialog_roundtrip,
    pto_dialog_roundtrip, notes_dialog_roundtrip,
    employee_delete_cascades_detail_tabs, employee_reid_cascades,
    fk_rename_refreshes_dependent_tabs, edit_refresh_preserves_picker_selection,
    inventory_edit_refreshes_value_labels,
    holidays_tab_observances, holidays_tab_defaults_crud,
)
from smoke.scheduling import (
    scheduling_working_days, scheduling_presser_capacity,
    scheduling_pressing_rate, scheduling_scrap_inflation,
    scheduling_deadlines, scheduling_primitives_fuzz,
    scheduling_scheduler, scheduling_scheduler_fuzz,
    scheduling_view_slice,
)
from smoke.pyright import pyright_baseline
from smoke.ui_fuzz import crash_fuzz

__all__ = [
    "compile_all", "empty_roundtrip",
    "production_roundtrip", "production_tool_change_roundtrip",
    "production_quantity_validation", "mixture_full_loi_material",
    "legacy_anika_migration", "legacy_becky_migration", "legacy_merge",
    "mercy_v3_to_v4_migration", "mercy_v4_to_v5_migration", "mercy_v5_to_v6_migration",
    "mercy_v6_to_v7_migration", "mercy_v7_to_v8_migration", "mercy_v8_to_v9_migration",
    "mercy_v9_to_v10_migration", "mercy_v10_to_v11_migration",
    "mercy_v11_to_v12_migration", "mercy_v12_to_v13_migration",
    "mercy_v13_to_v14_migration",
    "mercy_v4_to_v14_end_to_end", "scheduling_save_rollback",
    "production_report", "production_productivity_report",
    "production_employee_productivity_report", "production_trend_report",
    "product_employee_reports", "schedule_report", "order_status_report",
    "production_refresh_on_delete", "inventory_edit_missing_date", "production_batch_roundtrip",
    "materials_impossible_loi_rejected",
    "qsettings_reopen", "file_dialog_dir_memory", "close_confirm",
    "parts_tab_crud", "employees_tab_crud", "presses_tab_crud", "pressers_tab_crud",
    "shift_workweek_roundtrip", "part_press_pref_crud", "presser_press_pref_crud",
    "part_truck_crud",
    "clients_tab_crud", "orders_tab_crud",
    "order_status_crud", "order_status_trucks_entry", "order_report_window_generates",
    "schedule_tab_generates",
    "employee_detail_populates", "reviews_dialog_roundtrip",
    "training_dialog_roundtrip", "points_dialog_roundtrip",
    "pto_dialog_roundtrip", "notes_dialog_roundtrip",
    "employee_delete_cascades_detail_tabs", "employee_reid_cascades",
    "fk_rename_refreshes_dependent_tabs", "edit_refresh_preserves_picker_selection",
    "inventory_edit_refreshes_value_labels",
    "holidays_tab_observances", "holidays_tab_defaults_crud",
    "scheduling_working_days", "scheduling_presser_capacity",
    "scheduling_pressing_rate", "scheduling_scrap_inflation",
    "scheduling_deadlines", "scheduling_primitives_fuzz",
    "scheduling_scheduler", "scheduling_scheduler_fuzz",
    "scheduling_view_slice",
    "pyright_baseline",
    "crash_fuzz",
]
