"""Panel de resultados para diseño/revisión por cortante y torsión."""
from typing import Optional, Union
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt

from core.design_code import DesignCode, code_of
from core.shear import BeamShearResult, SlabShearResult
from core.torsion import BeamShearTorsionResult
from core.units import get_converter, UnitSystem
from ui.form_helpers import DetailsSection
from ui.theme import PALETTE, alpha


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
        # Rótulos cuyo texto depende de la norma; los llena _caption().
        self._code_captions = []
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

        title = QLabel("Resultado del diseño")
        title.setObjectName("panelTitle")
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
            cap_layout.addWidget(self._caption((
                "φVn (φ(Vc + Vs)):",
                "φVn (φ·mín(Vc+Vs, 0.25f'c·b·dv)):",
            )), 3, 0)
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
            self.s_max_caption = self._caption((
                "s máx. (ACI 9.7.6.2.2):", "s máx. (§5.7.2.6):",
            ))
            stir_layout.addWidget(self.s_max_caption, 5, 0)
            stir_layout.addWidget(self.s_max_label, 5, 1)
            stir_group.setLayout(stir_layout)

        # --- Geometría ---
        geom_group = QGroupBox("Geometría calculada")
        geom_layout = QGridLayout()
        geom_layout.setVerticalSpacing(5)
        self.d_label = self._make_value_label("—")
        self.b_label = self._make_value_label("—")
        self.d_caption = self._caption(("d efectivo:", "dv (cortante):"))
        geom_layout.addWidget(self.d_caption, 0, 0)
        geom_layout.addWidget(self.d_label, 0, 1)
        geom_layout.addWidget(QLabel("b considerado:"), 1, 0)
        geom_layout.addWidget(self.b_label, 1, 1)
        geom_group.setLayout(geom_layout)

        # --- Propio de AASHTO ---
        # d_v, β, θ, el tope de la sección y la revisión longitudinal §5.7.3.5.
        self.aashto_group = QGroupBox("AASHTO LRFD")
        aashto_layout = QGridLayout()
        aashto_layout.setVerticalSpacing(5)
        self.dv_label = self._make_value_label("—")
        self.beta_theta_label = self._make_value_label("—")
        self.vn_max_label = self._make_value_label("—")
        self.long_check_label = self._make_value_label("—")
        for fila, (texto, widget) in enumerate((
            ("dv (cortante):", self.dv_label),
            ("β / θ:", self.beta_theta_label),
            ("φVn,máx (0.25 f'c b dv):", self.vn_max_label),
            ("Refuerzo long. §5.7.3.5:", self.long_check_label),
        )):
            aashto_layout.addWidget(QLabel(texto), fila, 0)
            aashto_layout.addWidget(widget, fila, 1)
        self.aashto_group.setLayout(aashto_layout)

        main_layout.addWidget(cap_group)
        if self.is_slab:
            self.details = DetailsSection(
                "Geometría calculada", geom_group, self.aashto_group
            )
        else:
            # La separación adoptada permanece visible; los límites se consultan
            # en el desglose sin repetir el resultado en dos lugares.
            summary = QGroupBox("Separación de estribos")
            summary_layout = QGridLayout(summary)
            summary_layout.addWidget(QLabel("s adoptado"), 0, 0)
            summary_layout.addWidget(self.s_adopted_label, 0, 1)
            main_layout.addWidget(summary)
            self.details = DetailsSection(
                "Comprobaciones de cortante",
                stir_group, geom_group, self.aashto_group,
            )
            torsion_groups = self._build_torsion_groups()
            # No se reserva una página vacía para torsión inactiva.
            self.torsion_details = DetailsSection("Comprobaciones de torsión", *torsion_groups[:-1])
            main_layout.addWidget(self.torsion_long_group)
            main_layout.addWidget(self.torsion_details)
        main_layout.addWidget(self.details)

        # --- Advertencias ---
        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("warningLabel")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        main_layout.insertWidget(2, self.warnings_label)

        main_layout.addStretch()

    def _build_torsion_groups(self):
        """Grupos de torsión (sólo viga). Ocultos mientras no haya torsión.

        Devuelve las comprobaciones y el refuerzo longitudinal.
        """
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
            (("φTth (umbral, §22.7.4.1):", "Umbral 0.25·φTcr (§5.7.2.1):"),
             self.phi_tth_label),
            (("φTcr (agrietamiento, §22.7.5.1):",
              "φTcr (agrietamiento, §5.7.2.1):"), self.phi_tcr_label),
            ("Tu de diseño:", self.tu_design_label),
            ("φTn (con s adoptado):", self.phi_tn_label),
            ("φTn / Tu:", self.torsion_ratio_label),
            ("Régimen:", self.torsion_regime_label),
        ]
        for row, (text, widget) in enumerate(rows):
            tor_layout.addWidget(self._caption(text), row, 0)
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
            (("Interacción sección (§22.7.7.1):",
              "Tope de sección con Vu,eq (§5.7.3.3):"), self.section_check_label),
            ("Av/s (cortante):", self.av_s_label),
            ("At/s (torsión, 1 rama):", self.at_s_label),
            ("(Av+2At)/s requerido:", self.avt_s_label),
            (("(Av+2At)/s mínimo (§9.6.4.2):", "Av/s mínimo (§5.7.2.5):"),
             self.avt_s_min_label),
            ("s por resistencia V+T:", self.s_comb_label),
            (("s máx. torsión (§9.7.6.3.3):", "s máx. torsión:"),
             self.s_tor_max_label),
        ]
        for row, (text, widget) in enumerate(rows):
            comb_layout.addWidget(self._caption(text), row, 0)
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
            (("Al requerido (§22.7.6.1b):", "Al adicional (§5.7.3.6.3):"),
             self.al_req_label),
            (("Al mínimo (§9.6.4.3):", "Al mínimo (AASHTO no define):"),
             self.al_min_label),
            ("Al ADOPTADO:", self.al_adopted_label),
            ("Distribución sugerida:", self.al_bars_label),
        ]
        for row, (text, widget) in enumerate(rows):
            al_layout.addWidget(self._caption(text), row, 0)
            al_layout.addWidget(widget, row, 1)

        al_note = self._caption((
            "Al se reparte en el perímetro (≥1 barra por esquina, s ≤ 300 mm) y "
            "se suma al acero de flexión en la zona de tensión.",
            "AASHTO no calcula un Al aparte: exige que el acero longitudinal "
            "cubra momento, cortante y torsión a la vez (§5.7.3.6.3). El valor "
            "de arriba es lo que falta respecto del acero de flexión.",
        ))
        al_note.setObjectName("infoLabel")
        al_note.setWordWrap(True)
        al_layout.addWidget(al_note, len(rows), 0, 1, 2)
        al_group.setLayout(al_layout)
        self.torsion_long_group = al_group

        for group in (self.torsion_demand_group, self.torsion_combined_group,
                      self.torsion_long_group):
            group.setVisible(False)

        return (self.torsion_demand_group,
                self.torsion_combined_group, self.torsion_long_group)

    def _caption(self, text) -> QLabel:
        """Rótulo fijo, o que cambia con la norma si se dan dos textos.

        Con una tupla ``(texto ACI, texto AASHTO)`` el rótulo queda registrado
        y :meth:`_display_aashto` lo reescribe cada vez que cambia la norma.
        Así las referencias a artículos no se contradicen con los números que
        acompañan.
        """
        if isinstance(text, tuple):
            aci, aashto = text
            label = QLabel(aci)
            self._code_captions.append((label, aci, aashto))
            return label
        return QLabel(text)

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

        # Bloque propio de AASHTO
        self._display_aashto(result, cv)

        # Torsión (sólo viga)
        if not self.is_slab:
            self._display_torsion(result, cv)

        # Estado
        self._update_status_banner(result.status, result)

        # Advertencias
        if result.warnings:
            warn_text = "\n".join(result.warnings)
            self.warnings_label.setText(warn_text)
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

    def _display_aashto(self, result: ShearResultT, cv):
        """Llena (o esconde) los valores que sólo existen bajo AASHTO."""
        aplica = code_of(result) is DesignCode.AASHTO_LRFD_2020
        self.aashto_group.setVisible(aplica)

        for label, texto_aci, texto_aashto in self._code_captions:
            label.setText(texto_aashto if aplica else texto_aci)

        if not aplica:
            return

        self.dv_label.setText(
            f"{cv.format_length_small(result.dv_mm, 2)}  "
            f"({result.dv_governing})"
        )
        self.beta_theta_label.setText(
            f"{result.beta:.1f} / {result.theta_deg:.0f}°"
        )
        self.vn_max_label.setText(
            _force_in_user_unit(result.phi_vn_max_kn, cv)
        )

        if not getattr(result, "long_check_applies", False):
            self.long_check_label.setText("— (sin datos)")
            self.long_check_label.setStyleSheet("")
            return
        ok = result.long_reinf_ok
        self.long_check_label.setText(
            f"{_force_in_user_unit(result.long_capacity_n / 1000.0, cv)} de "
            f"{_force_in_user_unit(result.long_demand_n / 1000.0, cv)}"
            f"  {'✓' if ok else '✗'}"
        )
        self.long_check_label.setStyleSheet(
            f"color: {PALETTE.ok if ok else PALETTE.error}; font-weight: bold;"
        )

    def _display_torsion(self, result: ShearResultT, cv):
        """Llena (o esconde) los grupos de torsión."""
        active = (
            isinstance(result, BeamShearTorsionResult)
            and result.torsion_active
            and result.tu_knm > 0
        )
        negligible = active and result.torsion_regime == "DESPRECIABLE"

        self.torsion_details.setVisible(active)
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
        self.torsion_ratio_label.setText(
            "∞" if result.torsion_ratio == float("inf")
            else f"{result.torsion_ratio:.2f}"
        )
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
        # AASHTO no define una separación máxima propia de torsión ni un A_l
        # mínimo separado; un 0.00 se leería como un límite que no existe.
        # Bajo ACI, en cambio, un A_l,min nulo es un resultado legítimo.
        es_aashto = code_of(result) is DesignCode.AASHTO_LRFD_2020
        self.s_tor_max_label.setText(
            "no aplica" if es_aashto
            else cv.format_length_small(result.s_torsion_max_mm, 1)
        )

        # Acero longitudinal
        self.al_req_label.setText(cv.format_area(result.al_required_mm2 / 100.0))
        self.al_min_label.setText(
            "no aplica" if es_aashto
            else cv.format_area(result.al_min_mm2 / 100.0)
        )
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
            "OK": (PALETTE.ok, "Diseño correcto"),
            "NO REQUIERE ESTRIBOS": (PALETTE.ok, "No requiere estribos"),
            "ARMADO INSUFICIENTE": (PALETTE.error, "Armado insuficiente"),
            "AUMENTAR SECCIÓN": (PALETTE.error, "Aumentar sección"),
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
            self.torsion_details.setVisible(False)
        for lbl in labels:
            lbl.setText("—")
        self.status_label.setText("Estado: —")
        self.status_label.setStyleSheet("")
        self.warnings_label.setVisible(False)
