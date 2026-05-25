"""Tema oscuro basado en los colores del tema actual de Omarchy.

Lee ~/.config/omarchy/current/theme/colors.toml en runtime y deriva una
paleta cohesiva para toda la aplicación. Si no encuentra los colores,
cae a un tema oscuro por defecto razonable.
"""
from pathlib import Path
from typing import Dict


# Defaults razonables si no se encuentra Omarchy (tema oscuro genérico)
DEFAULT_COLORS = {
    "background": "#0e0f1a",
    "foreground": "#e6e6e6",
    "accent":     "#7aa2f7",
    "color0":     "#2a2e3e",
    "color1":     "#f7768e",  # rojo (compresión)
    "color2":     "#9ece6a",  # verde (ok, eje neutro)
    "color3":     "#e0af68",  # amarillo (warning)
    "color4":     "#7aa2f7",  # azul
    "color5":     "#bb9af7",  # magenta
    "color6":     "#7dcfff",  # cyan (tensión)
    "color7":     "#c0caf5",
    "color8":     "#414868",
    "color9":     "#f7768e",
    "color10":    "#9ece6a",
    "color11":    "#e0af68",
    "color12":    "#7aa2f7",
    "color13":    "#bb9af7",
    "color14":    "#7dcfff",
    "color15":    "#a9b1d6",
}


def _parse_colors_toml(path: Path) -> Dict[str, str]:
    """Lee un archivo colors.toml simple (clave = "valor")."""
    colors: Dict[str, str] = {}
    if not path.exists():
        return colors
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.startswith("#"):
                colors[key] = value
    except OSError:
        pass
    return colors


def load_theme() -> Dict[str, str]:
    """Carga el tema actual de Omarchy o cae a los defaults."""
    omarchy_path = Path.home() / ".config" / "omarchy" / "current" / "theme" / "colors.toml"
    colors = _parse_colors_toml(omarchy_path)
    # Mezclar con defaults para asegurar todas las claves
    merged = dict(DEFAULT_COLORS)
    merged.update({k: v for k, v in colors.items() if v})
    return merged


# ---------- Helpers de color ----------

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple) -> str:
    return "#" + "".join(f"{int(c):02x}" for c in rgb)


def mix(c1: str, c2: str, ratio: float) -> str:
    """Mezcla dos colores hex con un ratio (0=c1, 1=c2)."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((
        r1 + (r2 - r1) * ratio,
        g1 + (g2 - g1) * ratio,
        b1 + (b2 - b1) * ratio,
    ))


def alpha(color: str, a: float) -> str:
    """Devuelve rgba(r, g, b, a) a partir de un color hex."""
    r, g, b = _hex_to_rgb(color)
    return f"rgba({r}, {g}, {b}, {a:.2f})"


# ---------- Paleta semántica derivada ----------

class Palette:
    """Roles semánticos derivados de la paleta base."""

    def __init__(self, colors: Dict[str, str]):
        self.raw = colors

        bg = colors["background"]
        fg = colors["foreground"]
        white = "#ffffff"
        black = "#000000"

        # Capas de fondo (oscuro → claro)
        self.bg_base = bg                              # Fondo principal
        self.bg_surface = mix(bg, white, 0.06)         # Cards/panels
        self.bg_elevated = mix(bg, white, 0.12)        # Group boxes
        self.bg_input = mix(bg, white, 0.10)           # Spinboxes
        self.bg_hover = mix(bg, white, 0.16)           # Hover
        self.bg_selected = colors["color8"]            # Selecciones

        # Texto
        self.text_primary = fg
        self.text_secondary = mix(fg, bg, 0.35)
        self.text_muted = mix(fg, bg, 0.55)

        # Bordes
        self.border = mix(bg, white, 0.18)
        self.border_strong = colors["color0"]
        self.border_focus = colors["accent"]

        # Acentos semánticos
        self.accent = colors["accent"]
        self.accent_hover = mix(colors["accent"], white, 0.12)
        self.accent_pressed = mix(colors["accent"], black, 0.15)

        # Estados
        self.ok = colors["color2"]
        self.warning = colors["color3"]
        self.error = colors["color1"]
        self.info = colors["color6"]

        # Diagrama de esfuerzos
        self.concrete = mix(bg, white, 0.18)
        self.concrete_edge = mix(bg, white, 0.35)
        self.compression = colors["color1"]     # rojo
        self.tension = colors["color6"]         # cyan/azul
        self.neutral_axis = colors["color2"]    # verde
        self.steel = colors["color7"]           # claro/contraste
        self.dim_lines = self.text_muted


PALETTE: Palette = Palette(load_theme())


def reload_palette():
    """Recarga la paleta (útil tras cambio de tema)."""
    global PALETTE
    PALETTE = Palette(load_theme())


# ---------- Stylesheet QSS ----------

def build_stylesheet() -> str:
    p = PALETTE
    return f"""
QMainWindow, QWidget {{
    background-color: {p.bg_base};
    color: {p.text_primary};
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}

#headerFrame {{
    background-color: {p.bg_surface};
    border-bottom: 2px solid {p.accent};
}}

#headerTitle {{
    color: {p.text_primary};
    font-size: 18pt;
    font-weight: bold;
    padding: 8px 16px;
    background-color: transparent;
}}

#headerSubtitle {{
    color: {p.text_secondary};
    font-size: 10pt;
    padding: 0px 16px 8px 16px;
    background-color: transparent;
}}

QTabWidget::pane {{
    border: 1px solid {p.border};
    background: {p.bg_surface};
    border-radius: 4px;
    top: -1px;
}}

QTabBar::tab {{
    background: {p.bg_elevated};
    color: {p.text_secondary};
    padding: 10px 24px;
    font-size: 11pt;
    font-weight: 600;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    border: 1px solid {p.border};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background: {p.accent};
    color: {p.bg_base};
    border: 1px solid {p.accent};
}}

QTabBar::tab:hover:!selected {{
    background: {p.bg_hover};
    color: {p.text_primary};
}}

QGroupBox {{
    background-color: {p.bg_surface};
    border: 1px solid {p.border};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
    color: {p.text_primary};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: {p.bg_surface};
    color: {p.accent};
    font-size: 10pt;
}}

#panelTitle {{
    font-size: 13pt;
    font-weight: bold;
    color: {p.text_primary};
    padding: 8px;
    background-color: {p.bg_elevated};
    border-radius: 4px;
}}

QLabel {{
    color: {p.text_primary};
    background-color: transparent;
}}

#fieldLabel {{
    color: {p.text_primary};
    font-size: 10pt;
}}

#unitLabel {{
    color: {p.text_muted};
    font-size: 9pt;
    font-style: italic;
}}

#infoLabel {{
    color: {p.text_muted};
    font-size: 9pt;
    font-style: italic;
    padding: 4px;
}}

#valueLabel {{
    color: {p.text_primary};
    font-family: 'JetBrains Mono', 'Fira Code', 'Monospace', 'Courier New';
    font-size: 10pt;
    font-weight: 600;
    background-color: {p.bg_input};
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid {p.border};
    min-width: 80px;
}}

#asDesignLabel {{
    color: {p.ok};
    font-size: 12pt;
    font-weight: bold;
    background-color: {alpha(p.ok, 0.10)};
    border: 1px solid {alpha(p.ok, 0.40)};
}}

QDoubleSpinBox {{
    padding: 4px 6px;
    border: 1px solid {p.border};
    border-radius: 4px;
    background: {p.bg_input};
    color: {p.text_primary};
    font-size: 10pt;
    min-height: 22px;
    selection-background-color: {p.accent};
    selection-color: {p.bg_base};
}}

QDoubleSpinBox:focus {{
    border: 1px solid {p.border_focus};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {p.bg_elevated};
    border: none;
    width: 16px;
}}

QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {p.bg_hover};
}}

QComboBox {{
    padding: 6px 12px;
    border: 1px solid {p.border};
    border-radius: 4px;
    background: {p.bg_input};
    color: {p.text_primary};
    font-size: 10pt;
    min-height: 22px;
    selection-background-color: {p.accent};
    selection-color: {p.bg_base};
}}

QComboBox:hover {{
    border: 1px solid {p.border_focus};
}}

QComboBox QAbstractItemView {{
    background-color: {p.bg_elevated};
    color: {p.text_primary};
    border: 1px solid {p.border};
    selection-background-color: {p.accent};
    selection-color: {p.bg_base};
    outline: none;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    background-color: {p.bg_elevated};
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.accent};
    margin-right: 6px;
}}

QPushButton {{
    background-color: {p.accent};
    color: {p.bg_base};
    border: none;
    padding: 8px 24px;
    border-radius: 4px;
    font-size: 11pt;
    font-weight: 600;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: {p.accent_hover};
}}

QPushButton:pressed {{
    background-color: {p.accent_pressed};
}}

#calcButton {{
    background-color: {p.ok};
    color: {p.bg_base};
}}

#calcButton:hover {{
    background-color: {mix(p.ok, '#ffffff', 0.15)};
}}

QTableWidget {{
    border: 1px solid {p.border};
    border-radius: 4px;
    gridline-color: {p.border};
    background-color: {p.bg_input};
    color: {p.text_primary};
    selection-background-color: {p.accent};
    selection-color: {p.bg_base};
    alternate-background-color: {p.bg_elevated};
}}

QTableWidget::item {{
    padding: 6px;
}}

QHeaderView::section {{
    background-color: {p.bg_elevated};
    color: {p.accent};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {p.border};
    font-weight: 600;
}}

#warningLabel {{
    background-color: {alpha(p.warning, 0.15)};
    color: {p.warning};
    border: 1px solid {alpha(p.warning, 0.50)};
    border-radius: 4px;
    padding: 8px;
    font-weight: 600;
}}

QStatusBar {{
    background-color: {p.bg_surface};
    color: {p.text_secondary};
    font-size: 9pt;
    border-top: 1px solid {p.border};
}}

QSplitter::handle {{
    background-color: {p.border};
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QScrollBar:vertical {{
    background: {p.bg_base};
    width: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {p.bg_elevated};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p.bg_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}

QScrollBar:horizontal {{
    background: {p.bg_base};
    height: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {p.bg_elevated};
    border-radius: 6px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p.bg_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    background: transparent;
}}
"""
