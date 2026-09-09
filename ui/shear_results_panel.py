"""Panel de resultados para diseño/revisión por cortante y torsión."""
from typing import Optional, Union
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt

from core.shear import BeamShearResult, SlabShearResult
from core.torsion import BeamShearTorsionResult
from core.units import get_converter, UnitSystem
from ui.form_helpers import make_panel_tabs, tab_page
from ui.theme import PALETTE


ShearResultT = Union[BeamShearResult, SlabShearResult]


def _force_in_user_unit(kn: float, cv) -> str:
    """Convierte kN a la unidad de fuerza del sistema actual."""
    value = kn / cv.force_to_kn
    return f"{value:.2f} {cv.force_unit}"


def _moment_in_user_unit(knm: float, cv) -> str:
    """Convierte kN·m a la unidad de momento del sistema actual."""
    value = knm / cv.moment_to_knm
    return f"{value:.2f} {cv.moment_unit}"


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

        title_text = (
            "📊 Cortante en losa" if self.is_slab
            else "📊 Cortante y torsión en viga"
        )
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

        if self.is_slab:
            # La losa tiene pocos grupos: no hace falta repartirlos
            main_layout.addWidget(cap_group)
            main_layout.addWidget(geom_group)
        else:
            # Cortante y torsión se separan para no exigir scroll
            self.result_tabs = make_panel_tabs()
            self.result_tabs.addTab(
                tab_page(cap_group, stir_group, geom_group), "Cortante"
            )
            self.result_tabs.addTab(
                tab_page(*self._build_torsion_groups()), "Torsión"
            )
            main_layout.addWidget(self.result_tabs)

        # --- Advertencias ---
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        main_layout.addWidget(self.warnings_label)

        main_layout.addStretch()

    def _build_torsion_groups(self):
        """Grupos de torsión (sólo viga). Ocultos mientras no haya torsión.

        Devuelve los widgets en el orden en que van dentro de la pestaña.
        """
        # Aviso mientras la torsión no forme parte del diseño
        self.torsion_placeholder = QLabel(
            "La torsión no está incluida en este diseño.\n\n"
            "Actívala en la pestaña «Torsión» del panel de entradas para "
            "revisar cortante y torsión en conjunto."
        )
        self.torsion_placeholder.setObjectName("infoLabel")
        self.torsion_placeholder.setWordWrap(True)
        self.torsion_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Demanda vs capacidad a torsión ---
        tor_group = QGroupBox("Torsión — Demanda vs Capacidad")
        tor_layout = QGridLayout()
        tor_layout.setVerticalSpacing(5)
        self.tu_label = self._make_value_label("—")
        self.phi_tth_label = self._make_value_label("—")
        self.phi_tcr_label = self._make_value_label("—")
        self.tu_design_label = self._make_value_label("—")
        self.phi_tn_label = self._make_value_label("—")
        self.torsion_ratio_label = self._make_value_label("—")
        self.torsion_regime_label = self._make_value_label("—")

        rows = [
            ("Tu (demanda):", self.tu_label),
            ("φTth (umbral, §22.7.4.1):", self.phi_tth_label),
            ("φTcr (agrietamiento, §22.7.5.1):", self.phi_tcr_label),
            ("Tu de diseño:", self.tu_design_label),
            ("φTn (con s adoptado):", self.phi_tn_label),
            ("φTn / Tu:", self.torsion_ratio_label),
            ("Régimen:", self.torsion_regime_label),
        ]
        for row, (text, widget) in enumerate(rows):
            tor_layout.addWidget(QLabel(text), row, 0)
            tor_layout.addWidget(widget, row, 1)
        tor_group.setLayout(tor_layout)
        self.torsion_demand_group = tor_group

        # --- Interacción V–T y refuerzo combinado ---
        comb_group = QGroupBox("Refuerzo combinado V + T")
        comb_layout = QGridLayout()
        comb_layout.setVerticalSpacing(5)
        self.section_check_label = self._make_value_label("—")
        self.av_s_label = self._make_value_label("—")
        self.at_s_label = self._make_value_label("—")
        self.avt_s_label = self._make_value_label("—")
        self.avt_s_min_label = self._make_value_label("—")
        self.s_comb_label = self._make_value_label("—")
        self.s_tor_max_label = self._make_value_label("—")

        rows = [
            ("Interacción sección (§22.7.7.1):", self.section_check_label),
            ("Av/s (cortante):", self.av_s_label),
            ("At/s (torsión, 1 rama):", self.at_s_label),
            ("(Av+2At)/s requerido:", self.avt_s_label),
            ("(Av+2At)/s mínimo (§9.6.4.2):", self.avt_s_min_label),
            ("s por resistencia V+T:", self.s_comb_label),
            ("s máx. torsión (§9.7.6.3.3):", self.s_tor_max_label),
        ]
        for row, (text, widget) in enumerate(rows):
            comb_layout.addWidget(QLabel(text), row, 0)
            comb_layout.addWidget(widget, row, 1)
        comb_group.setLayout(comb_layout)
        self.torsion_combined_group = comb_group

        # --- Acero longitudinal por torsión ---
        al_group = QGroupBox("Acero longitudinal por torsión")
        al_layout = QGridLayout()
        al_layout.setVerticalSpacing(5)
        self.al_req_label = self._make_value_label("—")
        self.al_min_label = self._make_value_label("—")
        self.al_adopted_label = self._make_value_label("—")
        self.al_adopted_label.setObjectName("asDesignLabel")
        self.al_bars_label = self._make_value_label("—")

        rows = [
            ("Al requerido (§22.7.6.1b):", self.al_req_label),
            ("Al mínimo (§9.6.4.3):", self.al_min_label),
            ("Al ADOPTADO:", self.al_adopted_label),
            ("Distribución sugerida:", self.al_bars_label),
        ]
        for row, (text, widget) in enumerate(rows):
            al_layout.addWidget(QLabel(text), row, 0)
            al_layout.addWidget(widget, row, 1)

        al_note = QLabel(
            "Al se reparte en el perímetro (≥1 barra por esquina, s ≤ 300 mm) y "
            "se suma al acero de flexión en la zona de tensión."
        )
        al_note.setObjectName("infoLabel")
        al_note.setWordWrap(True)
        al_layout.addWidget(al_note, len(rows), 0, 1, 2)
        al_group.setLayout(al_layout)
        self.torsion_long_group = al_group

        for group in (self.torsion_demand_group, self.torsion_combined_group,
                      self.torsion_long_group):
            group.setVisible(False)

        return (self.torsion_placeholder, self.torsion_demand_group,
                self.torsion_combined_group, self.torsion_long_group)

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
        self._paint_ratio(self.ratio_label, ratio)

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

        # Torsión (sólo viga)
        if not self.is_slab:
            self._display_torsion(result, cv)

        # Estado
        self._update_status_banner(result.status, result)

        # Advertencias
        if result.warnings:
            warn_text = "\n".join(f"⚠ {w}" for w in result.warnings)
            self.warnings_label.setText(warn_text)
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

    def _display_torsion(self, result: ShearResultT, cv):
        """Llena (o esconde) los grupos de torsión."""
        active = (
            isinstance(result, BeamShearTorsionResult)
            and result.torsion_active
            and result.tu_knm > 0
        )
        negligible = active and result.torsion_regime == "DESPRECIABLE"

        self.torsion_placeholder.setVisible(not active)
        self.torsion_demand_group.setVisible(active)
        self.torsion_combined_group.setVisible(active and not negligible)
        self.torsion_long_group.setVisible(active and not negligible)
        if not active:
            return

        self.tu_label.setText(_moment_in_user_unit(result.tu_knm, cv))
        self.phi_tth_label.setText(_moment_in_user_unit(result.phi_t_th_knm, cv))
        self.phi_tcr_label.setText(_moment_in_user_unit(result.phi_t_cr_knm, cv))
        self.tu_design_label.setText(_moment_in_user_unit(result.tu_design_knm, cv))

        if negligible:
            self.torsion_regime_label.setText("Despreciable (Tu ≤ φTth)")
            self.phi_tn_label.setText("—")
            self.torsion_ratio_label.setText("—")
            self._paint_ratio(self.torsion_ratio_label, float("inf"))
            return

        regime = "Diseño por torsión"
        if result.redistributed:
            regime = "Compatibilidad — Tu reducido a φTcr"
        elif result.torsion_type == "COMPATIBILIDAD":
            regime = "Compatibilidad (Tu ≤ φTcr)"
        self.torsion_regime_label.setText(regime)

        self.phi_tn_label.setText(_moment_in_user_unit(result.phi_tn_knm, cv))
        self.torsion_ratio_label.setText(f"{result.torsion_ratio:.2f}")
        self._paint_ratio(self.torsion_ratio_label, result.torsion_ratio)

        # Interacción de la sección
        self.section_check_label.setText(
            f"{result.stress_demand_mpa:.2f} ≤ {result.stress_limit_mpa:.2f} MPa"
        )
        self._paint_ratio(
            self.section_check_label, 1.0 if result.section_ok else 0.0
        )

        self.av_s_label.setText(f"{result.av_s_required:.4f} mm²/mm")
        self.at_s_label.setText(f"{result.at_s_required:.4f} mm²/mm")
        self.avt_s_label.setText(f"{result.avt_s_required:.4f} mm²/mm")
        self.avt_s_min_label.setText(f"{result.avt_s_min:.4f} mm²/mm")
        self.s_comb_label.setText(
            cv.format_length_small(result.s_combined_required_mm, 1)
            if result.s_combined_required_mm > 0 else "—"
        )
        self.s_tor_max_label.setText(
            cv.format_length_small(result.s_torsion_max_mm, 1)
        )

        # Acero longitudinal
        self.al_req_label.setText(cv.format_area(result.al_required_mm2 / 100.0))
        self.al_min_label.setText(cv.format_area(result.al_min_mm2 / 100.0))
        self.al_adopted_label.setText(cv.format_area(result.al_adopted_mm2 / 100.0))
        if result.long_bars is not None:
            bars = result.long_bars
            self.al_bars_label.setText(
                f"{bars.label} = {cv.format_area(bars.area_total_mm2 / 100.0)}"
            )
        else:
            self.al_bars_label.setText("—")

    def _paint_ratio(self, label: QLabel, ratio: float):
        color = PALETTE.ok if (ratio == float("inf") or ratio >= 1.0) else PALETTE.error
        label.setStyleSheet(
            f"color: {color}; font-weight: bold;"
            f"background-color: {PALETTE.bg_input};"
            f"border: 1px solid {color}; border-radius: 3px;"
            f"padding: 2px 6px;"
        )

    def _regime_text(self, regime: str) -> str:
        return {
            "NO REQUIERE": "No requiere estribos",
            "MINIMO": "Estribos por mínimo",
            "DISEÑO": "Estribos por diseño",
            "TORSION": "Estribos exigidos por torsión",
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
                       self.s_max_label, self.s_adopted_label,
                       self.tu_label, self.phi_tth_label, self.phi_tcr_label,
                       self.tu_design_label, self.phi_tn_label,
                       self.torsion_ratio_label, self.torsion_regime_label,
                       self.section_check_label, self.av_s_label, self.at_s_label,
                       self.avt_s_label, self.avt_s_min_label, self.s_comb_label,
                       self.s_tor_max_label, self.al_req_label, self.al_min_label,
                       self.al_adopted_label, self.al_bars_label]
            for group in (self.torsion_demand_group, self.torsion_combined_group,
                          self.torsion_long_group):
                group.setVisible(False)
            self.torsion_placeholder.setVisible(True)
        for lbl in labels:
            lbl.setText("—")
        self.status_label.setText("Estado: —")
        self.status_label.setStyleSheet("")
        self.warnings_label.setVisible(False)
