"""Motor de diseño por cortante según ACI 318-19.

Cubre dos casos:
  1) Viga rectangular con estribos (modo diseño: dado Vu, calcular s).
  2) Losa en una dirección sin refuerzo por cortante (revisión: φVc ≥ Vu).

Todos los inputs internos están en SI: N, mm, MPa.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional


PHI_SHEAR = 0.75              # ACI 318-19 §21.2.1 (cortante)
S_PRACTICAL_ROUND_MM = 5.0    # redondeo práctico de la separación adoptada
RHO_W_MIN_SLAB = 0.0018       # ACI 318-19 §24.4.3.2 (retracción y temperatura)


def vc_one_way(fc_mpa: float, lam: float, b_mm: float, d_mm: float) -> float:
    """Resistencia al cortante del concreto en una dirección, en Newtons.

    ACI 318-19 Tabla 22.5.5.1, caso con Av ≥ Av,min (forma simplificada, sin Nu):
        Vc = 0.17 · λ · √f'c · bw · d   [N, MPa, mm]

    Sólo aplica cuando el elemento lleva al menos el refuerzo transversal
    mínimo. Para elementos sin estribos usar :func:`vc_no_stirrups`.
    """
    if fc_mpa <= 0 or b_mm <= 0 or d_mm <= 0:
        return 0.0
    return 0.17 * lam * math.sqrt(fc_mpa) * b_mm * d_mm


def size_effect_factor(d_mm: float) -> float:
    """Factor de tamaño λs (ACI 318-19 §22.5.5.1.3).

        λs = √(2 / (1 + d/250)) ≤ 1.0
    """
    if d_mm <= 0:
        return 1.0
    return min(math.sqrt(2.0 / (1.0 + d_mm / 250.0)), 1.0)


def vc_no_stirrups(
    fc_mpa: float, lam: float, b_mm: float, d_mm: float, rho_w: float
) -> float:
    """Vc de un elemento SIN refuerzo transversal mínimo, en Newtons.

    ACI 318-19 Tabla 22.5.5.1, caso Av < Av,min (sin Nu):
        Vc = 0.66 · λs · λ · (ρw)^(1/3) · √f'c · bw · d
    """
    if fc_mpa <= 0 or b_mm <= 0 or d_mm <= 0 or rho_w <= 0:
        return 0.0
    return (0.66 * size_effect_factor(d_mm) * lam * rho_w ** (1.0 / 3.0)
            * math.sqrt(fc_mpa) * b_mm * d_mm)


def vs_max(fc_mpa: float, b_mm: float, d_mm: float) -> float:
    """Límite superior del aporte del refuerzo Vs (ACI 22.5.1.2), en Newtons."""
    if fc_mpa <= 0:
        return 0.0
    return 0.66 * math.sqrt(fc_mpa) * b_mm * d_mm


# ============================================================
#                      VIGA — DISEÑO
# ============================================================

@dataclass
class BeamShearResult:
    # Geometría
    b_mm: float
    h_mm: float
    cover_mm: float
    d_mm: float

    # Materiales
    fc_mpa: float
    fyt_mpa: float
    lam: float

    # Estribo propuesto
    stirrup_diameter_mm: float
    stirrup_legs: int
    av_mm2: float                       # área total de ramas del estribo

    # Demanda
    vu_kn: float

    # Capacidades
    vc_kn: float                        # concreto
    phi_vc_kn: float                    # φVc
    vs_required_kn: float               # Vs requerido (0 si Vu ≤ φVc)
    vs_max_kn: float                    # límite ACI 22.5.1.2

    # Separaciones (mm)
    s_required_mm: float                # por resistencia
    s_min_required_mm: float            # por Av_min (ACI 9.6.3.4)
    s_max_mm: float                     # ACI 9.7.6.2.2
    s_adopted_mm: float                 # min(s_req, s_min_req, s_max) redondeado

    # Capacidad del estribo adoptado
    vs_provided_kn: float
    phi_vn_kn: float                    # φ(Vc + Vs_provided)

    # Estado / régimen
    regime: str                         # "NO REQUIERE" / "MINIMO" / "DISEÑO"
    status: str                         # "OK" / "AUMENTAR SECCIÓN" / "NO REQUIERE ESTRIBOS"
    warnings: List[str] = field(default_factory=list)


class BeamShearDesign:
    """Diseño por cortante en viga rectangular (estribos cerrados)."""

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
        db_long_assumed_mm: float = 19.05,   # #6 por defecto (típico viga)
        lam: float = 1.0,
        d_mm: float = 0.0,   # peralte efectivo real; 0 = estimarlo del db asumido
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

    def _d_effective_mm(self) -> float:
        """Peralte efectivo para cortante.

        Si se recibió el d real del diseño a flexión se usa ése, para que ambos
        análisis de la misma viga sean coherentes. Si no, se estima:
        d ≈ h - r - db_estribo - db_long/2
        """
        if self.d_override_mm > 0:
            return self.d_override_mm
        d = (self.h_mm - self.cover_mm
             - self.stirrup_diameter_mm
             - self.db_long_assumed_mm / 2.0)
        return max(d, 1e-6)

    def _round_down_to(self, value_mm: float, step_mm: float) -> float:
        if value_mm <= 0:
            return 0.0
        n = math.floor(value_mm / step_mm)
        return max(step_mm, n * step_mm)

    def design(self) -> BeamShearResult:
        warnings_list: List[str] = []
        err = self._validate()

        d_mm = self._d_effective_mm()
        av = self.stirrup_legs * self.stirrup_area_mm2

        vc_n = vc_one_way(self.fc_mpa, self.lam, self.b_mm, d_mm)
        phi_vc_n = PHI_SHEAR * vc_n
        vs_lim_n = vs_max(self.fc_mpa, self.b_mm, d_mm)

        # Av/s mínimo (ACI 9.6.3.4): max(0.062·√fc/fyt, 0.35/fyt) · bw
        avs_min = max(
            0.062 * math.sqrt(self.fc_mpa) / self.fyt_mpa,
            0.35 / self.fyt_mpa,
        ) * self.b_mm  # [mm²/mm]
        s_min_req_mm = av / avs_min if avs_min > 0 else float("inf")

        # Estado por defecto
        regime = "DISEÑO"
        status = "OK"
        s_required_mm = float("inf")
        vs_required_n = 0.0

        if err:
            status = "ERROR"
            warnings_list.append(err)
            s_max_mm = float("inf")
            s_adopted_mm = 0.0
            vs_provided_n = 0.0
        else:
            # Régimen según Vu
            if self.vu_n <= 0.5 * phi_vc_n:
                regime = "NO REQUIERE"
                status = "NO REQUIERE ESTRIBOS"
                vs_required_n = 0.0
                s_required_mm = float("inf")
            elif self.vu_n <= phi_vc_n:
                regime = "MINIMO"
                vs_required_n = 0.0
                s_required_mm = float("inf")
            else:
                regime = "DISEÑO"
                vs_required_n = (self.vu_n - phi_vc_n) / PHI_SHEAR
                if vs_required_n > vs_lim_n:
                    status = "AUMENTAR SECCIÓN"
                    warnings_list.append(
                        "Vs requerido excede 0.66·√f'c·b·d (ACI 22.5.1.2). "
                        "Aumentar la sección o f'c."
                    )
                # (Av/s)_req = Vs / (fyt·d)
                avs_req = vs_required_n / (self.fyt_mpa * d_mm)
                s_required_mm = av / avs_req if avs_req > 0 else float("inf")

            # s_max (ACI 9.7.6.2.2). Usamos Vs_req (en régimen DISEÑO) para clasificar.
            vs_for_smax = max(vs_required_n, 0.0)
            if vs_for_smax <= 0.33 * math.sqrt(self.fc_mpa) * self.b_mm * d_mm:
                s_max_mm = min(d_mm / 2.0, 600.0)
            else:
                s_max_mm = min(d_mm / 4.0, 300.0)

            # s adoptado (sólo si se requieren estribos)
            if regime == "NO REQUIERE":
                s_adopted_mm = 0.0
                vs_provided_n = 0.0
            else:
                s_candidate = min(s_required_mm, s_min_req_mm, s_max_mm)
                s_adopted_mm = self._round_down_to(s_candidate, S_PRACTICAL_ROUND_MM)
                if s_adopted_mm <= 0:
                    s_adopted_mm = S_PRACTICAL_ROUND_MM
                vs_provided_n = av * self.fyt_mpa * d_mm / s_adopted_mm

        phi_vn_n = PHI_SHEAR * (vc_n + (vs_provided_n if not err else 0.0))

        # Advertencia si el adoptado queda por encima de s_max
        if status == "OK" and regime != "NO REQUIERE" and s_adopted_mm > s_max_mm + 1e-6:
            warnings_list.append(
                f"Separación adoptada ({s_adopted_mm:.1f} mm) excede s_max "
                f"({s_max_mm:.1f} mm) — ACI 9.7.6.2.2."
            )

        return BeamShearResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=d_mm,
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
            s_max_mm=s_max_mm if not err else 0.0,
            s_adopted_mm=s_adopted_mm if not err else 0.0,
            vs_provided_kn=(vs_provided_n if not err else 0.0) / 1000.0,
            phi_vn_kn=phi_vn_n / 1000.0,
            regime=regime,
            status=status,
            warnings=warnings_list,
        )


# ============================================================
#                LOSA — REVISIÓN (sin refuerzo)
# ============================================================

@dataclass
class SlabShearResult:
    # Geometría
    b_mm: float                 # ancho considerado (1000 mm = franja unitaria)
    h_mm: float
    cover_mm: float
    d_mm: float

    # Materiales
    fc_mpa: float
    lam: float

    # Refuerzo longitudinal (entra en Vc por ACI 22.5.5.1)
    as_long_mm2: float          # acero de flexión en la franja
    rho_w: float                # cuantía usada en el cálculo
    rho_w_assumed: bool         # True si se usó el mínimo por falta de dato
    lambda_s: float             # factor de tamaño §22.5.5.1.3

    # Demanda y capacidad
    vu_kn: float
    vc_kn: float
    phi_vc_kn: float
    ratio: float                # φVc / Vu (inf si Vu = 0)

    # Estado
    status: str                 # "OK" o "AUMENTAR SECCIÓN"
    warnings: List[str] = field(default_factory=list)


class SlabShearCheck:
    """Revisión de cortante en una dirección para losa sin refuerzo (ACI 22.5)."""

    def __init__(
        self,
        vu_n: float,
        b_mm: float,                  # 1000 mm = franja unitaria
        h_mm: float,
        cover_mm: float,
        fc_mpa: float,
        db_long_assumed_mm: float = 12.7,   # #4 típico en losa
        lam: float = 1.0,
        as_long_mm2: float = 0.0,     # acero de flexión en la franja; 0 = desconocido
    ):
        self.vu_n = vu_n
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.cover_mm = cover_mm
        self.fc_mpa = fc_mpa
        self.db_long_assumed_mm = db_long_assumed_mm
        self.lam = lam
        self.as_long_mm2 = max(as_long_mm2, 0.0)

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

    def _d_effective_mm(self) -> float:
        # En losa sin estribos: d = h - r - db/2
        d = self.h_mm - self.cover_mm - self.db_long_assumed_mm / 2.0
        return max(d, 1e-6)

    def check(self) -> SlabShearResult:
        warnings_list: List[str] = []
        err = self._validate()

        d_mm = self._d_effective_mm()

        # La losa no lleva estribos, así que Vc se calcula con la cuantía
        # longitudinal y el factor de tamaño (ACI 318-19 Tabla 22.5.5.1,
        # caso Av < Av,min), no con la forma simplificada 0.17·λ·√f'c.
        rho_from_steel = (
            self.as_long_mm2 / (self.b_mm * d_mm)
            if self.b_mm > 0 and d_mm > 0 else 0.0
        )
        rho_assumed = rho_from_steel <= 0.0
        rho_w = RHO_W_MIN_SLAB if rho_assumed else rho_from_steel
        if rho_assumed:
            warnings_list.append(
                "No se conoce el acero longitudinal de la franja: se asumió "
                f"ρw = {RHO_W_MIN_SLAB:.4f} (mínimo por retracción y temperatura, "
                "ACI 24.4.3.2) para calcular Vc."
            )

        lam_s = size_effect_factor(d_mm)
        vc_n = vc_no_stirrups(self.fc_mpa, self.lam, self.b_mm, d_mm, rho_w)
        phi_vc_n = PHI_SHEAR * vc_n
        ratio = (phi_vc_n / self.vu_n) if self.vu_n > 0 else float("inf")

        if err:
            status = "ERROR"
            warnings_list.append(err)
        elif phi_vc_n >= self.vu_n:
            status = "OK"
        else:
            status = "AUMENTAR SECCIÓN"
            warnings_list.append(
                "La losa no resiste el cortante únicamente con el concreto. "
                "Aumentar el espesor h o f'c (ACI 8.6.1 no permite refuerzo "
                "transversal en losas delgadas)."
            )

        return SlabShearResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=d_mm,
            fc_mpa=self.fc_mpa,
            lam=self.lam,
            as_long_mm2=self.as_long_mm2,
            rho_w=rho_w,
            rho_w_assumed=rho_assumed,
            lambda_s=lam_s,
            vu_kn=self.vu_n / 1000.0,
            vc_kn=vc_n / 1000.0,
            phi_vc_kn=phi_vc_n / 1000.0,
            ratio=ratio,
            status=status,
            warnings=warnings_list,
        )
