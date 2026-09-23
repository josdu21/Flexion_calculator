"""Pestaña «Geometría y sección»: forma, dimensiones y materiales.

Es la única dueña de esos datos. Las pestañas de flexión y de cortante del mismo
elemento leen de acá en vez de tener cada una su copia.

Distribución (mockup de ``UI_Design``):

* A la izquierda, el formulario: la forma en tres mosaicos, las dimensiones y
  los materiales en campos con botones −/+, y «Continuar a Flexión».
* A la derecha, la sección transversal acotada, con el recubrimiento y el
  centroide como capas que se prenden y apagan, y abajo una franja con las
  propiedades de la sección bruta: A_g, ȳ, I_g, E_c y β₁.
"""
import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QButtonGroup, QComboBox, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QToolButton,
    QVBoxLayout, QWidget,
)

from core.design_code import DEFAULT_CODE, DesignCode
from core.section_geometry import SectionProfile, SectionShape
from core.units import UnitSystem, get_converter
from ui.form_helpers import set_choice, set_si
from ui.theme import PALETTE


SECTION_SHAPES = [
    ("Rectangular", SectionShape.RECTANGULAR),
    ("T", SectionShape.T),
    ("L", SectionShape.L),
]

# Rótulo corto de la forma, para la etiqueta de la cabecera.
SHAPE_TAG = {
    SectionShape.RECTANGULAR: "Rectangular",
    SectionShape.T: "Sección T",
    SectionShape.L: "Sección L",
}


def es_number(value: float, decimals: int = 1) -> str:
    """Número con coma decimal y punto de miles, como en el diseño."""
    texto = f"{value:,.{decimals}f}"
    return texto.replace(",", " ").replace(".", ",").replace(" ", ".")


# ------------------------------------------------------------ campos

class Stepper(QFrame):
    """Campo numérico con botones − y + a los lados y la unidad adentro."""

    def __init__(self, spin: QDoubleSpinBox, unit: str, parent=None):
        super().__init__(parent)
        self.setObjectName("stepper")
        self.spin = spin
        spin.setObjectName("stepperValue")
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setFrame(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        spin.setMinimumWidth(56)

        fila = QHBoxLayout(self)
        fila.setContentsMargins(2, 1, 2, 1)
        fila.setSpacing(0)
        menos = QToolButton()
        menos.setText("−")
        mas = QToolButton()
        mas.setText("+")
        for boton, paso in ((menos, spin.stepDown), (mas, spin.stepUp)):
            boton.setObjectName("stepperButton")
            boton.setAutoRepeat(True)
            boton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            boton.clicked.connect(paso)
        menos.setAccessibleName("Disminuir")
        mas.setAccessibleName("Aumentar")
        unidad = QLabel(unit)
        unidad.setObjectName("stepperUnit")

        fila.addWidget(menos)
        fila.addWidget(spin, 1)
        fila.addSpacing(4)
        fila.addWidget(unidad)
        fila.addSpacing(6)
        fila.addWidget(mas)
        self.setFixedWidth(150)


def _make_spinbox(value, rng, decimals, step) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setDecimals(decimals)
    sb.setRange(rng[0], rng[1])
    sb.setSingleStep(step)
    sb.setValue(value)
    sb.setKeyboardTracking(False)
    return sb


def _polygon(puntos) -> QPolygonF:
    return QPolygonF([QPointF(px, py) for px, py in puntos])


def _shape_icon(shape: SectionShape, color: str) -> QIcon:
    """Croquis de la forma, para los mosaicos."""
    pix = QPixmap(30, 30)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    if shape is SectionShape.RECTANGULAR:
        p.drawRect(QRectF(10, 4, 10, 22))
    elif shape is SectionShape.T:
        p.drawPolygon(_polygon([(3, 4), (27, 4), (27, 10), (19, 10), (19, 26),
                                (11, 26), (11, 10), (3, 10)]))
    else:
        p.drawPolygon(_polygon([(4, 4), (26, 4), (26, 10), (12, 10), (12, 26),
                                (4, 26)]))
    p.end()
    return QIcon(pix)


# ------------------------------------------------------------ panel

class GeometryPanel(QWidget):
    """Forma, dimensiones y materiales de una viga o de una franja de losa."""

    values_changed = pyqtSignal()
    shape_changed = pyqtSignal()
    continue_requested = pyqtSignal()

    def __init__(self, unit_system: UnitSystem, is_slab: bool = False,
                 design_code: DesignCode = DEFAULT_CODE):
        super().__init__()
        self.unit_system = unit_system
        self.is_slab = is_slab
        self.design_code = design_code
        self._building = True
        self._build_ui()
        self._building = False

    # ------------------------------------------------------------ construcción

    def _kicker(self, texto: str) -> QLabel:
        k = QLabel(texto.upper())
        k.setObjectName("kicker")
        return k

    def _row(self, grid: QGridLayout, fila: int, texto: str, simbolo: str,
             spin: QDoubleSpinBox, unidad: str):
        """Rótulo con el símbolo en cursiva y el campo −/+ a la derecha."""
        rotulo = QLabel(f"{texto} <i>{simbolo}</i>")
        rotulo.setObjectName("rowLabel")
        rotulo.setWordWrap(True)
        rotulo.setBuddy(spin)
        spin.setAccessibleName(f"{texto} ({unidad})")
        campo = Stepper(spin, unidad)
        grid.addWidget(rotulo, fila, 0)
        grid.addWidget(campo, fila, 1, Qt.AlignmentFlag.AlignRight)
        return rotulo, campo

    def _build_ui(self):
        cv = get_converter(self.unit_system)
        ingles = self.unit_system == UnitSystem.ENGLISH
        paso_largo = 0.5 if ingles else 1.0
        paso_recub = 0.25 if ingles else 0.5
        ul, us = cv.length_unit, cv.stress_unit

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 6, 0, 0)
        raiz.setSpacing(16)

        # ---- columna del formulario ----
        izquierda = QWidget()
        izquierda.setFixedWidth(320)
        col = QVBoxLayout(izquierda)
        col.setContentsMargins(0, 10, 0, 6)
        col.setSpacing(4)

        titulo = QLabel("Geometría y materiales")
        titulo.setObjectName("panelTitle")
        pista = QLabel(
            "La franja de losa se calcula por metro de ancho."
            if self.is_slab else
            "Lo que definas acá lo usan la flexión, el cortante y la torsión."
        )
        pista.setObjectName("panelHint")
        pista.setWordWrap(True)
        col.addWidget(titulo)
        col.addWidget(pista)

        cuerpo = QWidget()
        cuerpo.setObjectName("geometryBody")
        cl = QVBoxLayout(cuerpo)
        cl.setContentsMargins(0, 8, 4, 8)
        cl.setSpacing(10)

        self.shape_combo = None
        self.shape_buttons = {}
        self.b_spinbox = self.bf_spinbox = self.hf_spinbox = None
        self.b_label = None
        self._flange_widgets = []

        # --- forma: mosaicos; el combo oculto sigue siendo el modelo ---
        if not self.is_slab:
            cl.addWidget(self._kicker("Tipo de sección"))
            self.shape_combo = QComboBox(self)
            for etiqueta, dato in SECTION_SHAPES:
                self.shape_combo.addItem(etiqueta, dato)
            self.shape_combo.hide()
            self.shape_combo.currentIndexChanged.connect(self._on_shape_changed)
            mosaicos = QHBoxLayout()
            mosaicos.setSpacing(6)
            grupo = QButtonGroup(self)
            grupo.setExclusive(True)
            for etiqueta, forma in SECTION_SHAPES:
                t = QToolButton()
                t.setObjectName("shapeTile")
                t.setText(etiqueta)
                t.setIcon(_shape_icon(forma, PALETTE.text_primary))
                t.setIconSize(QSize(30, 30))
                t.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                t.setCheckable(True)
                t.setMinimumHeight(70)
                t.setSizePolicy(QSizePolicy.Policy.Expanding,
                                QSizePolicy.Policy.Fixed)
                t.setAccessibleName(f"Sección {etiqueta}")
                t.clicked.connect(
                    lambda _=False, f=forma: set_choice(self.shape_combo, f))
                grupo.addButton(t)
                mosaicos.addWidget(t, 1)
                self.shape_buttons[forma] = t
            self.shape_buttons[SectionShape.RECTANGULAR].setChecked(True)
            cl.addLayout(mosaicos)
            cl.addSpacing(6)

        # --- dimensiones ---
        cl.addWidget(self._kicker("Dimensiones"))
        dims = QGridLayout()
        dims.setHorizontalSpacing(10)
        dims.setVerticalSpacing(8)
        fila = 0
        if not self.is_slab:
            self.b_spinbox = _make_spinbox(cv.default_b, cv.range_b,
                                           cv.decimals_length, paso_largo)
            self.b_label, _ = self._row(dims, fila, "Ancho", "b",
                                        self.b_spinbox, ul)
            fila += 1
        else:
            franja = 39.37 if ingles else 100.0
            info = QLabel(f"b = {franja:.1f} {ul} (franja unitaria de 1 m)")
            info.setObjectName("infoLabel")
            dims.addWidget(info, fila, 0, 1, 2)
            fila += 1

        self.h_spinbox = _make_spinbox(
            (6.0 if ingles else 15.0) if self.is_slab else cv.default_h,
            cv.range_h, cv.decimals_length, paso_largo)
        self._row(dims, fila, "Altura", "h", self.h_spinbox, ul)
        fila += 1

        if not self.is_slab:
            self.bf_spinbox = _make_spinbox(cv.default_b * 4.0, cv.range_b,
                                            cv.decimals_length, paso_largo)
            self.bf_spinbox.setToolTip(
                "Ancho efectivo del ala. Se verifica el límite por espesor de "
                "ala (ACI 318-19 Tabla 6.3.2.1); los límites por luz y por "
                "separación entre almas quedan a tu cargo."
            )
            self._flange_widgets += list(self._row(
                dims, fila, "Ancho del ala", "b<sub>f</sub>", self.bf_spinbox, ul))
            fila += 1
            self.hf_spinbox = _make_spinbox(6.0 if ingles else 15.0, cv.range_h,
                                            cv.decimals_length, paso_largo)
            self._flange_widgets += list(self._row(
                dims, fila, "Espesor del ala", "h<sub>f</sub>", self.hf_spinbox, ul))
            fila += 1

        self.cover_spinbox = _make_spinbox(
            (0.75 if ingles else 2.0) if self.is_slab else cv.default_cover,
            cv.range_cover, cv.decimals_length, paso_recub)
        self._row(dims, fila, "Recubrimiento", "r", self.cover_spinbox, ul)
        dims.setColumnStretch(0, 1)
        cl.addLayout(dims)
        cl.addSpacing(6)

        # --- materiales ---
        cl.addWidget(self._kicker("Materiales"))
        mats = QGridLayout()
        mats.setHorizontalSpacing(10)
        mats.setVerticalSpacing(8)
        self.fc_spinbox = _make_spinbox(cv.default_fc, cv.range_fc,
                                        cv.decimals_stress,
                                        max(1.0, cv.default_fc * 0.05))
        self._row(mats, 0, "Resistencia del concreto", "f'c", self.fc_spinbox, us)
        self.fy_spinbox = _make_spinbox(cv.default_fy, cv.range_fy,
                                        cv.decimals_stress,
                                        max(1.0, cv.default_fy * 0.05))
        self._row(mats, 1, "Fluencia del acero long.", "fy", self.fy_spinbox, us)
        mats.setColumnStretch(0, 1)
        cl.addLayout(mats)
        cl.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(cuerpo)
        col.addWidget(scroll, 1)

        seguir = QPushButton("Continuar a Flexión  →")
        seguir.setToolTip("Pasar a la pestaña de flexión")
        seguir.clicked.connect(self.continue_requested.emit)
        fila_boton = QHBoxLayout()
        fila_boton.addWidget(seguir)
        fila_boton.addStretch()
        col.addLayout(fila_boton)
        raiz.addWidget(izquierda)

        # ---- tarjeta de la sección ----
        raiz.addWidget(self._build_preview_card(), 1)

        for sb in self._spinboxes():
            sb.valueChanged.connect(self._on_value_changed)
        self._apply_section_shape()
        self._refresh_properties()

    def _build_preview_card(self) -> QWidget:
        tarjeta = QFrame()
        tarjeta.setObjectName("previewCard")
        v = QVBoxLayout(tarjeta)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)

        cabecera = QHBoxLayout()
        cabecera.setContentsMargins(16, 12, 12, 4)
        rotulo = QLabel("Sección transversal")
        rotulo.setObjectName("previewTitle")
        cabecera.addWidget(rotulo)
        cabecera.addStretch()
        capas = QFrame()
        capas.setObjectName("segmented")
        cl = QHBoxLayout(capas)
        cl.setContentsMargins(2, 2, 2, 2)
        cl.setSpacing(2)
        self.cover_toggle = QPushButton("⬚  Recubrimiento")
        self.centroid_toggle = QPushButton("⊕  Centroide")
        for boton, activo in ((self.cover_toggle, True), (self.centroid_toggle, False)):
            boton.setObjectName("segOption")
            boton.setCheckable(True)
            boton.setChecked(activo)
            cl.addWidget(boton)
        cabecera.addWidget(capas)
        v.addLayout(cabecera)

        self.preview = SectionPreview(self)
        v.addWidget(self.preview, 1)
        for boton in (self.cover_toggle, self.centroid_toggle):
            boton.toggled.connect(lambda _=False: self.preview.update())

        franja = QFrame()
        franja.setObjectName("propsStrip")
        fl = QHBoxLayout(franja)
        fl.setContentsMargins(20, 12, 20, 14)
        fl.setSpacing(28)
        self._props = {}
        for clave, rotulo in (("ag", "Área bruta Ag"),
                              ("yc", "Centroide ȳ (desde arriba)"),
                              ("ig", "Inercia bruta Ig"),
                              ("ec", "Módulo Ec"),
                              ("b1", "β₁")):
            celda = QVBoxLayout()
            celda.setSpacing(3)
            titulo = QLabel(rotulo)
            titulo.setObjectName("statCaption")
            valor = QLabel("—")
            valor.setObjectName("statValue")
            valor.setTextFormat(Qt.TextFormat.RichText)
            celda.addWidget(titulo)
            celda.addWidget(valor)
            fl.addLayout(celda)
            self._props[clave] = valor
        fl.addStretch()
        v.addWidget(franja)
        return tarjeta

    def _spinboxes(self):
        return [sb for sb in (self.b_spinbox, self.bf_spinbox, self.hf_spinbox,
                              self.h_spinbox, self.cover_spinbox,
                              self.fc_spinbox, self.fy_spinbox) if sb is not None]

    # ------------------------------------------------------------ reacciones

    def _on_value_changed(self):
        self.preview.update()
        self._refresh_properties()
        if not self._building:
            self.values_changed.emit()

    def _on_shape_changed(self):
        self._apply_section_shape()
        self.preview.update()
        self._refresh_properties()
        if not self._building:
            self.shape_changed.emit()
            self.values_changed.emit()

    def _apply_section_shape(self):
        if self.shape_combo is None:
            return
        forma = self.section_shape()
        self.shape_buttons[forma].setChecked(True)
        con_ala = forma is not SectionShape.RECTANGULAR
        for w in self._flange_widgets:
            w.setVisible(con_ala)
        # Con ala, el ancho que se pide es el del alma: el que rige cortante,
        # torsión y el A_s mínimo.
        self.b_label.setText("Ancho del alma <i>b</i>" if con_ala
                             else "Ancho <i>b</i>")

    # ------------------------------------------------------------ propiedades

    def profile(self) -> SectionProfile:
        v = self.values()
        return SectionProfile.create(
            v["section_shape"], bw_mm=v["b_mm"], h_mm=v["h_mm"],
            bf_mm=v["bf_mm"], hf_mm=v["hf_mm"])

    def elastic_modulus_mpa(self) -> float:
        """E_c de la norma activa: ACI 318-19 §19.2.2.1 o AASHTO §5.4.2.4."""
        fc = self.values()["fc_mpa"]
        coef = 4800.0 if self.design_code is DesignCode.AASHTO_LRFD_2020 else 4700.0
        return coef * math.sqrt(fc) if fc > 0 else 0.0

    def beta_1(self) -> float:
        fc = self.values()["fc_mpa"]
        return 0.85 if fc <= 28.0 else max(0.85 - 0.05 * (fc - 28.0) / 7.0, 0.65)

    def _refresh_properties(self):
        if not hasattr(self, "_props"):
            return
        cv = get_converter(self.unit_system)
        mm_por_unidad = cv.length_to_m * 1000.0
        ag, y_inf, ig, _ = self.profile().gross_properties()
        y_sup = self.values()["h_mm"] - y_inf
        ul, us = cv.length_unit, cv.stress_unit

        def celda(valor, unidad, dec):
            return (f"{es_number(valor, dec)}"
                    f"<span style='font-size:8pt; font-weight:400; "
                    f"color:{PALETTE.text_muted}'>&nbsp;{unidad}</span>")

        self._props["ag"].setText(celda(ag / mm_por_unidad ** 2, f"{ul}²", 0))
        self._props["yc"].setText(celda(y_sup / mm_por_unidad, ul, 1))
        self._props["ig"].setText(celda(ig / mm_por_unidad ** 4, f"{ul}⁴", 0))
        ec = self.elastic_modulus_mpa() / cv.stress_to_mpa
        self._props["ec"].setText(celda(ec, us, 0 if ec >= 1000 else 1))
        self._props["b1"].setText(es_number(self.beta_1(), 3))

    # ------------------------------------------------------------ API

    def set_design_code(self, code: DesignCode):
        """La norma sólo cambia E_c de la franja de propiedades."""
        self.design_code = code
        self._refresh_properties()

    def section_shape(self) -> SectionShape:
        if self.shape_combo is None:
            return SectionShape.RECTANGULAR
        return self.shape_combo.currentData()

    def values(self) -> dict:
        """Datos en SI internas (mm, MPa), listos para los motores."""
        cv = get_converter(self.unit_system)
        mm = lambda sb: sb.value() * cv.length_to_m * 1000.0 if sb else 0.0
        return {
            "b_mm": 1000.0 if self.is_slab else mm(self.b_spinbox),
            "h_mm": mm(self.h_spinbox),
            "cover_mm": mm(self.cover_spinbox),
            "fc_mpa": self.fc_spinbox.value() * cv.stress_to_mpa,
            "fy_mpa": self.fy_spinbox.value() * cv.stress_to_mpa,
            "section_shape": self.section_shape(),
            "bf_mm": mm(self.bf_spinbox),
            "hf_mm": mm(self.hf_spinbox),
        }

    def get_state(self) -> dict:
        v = self.values()
        return {
            "b_mm": None if self.is_slab else v["b_mm"],
            "h_mm": v["h_mm"],
            "cover_mm": v["cover_mm"],
            "fc_mpa": v["fc_mpa"],
            "fy_mpa": v["fy_mpa"],
            "section_shape": v["section_shape"].name,
            "bf_mm": None if self.is_slab else v["bf_mm"],
            "hf_mm": None if self.is_slab else v["hf_mm"],
        }

    def set_state(self, state: dict) -> None:
        """Restaura desde SI sin emitir una señal por campo."""
        cv = get_converter(self.unit_system)
        largo = 1000.0 * cv.length_to_m
        previo, self._building = self._building, True
        try:
            if not self.is_slab:
                set_si(self.b_spinbox, state.get("b_mm"), largo)
                set_si(self.bf_spinbox, state.get("bf_mm"), largo)
                set_si(self.hf_spinbox, state.get("hf_mm"), largo)
                # Un estudio anterior a la v3 no trae forma: era rectangular.
                try:
                    forma = SectionShape[state.get("section_shape") or ""]
                except KeyError:
                    forma = SectionShape.RECTANGULAR
                set_choice(self.shape_combo, forma)
                self._apply_section_shape()
            set_si(self.h_spinbox, state.get("h_mm"), largo)
            set_si(self.cover_spinbox, state.get("cover_mm"), largo)
            set_si(self.fc_spinbox, state.get("fc_mpa"), cv.stress_to_mpa)
            set_si(self.fy_spinbox, state.get("fy_mpa"), cv.stress_to_mpa)
        finally:
            self._building = previo
        self.preview.update()
        self._refresh_properties()

    def update_unit_system(self, unit_system: UnitSystem):
        """Reconstruye los campos en la unidad nueva conservando los valores."""
        estado = self.get_state()
        capas = (self.cover_toggle.isChecked(), self.centroid_toggle.isChecked())
        self._building = True
        self.unit_system = unit_system
        viejo = self.layout()
        if viejo is not None:
            _clear_layout(viejo)
            QWidget().setLayout(viejo)
        self._build_ui()
        self.cover_toggle.setChecked(capas[0])
        self.centroid_toggle.setChecked(capas[1])
        self.set_state(estado)
        self._building = False


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


# ------------------------------------------------------------ dibujo

class SectionPreview(QWidget):
    """Sección acotada; el recubrimiento y el centroide son capas opcionales."""

    def __init__(self, panel: GeometryPanel):
        super().__init__()
        self.panel = panel
        self.setMinimumSize(320, 300)

    def sizeHint(self) -> QSize:
        return QSize(640, 480)

    def _label(self, mm: float, nombre: str, con_unidad: bool = True) -> str:
        cv = get_converter(self.panel.unit_system)
        valor = es_number(mm / 1000.0 / cv.length_to_m, 1)
        return f"{nombre} = {valor}" + (f" {cv.length_unit}" if con_unidad else "")

    def _dim_h(self, p, x1, x2, y, texto, texto_abajo=False):
        p.drawLine(QPointF(x1, y), QPointF(x2, y))
        p.drawLine(QPointF(x1, y - 4), QPointF(x1, y + 4))
        p.drawLine(QPointF(x2, y - 4), QPointF(x2, y + 4))
        caja_y = y + 6 if texto_abajo else y - 22
        p.drawText(QRectF((x1 + x2) / 2 - 110, caja_y, 220, 16),
                   int(Qt.AlignmentFlag.AlignCenter), texto)

    def _dim_v(self, p, x, y1, y2, texto, texto_a_la_izquierda=True):
        p.drawLine(QPointF(x, y1), QPointF(x, y2))
        p.drawLine(QPointF(x - 4, y1), QPointF(x + 4, y1))
        p.drawLine(QPointF(x - 4, y2), QPointF(x + 4, y2))
        p.save()
        p.translate(x + (-12 if texto_a_la_izquierda else 12), (y1 + y2) / 2)
        p.rotate(-90)
        p.drawText(QRectF(-110, -8, 220, 16), int(Qt.AlignmentFlag.AlignCenter), texto)
        p.restore()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fondo con un halo suave, a la manera de Nocturne.
        halo = QRadialGradient(QPointF(self.width() / 2, self.height() / 2),
                               max(self.width(), self.height()) * 0.6)
        halo.setColorAt(0.0, QColor(PALETTE.bg_elevated))
        halo.setColorAt(1.0, QColor(PALETTE.bg_base))
        p.fillRect(self.rect(), QBrush(halo))

        v = self.panel.values()
        perfil = self.panel.profile()
        if perfil.h_mm <= 0 or perfil.bw_mm <= 0:
            return

        margen = 80
        ancho_mm = max(perfil.bf_mm, perfil.bw_mm)
        # La sección no llena el lienzo: deja aire para las cotas y las capas.
        escala = 0.72 * min((self.width() - 2 * margen) / ancho_mm,
                            (self.height() - 2 * margen) / perfil.h_mm)
        b_px, h_px = ancho_mm * escala, perfil.h_mm * escala
        bw_px, hf_px = perfil.bw_mm * escala, perfil.hf_mm * escala
        x = (self.width() - b_px) / 2
        y = (self.height() - h_px) / 2
        web_x = x + (b_px - bw_px) / 2 if perfil.shape is SectionShape.T else x

        # Sección
        p.setPen(QPen(QColor(PALETTE.text_secondary), 1.4))
        p.setBrush(QColor(PALETTE.bg_surface))
        if perfil.is_flanged:
            p.drawPolygon(_polygon([
                (x, y), (x + b_px, y), (x + b_px, y + hf_px),
                (web_x + bw_px, y + hf_px), (web_x + bw_px, y + h_px),
                (web_x, y + h_px), (web_x, y + hf_px), (x, y + hf_px),
            ]))
        else:
            p.drawRect(QRectF(x, y, b_px, h_px))

        # Capa: recubrimiento (núcleo del estribo, en el alma)
        r = v["cover_mm"] * escala
        if self.panel.cover_toggle.isChecked() and 0 < 2 * r < min(bw_px, h_px):
            p.setPen(QPen(QColor(PALETTE.accent), 1.1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(web_x + r, y + r, bw_px - 2 * r, h_px - 2 * r),
                              3, 3)

        fuente = QFont(self.font().family(), 9)
        fuente.setWeight(QFont.Weight.Medium)
        p.setFont(fuente)

        # Capa: centroide de la sección bruta
        if self.panel.centroid_toggle.isChecked():
            _, y_inf, _, _ = perfil.gross_properties()
            yc = y + (perfil.h_mm - y_inf) * escala
            p.setPen(QPen(QColor(PALETTE.accent), 1.0, Qt.PenStyle.DashDotLine))
            p.drawLine(QPointF(x - 14, yc), QPointF(x + b_px + 14, yc))
            cx = web_x + bw_px / 2
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, yc), 6, 6)
            p.drawLine(QPointF(cx - 9, yc), QPointF(cx + 9, yc))
            p.drawLine(QPointF(cx, yc - 9), QPointF(cx, yc + 9))
            p.setPen(QColor(PALETTE.accent))
            p.drawText(QPointF(x + b_px + 40, yc + 4),
                       self._label(perfil.h_mm - y_inf, "ȳ"))

        # Cotas
        p.setPen(QPen(QColor(PALETTE.text_secondary), 1))
        nombre_b = "franja" if self.panel.is_slab else "b"
        self._dim_h(p, web_x, web_x + bw_px, y + h_px + 22,
                    self._label(perfil.bw_mm, nombre_b), texto_abajo=True)
        self._dim_v(p, x - 22, y, y + h_px, self._label(perfil.h_mm, "h"))
        if perfil.is_flanged:
            self._dim_h(p, x, x + b_px, y - 22, self._label(perfil.bf_mm, "bf"))
            self._dim_v(p, x + b_px + 22, y, y + hf_px,
                        self._label(perfil.hf_mm, "hf", con_unidad=False),
                        texto_a_la_izquierda=False)
