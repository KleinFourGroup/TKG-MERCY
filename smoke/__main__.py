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
    legacy_anika_migration, legacy_becky_migration, legacy_merge, mercy_v3_to_v4_migration,
    production_roundtrip, production_tool_change_roundtrip,
    production_report, production_productivity_report,
    production_employee_productivity_report, production_trend_report,
    product_employee_reports,
    production_refresh_on_delete, production_batch_roundtrip,
    production_quantity_validation,
    qsettings_reopen, close_confirm,
    parts_tab_crud, employees_tab_crud,
    employee_detail_populates, reviews_dialog_roundtrip,
    training_dialog_roundtrip, points_dialog_roundtrip,
    pto_dialog_roundtrip, notes_dialog_roundtrip,
    employee_delete_cascades_detail_tabs,
    holidays_tab_observances, holidays_tab_defaults_crud,
    pyright_baseline,
)


def main() -> int:
    failed = False
    for name, fn in [("compile_all", compile_all),
                     ("empty_roundtrip", empty_roundtrip),
                     ("legacy_anika_migration", legacy_anika_migration),
                     ("legacy_becky_migration", legacy_becky_migration),
                     ("legacy_merge", legacy_merge),
                     ("mercy_v3_to_v4_migration", mercy_v3_to_v4_migration),
                     ("production_roundtrip", production_roundtrip),
                     ("production_tool_change_roundtrip", production_tool_change_roundtrip),
                     ("production_report", production_report),
                     ("production_productivity_report", production_productivity_report),
                     ("production_employee_productivity_report", production_employee_productivity_report),
                     ("production_trend_report", production_trend_report),
                     ("product_employee_reports", product_employee_reports),
                     ("production_refresh_on_delete", production_refresh_on_delete),
                     ("production_batch_roundtrip", production_batch_roundtrip),
                     ("production_quantity_validation", production_quantity_validation),
                     ("qsettings_reopen", qsettings_reopen),
                     ("close_confirm", close_confirm),
                     ("parts_tab_crud", parts_tab_crud),
                     ("employees_tab_crud", employees_tab_crud),
                     ("employee_detail_populates", employee_detail_populates),
                     ("reviews_dialog_roundtrip", reviews_dialog_roundtrip),
                     ("training_dialog_roundtrip", training_dialog_roundtrip),
                     ("points_dialog_roundtrip", points_dialog_roundtrip),
                     ("pto_dialog_roundtrip", pto_dialog_roundtrip),
                     ("notes_dialog_roundtrip", notes_dialog_roundtrip),
                     ("employee_delete_cascades_detail_tabs", employee_delete_cascades_detail_tabs),
                     ("holidays_tab_observances", holidays_tab_observances),
                     ("holidays_tab_defaults_crud", holidays_tab_defaults_crud),
                     ("pyright_baseline", pyright_baseline)]:
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
