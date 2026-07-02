"""Central home for MERCY's app-wide Qt styling.

Historically MERCY shipped with pure native Qt styling and no stylesheet at all.
The team (MERGE_PLAN.md Step 63) asked for a stronger, higher-contrast *selected*
tab / sub-tab so the ribbon of (sub)tabs is easy to read at a glance. This module
owns that in one spot and applies it globally, so re-colouring it later is a
one-line change rather than a hunt through widget code.

Mode-aware: only the *selected* tab is a fixed accent (a filled blue that reads
well on both light and dark backgrounds). Every other tab colour — the unselected
face, its text, the hover tint, and the borders — is drawn from the active Qt
palette via `palette(...)`, so the tab bar follows the system light/dark theme the
same way the rest of the native widgets do. (Nothing here forces a colour scheme;
it just stops hardcoding one, which is what made the tabs stand out in dark mode.)

This is deliberately *not* a full theme — it touches only the tab bar / pane so the
rest of the app keeps its native look. Applied on the QApplication in `main.py`,
so every QTabWidget (the main tabs and all nested sub-tabs) picks it up uniformly.
"""

from PySide6.QtWidgets import QApplication

# --- Selected-tab accent -----------------------------------------------------
# The one fixed colour: a filled blue for the current tab, with bold white text.
# Blue-on-white reads clearly whether the surrounding app is light or dark, so the
# selected state is intentionally mode-independent. Change SELECTED_TAB_BG (and its
# border) here to recolour it; everything else adapts to the palette on its own.
SELECTED_TAB_BG = "#1a6dd8"
SELECTED_TAB_BORDER = "#1559b0"
SELECTED_TAB_TEXT = "#ffffff"

# --- Tab stylesheet ----------------------------------------------------------
# Once QTabBar::tab is styled at all, Qt drops its native tab rendering, so the
# unselected / hover / pane states are spelled out too or the result looks broken.
# The unselected / hover / border colours use palette(...) roles (button,
# button-text, midlight, mid) so they track light vs dark mode; only the selected
# tab is a fixed accent. The selected tab also gets a slight height bump (unselected
# tabs are nudged down via margin-top) so the current tab pops at every nesting level.
TAB_STYLE_SHEET = f"""
QTabWidget::pane {{
    border: 1px solid palette(mid);
    top: -1px;
}}
QTabBar::tab {{
    background: palette(button);
    color: palette(button-text);
    border: 1px solid palette(mid);
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:hover:!selected {{
    background: palette(midlight);
}}
QTabBar::tab:selected {{
    background: {SELECTED_TAB_BG};
    color: {SELECTED_TAB_TEXT};
    border-color: {SELECTED_TAB_BORDER};
    font-weight: bold;
}}
QTabBar::tab:!selected {{
    margin-top: 3px;
}}
"""


def applyStyle(app: QApplication) -> None:
    """Apply MERCY's app-wide stylesheet to `app` (the QApplication)."""
    app.setStyleSheet(TAB_STYLE_SHEET)
