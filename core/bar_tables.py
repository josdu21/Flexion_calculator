from dataclasses import dataclass
from typing import List, Optional
import math

@dataclass
class RebarSize:
    number: int
    diameter_mm: float
    area_cm2: float

    @property
    def label(self) -> str:
        return f"#{self.number}"

    @property
    def area_mm2(self) -> float:
        return self.area_cm2 * 100.0

# ASTM standard rebar sizes
REBAR_SIZES = [
    RebarSize(2, 6.35, 0.32),
    RebarSize(3, 9.52, 0.71),
    RebarSize(4, 12.70, 1.27),
    RebarSize(5, 15.88, 1.98),
    RebarSize(6, 19.05, 2.84),
    RebarSize(8, 25.40, 5.07),
    RebarSize(10, 31.75, 7.92),
    RebarSize(12, 38.10, 11.40),
]


def get_rebar_by_number(number: int) -> Optional[RebarSize]:
    """Devuelve la RebarSize correspondiente al #de varilla, o None."""
    for r in REBAR_SIZES:
        if r.number == number:
            return r
    return None

@dataclass
class BarCombination:
    count: int
    size: RebarSize
    total_area_cm2: float

    @property
    def label(self) -> str:
        return f"{self.count} × #{self.size.number}"

    @property
    def description(self) -> str:
        return f"{self.label} = {self.total_area_cm2:.2f} cm²"

def suggest_bar_combinations(as_required_cm2: float, max_suggestions: int = 3) -> List[BarCombination]:
    """
    Suggest bar combinations that meet or exceed the required area.
    Returns the most compact options first.
    """
    combinations = []

    for rebar in REBAR_SIZES:
        count = math.ceil(as_required_cm2 / rebar.area_cm2)
        total_area = count * rebar.area_cm2
        combinations.append(BarCombination(count, rebar, total_area))

    # Sort by total area (most compact first)
    combinations.sort(key=lambda x: x.total_area_cm2)

    return combinations[:max_suggestions]
