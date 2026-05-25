"""Paneles de entrada para diseño por cortante (viga y losa)."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox,
    QGridLayout, QGroupBox, QSpinBox, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.units import UnitSystem, get_converter
from core.bar_tables import get_rebar_by_number


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


def _make_spinbox(value, rng, decimals, step):
    sb = QDoubleSpinBox()
    sb.setDecimals(decimals)
    sb.setRange(rng[0], rng[1])
    sb.setSingleStep(step)
    sb.setValue(value)
    sb.setMinimumWidth(110)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
    return sb


def _add_field(layout, row, label, unit, widget):
    lbl = QLabel(label)
    lbl.setObjectName("fieldLabel")
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
    """Inputs para diseño por cortante en viga (modo: dado Vu, calcular s)."""

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem):
        super().__init__()
        self.unit_system = unit_system
        self._building = True
        self._build_ui()
        self._building = False

    def _build_ui(self):
        cv = get_converter(self.unit_system)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        title = QLabel("✂  Viga — Diseño por cortante")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        length_step = 0.5 if self.unit_system == UnitSystem.ENGLISH else 1.0
        cover_step = 0.25 if self.unit_system == UnitSystem.ENGLISH else 0.5

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
        main_layout.addWidget(load_group)

        # Geometría
        geom_group = QGroupBox("Geometría")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(6)

        self.b_spinbox = _make_spinbox(
            value=cv.default_b, rng=cv.range_b,
            decimals=cv.decimals_length, step=length_step,
        )
        _add_field(geom_layout, 0, "Ancho b", cv.length_unit, self.b_spinbox)

        self.h_spinbox = _make_spinbox(
            value=cv.default_h, rng=cv.range_h,
            decimals=cv.decimals_length, step=length_step,
        )
        _add_field(geom_layout, 1, "Altura h", cv.length_unit, self.h_spinbox)

        self.cover_spinbox = _make_spinbox(
            value=cv.default_cover, rng=cv.range_cover,
            decimals=cv.decimals_length, step=cover_step,
        )
        _add_field(geom_layout, 2, "Recubrimiento", cv.length_unit, self.cover_spinbox)
        geom_group.setLayout(geom_layout)
        main_layout.addWidget(geom_group)

        # Materiales
        mat_group = QGroupBox("Materiales")
        mat_layout = QGridLayout()
        mat_layout.setVerticalSpacing(6)
        self.fc_spinbox = _make_spinbox(
            value=cv.default_fc, rng=cv.range_fc,
            decimals=cv.decimals_stress,
            step=max(1.0, cv.default_fc * 0.05),
        )
        _add_field(mat_layout, 0, "f'c", cv.stress_unit, self.fc_spinbox)

        self.fyt_spinbox = _make_spinbox(
            value=cv.default_fy, rng=cv.range_fy,
            decimals=cv.decimals_stress,
            step=max(1.0, cv.default_fy * 0.05),
        )
        _add_field(mat_layout, 1, "fyt (estribo)", cv.stress_unit, self.fyt_spinbox)
        mat_group.setLayout(mat_layout)
        main_layout.addWidget(mat_group)

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
        stirrup_layout.addWidget(QLabel("Barra longitudinal (flexión):"), 2, 0)
        self.db_long_combo = QComboBox()
        for n in LONG_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.db_long_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        # Default #6 (índice de 6 en LONG_BAR_NUMBERS)
        self.db_long_combo.setCurrentIndex(LONG_BAR_NUMBERS.index(6))
        self.db_long_combo.currentIndexChanged.connect(self._emit_if_ready)
        stirrup_layout.addWidget(self.db_long_combo, 2, 1, 1, 2)

        note = QLabel("ACI 318-19 §22.5 / §9.6.3 / §9.7.6.2.2. φ = 0.75, λ = 1.0.")
        note.setObjectName("infoLabel")
        note.setWordWrap(True)
        stirrup_layout.addWidget(note, 3, 0, 1, 3)

        stirrup_group.setLayout(stirrup_layout)
        main_layout.addWidget(stirrup_group)

        main_layout.addStretch()
        self._connect_signals()

    def _connect_signals(self):
        for sb in [self.vu_spinbox, self.b_spinbox, self.h_spinbox,
                   self.cover_spinbox, self.fc_spinbox, self.fyt_spinbox]:
            sb.valueChanged.connect(self._emit_if_ready)

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
        }


# ============================================================
#               LOSA — Revisión por cortante
# ============================================================

class SlabShearInputPanel(QWidget):
    """Inputs para revisión de cortante en losa sin refuerzo (una dirección)."""

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem):
        super().__init__()
        self.unit_system = unit_system
        self._building = True
        self._build_ui()
        self._building = False

    def _build_ui(self):
        cv = get_converter(self.unit_system)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        title = QLabel("✂  Losa — Cortante (sin refuerzo)")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        length_step = 0.5 if self.unit_system == UnitSystem.ENGLISH else 1.0
        cover_step = 0.25 if self.unit_system == UnitSystem.ENGLISH else 0.5

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
        main_layout.addWidget(load_group)

        # Geometría (b fija = 1 m, sólo se muestra)
        geom_group = QGroupBox("Geometría")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(6)

        b_franja = 100.0 if self.unit_system != UnitSystem.ENGLISH else 39.37
        info = QLabel(
            f"b = {b_franja:.1f} {cv.length_unit} (franja unitaria de 1 m)"
        )
        info.setObjectName("infoLabel")
        geom_layout.addWidget(info, 0, 0, 1, 3)

        # Default un poco más fina para losa
        default_h_slab = 15.0 if self.unit_system != UnitSystem.ENGLISH else 6.0
        self.h_spinbox = _make_spinbox(
            value=default_h_slab, rng=cv.range_h,
            decimals=cv.decimals_length, step=length_step,
        )
        _add_field(geom_layout, 1, "Espesor h", cv.length_unit, self.h_spinbox)

        default_cover_slab = 2.0 if self.unit_system != UnitSystem.ENGLISH else 0.75
        self.cover_spinbox = _make_spinbox(
            value=default_cover_slab, rng=cv.range_cover,
            decimals=cv.decimals_length, step=cover_step,
        )
        _add_field(geom_layout, 2, "Recubrimiento", cv.length_unit, self.cover_spinbox)
        geom_group.setLayout(geom_layout)
        main_layout.addWidget(geom_group)

        # Materiales
        mat_group = QGroupBox("Materiales")
        mat_layout = QGridLayout()
        mat_layout.setVerticalSpacing(6)
        self.fc_spinbox = _make_spinbox(
            value=cv.default_fc, rng=cv.range_fc,
            decimals=cv.decimals_stress,
            step=max(1.0, cv.default_fc * 0.05),
        )
        _add_field(mat_layout, 0, "f'c", cv.stress_unit, self.fc_spinbox)
        mat_group.setLayout(mat_layout)
        main_layout.addWidget(mat_group)

        # Refuerzo longitudinal de flexión (sólo afecta el cálculo de d)
        ref_group = QGroupBox("Refuerzo longitudinal")
        ref_layout = QGridLayout()
        ref_layout.setVerticalSpacing(6)
        ref_layout.addWidget(QLabel("Barra longitudinal (flexión):"), 0, 0)
        self.db_long_combo = QComboBox()
        for n in LONG_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.db_long_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        # Default #4 (típico en losa)
        self.db_long_combo.setCurrentIndex(LONG_BAR_NUMBERS.index(4))
        self.db_long_combo.currentIndexChanged.connect(self._emit_if_ready)
        ref_layout.addWidget(self.db_long_combo, 0, 1, 1, 2)

        note = QLabel(
            "ACI 318-19 §22.5 (una dirección). Las losas no pueden llevar "
            "refuerzo por cortante (§8.6.1); si falla, aumentar h o f'c."
        )
        note.setObjectName("infoLabel")
        note.setWordWrap(True)
        ref_layout.addWidget(note, 1, 0, 1, 3)
        ref_group.setLayout(ref_layout)
        main_layout.addWidget(ref_group)

        main_layout.addStretch()
        self._connect_signals()

    def _connect_signals(self):
        for sb in [self.vu_spinbox, self.h_spinbox,
                   self.cover_spinbox, self.fc_spinbox]:
            sb.valueChanged.connect(self._emit_if_ready)

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
