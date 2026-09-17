from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QDoubleSpinBox,
    QGridLayout, QGroupBox, QSpinBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from core.units import UnitSystem, get_converter
from core.bar_tables import get_rebar_by_number
from core.design_code import DEFAULT_CODE, DesignCode
from core.flexion import ReinforcementConfig, RebarLayer
from ui.form_helpers import scroll_form, set_si, set_choice


MAX_LAYERS = 4
MAIN_BAR_NUMBERS = [3, 4, 5, 6, 8, 10, 12]
STIRRUP_BAR_NUMBERS = [2, 3, 4, 5]

# AASHTO §5.6.3.3 (γ₃) y §5.6.7 (γ_e); sólo se piden bajo esa norma.
BAR_SPECS = [
    ("ASTM A615 (γ₃ = 0.67)", "A615"),
    ("ASTM A706 (γ₃ = 0.75)", "A706"),
]
EXPOSURE_CLASSES = [
    ("Clase 1 — normal (γe = 1.00)", 1),
    ("Clase 2 — severa (γe = 0.75)", 2),
]


class InputPanel(QWidget):
    """Panel de entradas para diseño por flexión con configuración de refuerzo."""

    values_changed = pyqtSignal()

    def __init__(self, unit_system: UnitSystem, is_slab: bool = False,
                 design_code: DesignCode = DEFAULT_CODE):
        super().__init__()
        self.unit_system = unit_system
        self.is_slab = is_slab
        self.design_code = design_code
        self._building = True
        self._build_ui()
        self._building = False

    def _build_ui(self):
        converter = get_converter(self.unit_system)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        title = QLabel("Datos de entrada")
        title.setObjectName("panelTitle")
        main_layout.addWidget(title)
        hint = QLabel("Geometría y concreto compartidos con cortante.")
        hint.setObjectName("infoLabel")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

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
            value=(6.0 if self.unit_system == UnitSystem.ENGLISH else 15.0)
            if self.is_slab else converter.default_h, rng=converter.range_h,
            decimals=converter.decimals_length, step=length_step,
        )
        self._add_field(geom_layout, row, "Altura h", converter.length_unit, self.h_spinbox)
        row += 1

        self.cover_spinbox = self._make_spinbox(
            value=(0.75 if self.unit_system == UnitSystem.ENGLISH else 2.0)
            if self.is_slab else converter.default_cover, rng=converter.range_cover,
            decimals=converter.decimals_length, step=cover_step,
        )
        self._add_field(geom_layout, row, "Recubrimiento", converter.length_unit, self.cover_spinbox)
        geom_group.setLayout(geom_layout)

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

        # ----- Datos propios de AASHTO -----
        # Visible sólo bajo esa norma: ACI no usa ninguno de estos valores.
        self.aashto_group = QGroupBox("AASHTO LRFD")
        aashto_layout = QGridLayout()
        aashto_layout.setVerticalSpacing(6)

        aashto_layout.addWidget(QLabel("Tipo de barra:"), 0, 0)
        self.bar_spec_combo = QComboBox()
        for etiqueta, dato in BAR_SPECS:
            self.bar_spec_combo.addItem(etiqueta, dato)
        self.bar_spec_combo.setToolTip(
            "γ₃ del momento de fisuración M_cr (§5.6.3.3)"
        )
        self.bar_spec_combo.currentIndexChanged.connect(self._emit_if_ready)
        aashto_layout.addWidget(self.bar_spec_combo, 0, 1, 1, 2)

        aashto_layout.addWidget(QLabel("Exposición:"), 1, 0)
        self.exposure_combo = QComboBox()
        for etiqueta, dato in EXPOSURE_CLASSES:
            self.exposure_combo.addItem(etiqueta, dato)
        self.exposure_combo.setToolTip(
            "γ_e del control de fisuración (§5.6.7)"
        )
        self.exposure_combo.currentIndexChanged.connect(self._emit_if_ready)
        aashto_layout.addWidget(self.exposure_combo, 1, 1, 1, 2)

        self.ms_spinbox = self._make_spinbox(
            value=0.0, rng=(0.0, converter.range_mu[1]),
            decimals=converter.decimals_moment,
            step=max(0.1, converter.default_mu * 0.05),
        )
        self.ms_spinbox.setToolTip(
            "Momento de servicio para el control de fisuración (§5.6.7).\n"
            "En cero, esa verificación se omite."
        )
        self._add_field(aashto_layout, 2, "Ms (servicio)",
                        converter.moment_unit, self.ms_spinbox)

        nota = QLabel(
            "Ms en cero omite el control de fisuración de §5.6.7."
        )
        nota.setObjectName("infoLabel")
        nota.setWordWrap(True)
        aashto_layout.addWidget(nota, 3, 0, 1, 3)
        self.aashto_group.setLayout(aashto_layout)

        self.form_scroll = scroll_form(
            load_group, geom_group, mat_group, rebar_group, self.aashto_group
        )
        main_layout.addWidget(self.form_scroll)

        self._apply_design_code()

        # Conectar señales DESPUÉS de crear widgets
        self._connect_signals()

    # ---- helpers de construcción ----

    def _make_spinbox(self, value, rng, decimals, step):
        sb = QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setRange(rng[0], rng[1])
        sb.setSingleStep(step)
        sb.setValue(value)
        sb.setKeyboardTracking(False)
        sb.setMinimumWidth(100)
        sb.setAlignment(Qt.AlignmentFlag.AlignRight)
        return sb

    def _add_field(self, layout, row, label, unit, widget):
        lbl = QLabel(label)
        lbl.setObjectName("fieldLabel")
        lbl.setBuddy(widget)
        widget.setAccessibleName(f"{label} ({unit})")
        unit_lbl = QLabel(f"[{unit}]")
        unit_lbl.setObjectName("unitLabel")
        layout.addWidget(lbl, row, 0)
        layout.addWidget(widget, row, 1)
        layout.addWidget(unit_lbl, row, 2)

    def _connect_signals(self):
        for sb in [self.mu_spinbox, self.h_spinbox, self.cover_spinbox,
                   self.fc_spinbox, self.fy_spinbox, self.ms_spinbox]:
            if sb is not None:
                sb.valueChanged.connect(self._emit_if_ready)
        if self.b_spinbox is not None:
            self.b_spinbox.valueChanged.connect(self._emit_if_ready)

    def _apply_design_code(self):
        """Muestra los campos propios de AASHTO sólo cuando esa norma rige."""
        self.aashto_group.setVisible(
            self.design_code is DesignCode.AASHTO_LRFD_2020
        )

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
        # Reconstruir la UI pierde los combos, así que se rescatan antes.
        estado_aashto = (
            self.bar_spec_combo.currentData(),
            self.exposure_combo.currentData(),
            self.ms_spinbox.value() * get_converter(self.unit_system).moment_to_knm,
        )
        self.unit_system = unit_system
        old_layout = self.layout()
        if old_layout is not None:
            self._clear_layout(old_layout)
            QWidget().setLayout(old_layout)
        self._build_ui()
        bar_spec, exposure, ms_knm = estado_aashto
        set_choice(self.bar_spec_combo, bar_spec)
        set_choice(self.exposure_combo, exposure)
        set_si(self.ms_spinbox, ms_knm, get_converter(unit_system).moment_to_knm)
        self._building = False
        self.values_changed.emit()

    def set_design_code(self, code: DesignCode):
        """Cambia la norma activa y ajusta qué campos se muestran."""
        if code == self.design_code:
            return
        self.design_code = code
        self._apply_design_code()
        self._emit_if_ready()

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

    def get_state(self) -> dict:
        """Estado serializable del panel, con las magnitudes en SI internas."""
        cv = get_converter(self.unit_system)
        return {
            "mu_nmm": self.mu_spinbox.value() * cv.moment_to_knm * 1e6,
            "b_mm": (None if self.is_slab
                     else self.b_spinbox.value() * cv.length_to_m * 1000.0),
            "h_mm": self.h_spinbox.value() * cv.length_to_m * 1000.0,
            "cover_mm": self.cover_spinbox.value() * cv.length_to_m * 1000.0,
            "fc_mpa": self.fc_spinbox.value() * cv.stress_to_mpa,
            "fy_mpa": self.fy_spinbox.value() * cv.stress_to_mpa,
            "main_bar": self.main_bar_combo.currentData(),
            "stirrup_bar": (self.stirrup_combo.currentData()
                            if self.stirrup_combo else None),
            "n_layers": self.layers_spin.value() if self.layers_spin else 1,
            "layer_bars": [s.value() for s in self.layer_bar_spins],
            "bar_spec": self.bar_spec_combo.currentData(),
            "exposure_class": self.exposure_combo.currentData(),
            "ms_nmm": self.ms_spinbox.value() * cv.moment_to_knm * 1e6,
        }

    def set_state(self, state: dict) -> None:
        """Restaura el panel desde un estado en SI, sin recalcular por cada campo."""
        cv = get_converter(self.unit_system)
        self._building = True
        try:
            set_si(self.mu_spinbox, state.get("mu_nmm"), 1e6 * cv.moment_to_knm)
            if not self.is_slab:
                set_si(self.b_spinbox, state.get("b_mm"), 1000.0 * cv.length_to_m)
            set_si(self.h_spinbox, state.get("h_mm"), 1000.0 * cv.length_to_m)
            set_si(self.cover_spinbox, state.get("cover_mm"), 1000.0 * cv.length_to_m)
            set_si(self.fc_spinbox, state.get("fc_mpa"), cv.stress_to_mpa)
            set_si(self.fy_spinbox, state.get("fy_mpa"), cv.stress_to_mpa)
            set_choice(self.main_bar_combo, state.get("main_bar"))
            set_choice(self.stirrup_combo, state.get("stirrup_bar"))
            set_choice(self.bar_spec_combo, state.get("bar_spec"))
            set_choice(self.exposure_combo, state.get("exposure_class"))
            set_si(self.ms_spinbox, state.get("ms_nmm"), 1e6 * cv.moment_to_knm)

            if self.layers_spin is not None and state.get("n_layers"):
                self.layers_spin.setValue(int(state["n_layers"]))
                self._on_layers_changed(int(state["n_layers"]))
            for spin, n in zip(self.layer_bar_spins, state.get("layer_bars") or []):
                spin.setValue(int(n))
        finally:
            self._building = False
        self.values_changed.emit()

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

        # Se emite siempre el superconjunto de las dos normas; el despachador
        # de core/design_code.py entrega a cada motor sólo lo que acepta.
        return {
            "mu_nmm": mu_nmm,
            "b_mm": b_mm,
            "h_mm": h_mm,
            "cover_mm": cover_mm,
            "fc_mpa": fc_mpa,
            "fy_mpa": fy_mpa,
            "reinforcement": self.get_reinforcement_config(),
            "bar_spec": self.bar_spec_combo.currentData(),
            "exposure_class": self.exposure_combo.currentData(),
            "ms_nmm": self.ms_spinbox.value() * converter.moment_to_knm * 1e6,
            "lam": 1.0,
        }
