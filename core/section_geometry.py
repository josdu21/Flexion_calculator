"""Geometría de la sección y del armado, común a todas las normas.

Cómo se acomodan las barras en lechos, dónde cae el centroide del acero y qué
separación libre queda entre barras no depende de la norma de diseño: es
geometría. ACI 318-19 y AASHTO LRFD sólo difieren en el *mínimo* exigido a esas
separaciones, no en cómo se miden.

Los mínimos de separación que se usan acá son los de ACI 318-19 §25.2, que
coinciden con AASHTO LRFD §5.10.3.1.1 salvo por el término de 1.5·d_ag que
AASHTO agrega y esta aplicación no modela (no se pide el tamaño del agregado).

Todo en unidades internas SI: mm.
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple


MIN_BAR_SPACING_MM = 25.0   # ACI 318-19 §25.2.1 / AASHTO §5.10.3.1.1


@dataclass
class RebarLayer:
    """Un lecho de barras."""
    n_bars: int
    bar_diameter_mm: float
    bar_area_mm2: float

    @property
    def area_mm2(self) -> float:
        return self.n_bars * self.bar_area_mm2


@dataclass
class ReinforcementConfig:
    """Configuración del refuerzo: lechos, estribo, etc."""
    layers: List[RebarLayer]
    stirrup_diameter_mm: float = 9.52  # default #3
    # Separación vertical entre lechos (libre, mm). Si <0, se usa el mínimo.
    vertical_clear_spacing_mm: float = -1.0

    @property
    def total_bars(self) -> int:
        return sum(L.n_bars for L in self.layers)

    @property
    def total_area_mm2(self) -> float:
        return sum(L.area_mm2 for L in self.layers)

    @property
    def total_area_cm2(self) -> float:
        return self.total_area_mm2 / 100.0


def default_reinforcement(db_mm: float, n_bars: int = 2) -> ReinforcementConfig:
    """Armado por defecto: un lecho de ``n_bars`` barras del diámetro dado."""
    return ReinforcementConfig(
        layers=[RebarLayer(
            n_bars=n_bars,
            bar_diameter_mm=db_mm,
            bar_area_mm2=math.pi * (db_mm / 2.0) ** 2,
        )]
    )


def min_vertical_clear_spacing_mm(reinforcement: ReinforcementConfig) -> float:
    """Separación libre vertical mínima entre lechos: max(d_b, 25 mm)."""
    if not reinforcement.layers:
        return MIN_BAR_SPACING_MM
    db_main = max(L.bar_diameter_mm for L in reinforcement.layers)
    return max(db_main, MIN_BAR_SPACING_MM)


def effective_depth(
    reinforcement: ReinforcementConfig, h_mm: float, cover_mm: float
) -> Tuple[float, float, List[float]]:
    """Peralte efectivo a partir de la disposición real de los lechos.

    Retorna ``(d_mm, separación vertical usada, y de cada lecho)``, donde ``y``
    se mide desde la fibra inferior al centroide del lecho.

    El primer lecho queda a ``recubrimiento + d_estribo + d_b/2``; cada lecho
    siguiente se separa del anterior la separación libre vertical. ``d`` es la
    distancia desde la fibra en compresión al centroide del acero, ponderado por
    área.
    """
    if not reinforcement.layers:
        return h_mm * 0.9, 0.0, []

    db_st = reinforcement.stirrup_diameter_mm
    s_v_min = min_vertical_clear_spacing_mm(reinforcement)
    s_v = (reinforcement.vertical_clear_spacing_mm
           if reinforcement.vertical_clear_spacing_mm > 0 else s_v_min)

    y_layers: List[float] = []
    for i, layer in enumerate(reinforcement.layers):
        if i == 0:
            y_i = cover_mm + db_st + layer.bar_diameter_mm / 2.0
        else:
            prev = reinforcement.layers[i - 1]
            y_i = (y_layers[-1] + prev.bar_diameter_mm / 2.0
                   + s_v + layer.bar_diameter_mm / 2.0)
        y_layers.append(y_i)

    total_area = sum(L.area_mm2 for L in reinforcement.layers)
    if total_area <= 0:
        return h_mm * 0.9, s_v, []

    y_centroid = sum(
        L.area_mm2 * y for L, y in zip(reinforcement.layers, y_layers)
    ) / total_area

    return max(h_mm - y_centroid, 1e-6), s_v, y_layers


def horizontal_clear_spacing(
    reinforcement: ReinforcementConfig, b_mm: float, cover_mm: float
) -> Tuple[float, float]:
    """Separación libre horizontal real y mínima exigida, en mm.

    Evalúa el lecho con más barras, que es el crítico. Con una sola barra no hay
    separación que medir y se devuelve ``inf``.
    """
    if not reinforcement.layers:
        return 0.0, MIN_BAR_SPACING_MM

    critical = max(reinforcement.layers, key=lambda L: L.n_bars)
    n = critical.n_bars
    db = critical.bar_diameter_mm
    s_min = max(db, MIN_BAR_SPACING_MM)

    if n <= 1:
        return float("inf"), s_min

    # Ancho libre entre estribos, repartido entre los n-1 espacios.
    w_avail = b_mm - 2 * cover_mm - 2 * reinforcement.stirrup_diameter_mm
    return (w_avail - n * db) / (n - 1), s_min


# ---------------------------------------------------------------------------
#                    Forma de la sección de concreto
# ---------------------------------------------------------------------------
#
# Una sección con ala (T o L) no es un caso aparte sino el caso general: la
# rectangular sale de poner ``bf = bw``, y con eso todas las fórmulas de abajo
# se reducen exactamente a las de siempre. Por eso los motores de las dos
# normas pueden preguntarle a este objeto por el área comprimida y su centroide
# sin ramificar por forma en cada línea.
#
# Se modela únicamente el **ala comprimida** (momento positivo). Con el ala en
# tracción la sección responde como rectangular de ancho ``bw``, que es lo que
# se obtiene eligiendo la forma rectangular.


class SectionShape(Enum):
    """Forma de la sección de concreto."""
    RECTANGULAR = "Rectangular"
    T = "Viga T"
    L = "Viga L (borde)"


# Voladizos de ala que tiene cada forma: la T tiene dos, la L uno.
_FLANGE_SIDES = {SectionShape.RECTANGULAR: 0, SectionShape.T: 2, SectionShape.L: 1}

# ACI 318-19 Tabla 6.3.2.1: voladizo máximo del ala, en múltiplos de h_f. Es el
# único de los tres límites de la tabla que se puede verificar sin conocer la
# luz libre ni la separación entre almas.
_ACI_OVERHANG_FACTOR = {SectionShape.T: 8.0, SectionShape.L: 6.0}

# ACI 318-19 §22.7.4.1: para torsión el voladizo del ala se limita además a la
# proyección del alma bajo el ala y a 4·h_f.
_TORSION_OVERHANG_FACTOR = 4.0


@dataclass(frozen=True)
class SectionProfile:
    """Sección de concreto con ala opcional, con el ala del lado comprimido.

    ``bw_mm`` es el ancho del alma —el que rige cortante y torsión— y
    ``bf_mm``/``hf_mm`` describen el ala. En una sección rectangular el ala se
    normaliza a ``bf = bw`` y ``hf = h``, de modo que el bloque de compresión
    nunca sale del "ala" y las fórmulas devuelven exactamente los valores de
    una sección rectangular.
    """
    shape: SectionShape
    bw_mm: float
    h_mm: float
    bf_mm: float
    hf_mm: float

    @classmethod
    def create(
        cls,
        shape: SectionShape = SectionShape.RECTANGULAR,
        bw_mm: float = 0.0,
        h_mm: float = 0.0,
        bf_mm: float = 0.0,
        hf_mm: float = 0.0,
    ) -> "SectionProfile":
        """Normaliza los datos de entrada a un perfil consistente.

        Una forma rectangular ignora lo que venga en ``bf``/``hf``; una con ala
        que no alcance a tener ala real (``bf ≤ bw`` o ``hf ≤ 0``) se degrada a
        rectangular en vez de producir un ala de ancho negativo.
        """
        if shape is SectionShape.RECTANGULAR or bf_mm <= bw_mm or hf_mm <= 0.0:
            return cls(SectionShape.RECTANGULAR, bw_mm, h_mm, bw_mm, h_mm)
        return cls(shape, bw_mm, h_mm, bf_mm, min(hf_mm, h_mm))

    # ---- descripción ----

    @property
    def is_flanged(self) -> bool:
        return self.shape is not SectionShape.RECTANGULAR

    @property
    def flange_sides(self) -> int:
        return _FLANGE_SIDES[self.shape]

    @property
    def overhang_mm(self) -> float:
        """Voladizo del ala a cada lado del alma."""
        if not self.is_flanged or self.flange_sides == 0:
            return 0.0
        return (self.bf_mm - self.bw_mm) / self.flange_sides

    # ---- bloque de compresión ----

    def compression_area_mm2(self, a_mm: float) -> float:
        """Área comprimida para una profundidad de bloque ``a``."""
        a = max(a_mm, 0.0)
        if a <= self.hf_mm:
            return self.bf_mm * a
        return self.bf_mm * self.hf_mm + self.bw_mm * (a - self.hf_mm)

    def compression_centroid_mm(self, a_mm: float) -> float:
        """Profundidad del centroide del bloque comprimido, desde la fibra superior.

        En sección rectangular da exactamente ``a/2``.
        """
        a = max(a_mm, 0.0)
        if a <= self.hf_mm:
            return a / 2.0
        area_ala = self.bf_mm * self.hf_mm
        alma = a - self.hf_mm
        area_alma = self.bw_mm * alma
        total = area_ala + area_alma
        if total <= 0:
            return 0.0
        return (
            area_ala * self.hf_mm / 2.0
            + area_alma * (self.hf_mm + alma / 2.0)
        ) / total

    def block_depth_mm(self, area_mm2: float) -> float:
        """Profundidad ``a`` del bloque que encierra el área comprimida dada."""
        area = max(area_mm2, 0.0)
        area_ala = self.bf_mm * self.hf_mm
        if area <= area_ala:
            return area / self.bf_mm if self.bf_mm > 0 else 0.0
        if self.bw_mm <= 0:
            return self.hf_mm
        return self.hf_mm + (area - area_ala) / self.bw_mm

    def flange_is_fully_compressed(self, a_mm: float) -> bool:
        """¿El eje neutro cae bajo el ala, es decir, la sección trabaja como T?"""
        return self.is_flanged and a_mm > self.hf_mm

    # ---- sección bruta (momento de fisuración) ----

    def gross_properties(self) -> Tuple[float, float, float, float]:
        """``(A_g, y_inf, I_g, S_inf)`` de la sección bruta, sin fisurar.

        ``y_inf`` es la distancia del centroide a la fibra inferior y ``S_inf``
        el módulo de sección de esa fibra, que es la traccionada con el ala
        comprimida. En sección rectangular ``S_inf = b·h²/6``.
        """
        b_alma = self.bw_mm
        h_alma = self.h_mm - self.hf_mm
        area_ala = self.bf_mm * self.hf_mm
        area_alma = b_alma * h_alma
        ag = area_ala + area_alma
        if ag <= 0:
            return 0.0, 0.0, 0.0, 0.0

        # Centroides medidos desde la fibra superior.
        y_sup = (
            area_ala * self.hf_mm / 2.0
            + area_alma * (self.hf_mm + h_alma / 2.0)
        ) / ag
        y_inf = self.h_mm - y_sup

        ig = (
            self.bf_mm * self.hf_mm ** 3 / 12.0
            + area_ala * (y_sup - self.hf_mm / 2.0) ** 2
            + b_alma * h_alma ** 3 / 12.0
            + area_alma * (self.hf_mm + h_alma / 2.0 - y_sup) ** 2
        )
        s_inf = ig / y_inf if y_inf > 0 else 0.0
        return ag, y_inf, ig, s_inf

    # ---- torsión ----

    def torsion_overhang_mm(self) -> float:
        """Voladizo del ala computable en torsión (ACI 318-19 §22.7.4.1).

        Se limita a la proyección del alma bajo el ala y a 4·h_f, así que un ala
        muy ancha sólo aporta la parte que la norma reconoce.
        """
        if not self.is_flanged:
            return 0.0
        return min(
            self.overhang_mm,
            self.h_mm - self.hf_mm,
            _TORSION_OVERHANG_FACTOR * self.hf_mm,
        )

    def torsion_gross_properties(self) -> Tuple[float, float]:
        """``(A_cp, p_cp)`` del contorno exterior, con el ala ya limitada."""
        be = self.torsion_overhang_mm()
        lados = self.flange_sides
        acp = self.bw_mm * self.h_mm + lados * be * self.hf_mm
        pcp = 2.0 * (self.bw_mm + self.h_mm) + 2.0 * lados * be
        return acp, pcp

    # ---- límite normativo del ancho de ala ----

    def aci_max_flange_width_mm(self) -> float:
        """Ancho de ala que admite el término en h_f de la Tabla 6.3.2.1.

        Los otros dos límites de la tabla (s_w/2 y l_n/8, o l_n/12 en la L)
        dependen de la luz y de la separación entre almas, que esta aplicación
        no pide; quedan a cargo de quien diseña.
        """
        if not self.is_flanged:
            return self.bw_mm
        factor = _ACI_OVERHANG_FACTOR[self.shape]
        return self.bw_mm + self.flange_sides * factor * self.hf_mm


def steel_for_flanged_moment(
    section: SectionProfile,
    mn_nmm: float,
    d_mm: float,
    stress_mpa: float,
    fy_mpa: float,
) -> Tuple[float, bool]:
    """A_s que desarrolla ``mn_nmm`` en una sección con el ala comprimida.

    ``stress_mpa`` es el esfuerzo uniforme del bloque rectangular equivalente:
    ``0.85·f'c`` en ACI 318-19, ``α₁·f'c`` en AASHTO LRFD. La norma sólo entra
    por ese valor, así que las dos comparten este solver.

    Se resuelve como es clásico, en dos partes: si el bloque cabe dentro del
    ala la sección es rectangular de ancho ``b_f``; si no, los voladizos del
    ala aportan ``A_sf`` con brazo ``d − h_f/2`` y el alma toma el resto.

    Devuelve ``(A_s en mm², factible)``. No es factible cuando el momento
    excede lo que la sección puede tomar sin acero en compresión.
    """
    if mn_nmm <= 0:
        return 0.0, True
    if stress_mpa <= 0 or fy_mpa <= 0 or d_mm <= 0 or section.bw_mm <= 0:
        return 0.0, False

    # 1) ¿Alcanza con el bloque dentro del ala? Entonces es rectangular con b_f.
    disc = d_mm * d_mm - 2.0 * mn_nmm / (stress_mpa * section.bf_mm)
    if disc < 0:
        # Ni como rectangular del ancho completo del ala entra el momento.
        return 0.0, False
    a_ala = d_mm - math.sqrt(disc)
    if a_ala <= section.hf_mm:
        return stress_mpa * section.bf_mm * a_ala / fy_mpa, True

    # 2) Comportamiento de T: voladizos del ala + alma.
    asf = stress_mpa * (section.bf_mm - section.bw_mm) * section.hf_mm / fy_mpa
    mn_ala = asf * fy_mpa * (d_mm - section.hf_mm / 2.0)
    mn_alma = mn_nmm - mn_ala
    if mn_alma <= 0:
        return asf, True

    disc_alma = d_mm * d_mm - 2.0 * mn_alma / (stress_mpa * section.bw_mm)
    if disc_alma < 0:
        return 0.0, False
    a_alma = d_mm - math.sqrt(disc_alma)
    return asf + stress_mpa * section.bw_mm * a_alma / fy_mpa, True
