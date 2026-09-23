"""Diseño por flexión según AASHTO LRFD Bridge Design Specifications 2020.

Referencias principales:
  §5.4.2.4   Módulo de elasticidad del concreto E_c
  §5.4.2.6   Módulo de rotura f_r
  §5.4.3.2   Módulo de elasticidad del acero E_s = 200 000 MPa
  §5.5.4.2   Factor de resistencia φ, variable con la deformación ε_t
  §5.6.2.1   Suposiciones: ε_cu = 0.003, límites de deformación
  §5.6.2.2   Factores del bloque rectangular equivalente α₁ y β₁
  §5.6.3.2   Resistencia a flexión de secciones rectangulares
  §5.6.3.3   Refuerzo mínimo: M_r ≥ min(1.33·M_u, M_cr)
  §5.6.7     Control de fisuración por distribución del refuerzo

Diferencias de fondo con ACI 318-19, que es la otra norma de la aplicación:

* **φ no es constante.** ACI usa 0.90; AASHTO lo hace variar entre 0.75 y 0.90
  según ε_t (§5.5.4.2). Una sección muy armada puede tener φ bastante menor
  que 0.90, y ése es el mecanismo con el que AASHTO controla el sobrearmado.
* **El refuerzo mínimo es un criterio de momento, no de área** (§5.6.3.3).
* **No hay ρ_max explícito.** Lo reemplaza la caída de φ.

Secciones con ala (T y L): igual que en ACI se modela el **ala comprimida**.
El ala entra por el bloque de compresión y, a diferencia de ACI, también por el
módulo de sección con el que se calcula M_cr en §5.6.3.3, que deja de ser
``b·h²/6``. El ancho efectivo del ala se rige por §4.6.2.6.1, que desde la 4.ª
edición lo iguala al ancho tributario y no lo ata al espesor del ala.

Todos los inputs internos están en SI: N, mm, MPa.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.flexion import FlexionDesignResult
from core.section_geometry import (
    ReinforcementConfig,
    SectionProfile,
    SectionShape,
    default_reinforcement,
    effective_depth,
    horizontal_clear_spacing,
    min_vertical_clear_spacing_mm,
    steel_for_flanged_moment,
)


ES_MPA = 200000.0          # §5.4.3.2
EPSILON_CU = 0.003         # §5.6.2.1 deformación última del concreto

# Tabla C5.6.2.1-1: límites de deformación por grado de acero.
# (f_y MPa, ε_cl compresión controlada, ε_tl tracción controlada)
STRAIN_LIMITS: Tuple[Tuple[float, float, float], ...] = (
    (420.0, 0.0020, 0.0050),   # Grado 60
    (520.0, 0.0026, 0.0056),   # Grado 75
    (550.0, 0.0028, 0.0058),   # Grado 80
    (690.0, 0.0035, 0.0080),   # Grado 100
)

PHI_COMPRESSION = 0.75     # §5.5.4.2 compresión controlada
PHI_TENSION = 0.90         # §5.5.4.2 tracción controlada

GAMMA_1 = 1.6              # §5.6.3.3 variabilidad del momento de fisuración
GAMMA_3_A615 = 0.67        # §5.6.3.3 barras ASTM A615 Grado 60
GAMMA_3_A706 = 0.75        # §5.6.3.3 barras ASTM A706 Grado 60
GAMMA_E_CLASS_1 = 1.00     # §5.6.7 exposición clase 1
GAMMA_E_CLASS_2 = 0.75     # §5.6.7 exposición clase 2

FC_MIN_MPA = 16.0          # §5.4.2.1 resistencia mínima de diseño
FC_MAX_MPA = 70.0          # §5.4.2.1 por encima requiere aprobación
FY_MAX_MPA = 690.0         # §5.4.3.1 Grado 100

CRACK_CONTROL_COEFF = 123000.0   # §5.6.7 ecuación 5.6.7-1, en mm·MPa


def gamma_3(bar_spec: str) -> float:
    """γ₃ según el tipo de barra (§5.6.3.3)."""
    return GAMMA_3_A706 if str(bar_spec).upper().strip() == "A706" else GAMMA_3_A615


def gamma_e(exposure_class: int) -> float:
    """γ_e según la clase de exposición (§5.6.7)."""
    return GAMMA_E_CLASS_2 if int(exposure_class) == 2 else GAMMA_E_CLASS_1


def strain_limits(fy_mpa: float) -> Tuple[float, float]:
    """(ε_cl, ε_tl) interpolados de la Tabla C5.6.2.1-1 según f_y.

    Fuera del rango tabulado se toma el extremo más cercano; ε_cl siempre es
    la deformación de fluencia f_y/E_s, que es lo que define la norma.
    """
    eps_cl = fy_mpa / ES_MPA if fy_mpa > 0 else STRAIN_LIMITS[0][1]

    if fy_mpa <= STRAIN_LIMITS[0][0]:
        return eps_cl, STRAIN_LIMITS[0][2]
    if fy_mpa >= STRAIN_LIMITS[-1][0]:
        return eps_cl, STRAIN_LIMITS[-1][2]

    for (fy_a, _, tl_a), (fy_b, _, tl_b) in zip(STRAIN_LIMITS, STRAIN_LIMITS[1:]):
        if fy_a <= fy_mpa <= fy_b:
            t = (fy_mpa - fy_a) / (fy_b - fy_a) if fy_b > fy_a else 0.0
            return eps_cl, tl_a + t * (tl_b - tl_a)
    return eps_cl, STRAIN_LIMITS[-1][2]


def phi_flexure(eps_t: float, fy_mpa: float) -> float:
    """φ para flexión en concreto reforzado (§5.5.4.2).

        φ = 0.75                                        si ε_t ≤ ε_cl
        φ = 0.75 + 0.15·(ε_t − ε_cl)/(ε_tl − ε_cl)      en la transición
        φ = 0.90                                        si ε_t ≥ ε_tl
    """
    eps_cl, eps_tl = strain_limits(fy_mpa)
    if eps_t <= eps_cl:
        return PHI_COMPRESSION
    if eps_t >= eps_tl:
        return PHI_TENSION
    interpolado = PHI_COMPRESSION + (PHI_TENSION - PHI_COMPRESSION) * (
        (eps_t - eps_cl) / (eps_tl - eps_cl)
    )
    return min(max(interpolado, PHI_COMPRESSION), PHI_TENSION)


def alpha_1(fc_mpa: float) -> float:
    """α₁ del bloque rectangular equivalente (§5.6.2.2).

    0.85 hasta 70 MPa; por encima baja 0.02 por cada 7 MPa, con piso 0.75.
    """
    if fc_mpa <= FC_MAX_MPA:
        return 0.85
    return max(0.85 - 0.02 * ((fc_mpa - FC_MAX_MPA) / 7.0), 0.75)


def beta_1(fc_mpa: float) -> float:
    """β₁ del bloque rectangular equivalente (§5.6.2.2).

    Idéntico a ACI 318-19 §22.2.2.4.3.
    """
    if fc_mpa <= 28.0:
        return 0.85
    return max(0.85 - 0.05 * ((fc_mpa - 28.0) / 7.0), 0.65)


def modulus_of_rupture(fc_mpa: float, lam: float = 1.0) -> float:
    """Módulo de rotura f_r = 0.62·λ·√f'c (§5.4.2.6), en MPa."""
    if fc_mpa <= 0:
        return 0.0
    return 0.62 * lam * math.sqrt(fc_mpa)


def concrete_modulus(fc_mpa: float) -> float:
    """E_c = 4800·√f'c para concreto de peso normal (§5.4.2.4), en MPa."""
    if fc_mpa <= 0:
        return 0.0
    return 4800.0 * math.sqrt(fc_mpa)


@dataclass
class AashtoFlexionResult(FlexionDesignResult):
    """Resultado de flexión AASHTO.

    Hereda todos los campos de :class:`~core.flexion.FlexionDesignResult` para
    que los paneles y el diagrama de esfuerzos funcionen igual con las dos
    normas. Dos campos heredados cambian de significado y se documentan acá:

    * ``as_min_cm2`` es el **área equivalente** al mínimo por momento de
      §5.6.3.3, es decir el A_s con el que M_r alcanza ``mu_min_knm``. AASHTO
      no define un área mínima; la define en términos de momento.
    * ``as_max_cm2`` es el A_s con el que la sección llega a ε_t = ε_cl
      (compresión controlada). AASHTO **no** fija un máximo: por encima de ese
      valor la norma sigue permitiendo la sección, pero con φ = 0.75.
    """
    # --- Factor de resistencia (§5.5.4.2) ---
    phi_flexion: float = PHI_TENSION
    epsilon_t: float = 0.0             # deformación en el acero extremo
    epsilon_cl: float = 0.0            # límite de compresión controlada
    epsilon_tl: float = 0.0            # límite de tracción controlada
    dt_mm: float = 0.0                 # peralte al lecho extremo en tracción
    alpha_1: float = 0.85
    section_behaviour: str = "TRACCIÓN CONTROLADA"

    # --- Refuerzo mínimo por momento (§5.6.3.3) ---
    fr_mpa: float = 0.0
    sc_mm3: float = 0.0                # módulo de sección de la sección bruta
    mcr_knm: float = 0.0
    mu_min_knm: float = 0.0            # min(1.33·M_u, M_cr)
    gamma_1: float = GAMMA_1
    gamma_3: float = GAMMA_3_A615
    bar_spec: str = "A615"
    min_reinf_ok: bool = True

    # --- Control de fisuración (§5.6.7) ---
    crack_control_applies: bool = False   # sólo si se dio el momento de servicio
    ms_knm: float = 0.0                   # momento de servicio ingresado
    fss_mpa: float = 0.0                  # esfuerzo en el acero en servicio
    dc_mm: float = 0.0
    beta_s: float = 0.0
    gamma_e: float = GAMMA_E_CLASS_1
    exposure_class: int = 1
    crack_spacing_max_mm: float = 0.0     # separación máxima admisible
    crack_spacing_mm: float = 0.0         # separación centro a centro real
    crack_control_ok: bool = True

    aashto_warnings: List[str] = field(default_factory=list)


class AashtoBeamSection:
    """Sección de viga o losa diseñada a flexión (AASHTO LRFD): rectangular, T o L."""

    def __init__(
        self,
        mu_nmm: float,
        b_mm: float,
        h_mm: float,
        cover_mm: float,
        fc_mpa: float,
        fy_mpa: float,
        reinforcement: Optional[ReinforcementConfig] = None,
        db_assumed_mm: float = 16.0,
        bar_spec: str = "A615",
        exposure_class: int = 1,
        ms_nmm: float = 0.0,
        lam: float = 1.0,
        section_shape: SectionShape = SectionShape.RECTANGULAR,
        bf_mm: float = 0.0,
        hf_mm: float = 0.0,
    ):
        self.mu_nmm = mu_nmm
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.cover_mm = cover_mm
        self.fc_mpa = fc_mpa
        self.fy_mpa = fy_mpa
        self.bar_spec = bar_spec
        self.exposure_class = exposure_class
        self.ms_nmm = max(ms_nmm, 0.0)
        self.lam = lam
        self.reinforcement = (
            default_reinforcement(db_assumed_mm)
            if reinforcement is None else reinforcement
        )
        self.section = SectionProfile.create(
            shape=section_shape, bw_mm=b_mm, h_mm=h_mm,
            bf_mm=bf_mm, hf_mm=hf_mm,
        )

    # ------------------------------------------------------------
    #                        Auxiliares
    # ------------------------------------------------------------

    def _validate(self) -> Optional[str]:
        if self.b_mm <= 0 or self.h_mm <= 0:
            return "Dimensiones (b, h) deben ser positivas"
        if self.cover_mm <= 0 or self.cover_mm >= self.h_mm * 0.5:
            return "Recubrimiento inválido"
        if self.fc_mpa <= 0 or self.fy_mpa <= 0:
            return "Resistencias deben ser positivas"
        if self.section.is_flanged and self.section.hf_mm >= self.h_mm:
            return "El espesor del ala debe ser menor que la altura total"
        return None

    def _strain_at(self, c_mm: float, dt_mm: float) -> float:
        """ε_t en el acero extremo para una profundidad de eje neutro c."""
        if c_mm <= 0:
            return 0.0
        return EPSILON_CU * (dt_mm - c_mm) / c_mm

    def _as_for_strain(self, eps_t: float, dt_mm: float, a1: float, b1: float) -> float:
        """A_s (mm²) que produce exactamente la deformación ε_t dada."""
        denom = EPSILON_CU + eps_t
        if denom <= 0 or self.fy_mpa <= 0:
            return 0.0
        c = EPSILON_CU * dt_mm / denom
        a = b1 * c
        if self.section.is_flanged:
            return (a1 * self.fc_mpa
                    * self.section.compression_area_mm2(a) / self.fy_mpa)
        return a1 * self.fc_mpa * self.b_mm * a / self.fy_mpa

    def _as_for_moment(
        self, m_nmm: float, d_mm: float, dt_mm: float, a1: float, b1: float
    ) -> Tuple[float, bool]:
        """A_s (mm²) necesario para que M_r alcance ``m_nmm``.

        φ depende de ε_t, que a su vez depende de A_s, así que se itera: se
        parte de φ = 0.90 y se recalcula hasta que φ se estabiliza. Converge
        en pocas vueltas porque φ está acotado entre 0.75 y 0.90.

        Devuelve ``(as_mm2, factible)``; ``factible`` es False cuando la
        sección no puede tomar ese momento ni con el bloque balanceado.
        """
        if m_nmm <= 0:
            return 0.0, True
        if self.fc_mpa <= 0 or self.fy_mpa <= 0 or self.b_mm <= 0 or d_mm <= 0:
            return 0.0, False

        m_ratio = self.fy_mpa / (a1 * self.fc_mpa)
        phi = PHI_TENSION
        as_mm2 = 0.0

        if self.section.is_flanged:
            # Misma iteración en φ, pero el A_s de cada vuelta sale del solver
            # por partes (ala + alma) en vez de la cuantía cerrada.
            for _ in range(50):
                as_mm2, factible = steel_for_flanged_moment(
                    self.section, m_nmm / phi, d_mm,
                    a1 * self.fc_mpa, self.fy_mpa,
                )
                if not factible:
                    return 0.0, False
                area = as_mm2 * self.fy_mpa / (a1 * self.fc_mpa)
                c = self.section.block_depth_mm(area) / b1 if b1 > 0 else 0.0
                phi_nuevo = phi_flexure(self._strain_at(c, dt_mm), self.fy_mpa)
                if abs(phi_nuevo - phi) < 1e-10:
                    break
                phi = phi_nuevo
            return as_mm2, True

        for _ in range(50):
            rn = m_nmm / (phi * self.b_mm * d_mm * d_mm)
            disc = 1.0 - 2.0 * m_ratio * rn / self.fy_mpa
            if disc < 0:
                return 0.0, False
            rho = (1.0 / m_ratio) * (1.0 - math.sqrt(disc))
            as_mm2 = rho * self.b_mm * d_mm

            a = as_mm2 * self.fy_mpa / (a1 * self.fc_mpa * self.b_mm)
            c = a / b1 if b1 > 0 else 0.0
            phi_nuevo = phi_flexure(self._strain_at(c, dt_mm), self.fy_mpa)
            if abs(phi_nuevo - phi) < 1e-10:
                phi = phi_nuevo
                break
            phi = phi_nuevo

        return as_mm2, True

    def _crack_control(
        self, as_mm2: float, d_mm: float, warnings_list: List[str]
    ) -> dict:
        """Control de fisuración por distribución del refuerzo (§5.6.7).

        Requiere el momento de **servicio**; si no se dio, la revisión se omite.
        El esfuerzo en el acero sale de la sección fisurada transformada.
        """
        vacio = dict(
            crack_control_applies=False, fss_mpa=0.0, dc_mm=0.0, beta_s=0.0,
            crack_spacing_max_mm=0.0, crack_spacing_mm=0.0, crack_control_ok=True,
        )
        if self.ms_nmm <= 0 or as_mm2 <= 0 or d_mm <= 0 or self.b_mm <= 0:
            return vacio
        if not self.reinforcement.layers:
            return vacio

        capa = self.reinforcement.layers[0]
        db = capa.bar_diameter_mm
        # d_c: del borde traccionado al centro de la barra más cercana.
        dc = self.cover_mm + self.reinforcement.stirrup_diameter_mm + db / 2.0
        if dc >= self.h_mm:
            return vacio

        ec = concrete_modulus(self.fc_mpa)
        if ec <= 0:
            return vacio
        n = ES_MPA / ec
        # En servicio la zona comprimida suele quedar dentro del ala, así que
        # la sección fisurada se analiza con el ancho comprimido b_f (que en
        # rectangular es el ancho de siempre).
        b_comp = self.section.bf_mm
        rho = as_mm2 / (b_comp * d_mm)
        rn = rho * n
        k = math.sqrt(rn * rn + 2.0 * rn) - rn
        j = 1.0 - k / 3.0
        if self.section.is_flanged and k * d_mm > self.section.hf_mm:
            warnings_list.append(
                "Control de fisuración: en servicio el eje neutro cae bajo el "
                f"ala (k·d = {k * d_mm:.0f} mm > h_f = {self.section.hf_mm:.0f} "
                "mm). La sección fisurada se analizó como rectangular de ancho "
                "b_f, lo que subestima levemente f_ss (§5.6.7)."
            )

        fss = self.ms_nmm / (as_mm2 * j * d_mm)
        tope = 0.6 * self.fy_mpa
        if fss > tope:
            fss = tope
            warnings_list.append(
                "El esfuerzo del acero en servicio superó 0.6·f_y; se limitó a "
                f"{tope:.0f} MPa para el control de fisuración (§5.6.7)."
            )

        beta_s = 1.0 + dc / (0.7 * (self.h_mm - dc))
        ge = gamma_e(self.exposure_class)
        s_max = CRACK_CONTROL_COEFF * ge / (beta_s * fss) - 2.0 * dc if fss > 0 else 0.0
        s_max = max(s_max, 0.0)

        # Separación real centro a centro del lecho más poblado.
        s_libre, _ = horizontal_clear_spacing(
            self.reinforcement, self.b_mm, self.cover_mm
        )
        s_real = 0.0 if not math.isfinite(s_libre) else s_libre + db

        ok = True
        if s_real > 0 and s_max > 0 and s_real > s_max:
            ok = False
            warnings_list.append(
                f"Control de fisuración: la separación real ({s_real:.0f} mm) "
                f"excede la máxima admisible ({s_max:.0f} mm) para exposición "
                f"clase {int(self.exposure_class)} (§5.6.7)."
            )

        return dict(
            crack_control_applies=True, fss_mpa=fss, dc_mm=dc, beta_s=beta_s,
            crack_spacing_max_mm=s_max, crack_spacing_mm=s_real,
            crack_control_ok=ok,
        )

    # ------------------------------------------------------------
    #                          Diseño
    # ------------------------------------------------------------

    def design(self) -> AashtoFlexionResult:
        warnings_list: List[str] = []
        aashto_warnings: List[str] = []
        error = self._validate()

        d_mm, s_v_used, y_layers = effective_depth(
            self.reinforcement, self.h_mm, self.cover_mm
        )
        # d_t: al centroide del lecho extremo en tracción (el más bajo).
        dt_mm = (self.h_mm - y_layers[0]) if y_layers else d_mm

        a1 = alpha_1(self.fc_mpa)
        b1 = beta_1(self.fc_mpa)
        eps_cl, eps_tl = strain_limits(self.fy_mpa)

        if not error:
            if self.fc_mpa < FC_MIN_MPA:
                aashto_warnings.append(
                    f"f'c = {self.fc_mpa:.0f} MPa es menor que el mínimo de "
                    f"{FC_MIN_MPA:.0f} MPa para concreto estructural (§5.4.2.1)."
                )
            if self.fc_mpa > FC_MAX_MPA:
                aashto_warnings.append(
                    f"f'c = {self.fc_mpa:.0f} MPa supera 70 MPa; §5.4.2.1 exige "
                    "aprobación del propietario y verificación experimental."
                )
            if self.fy_mpa > FY_MAX_MPA:
                aashto_warnings.append(
                    f"f_y = {self.fy_mpa:.0f} MPa supera el Grado 100 "
                    "(690 MPa), máximo contemplado en §5.4.3.1."
                )

        # --- Refuerzo requerido por resistencia ---
        if error:
            status = "ERROR"
            as_required_mm2 = 0.0
            warnings_list.append(error)
        else:
            as_required_mm2, factible = self._as_for_moment(
                self.mu_nmm, d_mm, dt_mm, a1, b1
            )
            if factible:
                status = "OK"
            else:
                status = "AUMENTAR SECCIÓN"
                warnings_list.append(
                    "Sección insuficiente: M_u excede lo que la sección puede "
                    "tomar sin acero en compresión."
                )

        # --- Momento de fisuración y refuerzo mínimo (§5.6.3.3) ---
        fr = modulus_of_rupture(self.fc_mpa, self.lam)
        if self.section.is_flanged:
            # Con ala el módulo de sección de la fibra traccionada (la
            # inferior, con el ala comprimida) ya no es b·h²/6: el centroide
            # sube hacia el ala y S_inf crece.
            _, _, _, sc = self.section.gross_properties()
        else:
            sc = self.b_mm * self.h_mm ** 2 / 6.0     # sección bruta rectangular
        g3 = gamma_3(self.bar_spec)
        mcr_nmm = g3 * GAMMA_1 * fr * sc
        mu_min_nmm = min(1.33 * self.mu_nmm, mcr_nmm) if self.mu_nmm > 0 else mcr_nmm
        as_min_mm2 = 0.0
        if not error:
            as_min_mm2, _ = self._as_for_moment(mu_min_nmm, d_mm, dt_mm, a1, b1)

        # --- "Máximo": el A_s que lleva la sección a compresión controlada ---
        as_max_mm2 = (
            self._as_for_strain(eps_cl, dt_mm, a1, b1) if not error else 0.0
        )

        # --- Refuerzo provisto y capacidad real ---
        as_provided_mm2 = self.reinforcement.total_area_mm2
        as_provided_cm2 = as_provided_mm2 / 100.0
        rho_provided = (
            as_provided_mm2 / (self.b_mm * d_mm)
            if d_mm > 0 and self.b_mm > 0 else 0.0
        )

        if self.section.is_flanged:
            area_comp_mm2 = (
                as_provided_mm2 * self.fy_mpa / (a1 * self.fc_mpa)
                if self.fc_mpa > 0 else 0.0
            )
            a_mm = self.section.block_depth_mm(area_comp_mm2)
            yc_mm = self.section.compression_centroid_mm(a_mm)
            compression_kn = (a1 * self.fc_mpa
                              * self.section.compression_area_mm2(a_mm)) / 1000.0
        else:
            a_mm = (
                as_provided_mm2 * self.fy_mpa / (a1 * self.fc_mpa * self.b_mm)
                if self.b_mm > 0 and self.fc_mpa > 0 else 0.0
            )
            yc_mm = a_mm / 2.0
            compression_kn = (a1 * self.fc_mpa * self.b_mm * a_mm) / 1000.0
        c_mm = a_mm / b1 if b1 > 0 else 0.0
        jd_mm = d_mm - yc_mm
        eps_t = self._strain_at(c_mm, dt_mm)
        phi = phi_flexure(eps_t, self.fy_mpa)

        tension_kn = (as_provided_mm2 * self.fy_mpa) / 1000.0
        mn_nmm = as_provided_mm2 * self.fy_mpa * jd_mm
        phi_mn_knm = phi * mn_nmm / 1e6

        if eps_t <= eps_cl:
            comportamiento = "COMPRESIÓN CONTROLADA"
        elif eps_t >= eps_tl:
            comportamiento = "TRACCIÓN CONTROLADA"
        else:
            comportamiento = "TRANSICIÓN"

        # --- Verificaciones de resistencia ---
        min_reinf_ok = True
        if status == "OK":
            demanda_mm2 = max(as_required_mm2, as_min_mm2)
            if as_provided_mm2 < demanda_mm2 - 1e-9:
                status = "ARMADO INSUFICIENTE"
                faltante = (demanda_mm2 - as_provided_mm2) / 100.0
                warnings_list.append(
                    f"Acero proporcionado ({as_provided_cm2:.2f} cm²) < requerido "
                    f"({demanda_mm2 / 100.0:.2f} cm²). Faltan {faltante:.2f} cm²"
                )
            elif comportamiento == "COMPRESIÓN CONTROLADA":
                status = "REDUCIR SECCIÓN"

        if not error and phi_mn_knm * 1e6 < mu_min_nmm - 1e-6:
            min_reinf_ok = False
            aashto_warnings.append(
                f"Refuerzo mínimo (§5.6.3.3): M_r = {phi_mn_knm:.1f} kN·m no "
                f"alcanza min(1.33·M_u, M_cr) = {mu_min_nmm / 1e6:.1f} kN·m."
            )

        if not error and comportamiento == "COMPRESIÓN CONTROLADA":
            aashto_warnings.append(
                f"Sección de compresión controlada (ε_t = {eps_t:.4f} ≤ ε_cl = "
                f"{eps_cl:.4f}): φ cae a {PHI_COMPRESSION:.2f} (§5.5.4.2). La "
                "falla sería frágil; conviene aumentar el peralte o reducir A_s."
            )
        elif not error and comportamiento == "TRANSICIÓN":
            aashto_warnings.append(
                f"Sección en transición (ε_t = {eps_t:.4f}): φ = {phi:.3f} en vez "
                f"de {PHI_TENSION:.2f} (§5.5.4.2)."
            )

        # --- Control de fisuración (§5.6.7) ---
        fisuracion = self._crack_control(as_provided_mm2, d_mm, aashto_warnings)

        # --- Separaciones del armado ---
        s_h_actual, s_h_min = horizontal_clear_spacing(
            self.reinforcement, self.b_mm, self.cover_mm
        )
        s_h_ok = s_h_actual >= s_h_min
        if not s_h_ok and self.reinforcement.layers and \
           max(L.n_bars for L in self.reinforcement.layers) > 1:
            warnings_list.append(
                f"Separación horizontal insuficiente: {s_h_actual:.1f} mm < "
                f"{s_h_min:.1f} mm (§5.10.3.1.1)"
            )

        n_layers = len(self.reinforcement.layers)
        s_v_min = min_vertical_clear_spacing_mm(self.reinforcement)
        s_v_ok = (n_layers <= 1) or (s_v_used >= s_v_min)
        if n_layers > 1 and not s_v_ok:
            warnings_list.append(
                f"Separación vertical entre lechos insuficiente: {s_v_used:.1f} mm "
                f"< {s_v_min:.1f} mm (§5.10.3.1.2)"
            )

        # --- Ancho efectivo del ala (§4.6.2.6.1) ---
        comportamiento_t = self.section.flange_is_fully_compressed(a_mm)
        asf_cm2 = 0.0
        if comportamiento_t:
            asf_cm2 = (a1 * self.fc_mpa
                       * (self.section.bf_mm - self.section.bw_mm)
                       * self.section.hf_mm / self.fy_mpa) / 100.0

        return AashtoFlexionResult(
            b_mm=self.b_mm,
            h_mm=self.h_mm,
            cover_mm=self.cover_mm,
            d_mm=d_mm,
            fc_mpa=self.fc_mpa,
            fy_mpa=self.fy_mpa,
            beta_1=b1,
            rn=(self.mu_nmm / (phi * self.b_mm * d_mm * d_mm)
                if self.b_mm > 0 and d_mm > 0 and phi > 0 else 0.0),
            rho_required=(as_required_mm2 / (self.b_mm * d_mm)
                          if self.b_mm > 0 and d_mm > 0 else 0.0),
            as_required_cm2=as_required_mm2 / 100.0,
            as_min_cm2=as_min_mm2 / 100.0,
            as_max_cm2=as_max_mm2 / 100.0,
            as_provided_cm2=as_provided_cm2,
            rho_provided=rho_provided,
            a_mm=a_mm,
            c_mm=c_mm,
            jd_mm=jd_mm,
            compression_kn=compression_kn,
            tension_kn=tension_kn,
            horizontal_spacing_mm=(
                s_h_actual if math.isfinite(s_h_actual) else 0.0
            ),
            horizontal_spacing_min_mm=s_h_min,
            horizontal_spacing_ok=s_h_ok,
            vertical_spacing_mm=s_v_used if n_layers > 1 else 0.0,
            vertical_spacing_min_mm=s_v_min,
            vertical_spacing_ok=s_v_ok,
            phi_mn_knm=phi_mn_knm,
            mu_demand_knm=self.mu_nmm / 1e6,
            status=status,
            warnings=warnings_list + aashto_warnings,
            reinforcement=self.reinforcement,
            layer_y_positions_mm=y_layers,
            section_shape=self.section.shape,
            bf_mm=self.section.bf_mm,
            hf_mm=self.section.hf_mm,
            yc_mm=yc_mm,
            flanged_behaviour=comportamiento_t,
            asf_cm2=asf_cm2,
            bf_max_mm=self.section.aci_max_flange_width_mm(),
            # --- propios de AASHTO ---
            phi_flexion=phi,
            epsilon_t=eps_t,
            epsilon_cl=eps_cl,
            epsilon_tl=eps_tl,
            dt_mm=dt_mm,
            alpha_1=a1,
            section_behaviour=comportamiento,
            fr_mpa=fr,
            sc_mm3=sc,
            mcr_knm=mcr_nmm / 1e6,
            mu_min_knm=mu_min_nmm / 1e6,
            gamma_1=GAMMA_1,
            gamma_3=g3,
            bar_spec=self.bar_spec,
            min_reinf_ok=min_reinf_ok,
            gamma_e=gamma_e(self.exposure_class),
            exposure_class=int(self.exposure_class),
            ms_knm=self.ms_nmm / 1e6,
            aashto_warnings=aashto_warnings,
            **fisuracion,
        )
