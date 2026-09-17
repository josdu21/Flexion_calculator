"""Motor de diseño por flexión según ACI 318-19.

Todos los inputs internos están en SI: N, mm, MPa.

La geometría del armado (lechos, centroide, separaciones) vive en
:mod:`core.section_geometry` porque no depende de la norma; acá queda sólo lo
propio de ACI 318-19. ``RebarLayer`` y ``ReinforcementConfig`` se re-exportan
para no romper a quien las importe desde este módulo.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional

from core.section_geometry import (  # noqa: F401  (re-exportadas a propósito)
    MIN_BAR_SPACING_MM,
    RebarLayer,
    ReinforcementConfig,
    default_reinforcement,
    effective_depth,
    horizontal_clear_spacing,
    min_vertical_clear_spacing_mm,
)


@dataclass
class FlexionDesignResult:
    # Geometría
    b_mm: float
    h_mm: float
    cover_mm: float
    d_mm: float                  # peralte efectivo

    # Materiales
    fc_mpa: float
    fy_mpa: float
    beta_1: float

    # Cálculo de demanda
    rn: float
    rho_required: float
    as_required_cm2: float
    as_min_cm2: float
    as_max_cm2: float

    # Refuerzo elegido por el usuario
    as_provided_cm2: float
    rho_provided: float

    # Bloque de Whitney (basado en As proporcionado)
    a_mm: float
    c_mm: float
    jd_mm: float

    # Fuerzas internas (kN)
    compression_kn: float
    tension_kn: float

    # Verificaciones de separación
    horizontal_spacing_mm: float       # separación libre horizontal calculada
    horizontal_spacing_min_mm: float   # mínima requerida
    horizontal_spacing_ok: bool
    vertical_spacing_mm: float         # separación libre vertical (entre lechos)
    vertical_spacing_min_mm: float
    vertical_spacing_ok: bool

    # Capacidad
    phi_mn_knm: float                  # momento resistente φMn
    mu_demand_knm: float               # momento demandado

    # Estado
    status: str                        # "OK", "ARMADO INSUFICIENTE", "AUMENTAR SECCIÓN", etc.
    warnings: List[str] = field(default_factory=list)

    # Configuración de refuerzo usada (para dibujo)
    reinforcement: Optional["ReinforcementConfig"] = None
    layer_y_positions_mm: List[float] = field(default_factory=list)  # desde fibra inferior


class BeamSection:
    """Sección rectangular de viga/losa diseñada a flexión."""

    def __init__(
        self,
        mu_nmm: float,
        b_mm: float,
        h_mm: float,
        cover_mm: float,
        fc_mpa: float,
        fy_mpa: float,
        reinforcement: Optional[ReinforcementConfig] = None,
        # Compatibilidad: si no hay reinforcement, asume db simple
        db_assumed_mm: float = 16.0,
    ):
        self.mu_nmm = mu_nmm
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.cover_mm = cover_mm
        self.fc_mpa = fc_mpa
        self.fy_mpa = fy_mpa
        self.phi = 0.9  # ACI 318-19 §21.2.2 (tracción controlada)

        if reinforcement is None:
            # Configuración por defecto: 1 lecho, 2 barras del db_assumed
            self.reinforcement = default_reinforcement(db_assumed_mm)
        else:
            self.reinforcement = reinforcement

    def _calculate_beta_1(self) -> float:
        """β₁ según ACI 318-19 §22.2.2.4.3"""
        if self.fc_mpa <= 28.0:
            return 0.85
        beta_1 = 0.85 - 0.05 * ((self.fc_mpa - 28.0) / 7.0)
        return max(beta_1, 0.65)

    def _calculate_d_effective(self) -> tuple:
        """d efectivo según la disposición real de lechos (ACI 318-19 §25.2.2)."""
        return effective_depth(self.reinforcement, self.h_mm, self.cover_mm)

    def _calculate_horizontal_spacing(self) -> tuple:
        """Separación libre horizontal real y la mínima exigida (§25.2.1)."""
        return horizontal_clear_spacing(
            self.reinforcement, self.b_mm, self.cover_mm
        )

    def _validate(self) -> Optional[str]:
        if self.b_mm <= 0 or self.h_mm <= 0:
            return "Dimensiones (b, h) deben ser positivas"
        if self.cover_mm <= 0 or self.cover_mm >= self.h_mm * 0.5:
            return "Recubrimiento inválido"
        if self.fc_mpa <= 0 or self.fy_mpa <= 0:
            return "Resistencias deben ser positivas"
        return None

    def design(self) -> FlexionDesignResult:
        warnings_list: List[str] = []
        validation_error = self._validate()

        # 1) Peralte efectivo basado en la configuración real
        d_mm, s_v_used, y_layers = self._calculate_d_effective()

        # 2) β₁
        beta_1 = self._calculate_beta_1()

        # 3) Demanda
        rn = (self.mu_nmm / (self.phi * self.b_mm * d_mm * d_mm)
              if self.b_mm > 0 else 0.0)
        m = self.fy_mpa / (0.85 * self.fc_mpa) if self.fc_mpa > 0 else 0.0
        discriminant = (1.0 - 2.0 * m * rn / self.fy_mpa
                        if self.fy_mpa > 0 and m > 0 else 0.0)

        if validation_error:
            status = "ERROR"
            rho_required = 0.0
            as_required_cm2 = 0.0
            warnings_list.append(validation_error)
        elif discriminant < 0:
            rho_required = 0.0
            as_required_cm2 = 0.0
            status = "AUMENTAR SECCIÓN"
            warnings_list.append("Sección insuficiente: Mu excede capacidad balanceada")
        else:
            rho_required = (1.0 / m) * (1.0 - math.sqrt(discriminant))
            as_required_cm2 = rho_required * self.b_mm * d_mm / 100.0
            status = "OK"

        # 4) As mínimo (ACI 318-19 §9.6.1.2)
        if self.fy_mpa > 0 and self.fc_mpa > 0:
            term1 = (0.25 * math.sqrt(self.fc_mpa) / self.fy_mpa) * self.b_mm * d_mm / 100.0
            term2 = (1.4 / self.fy_mpa) * self.b_mm * d_mm / 100.0
        else:
            term1 = term2 = 0.0
        as_min_cm2 = max(term1, term2)

        # 5) As máximo
        rho_max = ((0.85 * beta_1 * self.fc_mpa / self.fy_mpa) * (0.003 / (0.003 + 0.004))
                   if self.fy_mpa > 0 else 0.0)
        as_max_cm2 = rho_max * self.b_mm * d_mm / 100.0

        # 6) As proporcionado (lo que el usuario eligió)
        as_provided_cm2 = self.reinforcement.total_area_cm2
        as_provided_mm2 = as_provided_cm2 * 100.0
        rho_provided = (as_provided_mm2 / (self.b_mm * d_mm)
                        if d_mm > 0 and self.b_mm > 0 else 0.0)

        # 7) Verificaciones de armado
        as_demand_cm2 = max(as_required_cm2, as_min_cm2)
        if status == "OK" and as_provided_cm2 < as_demand_cm2:
            status = "ARMADO INSUFICIENTE"
            faltante = as_demand_cm2 - as_provided_cm2
            warnings_list.append(
                f"Acero proporcionado ({as_provided_cm2:.2f} cm²) < requerido "
                f"({as_demand_cm2:.2f} cm²). Faltan {faltante:.2f} cm²"
            )
        elif status == "OK" and rho_provided > rho_max:
            status = "REDUCIR SECCIÓN"
            warnings_list.append(
                f"Cuantía proporcionada (ρ = {rho_provided:.4f}) excede "
                f"ρ_max (ρ = {rho_max:.4f})"
            )

        # 8) Bloque de Whitney basado en As proporcionado
        a_mm = ((as_provided_mm2 * self.fy_mpa) / (0.85 * self.fc_mpa * self.b_mm)
                if self.b_mm > 0 and self.fc_mpa > 0 else 0.0)
        c_mm = a_mm / beta_1 if beta_1 > 0 else 0.0
        jd_mm = d_mm - a_mm / 2.0

        # Fuerzas
        compression_kn = (0.85 * self.fc_mpa * self.b_mm * a_mm) / 1000.0
        tension_kn = (as_provided_mm2 * self.fy_mpa) / 1000.0

        # Capacidad φMn = φ · As · fy · (d - a/2) → N·mm → kN·m
        phi_mn_knm = (self.phi * as_provided_mm2 * self.fy_mpa * jd_mm) / 1e6

        # 9) Verificaciones de separación
        s_h_actual, s_h_min = self._calculate_horizontal_spacing()
        s_h_ok = s_h_actual >= s_h_min
        if not s_h_ok and self.reinforcement.layers and \
           max(L.n_bars for L in self.reinforcement.layers) > 1:
            warnings_list.append(
                f"Separación horizontal insuficiente: "
                f"{s_h_actual:.1f} mm < {s_h_min:.1f} mm (ACI 318-19 §25.2.1)"
            )

        # Separación vertical (solo si hay > 1 lecho)
        n_layers = len(self.reinforcement.layers)
        s_v_min = min_vertical_clear_spacing_mm(self.reinforcement)
        s_v_ok = (n_layers <= 1) or (s_v_used >= s_v_min)
        if n_layers > 1 and not s_v_ok:
            warnings_list.append(
                f"Separación vertical entre lechos insuficiente: "
                f"{s_v_used:.1f} mm < {s_v_min:.1f} mm (ACI 318-19 §25.2.2)"
            )

        return FlexionDesignResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=d_mm,
            fc_mpa=self.fc_mpa,
            fy_mpa=self.fy_mpa,
            beta_1=beta_1,
            rn=rn,
            rho_required=rho_required,
            as_required_cm2=as_required_cm2,
            as_min_cm2=as_min_cm2,
            as_max_cm2=as_max_cm2,
            as_provided_cm2=as_provided_cm2,
            rho_provided=rho_provided,
            a_mm=a_mm,
            c_mm=c_mm,
            jd_mm=jd_mm,
            compression_kn=compression_kn,
            tension_kn=tension_kn,
            horizontal_spacing_mm=s_h_actual if s_h_actual != float('inf') else 0.0,
            horizontal_spacing_min_mm=s_h_min,
            horizontal_spacing_ok=s_h_ok,
            vertical_spacing_mm=s_v_used if n_layers > 1 else 0.0,
            vertical_spacing_min_mm=s_v_min,
            vertical_spacing_ok=s_v_ok,
            phi_mn_knm=phi_mn_knm,
            mu_demand_knm=self.mu_nmm / 1e6,
            status=status,
            warnings=warnings_list,
            reinforcement=self.reinforcement,
            layer_y_positions_mm=y_layers,
        )
