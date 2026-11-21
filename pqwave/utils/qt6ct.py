"""Apply a qt6ct configuration without qt6ct's Qt plugin.

The pip PyQt6 wheel bundles its own Qt build. qt6ct's platform-theme plugin is
compiled by the distribution against the system Qt, and Qt rejects it when the
minor version differs from the bundled one. This module reproduces the parts of
qt6ct's platform theme that affect appearance: widget style, palette, general
font and user style sheets.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class Qt6ctTheme:
    style: str = ""
    palette: QPalette | None = None
    font: QFont | None = None
    style_sheet: str = ""


def load_palette(path: Path) -> QPalette | None:
    parser = _read_ini(path)
    if parser is None or not parser.has_section("ColorScheme"):
        return None

    section = parser["ColorScheme"]
    groups = (
        ("active_colors", QPalette.ColorGroup.Active),
        ("inactive_colors", QPalette.ColorGroup.Inactive),
        ("disabled_colors", QPalette.ColorGroup.Disabled),
    )
    color_lists: list[tuple[list[str], QPalette.ColorGroup]] = []
    for key, group in groups:
        colors = [c.strip() for c in section.get(key, "").split(",") if c.strip()]
        color_lists.append((colors, group))

    # qt6ct appends the highlight color when a scheme predates the Accent role.
    # PyQt6 stubs type the enum's value as the enum itself; at runtime it is int.
    accent = cast(int, QPalette.ColorRole.Accent.value)
    highlight = cast(int, QPalette.ColorRole.Highlight.value)
    role_count = cast(int, QPalette.ColorRole.NColorRoles.value)
    for colors, _ in color_lists:
        if len(colors) == accent:
            colors.append(colors[highlight])
        if len(colors) < role_count:
            return None

    palette = QPalette()
    for colors, group in color_lists:
        for index in range(role_count):
            color = QColor(colors[index])
            if not color.isValid():
                return None
            palette.setColor(group, QPalette.ColorRole(index), color)
    return palette


def parse_font(value: str) -> QFont | None:
    parts = [part.strip() for part in value.strip().strip('"').split(",")]
    if len(parts) < 2 or not parts[0]:
        return None
    try:
        point_size = int(float(parts[1]))
    except ValueError:
        return None

    font = QFont(parts[0])
    if point_size > 0:
        font.setPointSize(point_size)
    if len(parts) > 4:
        try:
            font.setWeight(QFont.Weight(int(parts[4])))
        except ValueError:
            pass
    return font


def load_theme(config_dir: Path | None = None) -> Qt6ctTheme | None:
    directory = Path(config_dir) if config_dir is not None else _default_config_dir()
    parser = _read_ini(directory / "qt6ct.conf")
    if parser is None:
        return None

    appearance = parser["Appearance"] if parser.has_section("Appearance") else None
    style = "" if appearance is None else str(appearance.get("style", "")).strip()

    palette = None
    if appearance is not None and appearance.getboolean(
        "custom_palette", fallback=False
    ):
        scheme_path = _resolve_path(str(appearance.get("color_scheme_path", "")))
        if scheme_path.is_file():
            palette = load_palette(scheme_path)

    font = None
    if parser.has_section("Fonts"):
        font = parse_font(parser["Fonts"].get("general", ""))

    style_sheet = _load_style_sheets(parser, directory)

    if not (style or palette is not None or font is not None or style_sheet):
        return None
    return Qt6ctTheme(style=style, palette=palette, font=font, style_sheet=style_sheet)


def apply_theme(
    app: QApplication,
    config_dir: Path | None = None,
    platform_theme: str | None = None,
) -> bool:
    theme_name = (
        os.environ.get("QT_QPA_PLATFORMTHEME", "")
        if platform_theme is None
        else platform_theme
    )
    if theme_name != "qt6ct":
        return False
    style = app.style()
    if style is not None and style.objectName() == "qt6ct-style":
        return False

    theme = load_theme(config_dir)
    if theme is None:
        return False

    if theme.style:
        # Style before palette: setStyle() may install the style's own palette.
        app.setStyle(theme.style)
    if theme.palette is not None:
        app.setPalette(theme.palette)
    if theme.font is not None:
        app.setFont(theme.font)
    if theme.style_sheet:
        app.setStyleSheet(theme.style_sheet + app.styleSheet())
    return True


def _default_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "qt6ct"


def _read_ini(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        if not parser.read(path, encoding="utf-8"):
            return None
    except (configparser.Error, OSError):
        return None
    return parser


def _resolve_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value.strip())))


def _load_style_sheets(parser: configparser.ConfigParser, directory: Path) -> str:
    if not parser.has_section("Interface"):
        return ""
    value = parser["Interface"].get("stylesheets", "")
    chunks: list[str] = []
    for entry in value.split(","):
        entry = entry.strip()
        if not entry or entry.startswith("@Invalid"):
            continue
        path = _resolve_path(entry)
        if not path.is_absolute():
            path = directory / path
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(chunks)
