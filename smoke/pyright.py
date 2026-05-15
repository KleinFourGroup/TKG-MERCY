"""Pyright baseline check. Runs ``pyright --outputjson`` as a subprocess
and parses the JSON output for any ``severity == "error"`` diagnostic.
The Step 36g closing move — keeps the 0-error baseline from silently
slipping as the codebase evolves. Slow (~5-15s) by smoke standards but
the only static-typing regression net we have."""
import json
import os
import subprocess
import sys


def pyright_baseline() -> list[str]:
    """Run pyright on the repo and return any errors as readable
    ``relpath:line [rule] message`` strings.

    Non-zero exit code is expected when errors are present and is NOT
    itself a failure of this check — only parsed errors count. Returns
    a stderr-bearing error string if pyright itself failed to run
    (not installed, timed out, produced non-JSON output)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyright", "--outputjson"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return ["pyright not found; install via `pip install -r requirements.txt`"]
    except subprocess.TimeoutExpired:
        return ["pyright timed out after 120s"]

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return [
            f"pyright did not produce JSON output: {e}",
            f"stdout (first 500 chars): {result.stdout[:500]!r}",
            f"stderr (first 500 chars): {result.stderr[:500]!r}",
        ]

    errors = []
    root = os.getcwd()
    for d in data.get("generalDiagnostics", []):
        if d.get("severity") != "error":
            continue
        path = d.get("file", "?")
        try:
            path = os.path.relpath(path, root)
        except ValueError:
            pass  # different drive on Windows — keep absolute
        line = d.get("range", {}).get("start", {}).get("line", -1) + 1
        rule = d.get("rule", "?")
        msg = d.get("message", "").split("\n", 1)[0]
        errors.append(f"{path}:{line} [{rule}] {msg}")
    return errors
