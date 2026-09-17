"""Diseño por cortante según AASHTO LRFD Bridge Design Specifications 2020.

Se implementa el **procedimiento simplificado** de §5.7.3.4.1: β = 2.0 y
θ = 45°. El procedimiento general de §5.7.3.4.2 (MCFT, con β y θ en función de
ε_s) no está implementado.

Referencias principales:
  §5.5.4.2    φ = 0.90 para cortante y torsión en concreto de peso normal
  §5.7.2.3    Cuándo se exige refuerzo transversal: V_u > 0.5·φ·(V_c + V_p)
  §5.7.2.5    Refuerzo transversal mínimo A_v ≥ 0.083·√f'c·b_v·s/f_y
  §5.7.2.6    Separación máxima del refuerzo transversal
  §5.7.2.8    Peralte efectivo de cortante d_v
  §5.7.3.3    V_n = min(V_c + V_s + V_p, 0.25·f'c·b_v·d_v + V_p)
  §5.7.3.4.1  Procedimiento simplificado: β = 2.0, θ = 45°
  §5.7.3.5    Refuerzo longitudinal mínimo por cortante

Diferencias de fondo con ACI 318-19:

* **φ = 0.90**, no 0.75. AASHTO calibra sus factores de carga y resistencia en
  conjunto, así que los φ no son comparables uno a uno con los de ACI.
* **Se usa d_v, no d.** El peralte efectivo de cortante tiene pisos (0.9·d_e y
  0.72·h) que en secciones poco armadas lo hacen mayor que el brazo interno,
  y en secciones muy armadas, menor que d.
* **El tope de la sección es V_n ≤ 0.25·f'c·b_v·d_v**, un límite sobre la
  resistencia total, mientras ACI acota sólo el aporte del acero.

Todos los inputs internos están en SI: N, mm, MPa.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.shear import BeamShearResult, SlabShearResult


PHI_SHEAR = 0.90               # §5.5.4.2 cortante y torsión, peso normal
BETA_SIMPLIFIED = 2.0          # §5.7.3.4.1
THETA_DEG = 45.0               # §5.7.3.4.1
S_PRACTICAL_ROUND_MM = 5.0     # redondeo práctico de la separación adoptada

# §5.7.3.4.1: el procedimiento simplificado exige que la sección lleve el
# refuerzo transversal mínimo O que su altura total sea menor que este valor.
H_MAX_SIN_ESTRIBOS_MM = 400.0

FYT_WARN_MPA = 520.0           # §5.4.3.3 (75 ksi) — por encima, verificar límite


def dv_effective(de_mm: float, a_mm: float, h_mm: float) -> Tuple[float, str]:
    """Peralte efectivo de cortante d_v (§5.7.2.8) y la rama que lo gobierna.

        d_v = max(d_e − a/2, 0.9·d_e, 0.72·h)

    donde ``d_e`` es la distancia de la fibra extrema en compresión al
    centroide de la fuerza de tracción y ``a`` la altura del bloque de
    compresión equivalente. Devuelve ``(d_v, etiqueta)``; la etiqueta dice cuál
    de los tres términos mandó, que es dato útil en la memoria.
    """
    candidatos = (
        ("d_e − a/2", de_mm - a_mm / 2.0),
        ("0.9·d_e", 0.9 * de_mm),
        ("0.72·h", 0.72 * h_mm),
    )
    etiqueta, valor = max(candidatos, key=lambda par: par[1])
    return max(valor, 1e-6), etiqueta


def vc_nominal(fc_mpa: float, lam: float, bv_mm: float, dv_mm: float,
               beta: float = BETA_SIMPLIFIED) -> float:
    """V_c = 0.083·β·λ·√f'c·b_v·d_v (§5.7.3.3-3), en Newtons."""
    if fc_mpa <= 0 or bv_mm <= 0 or dv_mm <= 0:
        return 0.0
    return 0.083 * beta * lam * math.sqrt(fc_mpa) * bv_mm * dv_mm


def vn_max(fc_mpa: float, bv_mm: float, dv_mm: float) -> float:
    """Tope de la resistencia nominal: 0.25·f'c·b_v·d_v (§5.7.3.3-2), en N."""
    if fc_mpa <= 0 or bv_mm <= 0 or dv_mm <= 0:
        return 0.0
    return 0.25 * fc_mpa * bv_mm * dv_mm


def av_s_min(fc_mpa: float, bv_mm: float, fy_mpa: float) -> float:
    """(A_v/s) mínimo = 0.083·√f'c·b_v/f_y (§5.7.2.5), en mm²/mm."""
    if fc_mpa <= 0 or bv_mm <= 0 or fy_mpa <= 0:
        return 0.0
    return 0.083 * math.sqrt(fc_mpa) * bv_mm / fy_mpa


def s_max_mm(vu_n: float, fc_mpa: float, bv_mm: float, dv_mm: float) -> float:
    """Separación máxima del refuerzo transversal (§5.7.2.6).

        v_u = V_u / (φ·b_v·d_v)
        v_u <  0.125·f'c  →  s ≤ min(0.8·d_v, 600 mm)
        v_u ≥  0.125·f'c  →  s ≤ min(0.4·d_v, 300 mm)
    """
    if bv_mm <= 0 or dv_mm <= 0:
        return 0.0
    vu_stress = vu_n / (PHI_SHEAR * bv_mm * dv_mm)
    if vu_stress < 0.125 * fc_mpa:
        return min(0.8 * dv_mm, 600.0)
    return min(0.4 * dv_mm, 300.0)


def _round_down_to(value_mm: float, step_mm: float) -> float:
    if value_mm <= 0 or not math.isfinite(value_mm):
        return 0.0
    return max(step_mm, math.floor(value_mm / step_mm) * step_mm)


# ============================================================
#                      VIGA — DISEÑO
# ============================================================

@dataclass
class AashtoBeamShearResult(BeamShearResult):
    """Resultado de cortante en viga según AASHTO.

    Hereda los campos de :class:`~core.shear.BeamShearResult` para que los
    paneles funcionen con ambas normas. Ojo con dos campos heredados:

    * ``d_mm`` guarda **d_v**, el peralte efectivo de cortante, porque es el
      que entra en todas las ecuaciones. El ``d`` de flexión queda en
      ``de_mm``.
    * ``vs_max_kn`` guarda el V_s que agota el tope ``0.25·f'c·b_v·d_v``, no
      un límite propio del acero como en ACI.
    """
    de_mm: float = 0.0             # peralte efectivo de flexión
    dv_mm: float = 0.0             # peralte efectivo de cortante (§5.7.2.8)
    dv_governing: str = ""         # cuál de las tres ramas mandó
    beta: float = BETA_SIMPLIFIED
    theta_deg: float = THETA_DEG
    vn_max_kn: float = 0.0         # 0.25·f'c·b_v·d_v
    phi_vn_max_kn: float = 0.0
    av_s_min_value: float = 0.0    # (A_v/s) mínimo [mm²/mm]
    av_s_provided: float = 0.0     # (A_v/s) adoptado [mm²/mm]

    # Revisión del refuerzo longitudinal (§5.7.3.5)
    long_check_applies: bool = False
    long_demand_n: float = 0.0     # demanda de tracción del lado del acero
    long_capacity_n: float = 0.0   # A_s·f_y provisto
    long_reinf_ok: bool = True

    aashto_warnings: List[str] = field(default_factory=list)


class AashtoBeamShearDesign:
    """Diseño por cortante en viga rectangular (AASHTO LRFD, simplificado)."""

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
        d_mm: float = 0.0,             # d de flexión; 0 = estimarlo
        a_mm: float = 0.0,             # bloque de compresión, para d_v
        # Datos opcionales para la revisión longitudinal §5.7.3.5
        mu_nmm: float = 0.0,
        as_long_mm2: float = 0.0,
        fy_long_mpa: float = 0.0,
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
        self.d_override_mm = d_mm
        self.a_mm = max(a_mm, 0.0)
        self.mu_nmm = max(mu_nmm, 0.0)
        self.as_long_mm2 = max(as_long_mm2, 0.0)
        self.fy_long_mpa = fy_long_mpa

    def _validate(self) -> Optional[str]:
        if self.b_mm <= 0 or self.h_mm <= 0:
            return "Dimensiones (b, h) deben ser positivas"
        if self.cover_mm <= 0 or self.cover_mm >= self.h_mm * 0.5:
            return "Recubrimiento inválido"
        if self.fc_mpa <= 0 or self.fyt_mpa <= 0:
            return "Resistencias deben ser positivas"
        if self.vu_n < 0:
            return "Vu no puede ser negativo"
        return None

    def _de_mm(self) -> float:
        """Peralte efectivo de flexión: el real si lo dieron, si no estimado."""
        if self.d_override_mm > 0:
            return self.d_override_mm
        d = (self.h_mm - self.cover_mm - self.stirrup_diameter_mm
             - self.db_long_assumed_mm / 2.0)
        return max(d, 1e-6)

    def _longitudinal_check(self, dv_mm: float, vs_provided_n: float,
                            warns: List[str]) -> dict:
        """Refuerzo longitudinal mínimo por cortante (§5.7.3.5).

            A_s·f_y ≥ |M_u|/(d_v·φ_f) + (|V_u|/φ_v − 0.5·V_s)·cot θ

        Sin preesfuerzo ni carga axial. Se omite si no se conocen M_u y el
        acero longitudinal; la memoria lo deja dicho.
        """
        vacio = dict(long_check_applies=False, long_demand_n=0.0,
                     long_capacity_n=0.0, long_reinf_ok=True)
        if self.mu_nmm <= 0 or self.as_long_mm2 <= 0 or self.fy_long_mpa <= 0:
            return vacio
        if dv_mm <= 0:
            return vacio

        cot = 1.0 / math.tan(math.radians(THETA_DEG))
        phi_f = 0.90   # φ de flexión, tracción controlada
        termino_cortante = max(self.vu_n / PHI_SHEAR - 0.5 * vs_provided_n, 0.0)
        demanda = self.mu_nmm / (dv_mm * phi_f) + termino_cortante * cot
        capacidad = self.as_long_mm2 * self.fy_long_mpa

        ok = capacidad >= demanda - 1e-6
        if not ok:
            warns.append(
                "Refuerzo longitudinal insuficiente para la interacción con el "
                f"cortante (§5.7.3.5): se necesitan {demanda / 1000.0:.0f} kN de "
                f"tracción y el acero de flexión aporta {capacidad / 1000.0:.0f} kN. "
                "Prolongar barras o agregar acero longitudinal."
            )
        return dict(long_check_applies=True, long_demand_n=demanda,
                    long_capacity_n=capacidad, long_reinf_ok=ok)

    def design(self) -> AashtoBeamShearResult:
        warnings_list: List[str] = []
        aashto_warnings: List[str] = []
        err = self._validate()

        de_mm = self._de_mm()
        dv_mm, dv_gob = dv_effective(de_mm, self.a_mm, self.h_mm)
        av = self.stirrup_legs * self.stirrup_area_mm2
        cot = 1.0 / math.tan(math.radians(THETA_DEG))

        vc_n = vc_nominal(self.fc_mpa, self.lam, self.b_mm, dv_mm)
        phi_vc_n = PHI_SHEAR * vc_n
        vn_lim_n = vn_max(self.fc_mpa, self.b_mm, dv_mm)
        phi_vn_lim_n = PHI_SHEAR * vn_lim_n
        # V_s que agota el tope de la sección; es el análogo del vs_max de ACI.
        vs_lim_n = max(vn_lim_n - vc_n, 0.0)

        avs_min = av_s_min(self.fc_mpa, self.b_mm, self.fyt_mpa)
        s_min_req_mm = av / avs_min if avs_min > 0 else float("inf")

        if not err and self.fyt_mpa > FYT_WARN_MPA:
            aashto_warnings.append(
                f"f_yt = {self.fyt_mpa:.0f} MPa supera 520 MPa (75 ksi). AASHTO "
                "limita la resistencia de fluencia de diseño del refuerzo "
                "transversal (§5.4.3.3); verificar el límite del grado usado."
            )

        regime = "DISEÑO"
        status = "OK"
        s_required_mm = float("inf")
        vs_required_n = 0.0

        if err:
            status = "ERROR"
            warnings_list.append(err)
            s_max_value = float("inf")
            s_adopted_mm = 0.0
            vs_provided_n = 0.0
        else:
            # §5.7.2.3: se exige refuerzo transversal por encima de 0.5·φ·V_c
            if self.vu_n <= 0.5 * phi_vc_n:
                regime = "NO REQUIERE"
                status = "NO REQUIERE ESTRIBOS"
            elif self.vu_n <= phi_vc_n:
                regime = "MINIMO"
            else:
                regime = "DISEÑO"
                vs_required_n = self.vu_n / PHI_SHEAR - vc_n
                # (A_v/s)_req = V_s / (f_yt·d_v·cot θ)
                avs_req = vs_required_n / (self.fyt_mpa * dv_mm * cot)
                s_required_mm = av / avs_req if avs_req > 0 else float("inf")

            # Tope de la sección (§5.7.3.3-2)
            if self.vu_n > phi_vn_lim_n:
                status = "AUMENTAR SECCIÓN"
                warnings_list.append(
                    f"V_u excede el tope φ·0.25·f'c·b_v·d_v = "
                    f"{phi_vn_lim_n / 1000.0:.0f} kN (§5.7.3.3). Aumentar la "
                    "sección o f'c; más estribos no ayudan."
                )

            s_max_value = s_max_mm(self.vu_n, self.fc_mpa, self.b_mm, dv_mm)

            if regime == "NO REQUIERE":
                s_adopted_mm = 0.0
                vs_provided_n = 0.0
            else:
                s_candidate = min(s_required_mm, s_min_req_mm, s_max_value)
                s_adopted_mm = _round_down_to(s_candidate, S_PRACTICAL_ROUND_MM)
                if s_adopted_mm <= 0:
                    s_adopted_mm = S_PRACTICAL_ROUND_MM
                vs_provided_n = av * self.fyt_mpa * dv_mm * cot / s_adopted_mm

        vn_provided_n = min(vc_n + vs_provided_n, vn_lim_n) if not err else 0.0
        phi_vn_n = PHI_SHEAR * vn_provided_n

        if status == "OK" and regime != "NO REQUIERE" and \
           s_adopted_mm > s_max_value + 1e-6:
            warnings_list.append(
                f"Separación adoptada ({s_adopted_mm:.1f} mm) excede s_max "
                f"({s_max_value:.1f} mm) — §5.7.2.6."
            )

        longitudinal = (
            self._longitudinal_check(dv_mm, vs_provided_n, aashto_warnings)
            if not err else
            dict(long_check_applies=False, long_demand_n=0.0,
                 long_capacity_n=0.0, long_reinf_ok=True)
        )
        # Un refuerzo longitudinal insuficiente es una deficiencia del diseño,
        # no un detalle: el estado no puede seguir diciendo OK.
        if status == "OK" and not longitudinal["long_reinf_ok"]:
            status = "ARMADO INSUFICIENTE"

        return AashtoBeamShearResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=dv_mm,                 # el d que gobierna el cortante
            fc_mpa=self.fc_mpa,
            fyt_mpa=self.fyt_mpa,
            lam=self.lam,
            stirrup_diameter_mm=self.stirrup_diameter_mm,
            stirrup_legs=self.stirrup_legs,
            av_mm2=av,
            vu_kn=self.vu_n / 1000.0,
            vc_kn=vc_n / 1000.0,
            phi_vc_kn=phi_vc_n / 1000.0,
            vs_required_kn=vs_required_n / 1000.0,
            vs_max_kn=vs_lim_n / 1000.0,
            s_required_mm=s_required_mm if math.isfinite(s_required_mm) else 0.0,
            s_min_required_mm=s_min_req_mm if math.isfinite(s_min_req_mm) else 0.0,
            s_max_mm=s_max_value if not err and math.isfinite(s_max_value) else 0.0,
            s_adopted_mm=s_adopted_mm if not err else 0.0,
            vs_provided_kn=(vs_provided_n if not err else 0.0) / 1000.0,
            phi_vn_kn=phi_vn_n / 1000.0,
            regime=regime,
            status=status,
            warnings=warnings_list + aashto_warnings,
            # --- propios de AASHTO ---
            de_mm=de_mm,
            dv_mm=dv_mm,
            dv_governing=dv_gob,
            beta=BETA_SIMPLIFIED,
            theta_deg=THETA_DEG,
            vn_max_kn=vn_lim_n / 1000.0,
            phi_vn_max_kn=phi_vn_lim_n / 1000.0,
            av_s_min_value=avs_min,
            av_s_provided=(av / s_adopted_mm if not err and s_adopted_mm > 0 else 0.0),
            aashto_warnings=aashto_warnings,
            **longitudinal,
        )


# ============================================================
#                LOSA — REVISIÓN (sin refuerzo)
# ============================================================

@dataclass
class AashtoSlabShearResult(SlabShearResult):
    """Revisión de cortante en losa según AASHTO.

    Como en la viga, ``d_mm`` guarda **d_v**; el ``d`` de flexión queda en
    ``de_mm``. Los campos heredados ``rho_w``, ``rho_w_assumed`` y ``lambda_s``
    vienen de la formulación de ACI y **no intervienen** acá: en el
    procedimiento simplificado β es fijo y no depende de la cuantía.
    """
    de_mm: float = 0.0
    dv_mm: float = 0.0
    dv_governing: str = ""
    beta: float = BETA_SIMPLIFIED
    theta_deg: float = THETA_DEG
    vn_max_kn: float = 0.0
    phi_vn_max_kn: float = 0.0
    simplified_applicable: bool = True   # §5.7.3.4.1
    aashto_warnings: List[str] = field(default_factory=list)


class AashtoSlabShearCheck:
    """Revisión de cortante en una dirección para losa sin refuerzo (AASHTO)."""

    def __init__(
        self,
        vu_n: float,
        b_mm: float,
        h_mm: float,
        cover_mm: float,
        fc_mpa: float,
        db_long_assumed_mm: float = 12.7,
        lam: float = 1.0,
        as_long_mm2: float = 0.0,
        a_mm: float = 0.0,
    ):
        self.vu_n = vu_n
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.cover_mm = cover_mm
        self.fc_mpa = fc_mpa
        self.db_long_assumed_mm = db_long_assumed_mm
        self.lam = lam
        self.as_long_mm2 = max(as_long_mm2, 0.0)
        self.a_mm = max(a_mm, 0.0)

    def _validate(self) -> Optional[str]:
        if self.b_mm <= 0 or self.h_mm <= 0:
            return "Dimensiones (b, h) deben ser positivas"
        if self.cover_mm <= 0 or self.cover_mm >= self.h_mm * 0.5:
            return "Recubrimiento inválido"
        if self.fc_mpa <= 0:
            return "Resistencia del concreto debe ser positiva"
        if self.vu_n < 0:
            return "Vu no puede ser negativo"
        return None

    def check(self) -> AashtoSlabShearResult:
        warnings_list: List[str] = []
        aashto_warnings: List[str] = []
        err = self._validate()

        de_mm = max(self.h_mm - self.cover_mm - self.db_long_assumed_mm / 2.0, 1e-6)
        dv_mm, dv_gob = dv_effective(de_mm, self.a_mm, self.h_mm)

        # §5.7.3.4.1: sin estribos, el simplificado sólo vale si h < 400 mm.
        aplicable = self.h_mm < H_MAX_SIN_ESTRIBOS_MM
        if not err and not aplicable:
            aashto_warnings.append(
                f"La losa tiene h = {self.h_mm:.0f} mm ≥ 400 mm y no lleva "
                "refuerzo transversal, así que queda fuera del alcance del "
                "procedimiento simplificado (§5.7.3.4.1). AASHTO exige el "
                "procedimiento general de §5.7.3.4.2, que esta aplicación no "
                "implementa: verificar este cortante por otro medio."
            )

        vc_n = vc_nominal(self.fc_mpa, self.lam, self.b_mm, dv_mm)
        phi_vc_n = PHI_SHEAR * vc_n
        vn_lim_n = vn_max(self.fc_mpa, self.b_mm, dv_mm)
        phi_vn_lim_n = PHI_SHEAR * vn_lim_n
        ratio = (phi_vc_n / self.vu_n) if self.vu_n > 0 else float("inf")

        if err:
            status = "ERROR"
            warnings_list.append(err)
        elif phi_vc_n >= self.vu_n:
            status = "OK"
        else:
            status = "AUMENTAR SECCIÓN"
            warnings_list.append(
                "La losa no resiste el cortante sólo con el concreto. Aumentar "
                "el espesor h o f'c, o disponer refuerzo transversal — que en "
                "losas delgadas no es practicable."
            )

        return AashtoSlabShearResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=dv_mm,
            fc_mpa=self.fc_mpa,
            lam=self.lam,
            as_long_mm2=self.as_long_mm2,
            rho_w=0.0,              # no interviene en el simplificado
            rho_w_assumed=False,
            lambda_s=1.0,           # el factor de tamaño es de ACI, no de AASHTO
            vu_kn=self.vu_n / 1000.0,
            vc_kn=vc_n / 1000.0,
            phi_vc_kn=phi_vc_n / 1000.0,
            ratio=ratio,
            status=status,
            warnings=warnings_list + aashto_warnings,
            # --- propios de AASHTO ---
            de_mm=de_mm,
            dv_mm=dv_mm,
            dv_governing=dv_gob,
            beta=BETA_SIMPLIFIED,
            theta_deg=THETA_DEG,
            vn_max_kn=vn_lim_n / 1000.0,
            phi_vn_max_kn=phi_vn_lim_n / 1000.0,
            simplified_applicable=aplicable,
            aashto_warnings=aashto_warnings,
        )
