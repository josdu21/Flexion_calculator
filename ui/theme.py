"""Tema oscuro basado en los colores del tema actual de Omarchy.

Lee ~/.config/omarchy/current/theme/colors.toml en runtime y deriva una
paleta cohesiva para toda la aplicación. Si no encuentra los colores,
cae a un tema oscuro por defecto razonable.
"""
from pathlib import Path
from typing import Dict


# Defaults razonables si no se encuentra Omarchy (tema oscuro genérico)
DEFAULT_COLORS = {
    "background": "#111820",
    "foreground": "#e6e6e6",
    "accent":     "#7cbeb5",
    "color0":     "#2a2e3e",
    "color1":     "#f7768e",  # rojo (compresión)
    "color2":     "#9ece6a",  # verde (ok, eje neutro)
    "color3":     "#e0af68",  # amarillo (warning)
    "color4":     "#7cbeb5",  # azul
    "color5":     "#bb9af7",  # magenta
    "color6":     "#7dcfff",  # cyan (tensión)
    "color7":     "#c0caf5",
    "color8":     "#414868",
    "color9":     "#f7768e",
    "color10":    "#9ece6a",
    "color11":    "#e0af68",
    "color12":    "#7cbeb5",
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
        self.text_muted = mix(fg, bg, 0.36)

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
    font-family: 'Segoe UI';
    font-size: 10pt;
}}
QLabel, #torsionOptions {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
#headerFrame {{
    background: {p.bg_surface};
    border-bottom: 1px solid {p.border};
}}
#headerTitle {{ font-size: 18pt; font-weight: 600; }}
#headerSubtitle {{ color: {p.text_secondary}; font-size: 9pt; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {p.border}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {p.text_secondary};
    padding: 12px 18px; margin-right: 8px;
    border-bottom: 3px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom: 3px solid {p.accent}; }}
QTabBar::tab:hover:!selected {{ background: {p.bg_surface}; color: {p.text_primary}; }}
#panelTitle {{ font-size: 12pt; font-weight: 600; padding: 2px 0; }}
QGroupBox {{
    background: {p.bg_surface}; border: 1px solid {p.border};
    border-radius: 8px; margin-top: 12px; padding: 12px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 6px; left: 10px; color: {p.text_secondary};
}}
#fieldLabel {{ color: {p.text_secondary}; }}
#unitLabel, #infoLabel {{ color: {p.text_muted}; font-size: 9pt; }}
#infoLabel {{ padding: 2px 0; }}
#valueLabel {{
    font-family: 'Consolas'; font-weight: 600; padding: 4px 6px;
    background: transparent; min-width: 70px;
}}
#asDesignLabel {{ font-size: 14pt; font-weight: 600; color: {p.accent}; padding: 6px; }}
QDoubleSpinBox, QSpinBox, QComboBox {{
    background: {p.bg_input}; color: {p.text_primary};
    border: 1px solid {p.border}; border-radius: 5px;
    min-height: 24px; padding: 4px 6px;
    selection-background-color: {p.accent}; selection-color: {p.bg_base};
}}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p.accent}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p.text_muted}; }}
QComboBox QAbstractItemView {{
    background: {p.bg_elevated}; color: {p.text_primary};
    selection-background-color: {p.accent}; selection-color: {p.bg_base};
}}
QPushButton {{
    background: {p.accent}; color: {p.bg_base}; border: 1px solid transparent;
    border-radius: 6px; padding: 8px 16px; min-height: 22px; font-weight: 600;
}}
QPushButton:hover {{ background: {p.accent_hover}; }}
QPushButton:pressed {{ background: {p.accent_pressed}; }}
QPushButton:focus {{ border: 1px solid {p.text_primary}; }}
#detailsToggle {{
    background: {p.bg_surface}; color: {p.text_secondary};
    text-align: left; padding: 10px 12px; border: 1px solid {p.border};
}}
#detailsToggle:hover, #detailsToggle:checked {{ color: {p.accent}; background: {p.bg_elevated}; }}
#detailsToggle:focus {{ border: 1px solid {p.accent}; }}
QGroupBox::indicator {{ width: 16px; height: 16px; }}
#warningLabel {{
    background: {alpha(p.warning, 0.10)}; color: {p.warning};
    border-left: 3px solid {p.warning}; border-radius: 4px; padding: 10px;
}}
QStatusBar {{
    background: {p.bg_surface}; color: {p.text_secondary};
    border-top: 1px solid {p.border}; font-size: 9pt;
}}
QStatusBar::item {{ border: none; }}
QSplitter::handle:horizontal {{ background: {p.border}; width: 1px; margin: 12px 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""
