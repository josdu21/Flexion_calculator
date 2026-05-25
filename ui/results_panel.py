"""Panel de resultados con diagrama de esfuerzos integrado."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QLabel, QHeaderView, QFrame,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from core.flexion import FlexionDesignResult
from core.units import get_converter, UnitSystem
from ui.stress_diagram import StressDiagramWidget
from ui.theme import PALETTE


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
        title = QLabel("📊 Resultados del diseño")
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Diagrama de esfuerzos
        diagram_group = QGroupBox("Diagrama de esfuerzos (ACI 318 — Bloque de Whitney)")
        diagram_layout = QVBoxLayout()
        self.diagram = StressDiagramWidget()
        self.diagram.setMinimumHeight(260)
        diagram_layout.addWidget(self.diagram)
        diagram_group.setLayout(diagram_layout)
        main_layout.addWidget(diagram_group)

        # Banner de estado
        self.status_label = QLabel("Estado: —")
        self.status_label.setObjectName("statusBanner")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(40)
        main_layout.addWidget(self.status_label)

        # Grid principal con 2 columnas
        info_layout = QHBoxLayout()
        info_layout.setSpacing(8)

        # --- Columna 1 ---
        col1 = QVBoxLayout()

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
        steel_layout.addWidget(QLabel("As máximo:"), 3, 0)
        steel_layout.addWidget(self.as_max_label, 3, 1)
        steel_group.setLayout(steel_layout)
        col1.addWidget(steel_group)

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
        col1.addWidget(cap_group)

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
        col1.addWidget(geom_group)

        info_layout.addLayout(col1, 1)

        # --- Columna 2 ---
        col2 = QVBoxLayout()

        # Separación de barras (NUEVO)
        spacing_group = QGroupBox("Separación entre barras (ACI 318-19)")
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
        col2.addWidget(spacing_group)

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
        col2.addWidget(forces_group)

        info_layout.addLayout(col2, 1)
        main_layout.addLayout(info_layout)

        # Lista de advertencias
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        main_layout.addWidget(self.warnings_label)

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

        # Estado
        self._update_status_banner(result.status)

        # Advertencias
        if result.warnings:
            warn_text = "\n".join(f"⚠ {w}" for w in result.warnings)
            self.warnings_label.setText(warn_text)
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

        # Diagrama
        self.diagram.set_result(result, self.unit_system)

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
            "OK": (PALETTE.ok, "✓ DISEÑO CORRECTO"),
            "ARMADO INSUFICIENTE": (PALETTE.error, "✗ ARMADO INSUFICIENTE"),
            "AUMENTAR SECCIÓN": (PALETTE.error, "✗ AUMENTAR SECCIÓN"),
            "REDUCIR SECCIÓN": (PALETTE.warning, "⚠ REDUCIR SECCIÓN"),
            "ERROR": (PALETTE.error, "✗ DATOS INVÁLIDOS"),
        }
        color, text = color_map.get(status, (PALETTE.text_muted, status))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"background-color: {color}; color: {PALETTE.bg_base}; "
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
