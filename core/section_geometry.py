"""Geometría del armado de una sección rectangular, común a todas las normas.

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
