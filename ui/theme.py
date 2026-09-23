"""Tema «Nocturne»: la interfaz oscura y compacta de Beam Calculator.

Los valores salen del sistema de diseño Nocturne (``UI_Design/…/styles.css``):
un fondo gris azulado casi neutro, texto claro, **un solo acento** violeta que
se usa como línea y no como relleno, radios de 8 px y la fuente Inter.

Tres reglas de Nocturne que se traducen a Qt:

* Los botones van **con contorno**: borde de 1 px sobre fondo transparente. El
  principal lleva el borde y el texto en acento; el secundario, borde de
  división y texto normal.
* Las tarjetas son superficies apenas más claras que el fondo, con un filo de
  1 px en lugar de sombra.
* El contraste sale de las rampas tonales, no de la saturación: los colores de
  estado (bien, aviso, error) están desaturados para no competir con el acento.

Qt no acepta ``color-mix`` ni ``text-transform``, así que las mezclas se
resuelven acá con :func:`mix` y los rótulos en versalitas se escriben en
mayúsculas donde se crean.
"""
from PyQt6.QtGui import QFontDatabase

# ---------- Tokens de Nocturne ----------

NOCTURNE = {
    "bg":          "#161826",
    "surface":     "#232532",
    "text":        "#e9e9ed",
    "accent":      "#9184d9",
    "neutral_300": "#cfd3e5",
    "neutral_600": "#75798c",
    "neutral_800": "#3f424d",
    "neutral_900": "#292b31",
    "accent_100":  "#f5f4ff",
    "accent_400":  "#b5abfc",
    "accent_600":  "#796cbf",
    "accent_800":  "#423a6a",
    "accent_900":  "#2b2741",
}

# Fuente del sistema de diseño, con la de Windows como respaldo si Inter no
# está instalada.
FONT_STACK = ("Inter", "Segoe UI Variable Text", "Segoe UI")


# ---------- Helpers de color ----------

def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple) -> str:
    return "#" + "".join(f"{int(round(c)):02x}" for c in rgb)


def mix(c1: str, c2: str, ratio: float) -> str:
    """Mezcla dos colores hex con un ratio (0 = c1, 1 = c2)."""
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


def font_family() -> str:
    """Primera fuente de :data:`FONT_STACK` disponible en el sistema."""
    try:
        disponibles = set(QFontDatabase.families())
    except Exception:          # sin QApplication todavía
        return FONT_STACK[-1]
    return next((f for f in FONT_STACK if f in disponibles), FONT_STACK[-1])


# ---------- Paleta semántica ----------

class Palette:
    """Roles semánticos que usan los paneles y los diagramas."""

    def __init__(self, t=NOCTURNE):
        bg, text = t["bg"], t["text"]

        # Fondos
        self.bg_base = bg
        self.bg_surface = t["surface"]                 # tarjetas, panel lateral
        self.bg_elevated = mix(t["surface"], text, 0.05)
        self.bg_input = t["surface"]                   # .input usa la superficie
        self.bg_hover = mix(t["surface"], text, 0.07)
        self.bg_selected = t["accent_800"]
        self.bg_bar = t["neutral_900"]                 # barra de estado

        # Texto: Nocturne atenúa mezclando con el fondo, no bajando opacidad.
        self.text_primary = text
        self.text_secondary = mix(bg, text, 0.70)
        self.text_muted = mix(bg, text, 0.55)

        # Bordes
        self.border = mix(bg, text, 0.16)              # --color-divider
        self.border_strong = t["neutral_800"]          # filo de las tarjetas
        self.border_hover = mix(bg, text, 0.45)
        self.border_focus = t["accent"]

        # Acento
        self.accent = t["accent"]
        self.accent_hover = t["accent_400"]
        self.accent_pressed = t["accent_600"]
        self.accent_tint = t["accent_900"]             # fondo de íconos
        self.accent_soft = t["accent_800"]             # etiquetas
        self.accent_on_soft = t["accent_100"]

        # Estados, desaturados para convivir con el acento
        self.ok = "#86c9a4"
        self.warning = "#d9b26f"
        self.error = "#e07a88"
        self.info = "#86b8e0"

        # Diagramas
        self.concrete = mix(t["surface"], text, 0.10)
        self.concrete_edge = t["neutral_600"]
        self.compression = self.error
        self.tension = self.info
        self.neutral_axis = self.ok
        self.steel = t["neutral_300"]
        self.dim_lines = self.text_muted


PALETTE: Palette = Palette()


def reload_palette():
    """Recarga la paleta (compatibilidad con la versión anterior del tema)."""
    global PALETTE
    PALETTE = Palette()


# ---------- Hoja de estilos ----------

def build_stylesheet() -> str:
    p = PALETTE
    fuente = font_family()
    return f"""
QMainWindow, QWidget {{
    background-color: {p.bg_base};
    color: {p.text_primary};
    font-family: '{fuente}';
    font-size: 10pt;
}}
QLabel, #torsionOptions {{ background: transparent; }}
QToolTip {{
    background: {p.bg_elevated}; color: {p.text_primary};
    border: 1px solid {p.border}; padding: 6px;
}}
QScrollArea {{ background: transparent; border: none; }}

/* ---- barra superior del espacio de trabajo ---- */
#headerFrame {{
    background: {p.bg_base};
    border-bottom: 1px solid {p.border};
}}
#headerTitle {{ font-size: 13.5pt; font-weight: 500; }}
#headerSubtitle {{ color: {p.text_muted}; font-size: 8.5pt; }}

/* ---- pantalla de inicio ---- */
#homeAside {{ background: {p.bg_surface}; }}
#homeAside QLabel {{ background: transparent; }}
#fieldBox, #segmented {{ background: transparent; }}
#brandTitle {{ font-size: 13.5pt; font-weight: 500; }}
#brandVersion {{ color: {p.text_muted}; font-size: 8pt; }}
#kicker {{ color: {p.accent}; font-size: 7.5pt; font-weight: 600; }}
#fieldCaption {{ color: {p.text_secondary}; font-size: 9pt; }}
#homeHeading {{ font-size: 19pt; font-weight: 500; }}
#sectionHeading {{ font-size: 11.5pt; font-weight: 500; }}
#elementCard {{
    background: {p.bg_surface}; border: 1px solid {p.border_strong};
    border-radius: 8px;
}}
#elementCard:hover, #elementCard:focus {{ border: 1px solid {p.accent}; }}
#elementCard QLabel {{ background: transparent; }}
#cardTitle {{ font-size: 13pt; font-weight: 500; }}
#cardBody {{ color: {p.text_secondary}; font-size: 9.5pt; }}
#emptyNote {{ color: {p.text_muted}; font-size: 9pt; }}

/* ---- cabecera del elemento ---- */
#iconButton {{
    color: {p.text_primary}; border: 1px solid {p.border}; border-radius: 8px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    padding: 0; font-size: 12pt; background: transparent;
}}
#iconButton:hover {{ background: {alpha(p.text_primary, 0.07)}; }}
#iconButton:focus {{ border: 1px solid {p.accent}; }}
#tag {{
    background: {p.accent_soft}; color: {p.accent_on_soft};
    border-radius: 6px; padding: 2px 9px; font-size: 8pt; font-weight: 600;
}}

/* ---- pestaña de geometría ---- */
#geometryBody {{ background: transparent; }}
#panelHint {{ color: {p.text_secondary}; font-size: 9pt; }}
#rowLabel {{ color: {p.text_primary}; font-size: 9.5pt; }}
#stepper {{
    background: {p.bg_surface}; border: 1px solid {p.border}; border-radius: 8px;
}}
#stepper:hover {{ border: 1px solid {p.border_hover}; }}
QDoubleSpinBox#stepperValue {{
    background: transparent; border: none; padding: 0 2px; min-height: 28px;
    font-weight: 600; font-size: 10.5pt;
}}
QDoubleSpinBox#stepperValue:hover, QDoubleSpinBox#stepperValue:focus {{ border: none; }}
#stepperUnit {{ color: {p.text_muted}; font-size: 8pt; }}
#stepperButton {{
    background: transparent; border: none; color: {p.text_secondary};
    font-size: 12pt; min-width: 26px; padding: 0;
}}
#stepperButton:hover {{ color: {p.accent}; }}
#shapeTile {{
    background: {p.bg_surface}; color: {p.text_primary};
    border: 1px solid {p.border_strong}; border-radius: 8px;
    padding: 8px 4px; font-size: 9pt;
}}
#shapeTile:hover {{ border: 1px solid {p.border_hover}; }}
#shapeTile:checked {{ background: {p.accent_tint}; border: 1px solid {p.accent}; }}
#previewCard {{
    background: {p.bg_base}; border: 1px solid {p.border_strong}; border-radius: 12px;
}}
#previewTitle {{ color: {p.text_primary}; font-size: 9.5pt; }}
#propsStrip {{
    background: {p.bg_surface}; border-top: 1px solid {p.border_strong};
    border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
}}
#statCaption {{ color: {p.text_muted}; font-size: 8pt; }}
#statValue {{ color: {p.text_primary}; font-size: 11.5pt; font-weight: 600; }}

/* ---- control segmentado (normativa) ---- */
#segmented {{
    border: 1px solid {p.border}; border-radius: 8px; background: transparent;
}}
#segOption {{
    background: transparent; color: {p.text_primary};
    border: 1px solid transparent; border-radius: 7px; padding: 6px 10px;
    font-weight: 400; font-size: 9.5pt; min-height: 18px;
}}
#segOption:hover:!checked {{ background: {p.bg_hover}; }}
#segOption:checked {{ color: {p.accent}; border: 1px solid {p.accent}; }}

/* ---- pestañas ---- */
QTabWidget::pane {{ border: none; border-top: 1px solid {p.border}; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{
    background: transparent; color: {p.text_secondary};
    padding: 11px 16px; margin-right: 6px;
    border-bottom: 2px solid transparent; font-weight: 500;
}}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom: 2px solid {p.accent}; }}
QTabBar::tab:hover:!selected {{ color: {p.text_primary}; }}

/* ---- tarjetas de formulario y resultados ---- */
#panelTitle {{ font-size: 12pt; font-weight: 500; padding: 2px 0; }}
QGroupBox {{
    background: {p.bg_surface}; border: 1px solid {p.border_strong};
    border-radius: 8px; margin-top: 14px; padding: 14px 10px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 6px; left: 10px; color: {p.accent};
}}
QGroupBox::indicator {{ width: 15px; height: 15px; }}
#fieldLabel {{ color: {p.text_secondary}; }}
#unitLabel, #infoLabel {{ color: {p.text_muted}; font-size: 9pt; }}
#infoLabel {{ padding: 2px 0; }}
#valueLabel {{
    font-family: 'Consolas'; font-weight: 600; padding: 4px 6px;
    background: transparent; min-width: 70px;
}}
#asDesignLabel {{ font-size: 14pt; font-weight: 500; color: {p.accent}; padding: 6px; }}

/* ---- campos (.input) ---- */
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit, QPlainTextEdit {{
    background: {p.bg_input}; color: {p.text_primary};
    border: 1px solid {p.border}; border-radius: 8px;
    min-height: 24px; padding: 5px 9px;
    selection-background-color: {alpha(p.accent, 0.30)};
    selection-color: {p.text_primary};
}}
QDoubleSpinBox:hover, QSpinBox:hover, QComboBox:hover,
QLineEdit:hover, QPlainTextEdit:hover {{ border: 1px solid {p.border_hover}; }}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus,
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {p.accent}; }}
QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {p.text_muted}; }}
QComboBox QAbstractItemView {{
    background: {p.bg_elevated}; color: {p.text_primary};
    border: 1px solid {p.border}; outline: none;
    selection-background-color: {p.accent_soft}; selection-color: {p.accent_on_soft};
}}
QCheckBox {{ background: transparent; spacing: 8px; }}

/* ---- botones: con contorno, nunca rellenos ---- */
QPushButton {{
    background: transparent; color: {p.accent};
    border: 1px solid {p.accent}; border-radius: 8px;
    padding: 6px 12px; min-height: 22px; font-weight: 500;
}}
QPushButton:hover {{ background: {alpha(p.accent, 0.12)}; }}
QPushButton:pressed {{ background: {alpha(p.accent, 0.22)}; }}
QPushButton:focus {{ border: 1px solid {p.accent_hover}; }}
QPushButton:disabled {{ color: {p.text_muted}; border-color: {p.border}; }}
#secondaryButton {{ color: {p.text_primary}; border: 1px solid {p.border}; }}
#secondaryButton:hover {{ background: {alpha(p.text_primary, 0.07)}; }}
#secondaryButton:pressed {{ background: {alpha(p.text_primary, 0.14)}; }}
#secondaryButton:focus {{ border: 1px solid {p.accent}; }}
#detailsToggle {{
    background: {p.bg_surface}; color: {p.text_secondary};
    text-align: left; padding: 10px 12px; border: 1px solid {p.border_strong};
}}
#detailsToggle:hover, #detailsToggle:checked {{ color: {p.accent}; background: {p.bg_elevated}; }}
#detailsToggle:focus {{ border: 1px solid {p.accent}; }}

/* ---- tabla de estudios recientes (.table) ---- */
QTableWidget#recentTable {{
    background: transparent; border: none; gridline-color: transparent;
    font-size: 10pt; outline: none;
}}
QTableWidget#recentTable::item {{
    border-bottom: 1px solid {mix(p.bg_base, p.text_primary, 0.08)};
    padding: 6px 4px;
}}
QTableWidget#recentTable::item:hover {{ background: {alpha(p.text_primary, 0.04)}; }}
QTableWidget#recentTable::item:selected {{
    background: {alpha(p.accent, 0.12)}; color: {p.text_primary};
}}
QHeaderView::section {{
    background: transparent; color: {p.text_muted}; border: none;
    border-bottom: 1px solid {p.border}; padding: 6px 4px;
    font-size: 8pt; font-weight: 600;
}}

/* ---- avisos, estado, divisores ---- */
#warningLabel {{
    background: {alpha(p.warning, 0.10)}; color: {p.warning};
    border-left: 3px solid {p.warning}; border-radius: 4px; padding: 10px;
}}
QStatusBar {{
    background: {p.bg_bar}; color: {p.text_muted};
    border-top: none; font-size: 8.5pt;
}}
QStatusBar QLabel {{ color: {p.text_muted}; background: transparent; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle:horizontal {{ background: {p.border}; width: 1px; margin: 12px 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""
