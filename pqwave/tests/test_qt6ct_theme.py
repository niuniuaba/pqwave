"""Tests for the in-process qt6ct fallback.

The pip PyQt6 wheel bundles its own Qt build, so a distro qt6ct platform-theme
plugin compiled against a different Qt minor version is rejected by Qt's plugin
loader (QT_DEBUG_PLUGINS reports "uses incompatible Qt library"). These tests
cover the fallback that applies the same configuration qt6ct would apply.
"""

from pathlib import Path

from PyQt6.QtGui import QFont, QPalette

from pqwave.utils.qt6ct import apply_theme, load_palette, load_theme, parse_font

# qt6ct maps each list entry by index to QPalette::ColorRole, so index 10 is
# Window, 12 Highlight and 21 Accent.
ACTIVE = [f"#ff{i:02x}0000" for i in range(22)]
SCHEME = (
    "[ColorScheme]\n"
    f"active_colors={', '.join(ACTIVE)}\n"
    f"inactive_colors={', '.join(ACTIVE)}\n"
    f"disabled_colors={', '.join(ACTIVE)}\n"
)


def write_scheme(config_dir: Path) -> Path:
    path = config_dir / "nord.colors"
    path.write_text(SCHEME, encoding="utf-8")
    return path


def write_config(config_dir: Path) -> Path:
    scheme = write_scheme(config_dir)
    (config_dir / "qt6ct.conf").write_text(
        "[Appearance]\n"
        "custom_palette=true\n"
        f"color_scheme_path={scheme}\n"
        "style=Fusion\n"
        "\n"
        "[Fonts]\n"
        'general="JetBrainsMono Nerd Font,15,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,Regular,0,0"\n'
        'fixed="JetBrainsMono Nerd Font,12,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,Regular,0,0"\n'
        "\n"
        "[Interface]\n"
        "stylesheets=@Invalid()\n",
        encoding="utf-8",
    )
    return config_dir


def test_load_palette_maps_color_list_by_qt_role_index(tmp_path):
    palette = load_palette(write_scheme(tmp_path))

    assert palette is not None
    assert (
        palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window).name()
        == "#0a0000"
    )
    assert (
        palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight).name()
        == "#0c0000"
    )
    assert (
        palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Accent).name()
        == "#150000"
    )


def test_load_palette_rejects_short_color_lists(tmp_path):
    path = tmp_path / "short.colors"
    path.write_text("[ColorScheme]\nactive_colors=#ff000000\n", encoding="utf-8")

    assert load_palette(path) is None


def test_parse_font_reads_family_point_size_and_weight():
    font = parse_font(
        "JetBrainsMono Nerd Font,15,-1,5,400,0,0,0,0,0,0,0,0,0,0,1,Regular,0,0"
    )

    assert font is not None
    assert font.family() == "JetBrainsMono Nerd Font"
    assert font.pointSize() == 15
    assert font.weight() == QFont.Weight.Normal


def test_load_theme_reads_style_font_and_palette(tmp_path):
    theme = load_theme(write_config(tmp_path))

    assert theme is not None
    assert theme.style == "Fusion"
    assert theme.font is not None
    assert theme.font.family() == "JetBrainsMono Nerd Font"
    assert theme.palette is not None
    assert theme.style_sheet == ""


def test_apply_theme_sets_palette_font_and_style(qapp, tmp_path):
    write_config(tmp_path)
    saved_palette = qapp.palette()
    saved_font = qapp.font()
    saved_style_name = qapp.style().objectName()
    saved_sheet = qapp.styleSheet()
    try:
        applied = apply_theme(qapp, config_dir=tmp_path, platform_theme="qt6ct")

        assert applied is True
        assert qapp.palette().color(QPalette.ColorRole.Window).name() == "#0a0000"
        assert qapp.font().family() == "JetBrainsMono Nerd Font"
        assert qapp.style().objectName() == "fusion"
    finally:
        # setStyle() deletes the previous QStyle object, so restore by name.
        qapp.setStyle(saved_style_name)
        qapp.setPalette(saved_palette)
        qapp.setFont(saved_font)
        qapp.setStyleSheet(saved_sheet)


def test_apply_theme_ignores_other_platform_themes(qapp, tmp_path):
    write_config(tmp_path)

    assert apply_theme(qapp, config_dir=tmp_path, platform_theme="kde") is False


def test_apply_theme_skips_when_native_plugin_already_loaded(tmp_path):
    write_config(tmp_path)

    class _Style:
        def objectName(self):
            return "qt6ct-style"

    class _App:
        def style(self):
            return _Style()

    assert apply_theme(_App(), config_dir=tmp_path, platform_theme="qt6ct") is False


def test_apply_theme_without_config_returns_false(qapp, tmp_path):
    assert (
        apply_theme(qapp, config_dir=tmp_path / "missing", platform_theme="qt6ct")
        is False
    )
