"""Run as ``./Scripts/python.exe -m smoke`` — the always-run dispatcher.

Runs every check in ``smoke.CHECKS`` in order and prints PASS/FAIL per
check; exit code 1 if any failed. The list itself lives in
``smoke/__init__.py`` (Step 85) so a check is registered in exactly one
place, and ``docs_single_source`` asserts its length matches the smoke
baseline quoted in HANDOFF.md's Cursor.

Step-specific verification still belongs in throwaway ``-c '...'`` scripts,
or in a new check function under one of the smoke/ submodules if broadly
useful.
"""
import sys

from smoke import CHECKS


def main() -> int:
    failed = False
    for name, fn in CHECKS:
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
