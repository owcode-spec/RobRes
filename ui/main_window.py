"""Premium main window, settings modal overlay, developer window, tray."""
from __future__ import annotations

import logging
import os
import sys
import webbrowser

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QRectF, Qt,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QGuiApplication, QKeySequence, QLinearGradient,
                           QPainter, QPen, QPixmap, QRadialGradient, QShortcut)
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

import config
from config import APP_VERSION, LOG_PATH, RESOLUTION_AUTO, RESOLUTION_2K, RESOLUTION_FHD
from core import win32
from ui import theme
from ui.theme import qc
from ui.controller import Controller, Phase, Snapshot
from ui.widgets import StatusDot, Switch, ToggleButton, _lerp, _mix, app_icon, asset

log = logging.getLogger(__name__)

WINDOW_TITLE = "RobRun 4:3"
WIN_W, WIN_H = 1100, 700
ICON_MIN, ICON_CLOSE, ICON_SETTINGS = "\uE921", "\u00D7", "\uE713"
TG_LINK = "https://t.me/owcode"


LOCAL_QSS = f"""
#Glass {{
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 20px;
}}
QLabel[role="title"] {{
    color: {theme.TEXT}; font-size: 56px; font-weight: 700;
}}
QLabel[role="muted"] {{ color: {theme.MUTED}; font-size: 13px; }}
QLabel[role="section"] {{
    color: {theme.MUTED}; font-family: "{theme.HEADING_FAMILY}"; font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
}}
QLabel[role="cardTitle"] {{ color: {theme.TEXT}; font-size: 15px; font-weight: 600; }}
QLabel[role="cardValue"] {{ color: {theme.ACCENT}; font-size: 18px; font-weight: 700; }}
QLabel[role="tiny"] {{ color: {theme.FAINT}; font-size: 11px; }}
QPushButton[kind="soft"] {{
    background: {theme.SURFACE_2};
    border: 1px solid {theme.BORDER};
    border-radius: 12px;
    padding: 10px 20px;
    color: {theme.TEXT};
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[kind="soft"]:hover {{
    border-color: {theme.ACCENT}; color: {theme.TEXT}; background: rgba(99, 102, 241, 0.10);
}}
QPushButton[kind="soft"]:pressed {{
    background: rgba(99, 102, 241, 0.20);
}}
QPushButton[kind="primary"] {{
    background: {theme.ACCENT_GRADIENT};
    border: none;
    border-radius: 12px;
    padding: 10px 20px;
    color: white;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{
    background: {theme.ACCENT_GRADIENT};
}}
QPushButton[kind="primary"]:pressed {{
    background: {theme.ACCENT_GRADIENT};
    opacity: 0.85;
}}
QComboBox {{
    background: {theme.SURFACE_2};
    border: 1px solid {theme.BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    color: {theme.TEXT};
    font-size: 13px;
    min-height: 38px;
}}
QComboBox:hover {{ border-color: {theme.ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ color: {theme.MUTED}; }}
"""


class QtLogBridge(QObject):
    line = Signal(str)

    def __init__(self):
        super().__init__()
        self.handler = _BridgeHandler(self)
        self.handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S"))


class _BridgeHandler(logging.Handler):
    def __init__(self, bridge: QtLogBridge):
        super().__init__()
        self.bridge = bridge

    def emit(self, record):
        try:
            self.bridge.line.emit(self.format(record))
        except RuntimeError:
            pass


def _label(text: str = "", role: str | None = None) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    return lab


def _button(text: str, kind: str, slot) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(slot)
    return b


def _inset(item, px: int = 0) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(px, 0, px, 0)
    (row.addLayout if isinstance(item, QHBoxLayout | QVBoxLayout) else row.addWidget)(item)
    return row


class ModeGlyph(QWidget):
    """A screen outline whose picture morphs between 16:9, 4:3 with bars and stretched 4:3."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 40)
        self._w = 1.0
        self._active = 0.0
        self._anim = QVariantAnimation(self, duration=550, easingCurve=QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._step)
        self._from = (1.0, 0.0)
        self._to = (1.0, 0.0)

    def _step(self, t):
        t = float(t)
        self._w = _lerp(self._from[0], self._to[0], t)
        self._active = _lerp(self._from[1], self._to[1], t)
        self.update()

    def set_mode(self, width_ratio: float, active: bool):
        target = (width_ratio, 1.0 if active else 0.0)
        if target == self._to:
            return
        self._from, self._to = (self._w, self._active), target
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        screen = QRectF(2, 2, self.width() - 4, self.height() - 4)
        p.setPen(QPen(qc("#2A2E3A"), 1.2))
        p.setBrush(qc("#060608"))
        p.drawRoundedRect(screen, 5, 5)
        gw = screen.width() * self._w
        pic = QRectF(screen.center().x() - gw / 2, screen.top() + 3, gw, screen.height() - 6)
        pic = pic.adjusted(3, 0, -3, 0)
        col = _mix(qc(theme.FAINT), qc(theme.ACCENT), self._active)
        fill = QColor(col)
        fill.setAlphaF(0.22 + 0.2 * self._active)
        p.setPen(QPen(col, 1.6))
        p.setBrush(fill)
        p.drawRoundedRect(pic, 3, 3)


class TitleButtons(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        for glyph, slot, oid, tip in ((ICON_MIN, window.showMinimized, None, "Свернуть"),
                                      (ICON_CLOSE, window.close, "CloseBtn", "Закрыть")):
            b = _button(glyph, "icon", slot)
            b.setToolTip(tip)
            if oid:
                b.setObjectName(oid)
            lay.addWidget(b)


class SettingsPanel(QWidget):
    """Модальное окно настроек — отдельный QWidget с флагом Qt.Dialog.

    Появляется поверх главного окна с затемнённым оверлеем (собственный виджет-оверлей,
    не влияющий на прозрачность главного окна).
    """
    closed = Signal()

    def __init__(self, controller: Controller, parent: QWidget):
        super().__init__(parent)
        self.c = controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()
        if parent:
            self.resize(parent.size())

        # Затемнённый оверлей — отдельный виджет поверх родителя, НЕ влияющий на прозрачность главного окна.
        self.scrim = QWidget(parent)
        self.scrim.setGeometry(parent.rect())
        self.scrim.setStyleSheet(f"background: rgba(10, 11, 15, 0.75);")
        self.scrim.hide()

        # Сама панель настроек — по центру родителя.
        self.panel = QFrame(self)
        self.panel.setObjectName("Panel")
        self.panel_w = 480
        self.panel_h = 620
        self.panel.setStyleSheet(f"""
            #Panel {{
                background: {theme.SURFACE};
                border: 1px solid {theme.BORDER};
                border-radius: 24px;
            }}
        """)

        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(40, 36, 40, 32)
        lay.setSpacing(0)

        # Заголовок + кнопка закрытия.
        head = QHBoxLayout()
        title = QLabel("НАСТРОЙКИ")
        title.setFont(theme.heading_font(22, 0.0))
        head.addWidget(title)
        head.addStretch(1)
        close_btn = _button(ICON_CLOSE, "icon", self.close_panel)
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(32, 32)
        close_btn.setToolTip("Закрыть")
        head.addWidget(close_btn)
        lay.addLayout(head)
        lay.addSpacing(28)

        cfg = controller.cfg

        # --- Разрешение ---
        lay.addWidget(_label("РАЗРЕШЕНИЕ ИГРЫ", "section"))
        lay.addSpacing(12)
        self.res_combo = QComboBox()
        self.res_combo.addItem("2K — 1728×1440", RESOLUTION_2K)
        self.res_combo.addItem("Full HD — 1440×1080", RESOLUTION_FHD)
        current_mode = cfg.resolution_mode or RESOLUTION_2K
        idx = self.res_combo.findData(current_mode)
        if idx < 0:
            idx = 0
        self.res_combo.setCurrentIndex(idx)
        lay.addWidget(self.res_combo)
        lay.addSpacing(28)

        # --- Переключатели (без описаний) ---
        lay.addWidget(_label("ПАРАМЕТРЫ", "section"))
        lay.addSpacing(12)

        self.sw_stretch = self._option(lay, "Растягивать на весь экран", cfg.stretch_mode,
                                       controller.set_stretch)
        lay.addSpacing(14)
        self.sw_auto_apply = self._option(lay, "Включать 4:3 при запуске игры", cfg.auto_apply_on_launch,
                                          lambda v: controller.store.update(auto_apply_on_launch=v))
        lay.addSpacing(14)
        self.sw_autostart = self._option(lay, "Запускать вместе с Windows",
                                         config.autostart_enabled(), self._set_autostart)
        lay.addSpacing(14)
        self.sw_tray = self._option(lay, "Сворачивать в трей при закрытии",
                                    cfg.minimize_to_tray, lambda v: controller.store.update(minimize_to_tray=v))
        lay.addSpacing(28)

        # --- Игра ---
        lay.addWidget(_label("ИГРА", "section"))
        lay.addSpacing(12)
        game_row = QHBoxLayout()
        game_row.setSpacing(10)
        self.game_dot = StatusDot()
        game_row.addWidget(self.game_dot)
        self.game_found = _label("", "cardTitle")
        game_row.addWidget(self.game_found, 1)
        lay.addLayout(game_row)
        lay.addSpacing(16)

        # Кнопки действия — две в ряд, равномерно распределённые.
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btn_browse = _button("Указать вручную", "soft", self._browse)
        btn_browse.setFixedHeight(40)
        btn_detect = _button("Найти автоматически", "soft", self._detect)
        btn_detect.setFixedHeight(40)
        btns.addWidget(btn_browse)
        btns.addWidget(btn_detect)
        btns.addStretch(1)
        lay.addLayout(btns)
        lay.addSpacing(16)

        # Кнопка Применить внизу
        apply_btn = _button("ПРИМЕНИТЬ", "primary", self._apply_and_close)
        apply_btn.setFixedHeight(44)
        lay.addWidget(apply_btn)

        # Анимация появления.
        self._opacity = 0.0
        self._fade_anim = QVariantAnimation(self, duration=220,
                                            easingCurve=QEasingCurve.OutCubic)
        self._fade_anim.valueChanged.connect(self._anim_step)
        self._fade_anim.finished.connect(self._anim_finished)

    def _option(self, layout, title: str, checked: bool, on_change) -> Switch:
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(0)
        lab = _label(title, "cardTitle")
        row.addWidget(lab, 1)
        sw = Switch()
        sw.setChecked(checked)
        sw.toggled.connect(on_change)
        row.addWidget(sw, 0, Qt.AlignVCenter)
        layout.addLayout(row)
        return sw

    def _anim_step(self, v):
        self._opacity = v
        eff = QGraphicsOpacityEffect(self.panel)
        eff.setOpacity(v)
        self.panel.setGraphicsEffect(eff)
        self.panel.setFixedSize(self.panel_w, int(self.panel_h * (0.9 + 0.1 * v)))
        self._reposition_panel()

    def _anim_finished(self):
        if self._opacity == 0.0:
            self.scrim.hide()
            self.hide()

    def _reposition_panel(self):
        parent = self.parentWidget()
        if parent:
            x = (parent.width() - self.panel.width()) // 2
            y = (parent.height() - self.panel.height()) // 2
            self.panel.move(x, y)
            self.scrim.setGeometry(parent.rect())

    def open_panel(self):
        parent = self.parentWidget()
        if parent:
            self.resize(parent.size())
            self.scrim.setGeometry(parent.rect())
        self.scrim.show()
        self.scrim.raise_()
        self.show()
        self.raise_()
        self._reposition_panel()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def close_panel(self):
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_panel()
        else:
            super().keyPressEvent(e)

    def _apply_and_close(self):
        mode = self.res_combo.currentData()
        self.c.set_resolution_mode(mode)
        self.close_panel()

    def _set_autostart(self, on: bool):
        try:
            config.set_autostart(on)
            self.c.store.update(launch_with_windows=on)
            log.info("Autostart %s", "enabled" if on else "disabled")
        except OSError as e:
            log.error("Could not change autostart: %s", e)
            self.sw_autostart.setChecked(not on)

    def _browse(self):
        start = self.c.install.folder if self.c.install else "C:\\"
        path, _ = QFileDialog.getOpenFileName(self, "Где находится Rob-Run?", str(start),
                                              "Игра Rob-Run (*.exe)")
        if path:
            self.c.set_game_exe(os.path.normpath(path))

    def _detect(self):
        if not self.c.auto_detect():
            self.game_found.setText("Не нашли игру в Steam — укажите её вручную")
            self.game_dot.set_color(theme.ACCENT, False)

    def show_snapshot(self, _s: Snapshot):
        inst = self.c.install
        if inst:
            self.game_found.setText("Rob-Run найдена" + (" в Steam" if inst.via_steam else ""))
            self.game_dot.set_color(theme.GREEN, False)
        else:
            self.game_found.setText("Игра не найдена")
            self.game_dot.set_color(theme.FAINT, False)


class DeveloperWindow(QWidget):
    def __init__(self, bridge: QtLogBridge):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Rob-Run 4:3 — режим разработчика")
        self.setWindowIcon(app_icon())
        self.resize(820, 520)
        self.setStyleSheet(f"background:{theme.BG};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        self.info = _label("", "muted")
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.info)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(3000)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(_button("Открыть папку с логом", "soft", lambda: os.startfile(LOG_PATH.parent)))
        row.addWidget(_button("Копировать", "soft",
                              lambda: QGuiApplication.clipboard().setText(self.view.toPlainText())))
        row.addStretch(1)
        lay.addLayout(row)
        bridge.line.connect(self.view.appendPlainText)
        try:
            tail = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            self.view.setPlainText("\n".join(tail))
        except OSError:
            pass

    def show_snapshot(self, s: Snapshot):
        self.info.setText(
            f"phase={s.phase.value}  running={s.running}  booting={s.booting}  stretched={s.stretched}\n"
            f"desktop={s.desktop}  game={s.game_res} ({s.game_mode}, {s.game_aspect})\n"
            f"{s.compat}\n{s.install_path}")


class StatusCard(QFrame):
    """Красивая карточка статуса с иконкой и значением."""

    def __init__(self, title: str, value: str, icon: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Glass")
        self.setFixedSize(230, 100)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(12)

        icon_lab = QLabel(icon)
        icon_lab.setFont(theme.heading_font(20, 0.0))
        icon_lab.setFixedSize(28, 28)
        lay.addWidget(icon_lab)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lab = _label(title, "muted")
        title_lab.setFont(theme.body_font(11, QFont.Weight.Medium))
        text_col.addWidget(title_lab)
        self.value_lab = _label(value, "cardValue")
        self.value_lab.setFont(theme.body_font(16, QFont.Weight.DemiBold))
        text_col.addWidget(self.value_lab)
        lay.addLayout(text_col, 1)


class MainWindow(QWidget):
    def __init__(self, controller: Controller, bridge: QtLogBridge):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Window)
        self.c = controller
        self._quitting = False
        self._drag: QPoint | None = None
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        self.setFixedSize(WIN_W, WIN_H)
        self.setStyleSheet(LOCAL_QSS)
        self._bg = self._prepare_background()

        self._build_content()
        self.titlebuttons = TitleButtons(self)
        self.titlebuttons.adjustSize()
        self.titlebuttons.move(WIN_W - self.titlebuttons.width() - 14, 14)

        self.settings = SettingsPanel(controller, self)
        self.settings.closed.connect(lambda: self.settings_btn.setFocus())
        self.dev = DeveloperWindow(bridge)
        QShortcut(QKeySequence("Ctrl+Shift+D"), self, activated=self.toggle_dev)
        QShortcut(QKeySequence("Escape"), self, activated=self.settings.close_panel)

        # При изменении разрешения — обновить карточки статуса.
        self.c.resolution_changed.connect(self._on_resolution_changed)

        self._build_tray()
        controller.state_changed.connect(self._render)
        controller.notify.connect(self._notify)

        # Fade-in при запуске.
        self._fade_in_anim = QVariantAnimation(self, duration=700,
                                               easingCurve=QEasingCurve.OutCubic)
        self._fade_in_anim.valueChanged.connect(self._fade_in_step)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self.setWindowOpacity(0.0)
        self._fade_in_anim.start()

        if "--dev" in sys.argv:
            self.dev.show()

    # -- background ------------------------------------------------------------------------------
    def _prepare_background(self) -> QPixmap:
        canvas = QPixmap(WIN_W, WIN_H)
        canvas.fill(qc(theme.BG))
        p = QPainter(canvas)
        p.setRenderHint(QPainter.Antialiasing)
        edge = QRadialGradient(WIN_W / 2, WIN_H / 2, WIN_W)
        edge.setColorAt(0.55, qc(theme.BG, 0))
        edge.setColorAt(0.85, qc(theme.BG, 60))
        edge.setColorAt(1.0, qc(theme.BG, 200))
        p.fillRect(canvas.rect(), edge)
        glow = QRadialGradient(WIN_W * 0.85, WIN_H * 0.15, 300)
        glow.setColorAt(0, qc(theme.ACCENT, 18))
        glow.setColorAt(1, qc(theme.ACCENT, 0))
        p.fillRect(canvas.rect(), glow)
        p.end()
        return canvas

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._bg)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Водяной знак owcode (кликабельный).
        p.setPen(QPen(qc(theme.FAINT, 150), 1))
        wm_font = QFont(theme.HEADING_FAMILY, 17)
        wm_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(wm_font)
        wm_text = "owcode"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(wm_text)
        th = fm.height()
        self._wm_rect = QRect(WIN_W - tw - 28, WIN_H - th - 8, tw, th)
        p.drawText(self._wm_rect, Qt.AlignVCenter | Qt.AlignRight, wm_text)

    def _fade_in_step(self, v):
        self.setWindowOpacity(v)

    # -- layout ----------------------------------------------------------------------------------------
    def _build_content(self):
        # Всё содержимое по центру окна — один вертикальный layout с addStretch сверху и снизу.
        self.center_col = QWidget(self)
        self.center_col.setFixedSize(520, WIN_H)
        self.center_col.move((WIN_W - 520) // 2, 0)

        lay = QVBoxLayout(self.center_col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Верхний stretch для вертикального центрирования.
        lay.addStretch(1)

        # Большой заголовок "4:3".
        title = QLabel("4:3")
        title.setFont(theme.heading_font(96, 0.0, QFont.Weight.Black))
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(8)

        # Точка индикатора состояния игры.
        dot_row = QHBoxLayout()
        dot_row.addStretch(1)
        self.dot = StatusDot()
        dot_row.addWidget(self.dot)
        dot_row.addStretch(1)
        lay.addLayout(dot_row)
        lay.addSpacing(4)

        # Статус-карточки по центру.
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        self.card_status = StatusCard("Статус", "Ожидание", "\u23F3", self)
        self.card_res = StatusCard("Разрешение", "1728×1440", "\u25A1", self)
        cards_row.addWidget(self.card_status)
        cards_row.addWidget(self.card_res)
        lay.addLayout(cards_row)
        lay.addSpacing(30)

        # Кнопка включения 4:3.
        self.button = ToggleButton()
        self.button.clicked.connect(self.c.toggle)
        lay.addWidget(self.button)
        lay.addSpacing(12)

        # Сообщение под кнопкой.
        self.message = _label("", "muted")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setFixedHeight(40)
        self.message.setStyleSheet("font-size: 13px;")
        lay.addWidget(self.message)

        # Кнопка Настройки — под кнопкой "Включить 4:3", по центру.
        self.settings_btn = _button("Настройки", "soft", lambda: self.settings.open_panel())
        self.settings_btn.setFixedSize(200, 44)
        lay.addWidget(self.settings_btn, alignment=Qt.AlignCenter)
        lay.addSpacing(20)

        # Нижний stretch.
        lay.addStretch(1)

    def _on_resolution_changed(self, mode: str):
        if mode == RESOLUTION_FHD:
            self.card_res.value_lab.setText("1440×1080")
        else:
            self.card_res.value_lab.setText("1728×1440")

    def showEvent(self, e):
        super().showEvent(e)
        win32.style_dark_frame(int(self.winId()))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            # Клик по водяному знаку — открываем ссылку на разработчика.
            if hasattr(self, '_wm_rect') and self._wm_rect.contains(e.position().toPoint()):
                webbrowser.open(TG_LINK)
                return
            if e.position().y() < 120:
                handle = self.windowHandle()
                if handle and handle.startSystemMove():
                    return
                self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def toggle_dev(self):
        self.dev.setVisible(not self.dev.isVisible())
        if self.dev.isVisible():
            self.dev.raise_()

    # -- state -------------------------------------------------------------------------------------------
    def _render(self, s: Snapshot):
        if s.booting:
            self.card_status.value_lab.setText("Запускается…")
            self.card_status.value_lab.setStyleSheet(f"color:{theme.ACCENT}; font-size: 18px; font-weight: 700;")
            self.dot.set_color(theme.ACCENT, True)
        elif s.running:
            self.card_status.value_lab.setText("Запущена")
            self.card_status.value_lab.setStyleSheet(f"color:{theme.GREEN}; font-size: 18px; font-weight: 700;")
            self.dot.set_color(theme.GREEN, s.phase == Phase.ACTIVE)
        else:
            self.card_status.value_lab.setText("Ожидание")
            self.card_status.value_lab.setStyleSheet(f"color:{theme.MUTED}; font-size: 18px; font-weight: 700;")
            self.dot.set_color(theme.FAINT, False)

        mode, ratio, lit = "—", 1.0, False
        if s.phase == Phase.ACTIVE:
            mode, ratio, lit = ("4:3 на весь экран", 1.0, True) if self.c.cfg.stretch_mode else ("4:3 с полосами", 0.75, True)
        elif s.phase == Phase.APPLYING:
            mode = "Переключаем…"
        elif s.phase == Phase.RESTORING:
            mode = "Возвращаем…"
        elif s.phase == Phase.LAUNCHING:
            mode = "Ждём игру…"
        elif s.running and not s.booting:
            mode = "Обычный 16:9"
        # glyph
        if not hasattr(self, '_glyph_widget'):
            self._glyph_widget = ModeGlyph()
        self._glyph_widget.set_mode(ratio, lit)

        if s.phase == Phase.ACTIVE:
            self.button.set_state("disable", "ВЫКЛЮЧИТЬ 4:3", "Вернуть обычный режим 16:9")
        elif s.phase == Phase.APPLYING:
            self.button.set_state("busy", "ВКЛЮЧАЕМ…", "Пара секунд")
        elif s.phase == Phase.RESTORING:
            self.button.set_state("busy", "ВЫКЛЮЧАЕМ…", "Пара секунд")
        elif s.phase == Phase.LAUNCHING:
            self.button.set_state("enable", "ЖДЁМ ИГРУ…", "Нажмите, чтобы отменить")
        else:
            self.button.set_state("enable", "ВКЛЮЧИТЬ 4:3",
                                  "Только для игры · рабочий стол не меняется" if s.running
                                  else "Rob-Run запустится автоматически")

        color = {"ok": theme.GREEN, "warn": theme.ACCENT, "error": theme.RED}.get(s.message_kind, "#A9AFBC")
        self.message.setStyleSheet(f"font-size: 13px; color:{color};")
        self.message.setText(s.message)

        self.settings.show_snapshot(s)
        if self.dev.isVisible():
            self.dev.show_snapshot(s)

        active = s.phase == Phase.ACTIVE
        self.tray_toggle.setText({Phase.ACTIVE: "Выключить 4:3", Phase.LAUNCHING: "Отменить ожидание"}
                                 .get(s.phase, "Включить 4:3"))
        self.tray_toggle.setEnabled(s.phase in (Phase.IDLE, Phase.ACTIVE, Phase.LAUNCHING))
        if active != self._tray_active:
            self._tray_active = active
            self.tray.setIcon(app_icon(active))
            self.tray.setToolTip(f"Rob-Run 4:3 — {'включён' if active else 'выключен'}")

    # -- tray ---------------------------------------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Rob-Run 4:3 — выключен")
        menu = QMenu()
        menu.addAction("Открыть", self.bring_to_front)
        self.tray_toggle = QAction("Включить 4:3", menu)
        self.tray_toggle.triggered.connect(self.c.toggle)
        menu.addAction(self.tray_toggle)
        menu.addSeparator()
        menu.addAction("Выход", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.bring_to_front() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self._tray_active = None

    def _notify(self, title: str, text: str, kind: str):
        icon = {"error": QSystemTrayIcon.Critical, "warn": QSystemTrayIcon.Warning}.get(
            kind, QSystemTrayIcon.Information)
        self.tray.showMessage(title, text, icon, 4000)

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if not self._quitting and self.c.cfg.minimize_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            e.ignore()
            self.hide()
            if not self.c.cfg.tray_hint_shown:
                self.tray.showMessage("Rob-Run 4:3", "Приложение работает в трее. Чтобы выйти — "
                                      "нажмите на значок правой кнопкой.", QSystemTrayIcon.Information, 4000)
                self.c.store.update(tray_hint_shown=True)
            return
        self.quit()
        e.accept()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self.hide()
        self.dev.hide()
        self.c.shutdown()
        self.tray.hide()
        QApplication.quit()
