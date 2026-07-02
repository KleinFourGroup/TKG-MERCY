"""Run as ``./Scripts/python.exe -m smoke``.

Two baseline checks that MERGE_PLAN steps rely on:

  1. ``compile_all`` -- every .py at the repo root compiles (catches syntax
     errors from scripted rewrites like 7c-1 / 7c-2 / 7c-3).
  2. ``empty_roundtrip`` -- build ``MainWindow()`` offscreen, save the
     empty DB to a tmp path, reload into a fresh ``MainWindow``, confirm
     no exceptions and the container collections are present and empty.

Step-specific verification still belongs in throwaway ``-c '...'`` scripts
or a new check function under one of the smoke/ submodules if broadly
useful. This file is the always-run dispatcher.
"""
import sys

from smoke import (
    compile_all, empty_roundtrip,
    legacy_anika_migration, legacy_becky_migration, legacy_merge,
    mercy_v3_to_v4_migration, mercy_v4_to_v5_migration, mercy_v5_to_v6_migration,
    mercy_v6_to_v7_migration, mercy_v7_to_v8_migration, mercy_v8_to_v9_migration,
    mercy_v9_to_v10_migration, mercy_v10_to_v11_migration,
    mercy_v11_to_v12_migration,
    mercy_v4_to_v12_end_to_end, scheduling_save_rollback,
    production_roundtrip, production_tool_change_roundtrip,
    production_report, production_productivity_report,
    production_employee_productivity_report, production_trend_report,
    product_employee_reports, schedule_report,
    production_refresh_on_delete, inventory_edit_missing_date, production_batch_roundtrip,
    production_quantity_validation,
    qsettings_reopen, close_confirm,
    parts_tab_crud, employees_tab_crud, presses_tab_crud, pressers_tab_crud,
    shift_workweek_roundtrip, part_press_pref_crud, presser_press_pref_crud,
    clients_tab_crud, orders_tab_crud,
    order_status_crud, schedule_tab_generates,
    employee_detail_populates, reviews_dialog_roundtrip,
    training_dialog_roundtrip, points_dialog_roundtrip,
    pto_dialog_roundtrip, notes_dialog_roundtrip,
    employee_delete_cascades_detail_tabs, employee_reid_cascades,
    holidays_tab_observances, holidays_tab_defaults_crud,
    scheduling_working_days, scheduling_presser_capacity,
    scheduling_pressing_rate, scheduling_scrap_inflation,
    scheduling_deadlines, scheduling_primitives_fuzz,
    scheduling_scheduler, scheduling_scheduler_fuzz,
    scheduling_view_slice,
    pyright_baseline,
    crash_fuzz,
)


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration),
                     ("legacy_becky_migration", legacy_becky_migration),
                     ("legacy_merge", legacy_merge),
                     ("mercy_v3_to_v4_migration", mercy_v3_to_v4_migration),
                     ("mercy_v4_to_v5_migration", mercy_v4_to_v5_migration),
                     ("mercy_v5_to_v6_migration", mercy_v5_to_v6_migration),
                     ("mercy_v6_to_v7_migration", mercy_v6_to_v7_migration),
                     ("mercy_v7_to_v8_migration", mercy_v7_to_v8_migration),
                     ("mercy_v8_to_v9_migration", mercy_v8_to_v9_migration),
                     ("mercy_v9_to_v10_migration", mercy_v9_to_v10_migration),
                     ("mercy_v10_to_v11_migration", mercy_v10_to_v11_migration),
                     ("mercy_v11_to_v12_migration", mercy_v11_to_v12_migration),
                     ("mercy_v4_to_v12_end_to_end", mercy_v4_to_v12_end_to_end),
                     ("scheduling_save_rollback", scheduling_save_rollback),
                     ("production_roundtrip", production_roundtrip),
                     ("production_tool_change_roundtrip", production_tool_change_roundtrip),
                     ("production_report", production_report),
                     ("production_productivity_report", production_productivity_report),
                     ("production_employee_productivity_report", production_employee_productivity_report),
                     ("production_trend_report", production_trend_report),
                     ("product_employee_reports", product_employee_reports),
                     ("schedule_report", schedule_report),
                     ("production_refresh_on_delete", production_refresh_on_delete),
                     ("inventory_edit_missing_date", inventory_edit_missing_date),
                     ("production_batch_roundtrip", production_batch_roundtrip),
                     ("production_quantity_validation", production_quantity_validation),
                     ("qsettings_reopen", qsettings_reopen),
                     ("close_confirm", close_confirm),
                     ("parts_tab_crud", parts_tab_crud),
                     ("employees_tab_crud", employees_tab_crud),
                     ("presses_tab_crud", presses_tab_crud),
                     ("pressers_tab_crud", pressers_tab_crud),
                     ("shift_workweek_roundtrip", shift_workweek_roundtrip),
                     ("part_press_pref_crud", part_press_pref_crud),
                     ("presser_press_pref_crud", presser_press_pref_crud),
                     ("clients_tab_crud", clients_tab_crud),
                     ("orders_tab_crud", orders_tab_crud),
                     ("order_status_crud", order_status_crud),
                     ("schedule_tab_generates", schedule_tab_generates),
                     ("employee_detail_populates", employee_detail_populates),
                     ("reviews_dialog_roundtrip", reviews_dialog_roundtrip),
                     ("training_dialog_roundtrip", training_dialog_roundtrip),
                     ("points_dialog_roundtrip", points_dialog_roundtrip),
                     ("pto_dialog_roundtrip", pto_dialog_roundtrip),
                     ("notes_dialog_roundtrip", notes_dialog_roundtrip),
                     ("employee_delete_cascades_detail_tabs", employee_delete_cascades_detail_tabs),
                     ("employee_reid_cascades", employee_reid_cascades),
                     ("holidays_tab_observances", holidays_tab_observances),
                     ("holidays_tab_defaults_crud", holidays_tab_defaults_crud),
                     ("scheduling_working_days", scheduling_working_days),
                     ("scheduling_presser_capacity", scheduling_presser_capacity),
                     ("scheduling_pressing_rate", scheduling_pressing_rate),
                     ("scheduling_scrap_inflation", scheduling_scrap_inflation),
                     ("scheduling_deadlines", scheduling_deadlines),
                     ("scheduling_primitives_fuzz", scheduling_primitives_fuzz),
                     ("scheduling_scheduler", scheduling_scheduler),
                     ("scheduling_scheduler_fuzz", scheduling_scheduler_fuzz),
                     ("scheduling_view_slice", scheduling_view_slice),
                     ("pyright_baseline", pyright_baseline),
                     ("crash_fuzz", crash_fuzz)]:
        errors = fn()
        if errors:
            failed = True
            print(f"FAIL {name}")
            for e in errors:
                print(f"  {e}")
        else:
            print(f"PASS {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
