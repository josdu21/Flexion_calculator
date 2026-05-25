"""Panel de resultados para diseño/revisión por cortante."""
from typing import Optional, Union
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt

from core.shear import BeamShearResult, SlabShearResult
from core.units import get_converter, UnitSystem
from ui.theme import PALETTE


ShearResultT = Union[BeamShearResult, SlabShearResult]


def _force_in_user_unit(kn: float, cv) -> str:
    """Convierte kN a la unidad de fuerza del sistema actual."""
    value = kn / cv.force_to_kn
    return f"{value:.2f} {cv.force_unit}"


class ShearResultsPanel(QWidget):
    """Panel polimórfico: muestra resultados de viga o losa por cortante."""

    def __init__(self, unit_system: UnitSystem, is_slab: bool = False):
        super().__init__()
        self.unit_system = unit_system
        self.is_slab = is_slab
        self.result: Optional[ShearResultT] = None
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

        title_text = "📊 Cortante en losa" if self.is_slab else "📊 Cortante en viga"
        title = QLabel(title_text)
        title.setObjectName("panelTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # Banner de estado
        self.status_label = QLabel("Estado: —")
        self.status_label.setObjectName("statusBanner")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(40)
        main_layout.addWidget(self.status_label)

        # --- Demanda vs Capacidad ---
        cap_group = QGroupBox("Demanda vs Capacidad")
        cap_layout = QGridLayout()
        cap_layout.setVerticalSpacing(5)
        self.vu_label = self._make_value_label("—")
        self.vc_label = self._make_value_label("—")
        self.phi_vc_label = self._make_value_label("—")
        self.phi_vn_label = self._make_value_label("—")
        self.ratio_label = self._make_value_label("—")

        cap_layout.addWidget(QLabel("Vu (demanda):"), 0, 0)
        cap_layout.addWidget(self.vu_label, 0, 1)
        cap_layout.addWidget(QLabel("Vc (concreto):"), 1, 0)
        cap_layout.addWidget(self.vc_label, 1, 1)
        cap_layout.addWidget(QLabel("φVc:"), 2, 0)
        cap_layout.addWidget(self.phi_vc_label, 2, 1)
        if not self.is_slab:
            cap_layout.addWidget(QLabel("φVn (φ(Vc + Vs)):"), 3, 0)
            cap_layout.addWidget(self.phi_vn_label, 3, 1)
            cap_layout.addWidget(QLabel("φVn / Vu:"), 4, 0)
            cap_layout.addWidget(self.ratio_label, 4, 1)
        else:
            cap_layout.addWidget(QLabel("φVc / Vu:"), 3, 0)
            cap_layout.addWidget(self.ratio_label, 3, 1)
        cap_group.setLayout(cap_layout)
        main_layout.addWidget(cap_group)

        # --- Estribos (sólo viga) ---
        if not self.is_slab:
            stir_group = QGroupBox("Estribos requeridos")
            stir_layout = QGridLayout()
            stir_layout.setVerticalSpacing(5)
            self.regime_label = self._make_value_label("—")
            self.av_label = self._make_value_label("—")
            self.vs_req_label = self._make_value_label("—")
            self.s_req_label = self._make_value_label("—")
            self.s_min_req_label = self._make_value_label("—")
            self.s_max_label = self._make_value_label("—")
            self.s_adopted_label = self._make_value_label("—")
            self.s_adopted_label.setObjectName("asDesignLabel")

            stir_layout.addWidget(QLabel("Régimen:"), 0, 0)
            stir_layout.addWidget(self.regime_label, 0, 1)
            stir_layout.addWidget(QLabel("Av (área de ramas):"), 1, 0)
            stir_layout.addWidget(self.av_label, 1, 1)
            stir_layout.addWidget(QLabel("Vs requerido:"), 2, 0)
            stir_layout.addWidget(self.vs_req_label, 2, 1)
            stir_layout.addWidget(QLabel("s por resistencia:"), 3, 0)
            stir_layout.addWidget(self.s_req_label, 3, 1)
            stir_layout.addWidget(QLabel("s por mínimo (Av,min):"), 4, 0)
            stir_layout.addWidget(self.s_min_req_label, 4, 1)
            stir_layout.addWidget(QLabel("s máx. (ACI 9.7.6.2.2):"), 5, 0)
            stir_layout.addWidget(self.s_max_label, 5, 1)
            stir_layout.addWidget(QLabel("s ADOPTADO:"), 6, 0)
            stir_layout.addWidget(self.s_adopted_label, 6, 1)
            stir_group.setLayout(stir_layout)
            main_layout.addWidget(stir_group)

        # --- Geometría ---
        geom_group = QGroupBox("Geometría calculada")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(5)
        self.d_label = self._make_value_label("—")
        self.b_label = self._make_value_label("—")
        geom_layout.addWidget(QLabel("d efectivo:"), 0, 0)
        geom_layout.addWidget(self.d_label, 0, 1)
        geom_layout.addWidget(QLabel("b considerado:"), 1, 0)
        geom_layout.addWidget(self.b_label, 1, 1)
        geom_group.setLayout(geom_layout)
        main_layout.addWidget(geom_group)

        # --- Advertencias ---
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        main_layout.addWidget(self.warnings_label)

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

    def display_results(self, result: ShearResultT):
        self.result = result
        cv = get_converter(self.unit_system)

        # Geometría común
        self.d_label.setText(cv.format_length_small(result.d_mm, 2))
        self.b_label.setText(cv.format_length_small(result.b_mm, 1))

        # Demanda vs capacidad
        self.vu_label.setText(_force_in_user_unit(result.vu_kn, cv))
        self.vc_label.setText(_force_in_user_unit(result.vc_kn, cv))
        self.phi_vc_label.setText(_force_in_user_unit(result.phi_vc_kn, cv))

        if isinstance(result, BeamShearResult):
            self.phi_vn_label.setText(_force_in_user_unit(result.phi_vn_kn, cv))
            ratio = (result.phi_vn_kn / result.vu_kn) if result.vu_kn > 0 else float("inf")
        else:
            ratio = result.ratio

        ratio_text = f"{ratio:.2f}" if ratio != float("inf") else "∞"
        self.ratio_label.setText(ratio_text)
        ratio_color = (
            PALETTE.ok if (ratio == float("inf") or ratio >= 1.0) else PALETTE.error
        )
        self.ratio_label.setStyleSheet(
            f"color: {ratio_color}; font-weight: bold;"
            f"background-color: {PALETTE.bg_input};"
            f"border: 1px solid {ratio_color}; border-radius: 3px;"
            f"padding: 2px 6px;"
        )

        # Estribos (sólo viga)
        if isinstance(result, BeamShearResult):
            self.regime_label.setText(self._regime_text(result.regime))
            self.av_label.setText(f"{result.av_mm2:.1f} mm² ({result.stirrup_legs} ramas)")
            self.vs_req_label.setText(_force_in_user_unit(result.vs_required_kn, cv))
            self.s_req_label.setText(
                cv.format_length_small(result.s_required_mm, 1)
                if result.s_required_mm > 0 else "—"
            )
            self.s_min_req_label.setText(
                cv.format_length_small(result.s_min_required_mm, 1)
                if result.s_min_required_mm > 0 else "—"
            )
            self.s_max_label.setText(
                cv.format_length_small(result.s_max_mm, 1)
                if result.s_max_mm > 0 else "—"
            )
            if result.s_adopted_mm > 0:
                self.s_adopted_label.setText(
                    cv.format_length_small(result.s_adopted_mm, 1)
                )
            else:
                self.s_adopted_label.setText("— (sin estribos)")

        # Estado
        self._update_status_banner(result.status, result)

        # Advertencias
        if result.warnings:
            warn_text = "\n".join(f"⚠ {w}" for w in result.warnings)
            self.warnings_label.setText(warn_text)
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

    def _regime_text(self, regime: str) -> str:
        return {
            "NO REQUIERE": "No requiere estribos",
            "MINIMO": "Estribos por mínimo",
            "DISEÑO": "Estribos por diseño",
        }.get(regime, regime)

    def _update_status_banner(self, status: str, result: ShearResultT):
        color_map = {
            "OK": (PALETTE.ok, "✓ DISEÑO CORRECTO"),
            "NO REQUIERE ESTRIBOS": (PALETTE.ok, "✓ NO REQUIERE ESTRIBOS"),
            "AUMENTAR SECCIÓN": (PALETTE.error, "✗ AUMENTAR SECCIÓN"),
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
        labels = [self.vu_label, self.vc_label, self.phi_vc_label,
                  self.ratio_label, self.d_label, self.b_label]
        if not self.is_slab:
            labels += [self.phi_vn_label, self.regime_label, self.av_label,
                       self.vs_req_label, self.s_req_label, self.s_min_req_label,
                       self.s_max_label, self.s_adopted_label]
        for lbl in labels:
            lbl.setText("—")
        self.status_label.setText("Estado: —")
        self.status_label.setStyleSheet("")
        self.warnings_label.setVisible(False)
