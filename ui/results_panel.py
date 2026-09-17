"""Panel de resultados con diagrama de esfuerzos integrado."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox, QLabel, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt

from core.design_code import DesignCode, code_of
from core.flexion import FlexionDesignResult
from core.units import get_converter, UnitSystem
from ui.stress_diagram import StressDiagramWidget
from ui.theme import PALETTE, alpha
from ui.form_helpers import DetailsSection, ResponsiveColumns


class ResultsPanel(QWidget):
    def __init__(self, unit_system: UnitSystem):
        super().__init__()
        self.unit_system = unit_system
        self.result: FlexionDesignResult = None
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Título
        title = QLabel("Resultado del diseño")
        title.setObjectName("panelTitle")
        main_layout.addWidget(title)

        # Diagrama de esfuerzos
        diagram_group = QGroupBox("Diagrama de esfuerzos (bloque rectangular equivalente)")
        diagram_layout = QVBoxLayout()
        self.diagram = StressDiagramWidget()
        self.diagram.setMinimumHeight(260)
        diagram_layout.addWidget(self.diagram)
        diagram_group.setLayout(diagram_layout)

        # Banner de estado
        self.status_label = QLabel("Estado: —")
        self.status_label.setObjectName("statusBanner")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(40)
        main_layout.addWidget(self.status_label)

        # Resumen adaptable: dos tarjetas que se apilan en ventanas estrechas.

        # Acero
        steel_group = QGroupBox("Acero")
        steel_layout = QGridLayout()
        steel_layout.setVerticalSpacing(5)
        self.as_provided_label = self._make_value_label("—")
        self.as_provided_label.setObjectName("asDesignLabel")
        self.as_required_label = self._make_value_label("—")
        self.as_min_label = self._make_value_label("—")
        self.as_max_label = self._make_value_label("—")

        steel_layout.addWidget(QLabel("As proporcionado:"), 0, 0)
        steel_layout.addWidget(self.as_provided_label, 0, 1)
        steel_layout.addWidget(QLabel("As requerido:"), 1, 0)
        steel_layout.addWidget(self.as_required_label, 1, 1)
        steel_layout.addWidget(QLabel("As mínimo:"), 2, 0)
        steel_layout.addWidget(self.as_min_label, 2, 1)
        # El rótulo cambia con la norma: AASHTO no define un máximo, sino el
        # acero con el que la sección pasa a ser de compresión controlada.
        self.as_max_caption = QLabel("As máximo:")
        steel_layout.addWidget(self.as_max_caption, 3, 0)
        steel_layout.addWidget(self.as_max_label, 3, 1)
        steel_group.setLayout(steel_layout)

        # Capacidad
        cap_group = QGroupBox("Capacidad vs Demanda")
        cap_layout = QGridLayout()
        cap_layout.setVerticalSpacing(5)
        self.phimn_label = self._make_value_label("—")
        self.mu_label = self._make_value_label("—")
        self.ratio_label = self._make_value_label("—")

        cap_layout.addWidget(QLabel("φMn (capacidad):"), 0, 0)
        cap_layout.addWidget(self.phimn_label, 0, 1)
        cap_layout.addWidget(QLabel("Mu (demanda):"), 1, 0)
        cap_layout.addWidget(self.mu_label, 1, 1)
        cap_layout.addWidget(QLabel("φMn / Mu:"), 2, 0)
        cap_layout.addWidget(self.ratio_label, 2, 1)
        cap_group.setLayout(cap_layout)

        # Geometría
        geom_group = QGroupBox("Geometría calculada")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(5)
        self.d_label = self._make_value_label("—")
        self.a_label = self._make_value_label("—")
        self.c_label = self._make_value_label("—")
        self.jd_label = self._make_value_label("—")
        self.beta1_label = self._make_value_label("—")

        geom_layout.addWidget(QLabel("d efectivo:"), 0, 0)
        geom_layout.addWidget(self.d_label, 0, 1)
        geom_layout.addWidget(QLabel("a (bloque):"), 1, 0)
        geom_layout.addWidget(self.a_label, 1, 1)
        geom_layout.addWidget(QLabel("c (eje neutro):"), 2, 0)
        geom_layout.addWidget(self.c_label, 2, 1)
        geom_layout.addWidget(QLabel("jd:"), 3, 0)
        geom_layout.addWidget(self.jd_label, 3, 1)
        geom_layout.addWidget(QLabel("β₁:"), 4, 0)
        geom_layout.addWidget(self.beta1_label, 4, 1)
        geom_group.setLayout(geom_layout)


        # Separación de barras (NUEVO)
        spacing_group = QGroupBox("Separación entre barras")
        spacing_layout = QGridLayout()
        spacing_layout.setVerticalSpacing(5)

        self.s_h_actual_label = self._make_value_label("—")
        self.s_h_min_label = self._make_value_label("—")
        self.s_h_status_label = QLabel("—")
        self.s_h_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.s_v_actual_label = self._make_value_label("—")
        self.s_v_min_label = self._make_value_label("—")
        self.s_v_status_label = QLabel("—")
        self.s_v_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        spacing_layout.addWidget(QLabel("Sep. horizontal:"), 0, 0)
        spacing_layout.addWidget(self.s_h_actual_label, 0, 1)
        spacing_layout.addWidget(self.s_h_status_label, 0, 2)
        spacing_layout.addWidget(QLabel("  → Mínima:"), 1, 0)
        spacing_layout.addWidget(self.s_h_min_label, 1, 1)
        spacing_layout.addWidget(QLabel("Sep. vertical:"), 2, 0)
        spacing_layout.addWidget(self.s_v_actual_label, 2, 1)
        spacing_layout.addWidget(self.s_v_status_label, 2, 2)
        spacing_layout.addWidget(QLabel("  → Mínima:"), 3, 0)
        spacing_layout.addWidget(self.s_v_min_label, 3, 1)

        spacing_group.setLayout(spacing_layout)

        # Fuerzas internas
        forces_group = QGroupBox("Fuerzas internas")
        forces_layout = QGridLayout()
        forces_layout.setVerticalSpacing(5)
        self.c_force_label = self._make_value_label("—")
        self.c_force_label.setStyleSheet(
            f"color: {PALETTE.compression}; font-weight: bold;"
            f"background-color: {PALETTE.bg_input};"
            f"border: 1px solid {PALETTE.border}; border-radius: 3px;"
            f"padding: 2px 6px;"
        )
        self.t_force_label = self._make_value_label("—")
        self.t_force_label.setStyleSheet(
            f"color: {PALETTE.tension}; font-weight: bold;"
            f"background-color: {PALETTE.bg_input};"
            f"border: 1px solid {PALETTE.border}; border-radius: 3px;"
            f"padding: 2px 6px;"
        )
        self.rho_label = self._make_value_label("—")

        forces_layout.addWidget(QLabel("C (compresión):"), 0, 0)
        forces_layout.addWidget(self.c_force_label, 0, 1)
        forces_layout.addWidget(QLabel("T (tensión):"), 1, 0)
        forces_layout.addWidget(self.t_force_label, 1, 1)
        forces_layout.addWidget(QLabel("ρ proporcionada:"), 2, 0)
        forces_layout.addWidget(self.rho_label, 2, 1)
        forces_group.setLayout(forces_layout)

        # Propio de AASHTO: φ variable, refuerzo mínimo por momento y fisuración.
        # Oculto bajo ACI, donde ninguno de estos valores existe.
        self.aashto_group = QGroupBox("AASHTO LRFD")
        aashto_layout = QGridLayout()
        aashto_layout.setVerticalSpacing(5)
        self.phi_label = self._make_value_label("—")
        self.eps_t_label = self._make_value_label("—")
        self.behaviour_label = self._make_value_label("—")
        self.mcr_label = self._make_value_label("—")
        self.mu_min_label = self._make_value_label("—")
        self.crack_label = self._make_value_label("—")

        for fila, (texto, widget) in enumerate((
            ("φ aplicado:", self.phi_label),
            ("εt (acero extremo):", self.eps_t_label),
            ("Comportamiento:", self.behaviour_label),
            ("Mcr (§5.6.3.3):", self.mcr_label),
            ("Mu,mín exigido:", self.mu_min_label),
            ("Sep. máx. fisuración:", self.crack_label),
        )):
            aashto_layout.addWidget(QLabel(texto), fila, 0)
            aashto_layout.addWidget(widget, fila, 1)
        self.aashto_group.setLayout(aashto_layout)

        main_layout.addWidget(ResponsiveColumns(steel_group, cap_group))
        main_layout.addWidget(diagram_group)
        self.details = DetailsSection(
            "Comprobaciones y valores intermedios",
            spacing_group, geom_group, forces_group, self.aashto_group,
        )
        main_layout.addWidget(self.details)

        # Lista de advertencias
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        main_layout.insertWidget(2, self.warnings_label)
        main_layout.addStretch()

    def _make_value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("valueLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return lbl

    def update_unit_system(self, unit_system: UnitSystem):
        self.unit_system = unit_system
        if self.result is not None:
            self.display_results(self.result)

    def display_results(self, result: FlexionDesignResult):
        self.result = result
        cv = get_converter(self.unit_system)

        # Geometría — en cm (SI/MKS) o pulgadas (Inglés)
        self.d_label.setText(cv.format_length_small(result.d_mm, decimals=2))
        self.a_label.setText(cv.format_length_small(result.a_mm, decimals=2))
        self.c_label.setText(cv.format_length_small(result.c_mm, decimals=2))
        self.jd_label.setText(cv.format_length_small(result.jd_mm, decimals=2))
        self.beta1_label.setText(f"{result.beta_1:.3f}")

        # Acero
        self.as_provided_label.setText(cv.format_area(result.as_provided_cm2, 2))
        self.as_required_label.setText(cv.format_area(result.as_required_cm2, 2))
        self.as_min_label.setText(cv.format_area(result.as_min_cm2, 2))
        self.as_max_label.setText(cv.format_area(result.as_max_cm2, 2))

        # Colorear As proporcionado según verificación
        as_demand = max(result.as_required_cm2, result.as_min_cm2)
        if result.as_provided_cm2 >= as_demand:
            self.as_provided_label.setStyleSheet(
                f"color: {PALETTE.ok}; font-weight: bold; font-size: 12pt;"
                f"background-color: {PALETTE.bg_input};"
                f"border: 1px solid {PALETTE.ok}; border-radius: 3px;"
                f"padding: 2px 6px;"
            )
        else:
            self.as_provided_label.setStyleSheet(
                f"color: {PALETTE.error}; font-weight: bold; font-size: 12pt;"
                f"background-color: {PALETTE.bg_input};"
                f"border: 1px solid {PALETTE.error}; border-radius: 3px;"
                f"padding: 2px 6px;"
            )

        # Capacidad
        # convertir kN·m a unidad del sistema
        mu_unit = result.mu_demand_knm / cv.moment_to_knm
        phimn_unit = result.phi_mn_knm / cv.moment_to_knm
        self.phimn_label.setText(f"{phimn_unit:.2f} {cv.moment_unit}")
        self.mu_label.setText(f"{mu_unit:.2f} {cv.moment_unit}")
        ratio = result.phi_mn_knm / result.mu_demand_knm if result.mu_demand_knm > 0 else 0.0
        self.ratio_label.setText(f"{ratio:.2f}")
        ratio_color = PALETTE.ok if ratio >= 1.0 else PALETTE.error
        self.ratio_label.setStyleSheet(
            f"color: {ratio_color}; font-weight: bold;"
            f"background-color: {PALETTE.bg_input};"
            f"border: 1px solid {ratio_color}; border-radius: 3px;"
            f"padding: 2px 6px;"
        )

        # Fuerzas
        self.c_force_label.setText(f"{result.compression_kn:.2f} kN")
        self.t_force_label.setText(f"{result.tension_kn:.2f} kN")
        self.rho_label.setText(f"{result.rho_provided:.4f}")

        # Separación — en cm (SI/MKS) o pulgadas (Inglés)
        s_h_text = (cv.format_length_small(result.horizontal_spacing_mm, 2)
                    if result.horizontal_spacing_mm > 0 else "—")
        self.s_h_actual_label.setText(s_h_text)
        self.s_h_min_label.setText(cv.format_length_small(result.horizontal_spacing_min_mm, 2))
        self._set_status_chip(
            self.s_h_status_label, result.horizontal_spacing_ok,
            applies=(result.horizontal_spacing_mm > 0)
        )

        s_v_text = (cv.format_length_small(result.vertical_spacing_mm, 2)
                    if result.vertical_spacing_mm > 0 else "n/a")
        self.s_v_actual_label.setText(s_v_text)
        self.s_v_min_label.setText(cv.format_length_small(result.vertical_spacing_min_mm, 2))
        self._set_status_chip(
            self.s_v_status_label, result.vertical_spacing_ok,
            applies=(result.vertical_spacing_mm > 0)
        )

        # Bloque propio de AASHTO
        self._display_aashto(result, cv)

        # Estado
        self._update_status_banner(result.status)

        # Advertencias
        if result.warnings:
            warn_text = "\n".join(result.warnings)
            self.warnings_label.setText(warn_text)
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

        # Diagrama
        self.diagram.set_result(result, self.unit_system)

    def _display_aashto(self, result, cv):
        """Llena (o esconde) los valores que sólo existen bajo AASHTO."""
        aplica = code_of(result) is DesignCode.AASHTO_LRFD_2020
        self.aashto_group.setVisible(aplica)

        if aplica:
            self.as_max_caption.setText("As en εt = εcl:")
            self.as_max_caption.setToolTip(
                "AASHTO no fija un As máximo. Es el acero con el que la sección\n"
                "llega a compresión controlada y φ cae a 0.75 (§5.5.4.2)."
            )
            self.as_min_caption_tip = (
                "Área equivalente al mínimo por momento de §5.6.3.3:\n"
                "M_r ≥ min(1.33·M_u, M_cr)."
            )
            self.as_min_label.setToolTip(self.as_min_caption_tip)
        else:
            self.as_max_caption.setText("As máximo:")
            self.as_max_caption.setToolTip("")
            self.as_min_label.setToolTip("")

        if not aplica:
            return

        self.phi_label.setText(f"{result.phi_flexion:.3f}")
        # φ por debajo de 0.90 es la señal de que la sección está sobrearmada.
        color = PALETTE.ok if result.phi_flexion >= 0.90 else PALETTE.warning
        self.phi_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        self.eps_t_label.setText(f"{result.epsilon_t:.5f}")
        self.behaviour_label.setText(result.section_behaviour.capitalize())

        m = lambda knm: f"{knm / cv.moment_to_knm:.2f} {cv.moment_unit}"
        self.mcr_label.setText(m(result.mcr_knm))
        self.mu_min_label.setText(m(result.mu_min_knm))

        if result.crack_control_applies:
            texto = cv.format_length_small(result.crack_spacing_max_mm, 1)
            if not result.crack_control_ok:
                texto += "  ✗"
            self.crack_label.setText(texto)
        else:
            self.crack_label.setText("— (falta Ms)")

    def _set_status_chip(self, label: QLabel, ok: bool, applies: bool = True):
        if not applies:
            label.setText("n/a")
            label.setStyleSheet(f"color: {PALETTE.text_muted}; font-style: italic;")
            return
        if ok:
            label.setText("✓ OK")
            label.setStyleSheet(
                f"color: {PALETTE.bg_base}; background-color: {PALETTE.ok};"
                f"font-weight: bold; border-radius: 4px; padding: 2px 8px;"
            )
        else:
            label.setText("✗ FALLA")
            label.setStyleSheet(
                f"color: {PALETTE.bg_base}; background-color: {PALETTE.error};"
                f"font-weight: bold; border-radius: 4px; padding: 2px 8px;"
            )

    def _update_status_banner(self, status: str):
        color_map = {
            "OK": (PALETTE.ok, "Diseño correcto"),
            "ARMADO INSUFICIENTE": (PALETTE.error, "Armado insuficiente"),
            "AUMENTAR SECCIÓN": (PALETTE.error, "Aumentar sección"),
            "REDUCIR SECCIÓN": (PALETTE.warning, "Reducir sección"),
            "ERROR": (PALETTE.error, "Datos inválidos"),
        }
        color, text = color_map.get(status, (PALETTE.text_muted, status))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"background-color: {alpha(color, 0.12)}; color: {color}; "
            f"border: 1px solid {alpha(color, 0.35)}; "
            f"font-size: 13pt; font-weight: bold; "
            f"border-radius: 6px; padding: 6px;"
        )

    def clear(self):
        self.result = None
        for lbl in [self.d_label, self.a_label, self.c_label, self.jd_label,
                    self.beta1_label, self.as_required_label, self.as_min_label,
                    self.as_max_label, self.as_provided_label, self.c_force_label,
                    self.t_force_label, self.rho_label, self.phimn_label,
                    self.mu_label, self.ratio_label,
                    self.s_h_actual_label, self.s_h_min_label,
                    self.s_v_actual_label, self.s_v_min_label]:
            lbl.setText("—")
        self.status_label.setText("Estado: —")
        self.status_label.setStyleSheet("")
        self.warnings_label.setVisible(False)
        self.diagram.set_result(None, self.unit_system)
