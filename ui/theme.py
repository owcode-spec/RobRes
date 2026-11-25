"""Palette, fonts and the global stylesheet — dark grey + blue/purple accents, Inter font."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

# --- colours ----------------------------------------------------------------
BG = "#0A0B0F"          # тёмно-серый фон
SURFACE = "#111318"     # поверхность карточек
SURFACE_2 = "#181A21"   # чуть светлее (hover, вложенные панели)
BORDER = "#242630"      # границы
TEXT = "#E8EAEF"        # основной текст
MUTED = "#8A90A0"       # вспомогательный текст
FAINT = "#4A5060"       # приглушённый текст
ACCENT = "#6366F1"      # синий акцент (indigo)
ACCENT_2 = "#A855F7"    # фиолетовый акцент
ACCENT_GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #A855F7)"
GREEN = "#34D399"
RED = "#F87171"

# --- fonts ------------------------------------------------------------------
HEADING_FAMILY = "Inter"
BODY_FAMILY = "Inter"
FALLBACK_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def qc(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def heading_font(px: int, spacing: float = 0.0, weight: QFont.Weight = QFont.Weight.DemiBold) -> QFont:
    f = QFont(HEADING_FAMILY)
    f.setPixelSize(px)
    f.setWeight(weight)
    f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def body_font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(BODY_FAMILY)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def load_fonts() -> None:
    """Register the bundled Inter font files so they are available by name.

    Falls back silently if the font files are missing (e.g. in a broken build).
    """
    from PySide6.QtWidgets import QApplication
    import sys
    from pathlib import Path

    # Try to find the fonts directory next to the executable / source.
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    font_dir = base / "assets" / "fonts"

    loaded_any = False
    for fname in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf"):
        path = font_dir / fname
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id != -1:
                loaded_any = True

    global HEADING_FAMILY, BODY_FAMILY

    # Tell the running application to use the loaded family globally.
    app = QApplication.instance()
    if app is not None:
        app.setFont(QFont(HEADING_FAMILY, 10))

    # If nothing loaded, fall back to the system Segoe UI so the app still looks decent.
    if not loaded_any:
        HEADING_FAMILY = FALLBACK_FAMILY
        BODY_FAMILY = FALLBACK_FAMILY
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont(FALLBACK_FAMILY, 10))


STYLESHEET = f"""
* {{
    color: {TEXT};
    font-family: "{HEADING_FAMILY}";
}}
#Root {{
    background: {BG};
    border: 1px solid {BORDER};
}}
QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {MUTED}; font-size: 12px; }}
QLabel[role="key"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="value"] {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel[role="section"] {{
    color: {MUTED}; font-family: "{HEADING_FAMILY}"; font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
}}
QLabel[role="message"] {{ color: {MUTED}; font-size: 12px; }}

#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; }}

QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 16px;
    color: {MUTED};
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[kind="ghost"]:hover {{
    border-color: {ACCENT};
    color: {TEXT};
    background: rgba(99, 102, 241, 0.08);
}}
QPushButton[kind="ghost"]:pressed {{ background: rgba(99, 102, 241, 0.16); }}

QPushButton[kind="icon"] {{
    background: transparent; border: none; border-radius: 8px;
    color: {MUTED}; font-size: 13px;
    min-width: 36px; min-height: 30px;
}}
QPushButton[kind="icon"]:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#CloseBtn:hover {{ background: {RED}; color: white; }}

QPlainTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 10px;
    font-family: "{MONO_FAMILY}", Consolas;
    font-size: 11px;
    color: #B9BFCC;
    selection-background-color: rgba(99, 102, 241, 0.35);
}}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0; background: none;
}}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px 8px; border-radius: 6px;
}}
QMenu {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px;
}}
QMenu::item {{ padding: 8px 24px 8px 16px; border-radius: 6px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::item:disabled {{ color: {FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 10px; }}
"""
