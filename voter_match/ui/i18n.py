"""Interface language switching (हिंदी / English).

The app's UI text is written in Hindi in the code. When English is selected,
this module translates whatever is on screen - labels, buttons, tabs, group
titles, opt-in combo boxes and tables, placeholders, tooltips, message boxes,
dialog captions and the status bar - using the table in ``i18n_en.py``.

Design notes
* Originals are remembered per widget, so switching back to Hindi restores
  the exact source text, and text the app changes later (counts, status
  messages) is picked up as the new original automatically.
* Dynamic text is handled by templates ("मिलान पूर्ण! मिला: {}, ...") whose
  variable parts are themselves translated recursively, and by splitting
  composite text on separators ("; ", " • ", " | ", new lines, HTML tags).
* Voter data (names etc.) is never in the table, so it is never changed.
  Combo boxes and tables are only translated when opted in with
  ``mark_translatable()``, because some code reads their text back.
* A light timer re-applies the language to visible windows so freshly
  created or updated text is translated without touching every call site.
"""

from __future__ import annotations
import re
from functools import lru_cache

from PySide6.QtCore import QObject, QSettings, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from voter_match.ui.i18n_en import EN_PLAIN, EN_TEMPLATES

LANG_HI = "hi"
LANG_EN = "en"
_SETTINGS_KEY = "ui/language"
_TRANSLATABLE = "_i18n_translatable"
_SKIP = "_i18n_skip"
_ROLE_ORIG = int(Qt.UserRole) + 0x4E1  # private item-data role for originals

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HTML_SPLIT = re.compile(r"(<[^>]+>)")
_SEPARATORS = ("\n", " | ", " • ", "; ", " — ")
_EDGE = re.compile(r"^([^ऀ-ॿA-Za-z0-9'\"<(]*)(.*?)([\s:➔→▶.]*)$", re.S)

_current = LANG_HI


# --------------------------------------------------------------- translation


def _compile_templates() -> list[tuple[re.Pattern, str]]:
    out = []
    # Longest constant text first so specific templates win over generic ones
    for hi, en in sorted(EN_TEMPLATES.items(), key=lambda kv: -len(kv[0].replace("{}", ""))):
        parts = [re.escape(p) for p in hi.split("{}")]
        out.append((re.compile("^" + "(.*?)".join(parts) + "$", re.S), en))
    return out


_TEMPLATES = _compile_templates()


@lru_cache(maxsize=20000)
def translate(text: str) -> str:
    """Hindi UI text -> English. Unknown text (e.g. voter names) is returned as is."""
    if not text or not _DEVANAGARI.search(text):
        return text
    hit = EN_PLAIN.get(text)
    if hit is not None:
        return hit
    for pattern, en in _TEMPLATES:
        m = pattern.match(text)
        if m and _clean_groups(m.groups()):
            return en.format(*(translate(g) for g in m.groups()))
    if "<" in text and ">" in text:
        pieces = _HTML_SPLIT.split(text)
        if len(pieces) > 1:
            return "".join(p if p.startswith("<") else _translate_padded(p) for p in pieces)
    for sep in _SEPARATORS:
        if sep in text:
            parts = text.split(sep)
            translated = [_translate_padded(p) for p in parts]
            if translated != parts:
                return sep.join(translated)
    m = _EDGE.match(text)
    if m and (m.group(1) or m.group(3)):
        core = m.group(2)
        t = EN_PLAIN.get(core)
        if t is None:
            for pattern, en in _TEMPLATES:
                mm = pattern.match(core)
                if mm:
                    t = en.format(*(translate(g) for g in mm.groups()))
                    break
        if t is not None:
            return m.group(1) + t + m.group(3)
    return text


def _clean_groups(groups) -> bool:
    """A template's variable part must not swallow other joined phrases
    ("A; B; C"), otherwise only the first phrase would get translated."""
    return not any(sep in g for g in groups for sep in _SEPARATORS)


def _translate_padded(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead + translate(stripped) + trail


def tr(text: str) -> str:
    """Translate text for the current language (identity in Hindi mode)."""
    return translate(text) if _current == LANG_EN else text


# --------------------------------------------------------------- settings


def _settings() -> QSettings:
    return QSettings("ElectoralRollCheck", "ui")


def current_language() -> str:
    return _current


def saved_language() -> str:
    try:
        v = _settings().value(_SETTINGS_KEY, LANG_HI)
        return v if v in (LANG_HI, LANG_EN) else LANG_HI
    except Exception:
        return LANG_HI


def mark_translatable(widget: QWidget) -> QWidget:
    """Opt a QComboBox / QTableWidget in to item translation (its code must use
    item data, not item text, for logic)."""
    widget.setProperty(_TRANSLATABLE, True)
    return widget


def skip_translation(widget: QWidget) -> QWidget:
    widget.setProperty(_SKIP, True)
    return widget


# --------------------------------------------------------------- widget walking


def _swap(obj, getter, setter, key: str) -> None:
    """Show the translation of the widget's original text for this property."""
    cur = getter()
    if not isinstance(cur, str):
        return
    orig_key, shown_key = f"_i18n_o_{key}", f"_i18n_s_{key}"
    shown = obj.property(shown_key)
    orig = obj.property(orig_key) if shown is not None and cur == shown else cur
    if orig != obj.property(orig_key):
        obj.setProperty(orig_key, orig)
    want = tr(orig)
    if want != cur:
        setter(want)
    obj.setProperty(shown_key, want)


def _swap_item(item, getter, setter) -> None:
    cur = getter()
    stored = item.data(_ROLE_ORIG)
    if isinstance(stored, (list, tuple)) and len(stored) == 2 and cur == stored[1]:
        orig = stored[0]
    else:
        orig = cur
    want = tr(orig)
    if want != cur:
        setter(want)
    item.setData(_ROLE_ORIG, [orig, want])


def _apply_table(table: QTableWidget, visible_only: bool) -> None:
    for c in range(table.columnCount()):
        h = table.horizontalHeaderItem(c)
        if h is not None:
            _swap_item(h, h.text, h.setText)
    rows = table.rowCount()
    if rows == 0:
        return
    if visible_only:
        top = table.rowAt(0)
        bottom = table.rowAt(table.viewport().height() - 1)
        first = 0 if top < 0 else top
        last = rows - 1 if bottom < 0 else bottom
    else:
        first, last = 0, rows - 1
    for r in range(first, last + 1):
        for c in range(table.columnCount()):
            it = table.item(r, c)
            if it is not None:
                _swap_item(it, it.text, it.setText)


def _apply_combo(combo: QComboBox) -> None:
    for i in range(combo.count()):
        cur = combo.itemText(i)
        stored = combo.itemData(i, _ROLE_ORIG)
        orig = stored[0] if isinstance(stored, (list, tuple)) and len(stored) == 2 and cur == stored[1] else cur
        want = tr(orig)
        if want != cur:
            combo.setItemText(i, want)
        combo.setItemData(i, [orig, want], _ROLE_ORIG)


def apply_to(root: QWidget, visible_only: bool = True) -> None:
    """Translate (or restore) every text-bearing widget under root."""
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        if w.property(_SKIP):
            continue
        if visible_only and not w.isVisible():
            continue
        try:
            if isinstance(w, QLabel):
                _swap(w, w.text, w.setText, "text")
            elif isinstance(w, QAbstractButton):
                _swap(w, w.text, w.setText, "text")
            elif isinstance(w, QGroupBox):
                _swap(w, w.title, w.setTitle, "title")
            elif isinstance(w, QLineEdit):
                _swap(w, w.placeholderText, w.setPlaceholderText, "ph")
            elif isinstance(w, QTabWidget):
                for i in range(w.count()):
                    _swap(w, lambda i=i: w.tabText(i), lambda t, i=i: w.setTabText(i, t), f"tab{i}")
            elif isinstance(w, QComboBox) and w.property(_TRANSLATABLE):
                _apply_combo(w)
            elif isinstance(w, QTableWidget) and w.property(_TRANSLATABLE):
                _apply_table(w, visible_only)
            if isinstance(w, QSpinBox):
                _swap(w, w.suffix, w.setSuffix, "suffix")
            if w.toolTip():
                _swap(w, w.toolTip, w.setToolTip, "tip")
            if w.isWindow() and w.windowTitle():
                _swap(w, w.windowTitle, w.setWindowTitle, "title_w")
        except RuntimeError:
            continue  # widget deleted while walking


def apply_all(visible_only: bool = False) -> None:
    app = QApplication.instance()
    if app is None:
        return
    for top in app.topLevelWidgets():
        if visible_only and not top.isVisible():
            continue
        apply_to(top, visible_only=visible_only)


# --------------------------------------------------------------- dialogs & status bar

_patched = False


def _patch_dialogs() -> None:
    """Translate titles/text of standard dialogs before they are shown."""
    global _patched
    if _patched:
        return
    _patched = True

    def wrap_msg(fn):
        def inner(parent, title, text, *args, **kwargs):
            return fn(parent, tr(title), tr(text), *args, **kwargs)
        return staticmethod(inner)

    for name in ("information", "warning", "critical", "question"):
        setattr(QMessageBox, name, wrap_msg(getattr(QMessageBox, name)))

    def wrap_file(fn):
        def inner(parent=None, caption="", *args, **kwargs):
            return fn(parent, tr(caption), *args, **kwargs)
        return staticmethod(inner)

    for name in ("getOpenFileName", "getSaveFileName", "getExistingDirectory"):
        setattr(QFileDialog, name, wrap_file(getattr(QFileDialog, name)))

    orig_get_text = QInputDialog.getText

    def get_text(parent, title, label, *args, **kwargs):
        return orig_get_text(parent, tr(title), tr(label), *args, **kwargs)

    QInputDialog.getText = staticmethod(get_text)

    orig_show = QStatusBar.showMessage

    def show_message(self, text, timeout=0):
        self.setProperty("_i18n_raw", text)
        return orig_show(self, tr(text), timeout)

    QStatusBar.showMessage = show_message


class _Refresher(QObject):
    """Periodically re-applies the language to visible windows (cheap: only
    visible widgets, and only the visible rows of opted-in tables)."""

    def __init__(self) -> None:
        super().__init__()
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        apply_all(visible_only=True)


_refresher: _Refresher | None = None
_listeners: list = []


def on_language_changed(callback) -> None:
    _listeners.append(callback)


def set_language(lang: str, persist: bool = True) -> None:
    """Switch the whole UI to lang ('hi' or 'en')."""
    global _current
    lang = lang if lang in (LANG_HI, LANG_EN) else LANG_HI
    _current = lang
    if persist:
        try:
            _settings().setValue(_SETTINGS_KEY, lang)
        except Exception:
            pass
    apply_all(visible_only=False)
    app = QApplication.instance()
    if app is not None:
        for top in app.topLevelWidgets():
            for bar in top.findChildren(QStatusBar):
                raw = bar.property("_i18n_raw")
                if raw:
                    bar.showMessage(raw)
    for cb in list(_listeners):
        try:
            cb(lang)
        except Exception:
            pass


def install() -> None:
    """Call once after the QApplication exists (before or after the main window)."""
    global _refresher, _current
    _patch_dialogs()
    _current = saved_language()
    if _refresher is None:
        _refresher = _Refresher()
        _refresher.timer.start()
