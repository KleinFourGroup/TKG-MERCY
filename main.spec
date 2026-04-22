# -*- mode: python ; coding: utf-8 -*-

import subprocess


def _build_version() -> str:
    # Mirrors version.py's _gitDescribe: tag + commits-since + dirty marker,
    # leading "v" stripped. Runs at spec-evaluation time so the result is
    # available both for the _version.py we bake in and for the exe filename.
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, check=True, timeout=5,
        )
    except Exception:
        return "dev-unknown"
    tag = out.stdout.strip()
    if not tag:
        return "dev-unknown"
    return tag[1:] if tag.startswith("v") else tag


VERSION = _build_version()

# Write the fallback module that version.py imports inside the frozen exe
# (PyInstaller strips .git, so the runtime git-describe path isn't available).
with open("_version.py", "w", encoding="utf-8") as f:
    f.write(
        "# Auto-generated at PyInstaller build time. Do not edit.\n"
        f'VERSION = "{VERSION}"\n'
    )


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ceramics_icon.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'mercy-{VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ceramics_icon.ico'],
)
