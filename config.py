"""Persistent settings, app constants and the Windows autostart entry."""
from __future__ import annotations

import json
import logging
import os
import sys
import winreg
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "RobRun 4:3"
APP_ID = "RobRun43Tool"
APP_VERSION = "2.0.0"

STEAM_APP_ID = 4262460
GAME_EXE_NAME = "ROB RUN.exe"
GAME_WINDOW_CLASS = "UnityWndClass"
UNITY_PREFS_KEY = r"Software\Kefir\ROB RUN"

# Целевые разрешения по режиму монитора.
# 2K (2560×1440)  →  1728×1440 (4:3)
# Full HD (1920×1080) → 1440×1080 (4:3)
DEFAULT_2K_W, DEFAULT_2K_H = 1728, 1440
DEFAULT_FHD_W, DEFAULT_FHD_H = 1440, 1080

RESOLUTION_AUTO = "auto"      # определить монитор автоматически
RESOLUTION_2K = "2k"          # 1728×1440
RESOLUTION_FHD = "fhd"        # 1440×1080

RESOLUTION_LABELS = {
    RESOLUTION_AUTO: "Авто (по монитору)",
    RESOLUTION_2K: "2K — 1728×1440",
    RESOLUTION_FHD: "Full HD — 1440×1080",
}

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_ID
CONFIG_PATH = DATA_DIR / "settings.json"
LOG_PATH = DATA_DIR / "app.log"

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

log = logging.getLogger(__name__)


@dataclass
class Settings:
    game_exe: str = ""
    launch_with_windows: bool = False
    minimize_to_tray: bool = True
    auto_apply_on_launch: bool = False
    stretch_mode: bool = False
    tray_hint_shown: bool = False
    # Режим целевого разрешения: auto | 2k | fhd
    resolution_mode: str = RESOLUTION_AUTO
    # Снимок экранных настроек Unity, хранится пока сессия 4:3 активна.
    prefs_snapshot: dict | None = field(default=None)


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.settings = self._load()

    def _load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in Settings.__dataclass_fields__}
            return Settings(**known)
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError, TypeError) as e:
            log.warning("Settings file unreadable (%s), using defaults", e)
            return Settings()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.settings), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def update(self, **changes) -> None:
        for k, v in changes.items():
            setattr(self.settings, k, v)
        self.save()


def target_resolution(mode: str | None = None) -> tuple[int, int]:
    """Вернуть (ширина, высота) целевого окна игры для заданного режима разрешения.

    Если mode is None или "auto" — разрешение монитора определяется автоматически
    (через PySide6, см. ui.controller). При невозможности определить — 1728×1440.
    """
    if mode in (None, RESOLUTION_AUTO):
        return DEFAULT_2K_W, DEFAULT_2K_H
    if mode == RESOLUTION_FHD:
        return DEFAULT_FHD_W, DEFAULT_FHD_H
    return DEFAULT_2K_W, DEFAULT_2K_H


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    main = Path(__file__).resolve().parent / "main.py"
    return f'"{interpreter}" "{main}" --minimized'


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_ID)
            return True
    except FileNotFoundError:
        return False
