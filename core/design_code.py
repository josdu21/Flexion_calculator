"""Registro de normas de diseño y despacho al motor que corresponde.

La interfaz, la memoria y el archivo del estudio hablan con este módulo; nunca
instancian una clase de motor directamente. Agregar una norma nueva es agregar
una entrada en :data:`SPECS`.

Los paneles de entrada producen el conjunto **unión** de datos (el de AASHTO es
un superconjunto del de ACI), y cada despachador entrega a su motor sólo las
claves que ese motor declara. Las listas de claves están escritas a mano, no
deducidas por reflexión, para que se lean de un vistazo;
``tests/test_design_code.py`` verifica que coincidan con las firmas reales y
que ninguna clave se pierda en silencio.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Type

from core import flexion as aci_flexion
from core import shear as aci_shear
from core import torsion as aci_torsion
from core.aashto import flexion as aashto_flexion
from core.aashto import shear as aashto_shear
from core.aashto import torsion as aashto_torsion


class DesignCode(Enum):
    """Normas de diseño soportadas."""
    ACI_318_19 = "ACI 318-19"
    AASHTO_LRFD_2020 = "AASHTO LRFD 2020"


# Claves que acepta el constructor de cada motor.
_ACI_FLEX_KEYS = frozenset({
    "mu_nmm", "b_mm", "h_mm", "cover_mm", "fc_mpa", "fy_mpa",
    "reinforcement", "db_assumed_mm",
    "section_shape", "bf_mm", "hf_mm",
    "negative_moment", "statically_determinate",
})
# AASHTO no tiene el caso isostático de §9.6.1.2: su mínimo es por momento.
_AASHTO_FLEX_KEYS = (_ACI_FLEX_KEYS - {"statically_determinate"}) | {
    "bar_spec", "exposure_class", "ms_nmm", "lam",
}

_ACI_BEAM_SHEAR_KEYS = frozenset({
    "vu_n", "b_mm", "h_mm", "cover_mm", "fc_mpa", "fyt_mpa",
    "stirrup_diameter_mm", "stirrup_area_mm2", "stirrup_legs",
    "db_long_assumed_mm", "lam", "d_mm",
    "torsion_enabled", "tu_nmm", "fy_long_mpa", "torsion_type",
    "section_shape", "bf_mm", "hf_mm",
})
_AASHTO_BEAM_SHEAR_KEYS = _ACI_BEAM_SHEAR_KEYS | {
    "a_mm", "mu_nmm", "as_long_mm2", "negative_moment",
}

_ACI_SLAB_SHEAR_KEYS = frozenset({
    "vu_n", "b_mm", "h_mm", "cover_mm", "fc_mpa",
    "db_long_assumed_mm", "lam", "as_long_mm2",
})
_AASHTO_SLAB_SHEAR_KEYS = _ACI_SLAB_SHEAR_KEYS | {"a_mm"}


@dataclass(frozen=True)
class CodeSpec:
    """Todo lo que la aplicación necesita saber de una norma."""
    code: DesignCode
    label: str                  # rótulo corto: cajetín, combos
    full_name: str              # nombre completo, para el pie de la memoria
    tagline: str                # de qué trata, para la memoria

    flexure_cls: Type[Any]
    flexure_keys: FrozenSet[str]
    beam_shear_cls: Type[Any]
    beam_shear_keys: FrozenSet[str]
    slab_shear_cls: Type[Any]
    slab_shear_keys: FrozenSet[str]

    # Si la norma pide datos que las otras no usan, van acá para que la
    # interfaz sepa qué campos mostrar.
    extra_flexure_inputs: bool = False


SPECS: Dict[DesignCode, CodeSpec] = {
    DesignCode.ACI_318_19: CodeSpec(
        code=DesignCode.ACI_318_19,
        label="ACI 318-19",
        full_name="ACI 318-19 — Building Code Requirements for Structural Concrete",
        tagline="Diseño de refuerzo según ACI 318-19",
        flexure_cls=aci_flexion.BeamSection,
        flexure_keys=_ACI_FLEX_KEYS,
        beam_shear_cls=aci_torsion.BeamShearTorsionDesign,
        beam_shear_keys=_ACI_BEAM_SHEAR_KEYS,
        slab_shear_cls=aci_shear.SlabShearCheck,
        slab_shear_keys=_ACI_SLAB_SHEAR_KEYS,
        extra_flexure_inputs=False,
    ),
    DesignCode.AASHTO_LRFD_2020: CodeSpec(
        code=DesignCode.AASHTO_LRFD_2020,
        label="AASHTO LRFD 2020",
        full_name=(
            "AASHTO LRFD Bridge Design Specifications, 9.ª edición (2020)"
        ),
        tagline=(
            "Diseño de refuerzo según AASHTO LRFD 2020 "
            "(cortante por el procedimiento simplificado de §5.7.3.4.1)"
        ),
        flexure_cls=aashto_flexion.AashtoBeamSection,
        flexure_keys=_AASHTO_FLEX_KEYS,
        beam_shear_cls=aashto_torsion.AashtoBeamShearTorsionDesign,
        beam_shear_keys=_AASHTO_BEAM_SHEAR_KEYS,
        slab_shear_cls=aashto_shear.AashtoSlabShearCheck,
        slab_shear_keys=_AASHTO_SLAB_SHEAR_KEYS,
        extra_flexure_inputs=True,
    ),
}

DEFAULT_CODE = DesignCode.ACI_318_19


def spec(code: DesignCode) -> CodeSpec:
    """Ficha de la norma; cae a la de por defecto si llega algo desconocido."""
    return SPECS.get(code, SPECS[DEFAULT_CODE])


def _only(values: Dict[str, Any], keys: FrozenSet[str]) -> Dict[str, Any]:
    return {k: v for k, v in values.items() if k in keys}


def flexure_design(code: DesignCode, **values):
    """Diseña la sección a flexión con la norma pedida."""
    s = spec(code)
    return s.flexure_cls(**_only(values, s.flexure_keys)).design()


def beam_shear_design(code: DesignCode, **values):
    """Diseña la viga por cortante (y torsión, si está activa)."""
    s = spec(code)
    return s.beam_shear_cls(**_only(values, s.beam_shear_keys)).design()


def slab_shear_check(code: DesignCode, **values):
    """Revisa la losa por cortante."""
    s = spec(code)
    return s.slab_shear_cls(**_only(values, s.slab_shear_keys)).check()


def code_of(result: Any) -> DesignCode:
    """Deduce con qué norma se produjo un resultado.

    Los resultados AASHTO heredan de los de ACI, así que la pregunta se hace
    por el módulo donde está definida la clase y no con ``isinstance``, que
    daría verdadero para ambos.
    """
    modulo = type(result).__module__
    if modulo.startswith("core.aashto"):
        return DesignCode.AASHTO_LRFD_2020
    return DesignCode.ACI_318_19
