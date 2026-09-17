"""Motor de diseño por torsión y combinación cortante + torsión (ACI 318-19).

Referencias principales:
  §22.7.4.1   Torsión umbral T_th  (por debajo se puede despreciar la torsión)
  §22.7.5.1   Torsión de agrietamiento T_cr (redistribución por compatibilidad)
  §22.7.7.1   Límite de dimensiones de la sección (interacción V–T)
  §22.7.6.1   Refuerzo transversal (A_t/s) y longitudinal (A_l) por torsión
  §9.6.4.2    Refuerzo transversal mínimo combinado (A_v + 2A_t)
  §9.6.4.3    Refuerzo longitudinal mínimo A_l,min
  §9.7.5.1    Distribución del refuerzo longitudinal por torsión
  §9.7.6.3.3  Separación máxima de estribos por torsión: min(p_h/8, 300 mm)
  §20.2.2.4   f_y y f_yt ≤ 420 MPa para refuerzo por torsión

Todos los inputs internos están en SI: N, mm, MPa (torsores en N·mm).
"""
import math
from dataclasses import dataclass, field, fields
from typing import List, Optional

from core.bar_tables import REBAR_SIZES
from core.shear import (
    PHI_SHEAR,
    S_PRACTICAL_ROUND_MM,
    BeamShearDesign,
    BeamShearResult,
)

PHI_TORSION = PHI_SHEAR          # ACI 318-19 §21.2.1 → φ = 0.75
THETA_DEG = 45.0                 # ACI 22.7.6.1.2: θ = 45° para no preesforzado
FY_TORSION_MAX_MPA = 420.0       # ACI 20.2.2.4
S_MAX_TORSION_MM = 300.0         # ACI 9.7.6.3.3
S_LONG_MAX_MM = 300.0            # ACI 9.7.5.1 (separación de barras longitudinales)
DB_LONG_MIN_MM = 9.52            # ACI 9.7.5.1: no menor que una #3


def t_threshold_nmm(fc_mpa: float, lam: float, acp_mm2: float, pcp_mm: float) -> float:
    """Torsión umbral para sección sólida no preesforzada (ACI 22.7.4.1a).

        T_th = 0.083 · λ · √f'c · (A_cp² / p_cp)
    """
    if fc_mpa <= 0 or acp_mm2 <= 0 or pcp_mm <= 0:
        return 0.0
    return 0.083 * lam * math.sqrt(fc_mpa) * acp_mm2 ** 2 / pcp_mm


def t_cracking_nmm(fc_mpa: float, lam: float, acp_mm2: float, pcp_mm: float) -> float:
    """Torsión de agrietamiento (ACI 22.7.5.1).

        T_cr = 0.33 · λ · √f'c · (A_cp² / p_cp)
    """
    if fc_mpa <= 0 or acp_mm2 <= 0 or pcp_mm <= 0:
        return 0.0
    return 0.33 * lam * math.sqrt(fc_mpa) * acp_mm2 ** 2 / pcp_mm


def _round_down_to(value_mm: float, step_mm: float) -> float:
    if value_mm <= 0 or not math.isfinite(value_mm):
        return 0.0
    n = math.floor(value_mm / step_mm)
    return max(step_mm, n * step_mm)


@dataclass
class LongBarSuggestion:
    """Distribución sugerida del acero longitudinal por torsión."""
    n_bars: int
    bar_number: int
    bar_diameter_mm: float
    area_per_bar_mm2: float
    area_total_mm2: float
    spacing_mm: float           # separación perimetral entre barras

    @property
    def label(self) -> str:
        return f"{self.n_bars} × #{self.bar_number}"


def suggest_longitudinal_bars(
    al_mm2: float, ph_mm: float, s_stirrup_mm: float
) -> Optional[LongBarSuggestion]:
    """Reparte A_l en el perímetro cumpliendo ACI 9.7.5.1.

    Barras espaciadas ≤ 300 mm, al menos una en cada esquina, y
    d_b ≥ max(0.042·s, #3).
    """
    if al_mm2 <= 0 or ph_mm <= 0:
        return None

    # Al menos 4 (esquinas) y separación perimetral ≤ 300 mm; se mantiene par
    n_bars = max(4, math.ceil(ph_mm / S_LONG_MAX_MM))
    if n_bars % 2:
        n_bars += 1

    db_min = max(DB_LONG_MIN_MM, 0.042 * s_stirrup_mm)
    area_needed = al_mm2 / n_bars

    for rebar in REBAR_SIZES:
        if rebar.diameter_mm >= db_min and rebar.area_mm2 >= area_needed:
            return LongBarSuggestion(
                n_bars=n_bars,
                bar_number=rebar.number,
                bar_diameter_mm=rebar.diameter_mm,
                area_per_bar_mm2=rebar.area_mm2,
                area_total_mm2=n_bars * rebar.area_mm2,
                spacing_mm=ph_mm / n_bars,
            )

    # Si ni la barra mayor alcanza, se aumenta el número de barras
    biggest = REBAR_SIZES[-1]
    n_bars = max(n_bars, math.ceil(al_mm2 / biggest.area_mm2))
    if n_bars % 2:
        n_bars += 1
    return LongBarSuggestion(
        n_bars=n_bars,
        bar_number=biggest.number,
        bar_diameter_mm=biggest.diameter_mm,
        area_per_bar_mm2=biggest.area_mm2,
        area_total_mm2=n_bars * biggest.area_mm2,
        spacing_mm=ph_mm / n_bars,
    )


@dataclass
class BeamShearTorsionResult(BeamShearResult):
    """Resultado de viga por cortante, opcionalmente combinado con torsión.

    Hereda todos los campos de :class:`BeamShearResult`; cuando
    ``torsion_active`` es ``True`` y el régimen es de diseño, los campos de
    separación heredados (``s_max_mm``, ``s_adopted_mm``, ``vs_provided_kn``,
    ``phi_vn_kn``) ya reflejan la combinación V + T.
    """
    torsion_active: bool = False

    # --- Solicitación y tipo ---
    tu_knm: float = 0.0                 # torsor último ingresado
    tu_design_knm: float = 0.0          # torsor de diseño (tras redistribución)
    torsion_type: str = "EQUILIBRIO"    # "EQUILIBRIO" | "COMPATIBILIDAD"
    redistributed: bool = False

    # --- Propiedades de la sección para torsión ---
    acp_mm2: float = 0.0                # área encerrada por el perímetro exterior
    pcp_mm: float = 0.0                 # perímetro exterior
    aoh_mm2: float = 0.0                # área encerrada por el eje del estribo
    ph_mm: float = 0.0                  # perímetro del eje del estribo
    ao_mm2: float = 0.0                 # 0.85·A_oh
    theta_deg: float = THETA_DEG
    fy_long_mpa: float = 0.0

    # --- Umbrales ---
    t_th_knm: float = 0.0
    phi_t_th_knm: float = 0.0
    t_cr_knm: float = 0.0
    phi_t_cr_knm: float = 0.0
    torsion_regime: str = "DESPRECIABLE"   # "DESPRECIABLE" | "DISEÑO"

    # --- Verificación de la sección (§22.7.7.1) ---
    stress_demand_mpa: float = 0.0      # raíz de la suma de cuadrados
    stress_limit_mpa: float = 0.0       # φ(Vc/(bw·d) + 0.66√f'c)
    section_ratio: float = 0.0          # límite / demanda
    section_ok: bool = True

    # --- Refuerzo transversal ---
    av_s_required: float = 0.0          # (A_v/s) por cortante  [mm²/mm]
    at_s_required: float = 0.0          # (A_t/s) por torsión, una rama [mm²/mm]
    avt_s_required: float = 0.0         # (A_v + 2A_t)/s requerido [mm²/mm]
    avt_s_min: float = 0.0              # mínimo §9.6.4.2 [mm²/mm]
    avt_s_provided: float = 0.0         # (n_ramas · A_b)/s adoptado [mm²/mm]
    s_torsion_max_mm: float = 0.0       # min(p_h/8, 300 mm)
    s_shear_only_max_mm: float = 0.0    # s_max de §9.7.6.2.2 (sólo cortante)
    s_combined_required_mm: float = 0.0  # s por resistencia combinada V + T

    # --- Refuerzo longitudinal por torsión ---
    al_required_mm2: float = 0.0
    al_min_mm2: float = 0.0
    al_adopted_mm2: float = 0.0
    long_bars: Optional[LongBarSuggestion] = None

    # --- Capacidad provista ---
    tn_provided_knm: float = 0.0
    phi_tn_knm: float = 0.0
    torsion_ratio: float = 0.0          # φTn / Tu,diseño

    torsion_warnings: List[str] = field(default_factory=list)


class BeamShearTorsionDesign:
    """Diseño de viga rectangular por cortante y torsión combinados.

    Con ``torsion_enabled=False`` (o Tu = 0) se comporta exactamente igual que
    :class:`~core.shear.BeamShearDesign`, devolviendo el mismo diseño por
    cortante dentro de un :class:`BeamShearTorsionResult`.
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
        # --- torsión ---
        torsion_enabled: bool = False,
        tu_nmm: float = 0.0,
        fy_long_mpa: float = 420.0,
        torsion_type: str = "EQUILIBRIO",
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
        self.torsion_enabled = torsion_enabled
        self.tu_nmm = max(tu_nmm, 0.0)
        self.fy_long_mpa = fy_long_mpa
        self.torsion_type = torsion_type

    # ------------------------------------------------------------

    def _shear_design(self) -> BeamShearResult:
        return BeamShearDesign(
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
        ).design()

    def _section_properties(self):
        """(A_cp, p_cp, A_oh, p_h) para sección rectangular sólida."""
        acp = self.b_mm * self.h_mm
        pcp = 2.0 * (self.b_mm + self.h_mm)
        # Ejes del estribo cerrado más exterior
        x1 = self.b_mm - 2.0 * self.cover_mm - self.stirrup_diameter_mm
        y1 = self.h_mm - 2.0 * self.cover_mm - self.stirrup_diameter_mm
        aoh = max(x1, 0.0) * max(y1, 0.0)
        ph = 2.0 * (max(x1, 0.0) + max(y1, 0.0))
        return acp, pcp, aoh, ph

    def design(self) -> BeamShearTorsionResult:
        shear = self._shear_design()
        base = {f.name: getattr(shear, f.name) for f in fields(BeamShearResult)}
        base["warnings"] = list(shear.warnings)

        if not self.torsion_enabled or self.tu_nmm <= 0.0 or shear.status == "ERROR":
            return BeamShearTorsionResult(**base, torsion_active=self.torsion_enabled)

        warns: List[str] = []
        d = shear.d_mm
        b = self.b_mm
        fc = self.fc_mpa
        fyt = self.fyt_mpa
        fy_l = self.fy_long_mpa
        cot = 1.0 / math.tan(math.radians(THETA_DEG))

        acp, pcp, aoh, ph = self._section_properties()
        ao = 0.85 * aoh

        if aoh <= 0 or ph <= 0:
            base["status"] = "ERROR"
            base["warnings"].append(
                "El recubrimiento y el diámetro del estribo no dejan un núcleo "
                "confinado válido para torsión (A_oh ≤ 0)."
            )
            return BeamShearTorsionResult(**base, torsion_active=True)

        # --- Límites de fluencia para torsión (ACI 20.2.2.4) ---
        if fyt > FY_TORSION_MAX_MPA + 1e-6:
            warns.append(
                f"f_yt = {fyt:.0f} MPa excede el límite de 420 MPa para refuerzo "
                "transversal por torsión (ACI 20.2.2.4)."
            )
        if fy_l > FY_TORSION_MAX_MPA + 1e-6:
            warns.append(
                f"f_y = {fy_l:.0f} MPa excede el límite de 420 MPa para refuerzo "
                "longitudinal por torsión (ACI 20.2.2.4)."
            )

        # --- Umbrales de torsión ---
        t_th = t_threshold_nmm(fc, self.lam, acp, pcp)
        t_cr = t_cracking_nmm(fc, self.lam, acp, pcp)
        phi_t_th = PHI_TORSION * t_th
        phi_t_cr = PHI_TORSION * t_cr

        common = dict(
            torsion_active=True,
            tu_knm=self.tu_nmm / 1e6,
            torsion_type=self.torsion_type,
            acp_mm2=acp, pcp_mm=pcp, aoh_mm2=aoh, ph_mm=ph, ao_mm2=ao,
            theta_deg=THETA_DEG, fy_long_mpa=fy_l,
            t_th_knm=t_th / 1e6, phi_t_th_knm=phi_t_th / 1e6,
            t_cr_knm=t_cr / 1e6, phi_t_cr_knm=phi_t_cr / 1e6,
            s_shear_only_max_mm=shear.s_max_mm,
        )

        # --- ¿Se puede despreciar la torsión? (§22.7.4.1) ---
        if self.tu_nmm <= phi_t_th:
            base["warnings"].extend(warns)
            return BeamShearTorsionResult(
                **base, **common,
                tu_design_knm=self.tu_nmm / 1e6,
                torsion_regime="DESPRECIABLE",
                section_ok=True,
                torsion_warnings=warns,
            )

        # --- Redistribución por compatibilidad (§22.7.3.2) ---
        tu_des = self.tu_nmm
        redistributed = False
        if self.torsion_type == "COMPATIBILIDAD" and self.tu_nmm > phi_t_cr:
            tu_des = phi_t_cr
            redistributed = True
            warns.append(
                "Torsión por compatibilidad: T_u se redujo a φT_cr (ACI 22.7.3.2). "
                "Deben redistribuirse de forma consistente los momentos y cortantes "
                "de los elementos adyacentes."
            )

        # --- Límite de dimensiones de la sección (§22.7.7.1) ---
        vc_n = shear.vc_kn * 1000.0
        v_stress = self.vu_n / (b * d)
        t_stress = tu_des * ph / (1.7 * aoh ** 2)
        stress_demand = math.sqrt(v_stress ** 2 + t_stress ** 2)
        stress_limit = PHI_SHEAR * (vc_n / (b * d) + 0.66 * math.sqrt(fc))
        section_ok = stress_demand <= stress_limit + 1e-9
        if not section_ok:
            warns.append(
                "La sección no cumple el límite de dimensiones por interacción "
                "V–T (ACI 22.7.7.1). Aumentar b, h o f'c."
            )

        # --- Refuerzo transversal por torsión (§22.7.6.1a) ---
        tn_req = tu_des / PHI_TORSION
        at_s = tn_req / (2.0 * ao * fyt * cot)          # una rama [mm²/mm]

        # --- Refuerzo transversal por cortante (del diseño a cortante) ---
        av_s = (
            (shear.vs_required_kn * 1000.0) / (fyt * d)
            if shear.vs_required_kn > 0 else 0.0
        )

        # --- Combinado (A_v + 2A_t)/s y mínimo §9.6.4.2 ---
        avt_s_req = av_s + 2.0 * at_s
        avt_s_min = max(0.062 * math.sqrt(fc) / fyt, 0.35 / fyt) * b

        # --- Separaciones ---
        ab = self.stirrup_area_mm2
        n = self.stirrup_legs
        # Sólo las 2 ramas exteriores del estribo cerrado toman torsión, mientras
        # que todas las ramas toman cortante → área por rama exterior:
        #     A_b/s ≥ A_t/s + (A_v/s)/n
        per_leg_demand = at_s + av_s / n
        s_comb = ab / per_leg_demand if per_leg_demand > 0 else float("inf")
        # Con el estribo cerrado: A_v = n·A_b y A_t = A_b (una rama), así que
        # el mínimo de §9.6.4.2 se cubre con (A_v + 2A_t)/s = (n + 2)·A_b/s.
        s_min_req = ((n + 2) * ab) / avt_s_min if avt_s_min > 0 else float("inf")
        s_tor_max = min(ph / 8.0, S_MAX_TORSION_MM)
        s_max = min(shear.s_max_mm, s_tor_max)

        s_adopted = _round_down_to(min(s_comb, s_min_req, s_max), S_PRACTICAL_ROUND_MM)
        if s_adopted <= 0:
            s_adopted = S_PRACTICAL_ROUND_MM

        # --- Capacidades provistas con el s adoptado ---
        vs_prov = n * ab * fyt * d / s_adopted
        phi_vn = PHI_SHEAR * (vc_n + vs_prov)
        tn_prov = 2.0 * ao * ab * fyt * cot / s_adopted      # A_t = una rama
        phi_tn = PHI_TORSION * tn_prov
        avt_s_prov = (n + 2) * ab / s_adopted                # (A_v + 2A_t)/s

        # --- Refuerzo longitudinal por torsión (§22.7.6.1b) ---
        al_req = at_s * ph * (fyt / fy_l) * cot ** 2
        # ACI 9.6.4.3: A_t/s no se toma menor que 0.175·b_w/f_yt
        at_s_floor = 0.175 * b / fyt
        al_min = (
            0.42 * math.sqrt(fc) * acp / fy_l
            - max(at_s, at_s_floor) * ph * (fyt / fy_l)
        )
        al_min = max(al_min, 0.0)
        al_adopted = max(al_req, al_min)
        long_bars = suggest_longitudinal_bars(al_adopted, ph, s_adopted)

        if long_bars is not None and long_bars.spacing_mm > S_LONG_MAX_MM + 1e-6:
            warns.append(
                "La separación perimetral del refuerzo longitudinal por torsión "
                f"({long_bars.spacing_mm:.0f} mm) excede 300 mm (ACI 9.7.5.1)."
            )

        warns.append(
            "El refuerzo por torsión exige estribos CERRADOS (ganchos de 135°) y "
            "el A_l debe sumarse al acero de flexión en la zona de tensión."
        )

        # --- Estado global ---
        # Aunque el cortante no exija estribos, la torsión sí los requiere.
        if base["regime"] == "NO REQUIERE":
            base["regime"] = "TORSION"
        status = "OK" if shear.status == "NO REQUIERE ESTRIBOS" else shear.status
        if not section_ok:
            status = "AUMENTAR SECCIÓN"
        base["status"] = status
        base["s_max_mm"] = s_max
        base["s_adopted_mm"] = s_adopted
        base["vs_provided_kn"] = vs_prov / 1000.0
        base["phi_vn_kn"] = phi_vn / 1000.0
        base["warnings"].extend(warns)

        torsion_ratio = (phi_tn / tu_des) if tu_des > 0 else float("inf")

        return BeamShearTorsionResult(
            **base, **common,
            tu_design_knm=tu_des / 1e6,
            redistributed=redistributed,
            torsion_regime="DISEÑO",
            stress_demand_mpa=stress_demand,
            stress_limit_mpa=stress_limit,
            section_ratio=(
                (stress_limit / stress_demand) if stress_demand > 0 else float("inf")
            ),  # inf = sin solicitación; el consumidor decide cómo mostrarlo
            section_ok=section_ok,
            av_s_required=av_s,
            at_s_required=at_s,
            avt_s_required=avt_s_req,
            avt_s_min=avt_s_min,
            avt_s_provided=avt_s_prov,
            s_torsion_max_mm=s_tor_max,
            s_combined_required_mm=s_comb if math.isfinite(s_comb) else 0.0,
            al_required_mm2=al_req,
            al_min_mm2=al_min,
            al_adopted_mm2=al_adopted,
            long_bars=long_bars,
            tn_provided_knm=tn_prov / 1e6,
            phi_tn_knm=phi_tn / 1e6,
            torsion_ratio=torsion_ratio,
            torsion_warnings=warns,
        )
