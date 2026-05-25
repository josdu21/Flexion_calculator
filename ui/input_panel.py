from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QGridLayout, QGroupBox, QFrame, QSpinBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.units import UnitSystem, get_converter
from core.bar_tables import REBAR_SIZES, get_rebar_by_number
from core.flexion import ReinforcementConfig, RebarLayer


MAX_LAYERS = 4
MAIN_BAR_NUMBERS = [3, 4, 5, 6, 8, 10, 12]
STIRRUP_BAR_NUMBERS = [2, 3, 4, 5]


class InputPanel(QWidget):
    """Panel de entradas para diseño por flexión con configuración de refuerzo."""

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem, is_slab: bool = False):
        super().__init__()
        self.unit_system = unit_system
        self.is_slab = is_slab
        self._building = True
        self._build_ui()
        self._building = False

    def _build_ui(self):
        converter = get_converter(self.unit_system)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Título
        title_text = "Losa (franja unitaria 1 m)" if self.is_slab else "Viga rectangular"
        title = QLabel(f"📐 {title_text}")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Solicitación
        load_group = QGroupBox("Solicitación")
        load_layout = QGridLayout()
        load_layout.setVerticalSpacing(6)
        self.mu_spinbox = self._make_spinbox(
            value=converter.default_mu, rng=converter.range_mu,
            decimals=converter.decimals_moment,
            step=max(0.1, converter.default_mu * 0.05),
        )
        self._add_field(load_layout, 0, "Mu", converter.moment_unit, self.mu_spinbox)
        load_group.setLayout(load_layout)
        main_layout.addWidget(load_group)

        # Geometría
        geom_group = QGroupBox("Geometría")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(6)

        # Step apropiado para la unidad: 1 cm o 0.5 in
        from core.units import UnitSystem
        length_step = 0.5 if self.unit_system == UnitSystem.ENGLISH else 1.0
        cover_step = 0.25 if self.unit_system == UnitSystem.ENGLISH else 0.5

        row = 0
        if not self.is_slab:
            self.b_spinbox = self._make_spinbox(
                value=converter.default_b, rng=converter.range_b,
                decimals=converter.decimals_length, step=length_step,
            )
            self._add_field(geom_layout, row, "Ancho b", converter.length_unit, self.b_spinbox)
            row += 1
        else:
            self.b_spinbox = None
            # Mostrar el ancho de la franja unitaria en la unidad actual
            # 1 m = 100 cm = 39.37 in
            b_franja = 100.0 if self.unit_system != UnitSystem.ENGLISH else 39.37
            info = QLabel(
                f"b = {b_franja:.1f} {converter.length_unit} "
                f"(franja unitaria de 1 m)"
            )
            info.setObjectName("infoLabel")
            geom_layout.addWidget(info, row, 0, 1, 3)
            row += 1

        self.h_spinbox = self._make_spinbox(
            value=converter.default_h, rng=converter.range_h,
            decimals=converter.decimals_length, step=length_step,
        )
        self._add_field(geom_layout, row, "Altura h", converter.length_unit, self.h_spinbox)
        row += 1

        self.cover_spinbox = self._make_spinbox(
            value=converter.default_cover, rng=converter.range_cover,
            decimals=converter.decimals_length, step=cover_step,
        )
        self._add_field(geom_layout, row, "Recubrimiento", converter.length_unit, self.cover_spinbox)
        geom_group.setLayout(geom_layout)
        main_layout.addWidget(geom_group)

        # Materiales
        mat_group = QGroupBox("Materiales")
        mat_layout = QGridLayout()
        mat_layout.setVerticalSpacing(6)
        self.fc_spinbox = self._make_spinbox(
            value=converter.default_fc, rng=converter.range_fc,
            decimals=converter.decimals_stress,
            step=max(1.0, converter.default_fc * 0.05),
        )
        self._add_field(mat_layout, 0, "f'c", converter.stress_unit, self.fc_spinbox)

        self.fy_spinbox = self._make_spinbox(
            value=converter.default_fy, rng=converter.range_fy,
            decimals=converter.decimals_stress,
            step=max(1.0, converter.default_fy * 0.05),
        )
        self._add_field(mat_layout, 1, "fy", converter.stress_unit, self.fy_spinbox)
        mat_group.setLayout(mat_layout)
        main_layout.addWidget(mat_group)

        # ----- Refuerzo -----
        rebar_group = QGroupBox("Refuerzo")
        rebar_layout = QGridLayout()
        rebar_layout.setVerticalSpacing(6)
        rebar_layout.setHorizontalSpacing(8)

        # Tamaño de barra principal (siempre)
        rebar_layout.addWidget(QLabel("Barra principal:"), 0, 0)
        self.main_bar_combo = QComboBox()
        for n in MAIN_BAR_NUMBERS:
            r = get_rebar_by_number(n)
            self.main_bar_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
        default_idx = MAIN_BAR_NUMBERS.index(4 if self.is_slab else 5)
        self.main_bar_combo.setCurrentIndex(default_idx)
        self.main_bar_combo.currentIndexChanged.connect(self._emit_if_ready)
        rebar_layout.addWidget(self.main_bar_combo, 0, 1, 1, 2)

        # Inicializar atributos para que existan aunque no se muestren
        self.stirrup_combo = None
        self.layers_spin = None
        self.layer_bar_spins = []
        self.layer_row_widgets = []

        if self.is_slab:
            # ---- Losa: solo barras por metro (sin estribo, sin lechos múltiples) ----
            rebar_layout.addWidget(QLabel("N° de barras por metro:"), 1, 0)
            slab_spin = QSpinBox()
            slab_spin.setRange(2, 20)
            slab_spin.setValue(5)
            slab_spin.setSuffix("  barras/m")
            slab_spin.valueChanged.connect(self._emit_if_ready)
            rebar_layout.addWidget(slab_spin, 1, 1, 1, 2)
            self.layer_bar_spins = [slab_spin]

            note = QLabel("Las losas no llevan estribos ni lechos múltiples.")
            note.setObjectName("infoLabel")
            note.setWordWrap(True)
            rebar_layout.addWidget(note, 2, 0, 1, 3)
        else:
            # ---- Viga: estribo + lechos múltiples ----
            rebar_layout.addWidget(QLabel("Estribo:"), 1, 0)
            self.stirrup_combo = QComboBox()
            for n in STIRRUP_BAR_NUMBERS:
                r = get_rebar_by_number(n)
                self.stirrup_combo.addItem(f"#{n} (db={r.diameter_mm:.1f} mm)", n)
            idx = STIRRUP_BAR_NUMBERS.index(3) if 3 in STIRRUP_BAR_NUMBERS else 0
            self.stirrup_combo.setCurrentIndex(idx)
            self.stirrup_combo.currentIndexChanged.connect(self._emit_if_ready)
            rebar_layout.addWidget(self.stirrup_combo, 1, 1, 1, 2)

            rebar_layout.addWidget(QLabel("N° de lechos:"), 2, 0)
            self.layers_spin = QSpinBox()
            self.layers_spin.setRange(1, MAX_LAYERS)
            self.layers_spin.setValue(1)
            self.layers_spin.valueChanged.connect(self._on_layers_changed)
            rebar_layout.addWidget(self.layers_spin, 2, 1, 1, 2)

            for i in range(MAX_LAYERS):
                label = QLabel(f"  Lecho {i + 1}:")
                spin = QSpinBox()
                spin.setRange(1, 12)
                spin.setValue(2)
                spin.setSuffix("  barras")
                spin.valueChanged.connect(self._emit_if_ready)
                row_idx = 3 + i
                rebar_layout.addWidget(label, row_idx, 0)
                rebar_layout.addWidget(spin, row_idx, 1, 1, 2)
                self.layer_bar_spins.append(spin)
                self.layer_row_widgets.append((label, spin))

            self._on_layers_changed(1)

        rebar_group.setLayout(rebar_layout)
        main_layout.addWidget(rebar_group)

        main_layout.addStretch()

        # Conectar señales DESPUÉS de crear widgets
        self._connect_signals()

    # ---- helpers de construcción ----

    def _make_spinbox(self, value, rng, decimals, step):
        sb = QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setRange(rng[0], rng[1])
        sb.setSingleStep(step)
        sb.setValue(value)
        sb.setMinimumWidth(110)
        sb.setAlignment(Qt.AlignmentFlag.AlignRight)
        return sb

    def _add_field(self, layout, row, label, unit, widget):
        lbl = QLabel(label)
        lbl.setObjectName("fieldLabel")
        unit_lbl = QLabel(f"[{unit}]")
        unit_lbl.setObjectName("unitLabel")
        layout.addWidget(lbl, row, 0)
        layout.addWidget(widget, row, 1)
        layout.addWidget(unit_lbl, row, 2)

    def _connect_signals(self):
        for sb in [self.mu_spinbox, self.h_spinbox, self.cover_spinbox,
                   self.fc_spinbox, self.fy_spinbox]:
            if sb is not None:
                sb.valueChanged.connect(self._emit_if_ready)
        if self.b_spinbox is not None:
            self.b_spinbox.valueChanged.connect(self._emit_if_ready)

    def _emit_if_ready(self):
        if not self._building:
            self.values_changed.emit()

    def _on_layers_changed(self, n_layers: int):
        """Muestra/oculta las filas de lechos según la cantidad seleccionada."""
        for i, (label, spin) in enumerate(self.layer_row_widgets):
            visible = i < n_layers
            label.setVisible(visible)
            spin.setVisible(visible)
        self._emit_if_ready()

    # ---- API pública ----

    def update_unit_system(self, unit_system: UnitSystem):
        self._building = True
        self.unit_system = unit_system
        old_layout = self.layout()
        if old_layout is not None:
            self._clear_layout(old_layout)
            QWidget().setLayout(old_layout)
        self._build_ui()
        self._building = False
        self.values_changed.emit()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout is not None:
                    self._clear_layout(sub_layout)

    def get_reinforcement_config(self) -> ReinforcementConfig:
        """Construye la ReinforcementConfig basada en la UI."""
        main_n = self.main_bar_combo.currentData()
        main_rebar = get_rebar_by_number(main_n)

        if self.is_slab:
            # Losa: sin estribo, 1 lecho con N barras/metro
            n_bars = self.layer_bar_spins[0].value()
            layers = [RebarLayer(
                n_bars=n_bars,
                bar_diameter_mm=main_rebar.diameter_mm,
                bar_area_mm2=main_rebar.area_mm2,
            )]
            return ReinforcementConfig(layers=layers, stirrup_diameter_mm=0.0)

        # Viga: estribo + lechos múltiples
        stirrup_n = self.stirrup_combo.currentData()
        stirrup_rebar = get_rebar_by_number(stirrup_n)
        n_layers = self.layers_spin.value()
        layers = []
        for i in range(n_layers):
            n_bars = self.layer_bar_spins[i].value()
            layers.append(RebarLayer(
                n_bars=n_bars,
                bar_diameter_mm=main_rebar.diameter_mm,
                bar_area_mm2=main_rebar.area_mm2,
            ))
        return ReinforcementConfig(
            layers=layers,
            stirrup_diameter_mm=stirrup_rebar.diameter_mm,
        )

    def get_values(self) -> dict:
        """Valores convertidos a SI internas (N·mm, mm, MPa) más reinforcement."""
        converter = get_converter(self.unit_system)

        mu_nmm = self.mu_spinbox.value() * converter.moment_to_knm * 1e6

        if self.is_slab:
            b_mm = 1000.0
        else:
            b_mm = self.b_spinbox.value() * converter.length_to_m * 1000.0

        h_mm = self.h_spinbox.value() * converter.length_to_m * 1000.0
        cover_mm = self.cover_spinbox.value() * converter.length_to_m * 1000.0
        fc_mpa = self.fc_spinbox.value() * converter.stress_to_mpa
        fy_mpa = self.fy_spinbox.value() * converter.stress_to_mpa

        return {
            "mu_nmm": mu_nmm,
            "b_mm": b_mm,
            "h_mm": h_mm,
            "cover_mm": cover_mm,
            "fc_mpa": fc_mpa,
            "fy_mpa": fy_mpa,
            "reinforcement": self.get_reinforcement_config(),
        }
