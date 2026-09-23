"""Paneles de entrada para diseño por cortante y torsión (viga y losa)."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox,
    QGridLayout, QGroupBox, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.units import UnitSystem, get_converter
from core.bar_tables import get_rebar_by_number
from core.design_code import DEFAULT_CODE, DesignCode
from core.section_geometry import SectionShape
from ui.geometry_panel import GeometryPanel
from ui.form_helpers import scroll_form, set_si, set_choice


STIRRUP_BAR_NUMBERS = [2, 3, 4, 5]
STIRRUP_LEGS_OPTIONS = [2, 3, 4]
LONG_BAR_NUMBERS = [3, 4, 5, 6, 8, 10, 12]


def _force_input_factor(unit_system: UnitSystem) -> float:
    """Factor para convertir el valor ingresado en la unidad del usuario a Newtons.

    En `core.units.UnitConverter.force_to_kn` está el factor a kN; lo escalamos a N.
    """
    return get_converter(unit_system).force_to_kn * 1000.0


def _default_vu(unit_system: UnitSystem) -> float:
    """Vu razonable por sistema (mismo orden de magnitud que default_mu/d)."""
    if unit_system == UnitSystem.MKS:
        return 12.0          # tonf
    if unit_system == UnitSystem.ENGLISH:
        return 25.0          # kip
    return 120.0             # kN (SI)


def _range_vu(unit_system: UnitSystem):
    if unit_system == UnitSystem.MKS:
        return (0.0, 1000.0)        # tonf
    if unit_system == UnitSystem.ENGLISH:
        return (0.0, 2000.0)        # kip
    return (0.0, 10000.0)           # kN


def _default_tu(unit_system: UnitSystem) -> float:
    """Torsor último razonable por sistema (orden de magnitud de Mu/10)."""
    if unit_system == UnitSystem.MKS:
        return 2.0           # tonf·m
    if unit_system == UnitSystem.ENGLISH:
        return 15.0          # kip·ft
    return 20.0              # kN·m (SI)


def _make_spinbox(value, rng, decimals, step):
    sb = QDoubleSpinBox()
    sb.setDecimals(decimals)
    sb.setRange(rng[0], rng[1])
    sb.setSingleStep(step)
    sb.setValue(value)
    sb.setKeyboardTracking(False)
    sb.setMinimumWidth(100)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
    return sb


def _add_field(layout, row, label, unit, widget):
    lbl = QLabel(label)
    lbl.setObjectName("fieldLabel")
    lbl.setBuddy(widget)
    widget.setAccessibleName(f"{label} ({unit})")
    unit_lbl = QLabel(f"[{unit}]")
    unit_lbl.setObjectName("unitLabel")
    layout.addWidget(lbl, row, 0)
    layout.addWidget(widget, row, 1)
    layout.addWidget(unit_lbl, row, 2)


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            sub = item.layout()
            if sub is not None:
                _clear_layout(sub)


# ============================================================
#               VIGA — Diseño por cortante
# ============================================================

class BeamShearInputPanel(QWidget):
    """Inputs para diseño por cortante y torsión en viga.

    Modo: dados Vu y (opcionalmente) Tu, calcular la separación de estribos
    cerrados y el acero longitudinal por torsión.
    """

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem,
                 design_code: DesignCode = DEFAULT_CODE,
                 geometry: "GeometryPanel | None" = None):
        super().__init__()
        self.geometry = geometry or GeometryPanel(unit_system)
        self.unit_system = unit_system
        self.design_code = design_code
        self.section_shape = SectionShape.RECTANGULAR
        self._building = True
        self._build_ui()
        self._building = False

    def _apply_section_note(self):
        """Refleja la forma elegida en flexión, que acá sólo se informa."""
        if self.section_shape is SectionShape.RECTANGULAR:
            self.shape_note.setText(
                "Sección rectangular. El tipo de sección se elige en la "
                "pestaña de flexión."
            )
        else:
            self.shape_note.setText(
                f"Sección «{self.section_shape.value}» definida en flexión: "
                "«b» es el ancho del alma b_w, que es el que rige el cortante. "
                "El ala entra sólo en A_cp de torsión."
            )

    def set_section_shape(self, shape: SectionShape):
        """La pestaña de flexión avisa con qué forma se está calculando."""
        self.section_shape = shape
        self._apply_section_note()

    def _build_ui(self):
        cv = get_converter(self.unit_system)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        title = QLabel("Datos de entrada")
        title.setObjectName("panelTitle")
        main_layout.addWidget(title)
        hint = QLabel("Geometría y materiales: pestaña «Geometría».")
        hint.setObjectName("infoLabel")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

        # La forma se elige en «Geometría»; acá se informa porque cambia el
        # significado de «b» y el A_cp de torsión.
        self.shape_note = QLabel()
        self.shape_note.setObjectName("infoLabel")
        self.shape_note.setWordWrap(True)
        main_layout.addWidget(self.shape_note)
        self._apply_section_note()

        # Solicitación
        load_group = QGroupBox("Solicitación")
        load_layout = QGridLayout()
        load_layout.setVerticalSpacing(6)
        self.vu_spinbox = _make_spinbox(
            value=_default_vu(self.unit_system),
            rng=_range_vu(self.unit_system),
            decimals=2,
            step=max(0.5, _default_vu(self.unit_system) * 0.05),
        )
        _add_field(load_layout, 0, "Vu", cv.force_unit, self.vu_spinbox)
        load_group.setLayout(load_layout)

        # Torsión (grupo activable)
        self.torsion_group = QGroupBox("Incluir torsión · Tu")
        self.torsion_group.setAccessibleName("Incluir torsión en el diseño de viga")
        self.torsion_group.setToolTip(
            "Activa el diseño combinado de cortante y torsión"
        )
        self.torsion_group.setCheckable(True)
        self.torsion_group.setChecked(False)
        self.torsion_group.toggled.connect(self._emit_if_ready)
        tor_layout = QGridLayout()
        tor_layout.setVerticalSpacing(6)

        default_tu = _default_tu(self.unit_system)
        self.tu_spinbox = _make_spinbox(
            value=default_tu,
            rng=(0.0, cv.range_mu[1]),
            decimals=cv.decimals_moment,
            step=max(0.1, default_tu * 0.05),
        )
        _add_field(tor_layout, 0, "Tu", cv.moment_unit, self.tu_spinbox)

        tor_layout.addWidget(QLabel("Tipo de torsión:"), 1, 0)
        self.torsion_type_combo = QComboBox()
        self.torsion_type_combo.addItem("Equilibrio", "EQUILIBRIO")
        self.torsion_type_combo.addItem("Compatibilidad", "COMPATIBILIDAD")
        self.torsion_type_combo.currentIndexChanged.connect(self._emit_if_ready)
        tor_layout.addWidget(self.torsion_type_combo, 1, 1, 1, 2)

        self.fy_long_spinbox = _make_spinbox(
            value=cv.default_fy, rng=cv.range_fy,
            decimals=cv.decimals_stress,
            step=max(1.0, cv.default_fy * 0.05),
        )
        _add_field(tor_layout, 2, "fy (long. torsión)", cv.stress_unit, self.fy_long_spinbox)

        self.tor_note = QLabel()
        self.tor_note.setObjectName("infoLabel")
        self.tor_note.setWordWrap(True)
        tor_layout.addWidget(self.tor_note, 3, 0, 1, 3)


        # Materiales
        mat_group = QGroupBox("Materiales")
        mat_layout = QGridLayout()
        mat_layout.setVerticalSpacing(6)
        self.fyt_spinbox = _make_spinbox(
            value=cv.default_fy, rng=cv.range_fy,
            decimals=cv.decimals_stress,
            step=max(1.0, cv.default_fy * 0.05),
        )
        _add_field(mat_layout, 0, "fyt (estribo)", cv.stress_unit, self.fyt_spinbox)
        mat_group.setLayout(mat_layout)

        # Estribo propuesto
        stirrup_group = QGroupBox("Estribo propuesto")
        stirrup_layout = QGridLayout()
        stirrup_layout.setVerticalSpacing(6)
        stirrup_layout.setHorizontalSpacing(8)

        stirrup_layout.addWidget(QLabel("Diámetro:"), 0, 0)
        self.stirrup_combo = QComboBox()
        for n in STIRRUP_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.stirrup_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        self.stirrup_combo.setCurrentIndex(STIRRUP_BAR_NUMBERS.index(3))
        self.stirrup_combo.currentIndexChanged.connect(self._emit_if_ready)
        stirrup_layout.addWidget(self.stirrup_combo, 0, 1, 1, 2)

        stirrup_layout.addWidget(QLabel("N° de ramas:"), 1, 0)
        self.legs_combo = QComboBox()
        for n in STIRRUP_LEGS_OPTIONS:
            self.legs_combo.addItem(f"{n} ramas", n)
        self.legs_combo.setCurrentIndex(0)
        self.legs_combo.currentIndexChanged.connect(self._emit_if_ready)
        stirrup_layout.addWidget(self.legs_combo, 1, 1, 1, 2)

        # Barra longitudinal de flexión (sólo afecta el cálculo de d)
        stirrup_layout.addWidget(QLabel("Barra long. para d:"), 2, 0)
        self.db_long_combo = QComboBox()
        for n in LONG_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.db_long_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        # Default #6 (índice de 6 en LONG_BAR_NUMBERS)
        self.db_long_combo.setCurrentIndex(LONG_BAR_NUMBERS.index(6))
        self.db_long_combo.currentIndexChanged.connect(self._emit_if_ready)
        stirrup_layout.addWidget(self.db_long_combo, 2, 1, 1, 2)

        self.code_note = QLabel()
        self.code_note.setObjectName("infoLabel")
        self.code_note.setWordWrap(True)
        stirrup_layout.addWidget(self.code_note, 3, 0, 1, 3)

        stirrup_group.setLayout(stirrup_layout)

        # Torsión muestra sus opciones solamente cuando está activada.
        self.torsion_options = QWidget()
        self.torsion_options.setObjectName("torsionOptions")
        self.torsion_options.setLayout(tor_layout)
        wrapper = QVBoxLayout(self.torsion_group)
        self.torsion_hint = QLabel("Activa esta casilla para ingresar Tu y calcular el refuerzo por torsión.")
        self.torsion_hint.setObjectName("infoLabel")
        self.torsion_hint.setWordWrap(True)
        wrapper.addWidget(self.torsion_hint)
        wrapper.addWidget(self.torsion_options)
        self.torsion_options.setVisible(False)
        self.torsion_group.toggled.connect(self.torsion_options.setVisible)
        self.torsion_group.toggled.connect(lambda active: self.torsion_hint.setVisible(not active))
        self.form_scroll = scroll_form(
            load_group, self.torsion_group, mat_group, stirrup_group
        )
        main_layout.addWidget(self.form_scroll)
        self._apply_design_code()
        self._connect_signals()

    # ---- geometría: la edita la pestaña «Geometría», acá sólo se lee ----
    b_spinbox = property(lambda self: self.geometry.b_spinbox)
    h_spinbox = property(lambda self: self.geometry.h_spinbox)
    cover_spinbox = property(lambda self: self.geometry.cover_spinbox)
    fc_spinbox = property(lambda self: self.geometry.fc_spinbox)

    def _apply_design_code(self):
        """Ajusta las notas de norma; el cortante no cambia de campos."""
        if self.design_code is DesignCode.AASHTO_LRFD_2020:
            self.code_note.setText(
                "AASHTO LRFD §5.7.2 / §5.7.3 (cortante) y §5.7.2.1 / §5.7.3.6 "
                "(torsión), procedimiento simplificado de §5.7.3.4.1: "
                "φ = 0.90, β = 2.0, θ = 45°, λ = 1.0. El cortante se evalúa "
                "sobre dv, no sobre d."
            )
            self.tor_note.setText(
                "AASHTO no admite reducir Tu por compatibilidad como ACI: se "
                "diseña para la torsión de equilibrio completa. Requiere "
                "estribos cerrados y acero longitudinal en el perímetro."
            )
        else:
            self.code_note.setText(
                "ACI 318-19 §22.5 / §9.6.3 / §9.7.6.2.2 (cortante) y §22.7 / "
                "§9.6.4 / §9.7.6.3 (torsión). φ = 0.75, λ = 1.0, θ = 45°."
            )
            self.tor_note.setText(
                "En torsión por compatibilidad, Tu puede reducirse a φTcr "
                "(§22.7.3.2). Requiere estribos cerrados y acero longitudinal Al."
            )

    def set_design_code(self, code: DesignCode):
        if code == self.design_code:
            return
        self.design_code = code
        self._apply_design_code()
        self._emit_if_ready()

    def _connect_signals(self):
        for sb in [self.vu_spinbox, self.tu_spinbox, self.fyt_spinbox,
                   self.fy_long_spinbox]:
            sb.valueChanged.connect(self._emit_if_ready)

    def _emit_if_ready(self):
        if not self._building:
            self.values_changed.emit()

    # ---- API pública ----

    def update_unit_system(self, unit_system: UnitSystem):
        self._building = True
        self.unit_system = unit_system
        # El modo y tipo de torsión sobreviven al cambio de unidades.
        torsion_on = self.torsion_group.isChecked()
        torsion_type = self.torsion_type_combo.currentData()
        old_layout = self.layout()
        if old_layout is not None:
            _clear_layout(old_layout)
            QWidget().setLayout(old_layout)
        self._build_ui()
        self.torsion_group.setChecked(torsion_on)
        idx = self.torsion_type_combo.findData(torsion_type)
        if idx >= 0:
            self.torsion_type_combo.setCurrentIndex(idx)
        self._building = False
        self.values_changed.emit()

    def get_state(self) -> dict:
        """Estado serializable del panel, con las magnitudes en SI internas."""
        cv = get_converter(self.unit_system)
        return {
            "vu_n": self.vu_spinbox.value() * _force_input_factor(self.unit_system),
            "b_mm": self.b_spinbox.value() * cv.length_to_m * 1000.0,
            "h_mm": self.h_spinbox.value() * cv.length_to_m * 1000.0,
            "cover_mm": self.cover_spinbox.value() * cv.length_to_m * 1000.0,
            "fc_mpa": self.fc_spinbox.value() * cv.stress_to_mpa,
            "fyt_mpa": self.fyt_spinbox.value() * cv.stress_to_mpa,
            "stirrup_bar": self.stirrup_combo.currentData(),
            "legs": self.legs_combo.currentData(),
            "db_long_bar": self.db_long_combo.currentData(),
            "torsion_enabled": self.torsion_group.isChecked(),
            "tu_nmm": self.tu_spinbox.value() * cv.moment_to_knm * 1e6,
            "fy_long_mpa": self.fy_long_spinbox.value() * cv.stress_to_mpa,
            "torsion_type": self.torsion_type_combo.currentData(),
        }

    def set_state(self, state: dict) -> None:
        """Restaura el panel desde un estado en SI, sin recalcular por cada campo."""
        cv = get_converter(self.unit_system)
        self._building = True
        try:
            set_si(self.vu_spinbox, state.get("vu_n"),
                   _force_input_factor(self.unit_system))
            set_si(self.fyt_spinbox, state.get("fyt_mpa"), cv.stress_to_mpa)
            set_si(self.tu_spinbox, state.get("tu_nmm"), 1e6 * cv.moment_to_knm)
            set_si(self.fy_long_spinbox, state.get("fy_long_mpa"), cv.stress_to_mpa)
            set_choice(self.stirrup_combo, state.get("stirrup_bar"))
            set_choice(self.legs_combo, state.get("legs"))
            set_choice(self.db_long_combo, state.get("db_long_bar"))
            set_choice(self.torsion_type_combo, state.get("torsion_type"))
            if "torsion_enabled" in state:
                self.torsion_group.setChecked(bool(state["torsion_enabled"]))
        finally:
            self._building = False
        self.values_changed.emit()

    def get_values(self) -> dict:
        cv = get_converter(self.unit_system)
        vu_n = self.vu_spinbox.value() * _force_input_factor(self.unit_system)
        b_mm = self.b_spinbox.value() * cv.length_to_m * 1000.0
        h_mm = self.h_spinbox.value() * cv.length_to_m * 1000.0
        cover_mm = self.cover_spinbox.value() * cv.length_to_m * 1000.0
        fc_mpa = self.fc_spinbox.value() * cv.stress_to_mpa
        fyt_mpa = self.fyt_spinbox.value() * cv.stress_to_mpa

        stirrup_n = self.stirrup_combo.currentData()
        stirrup = get_rebar_by_number(stirrup_n)
        legs = self.legs_combo.currentData()
        db_long_n = self.db_long_combo.currentData()
        db_long = get_rebar_by_number(db_long_n)

        torsion_on = self.torsion_group.isChecked()
        tu_nmm = self.tu_spinbox.value() * cv.moment_to_knm * 1e6

        return {
            "vu_n": vu_n,
            "b_mm": b_mm,
            "h_mm": h_mm,
            "cover_mm": cover_mm,
            "fc_mpa": fc_mpa,
            "fyt_mpa": fyt_mpa,
            "stirrup_diameter_mm": stirrup.diameter_mm,
            "stirrup_area_mm2": stirrup.area_mm2,
            "stirrup_legs": legs,
            "db_long_assumed_mm": db_long.diameter_mm,
            "lam": 1.0,
            "torsion_enabled": torsion_on,
            "tu_nmm": tu_nmm if torsion_on else 0.0,
            "fy_long_mpa": self.fy_long_spinbox.value() * cv.stress_to_mpa,
            "torsion_type": self.torsion_type_combo.currentData(),
        }


# ============================================================
#               LOSA — Revisión por cortante
# ============================================================

class SlabShearInputPanel(QWidget):
    """Inputs para revisión de cortante en losa sin refuerzo (una dirección)."""

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem,
                 design_code: DesignCode = DEFAULT_CODE,
                 geometry: "GeometryPanel | None" = None):
        super().__init__()
        self.geometry = geometry or GeometryPanel(unit_system, is_slab=True)
        self.unit_system = unit_system
        self.design_code = design_code
        self._building = True
        self._build_ui()
        self._building = False

    def _build_ui(self):
        cv = get_converter(self.unit_system)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        title = QLabel("Datos de entrada")
        title.setObjectName("panelTitle")
        main_layout.addWidget(title)
        hint = QLabel("Geometría y materiales: pestaña «Geometría».")
        hint.setObjectName("infoLabel")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)


        # Solicitación
        load_group = QGroupBox("Solicitación")
        load_layout = QGridLayout()
        load_layout.setVerticalSpacing(6)
        # Default más bajo para losa
        default_vu = max(_default_vu(self.unit_system) * 0.25, 0.5)
        self.vu_spinbox = _make_spinbox(
            value=default_vu, rng=_range_vu(self.unit_system),
            decimals=2, step=max(0.5, default_vu * 0.10),
        )
        _add_field(load_layout, 0, "Vu (por franja 1 m)", cv.force_unit, self.vu_spinbox)
        load_group.setLayout(load_layout)

        # Refuerzo longitudinal de flexión (sólo afecta el cálculo de d)
        ref_group = QGroupBox("Refuerzo longitudinal")
        ref_layout = QGridLayout()
        ref_layout.setVerticalSpacing(6)
        ref_layout.addWidget(QLabel("Barra long. para d:"), 0, 0)
        self.db_long_combo = QComboBox()
        for n in LONG_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.db_long_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        # Default #4 (típico en losa)
        self.db_long_combo.setCurrentIndex(LONG_BAR_NUMBERS.index(4))
        self.db_long_combo.currentIndexChanged.connect(self._emit_if_ready)
        ref_layout.addWidget(self.db_long_combo, 0, 1, 1, 2)

        self.code_note = QLabel()
        self.code_note.setObjectName("infoLabel")
        self.code_note.setWordWrap(True)
        ref_layout.addWidget(self.code_note, 1, 0, 1, 3)
        ref_group.setLayout(ref_layout)

        self.form_scroll = scroll_form(load_group, ref_group)
        main_layout.addWidget(self.form_scroll)

        self._apply_design_code()
        self._connect_signals()

    # ---- geometría: la edita la pestaña «Geometría», acá sólo se lee ----
    h_spinbox = property(lambda self: self.geometry.h_spinbox)
    cover_spinbox = property(lambda self: self.geometry.cover_spinbox)
    fc_spinbox = property(lambda self: self.geometry.fc_spinbox)

    def _apply_design_code(self):
        if self.design_code is DesignCode.AASHTO_LRFD_2020:
            self.code_note.setText(
                "AASHTO LRFD §5.7.3, procedimiento simplificado de §5.7.3.4.1 "
                "(β = 2.0, θ = 45°, φ = 0.90), evaluado sobre dv. Ese "
                "procedimiento sólo cubre elementos sin estribos si h < 400 mm; "
                "por encima, la app avisa que el resultado no sirve como "
                "verificación normativa."
            )
        else:
            self.code_note.setText(
                "ACI 318-19 §22.5 (una dirección). Las losas no pueden llevar "
                "refuerzo por cortante (§8.6.1); si falla, aumentar h o f'c."
            )

    def set_design_code(self, code: DesignCode):
        if code == self.design_code:
            return
        self.design_code = code
        self._apply_design_code()
        self._emit_if_ready()

    def _connect_signals(self):
        self.vu_spinbox.valueChanged.connect(self._emit_if_ready)

    def _emit_if_ready(self):
        if not self._building:
            self.values_changed.emit()

    # ---- API pública ----

    def update_unit_system(self, unit_system: UnitSystem):
        self._building = True
        self.unit_system = unit_system
        old_layout = self.layout()
        if old_layout is not None:
            _clear_layout(old_layout)
            QWidget().setLayout(old_layout)
        self._build_ui()
        self._building = False
        self.values_changed.emit()

    def get_state(self) -> dict:
        """Estado serializable del panel, con las magnitudes en SI internas."""
        cv = get_converter(self.unit_system)
        return {
            "vu_n": self.vu_spinbox.value() * _force_input_factor(self.unit_system),
            "h_mm": self.h_spinbox.value() * cv.length_to_m * 1000.0,
            "cover_mm": self.cover_spinbox.value() * cv.length_to_m * 1000.0,
            "fc_mpa": self.fc_spinbox.value() * cv.stress_to_mpa,
            "db_long_bar": self.db_long_combo.currentData(),
        }

    def set_state(self, state: dict) -> None:
        """Restaura el panel desde un estado en SI, sin recalcular por cada campo."""
        cv = get_converter(self.unit_system)
        self._building = True
        try:
            set_si(self.vu_spinbox, state.get("vu_n"),
                   _force_input_factor(self.unit_system))
            set_choice(self.db_long_combo, state.get("db_long_bar"))
        finally:
            self._building = False
        self.values_changed.emit()

    def get_values(self) -> dict:
        cv = get_converter(self.unit_system)
        vu_n = self.vu_spinbox.value() * _force_input_factor(self.unit_system)
        h_mm = self.h_spinbox.value() * cv.length_to_m * 1000.0
        cover_mm = self.cover_spinbox.value() * cv.length_to_m * 1000.0
        fc_mpa = self.fc_spinbox.value() * cv.stress_to_mpa
        db_long_n = self.db_long_combo.currentData()
        db_long = get_rebar_by_number(db_long_n)

        return {
            "vu_n": vu_n,
            "b_mm": 1000.0,
            "h_mm": h_mm,
            "cover_mm": cover_mm,
            "fc_mpa": fc_mpa,
            "db_long_assumed_mm": db_long.diameter_mm,
            "lam": 1.0,
        }
