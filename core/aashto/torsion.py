"""Torsión y combinación cortante + torsión según AASHTO LRFD 2020.

Referencias principales:
  §5.7.2.1    Torsión de agrietamiento T_cr y umbral T_u > 0.25·φ·T_cr
  §5.7.3.6.2  Resistencia a torsión T_n = 2·A_o·A_t·f_y·cot θ / s
              y cortante equivalente V_u,eq para secciones sólidas
  §5.7.3.6.3  Refuerzo longitudinal para cortante y torsión combinados
  §5.7.2.5    Refuerzo transversal mínimo
  §5.7.2.6    Separación máxima del refuerzo transversal

Diferencias de fondo con ACI 318-19:

* **El umbral es 0.25·φ·T_cr**, no φ·T_th con una T_th aparte. AASHTO usa una
  sola torsión de referencia, la de agrietamiento, y desprecia la torsión por
  debajo de un cuarto de ella.
* **El refuerzo longitudinal no tiene fórmula propia.** ACI calcula un A_l
  separado; AASHTO mete la torsión dentro de la misma revisión de refuerzo
  longitudinal del cortante (§5.7.3.6.3), combinando ambos efectos bajo una
  raíz cuadrada. Lo que se reporta como «A_l» es el acero longitudinal
  *adicional* al de flexión que hace falta para satisfacer esa revisión.
* **No hay separación máxima propia de torsión.** ACI agrega min(p_h/8, 300 mm);
  AASHTO usa la misma regla general de §5.7.2.6.
* **No se implementa redistribución por compatibilidad.** Es una disposición de
  ACI (§22.7.3.2) sin equivalente aplicado acá: AASHTO se diseña siempre para
  la torsión de equilibrio.

Todos los inputs internos están en SI: N, mm, MPa (torsores en N·mm).
"""
import math
from dataclasses import dataclass, field, fields
from typing import List, Optional

from core.section_geometry import SectionProfile, SectionShape
from core.torsion import (
    BeamShearTorsionResult,
    LongBarSuggestion,
    suggest_longitudinal_bars,
)
from core.aashto.shear import (
    PHI_SHEAR,
    S_PRACTICAL_ROUND_MM,
    THETA_DEG,
    AashtoBeamShearDesign,
    AashtoBeamShearResult,
    av_s_min,
    s_max_mm,
)

PHI_TORSION = PHI_SHEAR          # §5.5.4.2 → φ = 0.90
TORSION_THRESHOLD_FACTOR = 0.25  # §5.7.2.1


def t_cracking_nmm(fc_mpa: float, lam: float, acp_mm2: float, pc_mm: float) -> float:
    """Torsión de agrietamiento (§5.7.2.1-4), sección sólida no preesforzada.

        T_cr = 0.125 · λ · √f'c · (A_cp² / p_c)

    El factor K de la ecuación vale 1.0 sin preesfuerzo (f_pc = 0).
    """
    if fc_mpa <= 0 or acp_mm2 <= 0 or pc_mm <= 0:
        return 0.0
    return 0.125 * lam * math.sqrt(fc_mpa) * acp_mm2 ** 2 / pc_mm


def equivalent_shear_n(vu_n: float, tu_nmm: float, ph_mm: float,
                       ao_mm2: float) -> float:
    """Cortante equivalente para sección sólida (§5.7.3.6.2).

        V_u,eq = √( V_u² + (0.9 · p_h · T_u / (2 · A_o))² )
    """
    if ao_mm2 <= 0 or tu_nmm <= 0:
        return abs(vu_n)
    termino_torsion = 0.9 * ph_mm * tu_nmm / (2.0 * ao_mm2)
    return math.sqrt(vu_n ** 2 + termino_torsion ** 2)


def _round_down_to(value_mm: float, step_mm: float) -> float:
    if value_mm <= 0 or not math.isfinite(value_mm):
        return 0.0
    return max(step_mm, math.floor(value_mm / step_mm) * step_mm)


@dataclass
class AashtoBeamShearTorsionResult(BeamShearTorsionResult):
    """Cortante y torsión combinados según AASHTO.

    Hereda de :class:`~core.torsion.BeamShearTorsionResult` para que el panel
    de resultados sirva a las dos normas. Campos heredados que cambian de
    significado:

    * ``t_th_knm`` es ``0.25·T_cr``, de modo que ``phi_t_th_knm`` sigue siendo
      el umbral con el que se compara T_u, igual que en ACI.
    * ``al_required_mm2`` es el acero longitudinal **adicional al de flexión**
      que exige §5.7.3.6.3, no un A_l independiente; ``al_min_mm2`` es 0
      porque AASHTO no define un mínimo separado.
    * ``stress_demand_mpa`` y ``stress_limit_mpa`` comparan
      ``V_u,eq/(φ·b_v·d_v)`` contra ``0.25·f'c`` (§5.7.3.3-2), en vez de la
      raíz de la suma de cuadrados de ACI.
    """
    # --- propios de AASHTO (los de cortante se repiten para el panel) ---
    de_mm: float = 0.0
    dv_mm: float = 0.0
    dv_governing: str = ""
    beta: float = 2.0
    vn_max_kn: float = 0.0
    phi_vn_max_kn: float = 0.0
    av_s_min_value: float = 0.0
    av_s_provided: float = 0.0

    vu_equivalent_kn: float = 0.0     # V_u,eq de §5.7.3.6.2
    long_check_applies: bool = False
    long_demand_n: float = 0.0
    long_capacity_n: float = 0.0
    long_reinf_ok: bool = True

    aashto_warnings: List[str] = field(default_factory=list)


class AashtoBeamShearTorsionDesign:
    """Viga rectangular por cortante y torsión combinados (AASHTO LRFD).

    Con ``torsion_enabled=False`` o ``T_u = 0`` se comporta igual que
    :class:`~core.aashto.shear.AashtoBeamShearDesign`.
    """

    def __init__(
        self,
        vu_n: float,
        b_mm: float,
        h_mm: float,
        cover_mm: float,
        fc_mpa: float,
        fyt_mpa: float,
        stirrup_diameter_mm: float,
        stirrup_area_mm2: float,
        stirrup_legs: int = 2,
        db_long_assumed_mm: float = 19.05,
        lam: float = 1.0,
        d_mm: float = 0.0,
        a_mm: float = 0.0,
        mu_nmm: float = 0.0,
        as_long_mm2: float = 0.0,
        # --- torsión ---
        torsion_enabled: bool = False,
        tu_nmm: float = 0.0,
        fy_long_mpa: float = 420.0,
        torsion_type: str = "EQUILIBRIO",
        # --- forma de la sección ---
        section_shape: SectionShape = SectionShape.RECTANGULAR,
        bf_mm: float = 0.0,
        hf_mm: float = 0.0,
        negative_moment: bool = False,
    ):
        self.vu_n = vu_n
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.cover_mm = cover_mm
        self.fc_mpa = fc_mpa
        self.fyt_mpa = fyt_mpa
        self.stirrup_diameter_mm = stirrup_diameter_mm
        self.stirrup_area_mm2 = stirrup_area_mm2
        self.stirrup_legs = max(2, int(stirrup_legs))
        self.db_long_assumed_mm = db_long_assumed_mm
        self.lam = lam
        self.d_mm = d_mm
        self.a_mm = a_mm
        self.mu_nmm = max(mu_nmm, 0.0)
        self.as_long_mm2 = max(as_long_mm2, 0.0)
        self.torsion_enabled = torsion_enabled
        self.tu_nmm = max(tu_nmm, 0.0)
        self.fy_long_mpa = fy_long_mpa
        self.torsion_type = torsion_type
        self.section_shape = section_shape
        self.bf_mm = bf_mm
        self.hf_mm = hf_mm
        self.negative_moment = negative_moment
        self.section = SectionProfile.create(
            shape=section_shape, bw_mm=b_mm, h_mm=h_mm,
            bf_mm=bf_mm, hf_mm=hf_mm,
        )

    # ------------------------------------------------------------

    def _shear_design(self) -> AashtoBeamShearResult:
        return AashtoBeamShearDesign(
            vu_n=self.vu_n,
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            fc_mpa=self.fc_mpa,
            fyt_mpa=self.fyt_mpa,
            stirrup_diameter_mm=self.stirrup_diameter_mm,
            stirrup_area_mm2=self.stirrup_area_mm2,
            stirrup_legs=self.stirrup_legs,
            db_long_assumed_mm=self.db_long_assumed_mm,
            lam=self.lam,
            d_mm=self.d_mm,
            a_mm=self.a_mm,
            mu_nmm=self.mu_nmm,
            as_long_mm2=self.as_long_mm2,
            fy_long_mpa=self.fy_long_mpa,
            section_shape=self.section_shape,
            bf_mm=self.bf_mm,
            hf_mm=self.hf_mm,
            negative_moment=self.negative_moment,
        ).design()

    def _section_properties(self):
        """(A_cp, p_c, A_oh, p_h) de la sección sólida.

        Con ala se aplica el mismo criterio que ACI 318-19 §22.7.4.1: el
        voladizo computable se limita a la proyección del alma bajo el ala y a
        4·h_f. A_oh y p_h siguen siendo los del estribo cerrado del alma.
        """
        acp, pc = self.section.torsion_gross_properties()
        x1 = self.b_mm - 2.0 * self.cover_mm - self.stirrup_diameter_mm
        y1 = self.h_mm - 2.0 * self.cover_mm - self.stirrup_diameter_mm
        aoh = max(x1, 0.0) * max(y1, 0.0)
        ph = 2.0 * (max(x1, 0.0) + max(y1, 0.0))
        return acp, pc, aoh, ph

    def design(self) -> AashtoBeamShearTorsionResult:
        shear = self._shear_design()
        base = {f.name: getattr(shear, f.name)
                for f in fields(AashtoBeamShearResult)}
        base["warnings"] = list(shear.warnings)
        base["aashto_warnings"] = list(shear.aashto_warnings)

        if not self.torsion_enabled or self.tu_nmm <= 0.0 or shear.status == "ERROR":
            return AashtoBeamShearTorsionResult(
                **base, torsion_active=self.torsion_enabled
            )

        warns: List[str] = []
        dv = shear.dv_mm
        b = self.b_mm
        fc = self.fc_mpa
        fyt = self.fyt_mpa
        fy_l = self.fy_long_mpa
        cot = 1.0 / math.tan(math.radians(THETA_DEG))

        acp, pc, aoh, ph = self._section_properties()
        ao = 0.85 * aoh
        be = self.section.torsion_overhang_mm()
        if be > 0:
            lados = ("a cada lado" if self.section.flange_sides == 2
                     else "del lado del ala")
            warns.append(
                f"A_cp y p_c incluyen {be:.0f} mm de voladizo de ala {lados} "
                f"(criterio de ACI 318-19 §22.7.4.1: el menor entre el voladizo "
                f"real, la proyección del alma bajo el ala y 4·h_f). Vale si el "
                f"ala es monolítica con el alma."
            )

        if aoh <= 0 or ph <= 0:
            base["status"] = "ERROR"
            base["warnings"].append(
                "El recubrimiento y el diámetro del estribo no dejan un núcleo "
                "confinado válido para torsión (A_oh ≤ 0)."
            )
            return AashtoBeamShearTorsionResult(**base, torsion_active=True)

        if self.torsion_type == "COMPATIBILIDAD":
            warns.append(
                "AASHTO no contempla la reducción de T_u a φ·T_cr por "
                "compatibilidad que sí permite ACI 318-19 §22.7.3.2; se diseña "
                "para la torsión de equilibrio completa."
            )

        # --- Umbral de torsión (§5.7.2.1) ---
        t_cr = t_cracking_nmm(fc, self.lam, acp, pc)
        t_th = TORSION_THRESHOLD_FACTOR * t_cr
        phi_t_th = PHI_TORSION * t_th
        phi_t_cr = PHI_TORSION * t_cr

        common = dict(
            torsion_active=True,
            tu_knm=self.tu_nmm / 1e6,
            tu_design_knm=self.tu_nmm / 1e6,
            torsion_type=self.torsion_type,
            redistributed=False,
            acp_mm2=acp, pcp_mm=pc, aoh_mm2=aoh, ph_mm=ph, ao_mm2=ao,
            section_shape=self.section.shape, flange_overhang_mm=be,
            # theta_deg ya viene del resultado de cortante, en `base`.
            fy_long_mpa=fy_l,
            t_th_knm=t_th / 1e6, phi_t_th_knm=phi_t_th / 1e6,
            t_cr_knm=t_cr / 1e6, phi_t_cr_knm=phi_t_cr / 1e6,
            s_shear_only_max_mm=shear.s_max_mm,
            s_torsion_max_mm=0.0,   # AASHTO no agrega un s_max propio de torsión
        )

        # --- ¿Se puede despreciar la torsión? (§5.7.2.1) ---
        if self.tu_nmm <= phi_t_th:
            base["warnings"].extend(warns)
            base["aashto_warnings"].extend(warns)
            return AashtoBeamShearTorsionResult(
                **base, **common,
                torsion_regime="DESPRECIABLE",
                section_ok=True,
                torsion_warnings=warns,
            )

        # --- Cortante equivalente y tope de la sección (§5.7.3.6.2) ---
        vu_eq = equivalent_shear_n(self.vu_n, self.tu_nmm, ph, ao)
        stress_demand = vu_eq / (PHI_SHEAR * b * dv)
        stress_limit = 0.25 * fc
        section_ok = stress_demand <= stress_limit + 1e-9
        if not section_ok:
            warns.append(
                "La sección no cumple el tope de §5.7.3.3 con el cortante "
                f"equivalente V_u,eq = {vu_eq / 1000.0:.0f} kN de §5.7.3.6.2. "
                "Aumentar b, h o f'c."
            )

        # --- Refuerzo transversal por torsión (§5.7.3.6.2) ---
        tn_req = self.tu_nmm / PHI_TORSION
        at_s = tn_req / (2.0 * ao * fyt * cot)          # una rama [mm²/mm]

        av_s = (
            (shear.vs_required_kn * 1000.0) / (fyt * dv * cot)
            if shear.vs_required_kn > 0 else 0.0
        )

        avt_s_req = av_s + 2.0 * at_s
        avt_s_min_value = av_s_min(fc, b, fyt)

        # --- Separaciones ---
        ab = self.stirrup_area_mm2
        n = self.stirrup_legs
        # Sólo las 2 ramas exteriores toman torsión; todas toman cortante:
        #     A_b/s ≥ A_t/s + (A_v/s)/n
        per_leg_demand = at_s + av_s / n
        s_comb = ab / per_leg_demand if per_leg_demand > 0 else float("inf")
        s_min_req = ((n + 2) * ab) / avt_s_min_value if avt_s_min_value > 0 else float("inf")
        # El s_max se recalcula con el cortante equivalente (§5.7.2.6).
        s_max = s_max_mm(vu_eq, fc, b, dv)

        s_adopted = _round_down_to(
            min(s_comb, s_min_req, s_max), S_PRACTICAL_ROUND_MM
        )
        if s_adopted <= 0:
            s_adopted = S_PRACTICAL_ROUND_MM

        # --- Capacidades provistas con el s adoptado ---
        vc_n = shear.vc_kn * 1000.0
        vs_prov = n * ab * fyt * dv * cot / s_adopted
        vn_prov = min(vc_n + vs_prov, shear.vn_max_kn * 1000.0)
        phi_vn = PHI_SHEAR * vn_prov
        tn_prov = 2.0 * ao * ab * fyt * cot / s_adopted      # A_t = una rama
        phi_tn = PHI_TORSION * tn_prov
        avt_s_prov = (n + 2) * ab / s_adopted

        # --- Refuerzo longitudinal combinado (§5.7.3.6.3) ---
        # A_s·f_y ≥ |M_u|/(φ_f·d_v) + cot θ·√[(V_u/φ_v − 0.5·V_s)² +
        #                                      (0.45·p_h·T_u/(2·A_o·φ))²]
        phi_f = 0.90
        termino_v = max(self.vu_n / PHI_SHEAR - 0.5 * vs_prov, 0.0)
        termino_t = 0.45 * ph * self.tu_nmm / (2.0 * ao * PHI_TORSION)
        demanda_long = (
            (self.mu_nmm / (phi_f * dv) if self.mu_nmm > 0 else 0.0)
            + cot * math.sqrt(termino_v ** 2 + termino_t ** 2)
        )
        capacidad_long = self.as_long_mm2 * fy_l
        long_aplica = self.as_long_mm2 > 0 and fy_l > 0 and self.mu_nmm > 0
        long_ok = (not long_aplica) or capacidad_long >= demanda_long - 1e-6

        # A_l reportado: el acero longitudinal que falta respecto al de flexión.
        al_req = max(demanda_long - capacidad_long, 0.0) / fy_l if fy_l > 0 else 0.0
        long_bars = suggest_longitudinal_bars(al_req, ph, s_adopted) if al_req > 0 else None

        if long_aplica and not long_ok:
            warns.append(
                "El acero longitudinal de flexión no alcanza para la "
                f"combinación de momento, cortante y torsión (§5.7.3.6.3): "
                f"faltan {al_req / 100.0:.2f} cm² distribuidos en el perímetro."
            )
        elif not long_aplica:
            warns.append(
                "No se revisó el refuerzo longitudinal combinado de §5.7.3.6.3 "
                "porque no se conocen M_u y el acero de flexión de esta sección."
            )

        warns.append(
            "El refuerzo por torsión exige estribos CERRADOS (ganchos de 135°) y "
            "el acero longitudinal debe distribuirse en el perímetro de la "
            "sección, no sólo en la zona de tracción por flexión."
        )

        # --- Estado global ---
        if base["regime"] == "NO REQUIERE":
            base["regime"] = "TORSION"
        status = "OK" if shear.status == "NO REQUIERE ESTRIBOS" else shear.status
        # Con torsión manda la revisión longitudinal combinada de §5.7.3.6.3,
        # que sustituye a la de §5.7.3.5 hecha en el diseño a cortante.
        if status == "ARMADO INSUFICIENTE" and long_ok:
            status = "OK"
        elif long_aplica and not long_ok:
            status = "ARMADO INSUFICIENTE"
        if not section_ok:
            status = "AUMENTAR SECCIÓN"
        base["status"] = status
        base["s_max_mm"] = s_max
        base["s_adopted_mm"] = s_adopted
        base["vs_provided_kn"] = vs_prov / 1000.0
        base["phi_vn_kn"] = phi_vn / 1000.0
        base["av_s_provided"] = n * ab / s_adopted
        base["warnings"].extend(warns)
        base["aashto_warnings"].extend(warns)
        base["long_check_applies"] = long_aplica
        base["long_demand_n"] = demanda_long
        base["long_capacity_n"] = capacidad_long
        base["long_reinf_ok"] = long_ok
        # La revisión de §5.7.3.6.3 incluye el término de torsión y sustituye a
        # la de §5.7.3.5 que hizo el diseño a cortante: dejar las dos sería
        # reportar dos veces la misma deficiencia, con números distintos.
        for clave in ("warnings", "aashto_warnings"):
            base[clave] = [w for w in base[clave] if "§5.7.3.5" not in w]

        torsion_ratio = (phi_tn / self.tu_nmm) if self.tu_nmm > 0 else float("inf")

        return AashtoBeamShearTorsionResult(
            **base, **common,
            torsion_regime="DISEÑO",
            stress_demand_mpa=stress_demand,
            stress_limit_mpa=stress_limit,
            section_ratio=(
                (stress_limit / stress_demand) if stress_demand > 0 else float("inf")
            ),
            section_ok=section_ok,
            av_s_required=av_s,
            at_s_required=at_s,
            avt_s_required=avt_s_req,
            avt_s_min=avt_s_min_value,
            avt_s_provided=avt_s_prov,
            s_combined_required_mm=s_comb if math.isfinite(s_comb) else 0.0,
            al_required_mm2=al_req,
            al_min_mm2=0.0,     # AASHTO no define un A_l mínimo separado
            al_adopted_mm2=al_req,
            long_bars=long_bars,
            tn_provided_knm=tn_prov / 1e6,
            phi_tn_knm=phi_tn / 1e6,
            torsion_ratio=torsion_ratio,
            vu_equivalent_kn=vu_eq / 1000.0,
            torsion_warnings=warns,
        )
