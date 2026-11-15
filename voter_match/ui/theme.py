"""Universal High-Contrast Theme and Stylesheet for Electoral Roll Check.

Designed specifically for non-technical Government School Teachers / BLOs in Uttar Pradesh.
Guarantees high contrast, clear Hindi Devanagari typography, explicit text and background colors
to prevent white-on-white rendering bugs, and friendly visual status cues.
"""

from PySide6.QtCore import Qt

# Color Palette: Deep Navy Authority + High-Contrast Accents
NAVY_PRIMARY = "#1E3A8A"      # Deep Navy Blue (Headers & Primary Action)
NAVY_HOVER = "#1E40AF"
NAVY_LIGHT = "#EFF6FF"        # Soft Ice Blue for active tabs / panels
TEXT_DARK = "#0F172A"         # Crisp Dark Slate for all text
TEXT_MUTED = "#475569"        # Secondary gray text
BORDER_COLOR = "#CBD5E1"      # Clean neutral border

# Semantic Status Colors
GREEN_BG = "#DCFCE7"          # Soft Mint Green
GREEN_TEXT = "#166534"        # Dark Forest Green
GREEN_PRIMARY = "#16A34A"     # Vibrant Green Button
GREEN_HOVER = "#15803D"

AMBER_BG = "#FEF3C7"          # Soft Warning Yellow
AMBER_TEXT = "#92400E"        # Dark Warning Amber
AMBER_PRIMARY = "#D97706"

RED_BG = "#FEE2E2"            # Soft Alert Red
RED_TEXT = "#991B1B"          # Dark Alert Red
RED_PRIMARY = "#DC2626"
RED_HOVER = "#B91C1C"

BLUE_BG = "#DBEAFE"           # Soft Info Blue
BLUE_TEXT = "#1E40AF"

def rgba(hex_color: str, alpha: float) -> str:
    """CSS rgba() from '#RRGGBB'. (Qt reads 8-digit hex as #AARRGGBB, so
    appending an alpha suffix like '#DC262618' produces the wrong colour.)"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


_scope_counter = 0


def scoped_style(widget, css: str, hover_css: str | None = None) -> None:
    """Apply css to this widget ONLY.

    A selector-less stylesheet (or a 'QFrame { }' rule) on a container also
    styles every child QLabel - QLabel is a QFrame subclass - which drew a
    border, padding and background box around every label inside cards.
    Scoping the rule to the widget's own objectName prevents that.
    """
    global _scope_counter
    name = widget.objectName()
    if not name:
        _scope_counter += 1
        name = f"scoped{_scope_counter}"
        widget.setObjectName(name)
    sheet = f"#{name} {{ {css} }}"
    if hover_css:
        sheet += f" #{name}:hover {{ {hover_css} }}"
    widget.setStyleSheet(sheet)


def fit_table_columns(table, max_col_width: int = 280) -> None:
    """Fit columns to content but let the LAST (long text) column take the
    remaining width (elided, full text on hover) instead of forcing a wide
    horizontal scroll. Very wide content columns are capped."""
    from PySide6.QtWidgets import QHeaderView

    hdr = table.horizontalHeader()
    n = table.columnCount()
    if n == 0:
        return
    hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
    table.resizeColumnsToContents()
    for c in range(n - 1):
        hdr.setSectionResizeMode(c, QHeaderView.Interactive)
        if table.columnWidth(c) > max_col_width:
            table.setColumnWidth(c, max_col_width)
    hdr.setSectionResizeMode(n - 1, QHeaderView.Stretch)
    table.setTextElideMode(Qt.ElideRight)
    for r in range(table.rowCount()):
        for c in range(n):
            it = table.item(r, c)
            if it is not None and not it.toolTip() and len(it.text()) > 25:
                it.setToolTip(it.text())


GLOBAL_QSS = f"""
/* Universal Window & Typography */
QWidget {{
    font-family: 'Nirmala UI', 'Mangal', 'Noto Sans Devanagari', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: {TEXT_DARK};
    background-color: #F8FAFC;
}}

/* Labels and check boxes sit on whatever card they are placed in */
QLabel, QCheckBox, QRadioButton {{
    background-color: transparent;
}}

/* Main Containers & Cards */
QMainWindow {{
    background-color: #F1F5F9;
}}

QGroupBox {{
    font-weight: bold;
    font-size: 13px;
    color: {NAVY_PRIMARY};
    background-color: #FFFFFF;
    border: 1px solid {BORDER_COLOR};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    padding-left: 10px;
    padding-right: 10px;
    padding-bottom: 10px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    background-color: #FFFFFF;
    color: {NAVY_PRIMARY};
    border-radius: 4px;
}}

/* Form Controls: Combo Boxes, SpinBoxes, Inputs */
QComboBox {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    border: 1px solid #94A3B8;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 22px;
}}

QComboBox:focus {{
    border: 2px solid {NAVY_PRIMARY};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid #CBD5E1;
}}

QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    selection-background-color: {BLUE_BG};
    selection-color: {NAVY_PRIMARY};
    border: 1px solid #94A3B8;
    padding: 4px;
}}

QLineEdit, QSpinBox {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    border: 1px solid #94A3B8;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 22px;
}}

QLineEdit:focus, QSpinBox:focus {{
    border: 2px solid {NAVY_PRIMARY};
}}

/* Standard Buttons */
QPushButton {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    border: 1px solid #94A3B8;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: #F1F5F9;
    border-color: #64748B;
}}

QPushButton:pressed {{
    background-color: #E2E8F0;
}}

QPushButton:disabled {{
    background-color: #E2E8F0;
    color: #94A3B8;
    border-color: #CBD5E1;
}}

/* Tables and High-Contrast Headers */
QTableWidget, QTableView {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    gridline-color: #E2E8F0;
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    font-size: 12px;
    selection-background-color: {BLUE_BG};
    selection-color: {NAVY_PRIMARY};
    alternate-background-color: #F8FAFC;
}}

QTableWidget::item {{
    padding: 6px 8px;
    color: {TEXT_DARK};
    background-color: transparent;
}}

QTableWidget::item:selected {{
    background-color: {BLUE_BG};
    color: {NAVY_PRIMARY};
    font-weight: bold;
}}

/* Table Header: Dark Navy background with crisp bold WHITE text */
QHeaderView::section {{
    background-color: {NAVY_PRIMARY};
    color: #FFFFFF;
    font-weight: bold;
    font-size: 12px;
    padding: 8px 6px;
    border: 1px solid #0F2D6B;
    border-right: 1px solid #334E68;
    text-align: center;
}}

QHeaderView::section:horizontal {{
    background-color: {NAVY_PRIMARY};
    color: #FFFFFF;
}}

QHeaderView::section:vertical {{
    background-color: #F1F5F9;
    color: {TEXT_MUTED};
    font-weight: bold;
    border: 1px solid #E2E8F0;
}}

/* Scrollbars */
QScrollBar:vertical {{
    border: none;
    background: #F1F5F9;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: #CBD5E1;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: #94A3B8;
}}

QScrollBar:horizontal {{
    border: none;
    background: #F1F5F9;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: #CBD5E1;
    min-width: 20px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #94A3B8;
}}

/* Tabs */
QTabWidget::pane {{
    border: 1px solid {BORDER_COLOR};
    background-color: #FFFFFF;
    border-radius: 6px;
    padding: 8px;
}}

QTabBar::tab {{
    background-color: #E2E8F0;
    color: {TEXT_MUTED};
    font-weight: bold;
    padding: 8px 18px;
    margin-right: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {BORDER_COLOR};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: #FFFFFF;
    color: {NAVY_PRIMARY};
    border-bottom: 2px solid {NAVY_PRIMARY};
}}

QTabBar::tab:hover:!selected {{
    background-color: #F1F5F9;
    color: {TEXT_DARK};
}}

/* Status Bar */
QStatusBar {{
    background-color: #FFFFFF;
    color: {TEXT_DARK};
    border-top: 1px solid #E2E8F0;
    font-size: 12px;
}}
"""
