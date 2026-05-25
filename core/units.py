from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple

class UnitSystem(Enum):
    MKS = "MKS (tonf, m)"
    SI = "SI (kN, m)"
    ENGLISH = "Inglés (kip, ft)"

# Constantes de conversión
CM2_TO_IN2 = 0.155  # 1 cm² = 0.155 in²
IN2_TO_CM2 = 6.4516  # 1 in² = 6.4516 cm²

@dataclass
class UnitConverter:
    system: UnitSystem

    # Factores de conversión a unidades SI internas (N, mm, MPa)
    force_to_kn: float
    length_to_m: float
    stress_to_mpa: float
    moment_to_knm: float

    # Etiquetas de visualización
    force_unit: str
    length_unit: str
    stress_unit: str
    moment_unit: str
    area_unit: str

    # Defaults razonables por sistema
    default_mu: float
    default_b: float
    default_h: float
    default_cover: float
    default_fc: float
    default_fy: float

    # Rangos (min, max) para QDoubleSpinBox
    range_mu: Tuple[float, float]
    range_b: Tuple[float, float]
    range_h: Tuple[float, float]
    range_cover: Tuple[float, float]
    range_fc: Tuple[float, float]
    range_fy: Tuple[float, float]

    # Decimales para mostrar
    decimals_length: int = 3
    decimals_stress: int = 0
    decimals_moment: int = 1

    def area_label(self) -> str:
        """Etiqueta de área según sistema"""
        return self.area_unit

    def convert_area_from_cm2(self, area_cm2: float) -> float:
        """Convierte cm² al sistema actual"""
        if self.system == UnitSystem.ENGLISH:
            return area_cm2 * CM2_TO_IN2
        return area_cm2

    def format_area(self, area_cm2: float, decimals: int = 2) -> str:
        """Formatea un área (siempre recibida en cm²) al sistema actual"""
        value = self.convert_area_from_cm2(area_cm2)
        return f"{value:.{decimals}f} {self.area_unit}"

    def convert_length_from_mm(self, length_mm: float) -> float:
        """Convierte mm al sistema actual"""
        # length_to_m: factor para convertir input -> m
        # 1 m = 1000 mm; output_unit_value = length_mm/1000/length_to_m
        return length_mm / 1000.0 / self.length_to_m

    def format_length(self, length_mm: float, decimals: int = 3) -> str:
        """Formatea una longitud (mm) al sistema actual"""
        value = self.convert_length_from_mm(length_mm)
        return f"{value:.{decimals}f} {self.length_unit}"

    def format_length_small(self, length_mm: float, decimals: int = 1) -> str:
        """Formatea longitudes pequeñas en cm (SI/MKS) o pulgadas (Inglés).

        Útil para geometría calculada (d, a, c, jd) y separaciones donde
        los valores en m/ft tendrían demasiados decimales.
        """
        if self.system == UnitSystem.ENGLISH:
            value = length_mm / 25.4  # mm a pulgadas
            return f"{value:.{decimals}f} in"
        value = length_mm / 10.0      # mm a cm
        return f"{value:.{decimals}f} cm"


# Conversion factors
# length_to_m: factor para convertir el valor ingresado por el usuario a metros.
# Para que las longitudes sean prácticas, usamos cm para SI/MKS y pulgadas para Inglés.
#   1 cm = 0.01 m   -> length_to_m = 0.01
#   1 in = 0.0254 m -> length_to_m = 0.0254
UNIT_SYSTEMS: Dict[UnitSystem, UnitConverter] = {
    UnitSystem.MKS: UnitConverter(
        system=UnitSystem.MKS,
        force_to_kn=9.80665,
        length_to_m=0.01,        # cm a m
        stress_to_mpa=0.0980665,
        moment_to_knm=9.80665,
        force_unit="tonf",
        length_unit="cm",
        stress_unit="kgf/cm²",
        moment_unit="tonf·m",
        area_unit="cm²",
        default_mu=15.0,
        default_b=30.0,           # cm
        default_h=50.0,           # cm
        default_cover=4.0,        # cm
        default_fc=280.0,
        default_fy=4200.0,
        range_mu=(0.0, 5000.0),
        range_b=(5.0, 500.0),     # cm
        range_h=(5.0, 500.0),     # cm
        range_cover=(1.0, 20.0),  # cm
        range_fc=(100.0, 500.0),
        range_fy=(2000.0, 5000.0),
        decimals_length=1,
        decimals_stress=0,
        decimals_moment=2,
    ),
    UnitSystem.SI: UnitConverter(
        system=UnitSystem.SI,
        force_to_kn=1.0,
        length_to_m=0.01,        # cm a m
        stress_to_mpa=1.0,
        moment_to_knm=1.0,
        force_unit="kN",
        length_unit="cm",
        stress_unit="MPa",
        moment_unit="kN·m",
        area_unit="cm²",
        default_mu=150.0,
        default_b=30.0,           # cm
        default_h=50.0,           # cm
        default_cover=4.0,        # cm
        default_fc=28.0,
        default_fy=420.0,
        range_mu=(0.0, 50000.0),
        range_b=(5.0, 500.0),     # cm
        range_h=(5.0, 500.0),     # cm
        range_cover=(1.0, 20.0),  # cm
        range_fc=(10.0, 100.0),
        range_fy=(200.0, 600.0),
        decimals_length=1,
        decimals_stress=1,
        decimals_moment=1,
    ),
    UnitSystem.ENGLISH: UnitConverter(
        system=UnitSystem.ENGLISH,
        force_to_kn=4.44822,
        length_to_m=0.0254,       # in a m
        stress_to_mpa=0.00689476,
        moment_to_knm=1.35582,
        force_unit="kip",
        length_unit="in",
        stress_unit="psi",
        moment_unit="kip·ft",
        area_unit="in²",
        default_mu=110.0,
        default_b=12.0,           # in
        default_h=20.0,           # in
        default_cover=1.5,        # in
        default_fc=4000.0,
        default_fy=60000.0,
        range_mu=(0.0, 50000.0),
        range_b=(2.0, 200.0),     # in
        range_h=(2.0, 200.0),     # in
        range_cover=(0.5, 6.0),   # in
        range_fc=(2000.0, 12000.0),
        range_fy=(20000.0, 100000.0),
        decimals_length=2,
        decimals_stress=0,
        decimals_moment=2,
    ),
}

def get_converter(system: UnitSystem) -> UnitConverter:
    return UNIT_SYSTEMS[system]
