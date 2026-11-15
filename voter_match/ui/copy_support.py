"""Excel-friendly copy support for tables and text labels.

* Tables: Ctrl+C copies the selected cells as tab-separated text (rows on new
  lines), which Excel / Google Sheets / Notepad paste into separate cells.
  A right-click menu offers copy, copy with headings, copy whole table and
  select all.
* Labels: voter details can be selected with the mouse and copied.

Copying only READS what is displayed; it never changes cell text, item data,
selection-dependent logic or the translation layer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView, QLabel, QMenu, QTableWidget

from voter_match.ui.i18n import tr


def _clean(text: str) -> str:
    # A tab or line break inside a cell would split it across Excel cells
    return " ".join((text or "").replace("\t", " ").splitlines()).strip()


def _header_text(table: QTableWidget, col: int) -> str:
    item = table.horizontalHeaderItem(col)
    return _clean(item.text()) if item is not None else str(col + 1)


def table_to_tsv(table: QTableWidget, whole_table: bool = False, with_headers: bool = False) -> str:
    """Tab-separated text of the selected cells (or the whole table).

    The selection's bounding box is copied, so pasting keeps rows/columns
    aligned; unselected cells inside the box are left empty. Hidden rows and
    columns are skipped.
    """
    if whole_table:
        cells = {(r, c) for r in range(table.rowCount()) for c in range(table.columnCount())}
    else:
        cells = {(i.row(), i.column()) for i in table.selectedIndexes()}
    if not cells:
        return ""
    rows = sorted({r for r, _ in cells if not table.isRowHidden(r)})
    cols = sorted({c for _, c in cells if not table.isColumnHidden(c)})
    lines = []
    if with_headers:
        lines.append("\t".join(_header_text(table, c) for c in cols))
    for r in rows:
        values = []
        for c in cols:
            item = table.item(r, c)
            values.append(_clean(item.text()) if (item is not None and (r, c) in cells) else "")
        lines.append("\t".join(values))
    return "\n".join(lines)


def copy_table(table: QTableWidget, whole_table: bool = False, with_headers: bool = False) -> int:
    """Copy to the clipboard; returns the number of rows copied."""
    text = table_to_tsv(table, whole_table=whole_table, with_headers=with_headers)
    if text:
        QGuiApplication.clipboard().setText(text)
    return text.count("\n") + 1 if text else 0


def enable_table_copy(table: QTableWidget, read_only: bool = False, cell_selection: bool = False) -> QTableWidget:
    """Add Ctrl+C, Ctrl+Shift+C (with headings) and a right-click copy menu.

    read_only: stop accidental in-place edits of display-only tables.
    cell_selection: allow selecting individual cells (Excel-style) instead of rows.
    The existing selection mode is otherwise left untouched, because some
    dialogs rely on single-row selection.
    """
    if read_only:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    if cell_selection:
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)

    sc = QShortcut(QKeySequence.Copy, table)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
    sc.activated.connect(lambda: copy_table(table))
    sc_h = QShortcut(QKeySequence("Ctrl+Shift+C"), table)
    sc_h.setContext(Qt.WidgetWithChildrenShortcut)
    sc_h.activated.connect(lambda: copy_table(table, with_headers=True))

    table.setContextMenuPolicy(Qt.CustomContextMenu)
    table.customContextMenuRequested.connect(lambda pos: _show_menu(table, pos))
    return table


def _show_menu(table: QTableWidget, pos) -> None:
    # Menu texts are translated here with tr(); the i18n walker never touches them.
    menu = QMenu(table)
    has_sel = bool(table.selectedIndexes())
    a_copy = menu.addAction(tr("📋 कॉपी करें") + "\tCtrl+C")
    a_copy.setEnabled(has_sel)
    a_head = menu.addAction(tr("📋 शीर्षक सहित कॉपी करें") + "\tCtrl+Shift+C")
    a_head.setEnabled(has_sel)
    menu.addSeparator()
    a_all = menu.addAction(tr("📄 पूरी तालिका कॉपी करें (शीर्षक सहित)"))
    a_select = menu.addAction(tr("✅ सब चुनें") + "\tCtrl+A")
    chosen = menu.exec(table.viewport().mapToGlobal(pos))
    if chosen is a_copy:
        copy_table(table)
    elif chosen is a_head:
        copy_table(table, with_headers=True)
    elif chosen is a_all:
        copy_table(table, whole_table=True, with_headers=True)
    elif chosen is a_select:
        table.selectAll()


# Field order for copying one voter record as an Excel row
RECORD_FIELDS = [
    ("serial_no", "क्र०"),
    ("voter_name", "मतदाता का नाम"),
    ("relative_name", "पिता/पति का नाम"),
    ("age", "आयु"),
    ("gender", "लिंग"),
    ("house_no", "मकान"),
    ("epic", "EPIC"),
    ("ward", "वार्ड/भाग"),
]


def record_to_tsv(record: dict, mappings: list, side: str, with_headers: bool = False) -> str:
    """One voter record as a tab-separated Excel row, using the ORIGINAL values
    (never translated). side='a' or 'b' selects the List A / List B column."""
    by_role = {m.role: m for m in mappings}
    heads, vals = [], []
    for role, label in RECORD_FIELDS:
        m = by_role.get(role)
        col = (m.col_a if side == "a" else m.col_b) if m else None
        if not col:
            continue
        v = record.get(col, "")
        v = "" if v is None else str(v)
        heads.append(tr(label))
        vals.append(_clean("" if v.strip().lower() == "nan" else v))
    if "_orig_row" in record:
        heads.append(tr("मूल पंक्ति"))
        vals.append(str(record.get("_orig_row", "")))
    row = "\t".join(vals)
    return ("\t".join(heads) + "\n" + row) if with_headers else row


def copy_text(text: str) -> None:
    if text:
        QGuiApplication.clipboard().setText(text)


def make_copy_button(button, get_text, label: str, tooltip: str = "", persistent: bool = False) -> None:
    """Wire a button: click copies get_text(False); right-click menu offers
    the version with headings. Shows a short confirmation on the button.

    The button manages its own (translated) label and is excluded from the
    automatic translator, so the temporary "copied" text can never be mistaken
    for the button's original label.
    """
    from PySide6.QtCore import QTimer
    from voter_match.ui.i18n import on_language_changed, skip_translation

    skip_translation(button)

    def refresh() -> None:
        try:
            button.setText(tr(label))
            if tooltip:
                button.setToolTip(tr(tooltip))
        except RuntimeError:
            pass  # button already deleted (candidate cards are rebuilt per record)

    refresh()
    if persistent:
        # Long-lived buttons follow language switches; short-lived ones (rebuilt
        # with every record) get the right language when they are recreated.
        on_language_changed(lambda _lang: refresh())

    def flash() -> None:
        button.setText(tr("✅ कॉपी हुआ"))
        QTimer.singleShot(1200, refresh)

    def do_copy(with_headers: bool) -> None:
        text = get_text(with_headers)
        if text:
            copy_text(text)
            flash()

    button.clicked.connect(lambda: do_copy(False))
    button.setContextMenuPolicy(Qt.CustomContextMenu)

    def menu_at(pos) -> None:
        menu = QMenu(button)
        a_vals = menu.addAction(tr("📋 कॉपी करें"))
        a_head = menu.addAction(tr("📋 शीर्षक सहित कॉपी करें"))
        chosen = menu.exec(button.mapToGlobal(pos))
        if chosen is a_vals:
            do_copy(False)
        elif chosen is a_head:
            do_copy(True)

    button.customContextMenuRequested.connect(menu_at)


def make_selectable(*labels: QLabel) -> None:
    """Let the user select (and Ctrl+C / right-click copy) label text."""
    for lbl in labels:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setCursor(Qt.IBeamCursor)
