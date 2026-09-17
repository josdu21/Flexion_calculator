"""Estudio guardable: metadatos del cajetín + estado de los cuatro análisis.

El archivo es JSON y almacena las magnitudes en unidades internas SI
(N·mm, mm, MPa), de modo que un estudio guardado en un sistema de unidades
se pueda abrir en cualquier otro sin perder precisión.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict

from core.design_code import DEFAULT_CODE, DesignCode
from core.units import UnitSystem


FILE_FORMAT = "calculadora-acero"
# v1 → v2: se agregó la norma de diseño. Un archivo v1 se lee como ACI 318-19,
# que era la única norma que existía cuando se escribió.
FILE_VERSION = 2
FILE_FILTER = "Estudio de acero (*.json);;Todos los archivos (*)"


@dataclass
class ProjectInfo:
    """Datos del cajetín de la memoria."""
    project: str = "Proyecto sin título"
    designer: str = ""
    reviewer: str = ""
    revision: str = ""
    notes: str = ""
    beam_name: str = "Viga V-1"
    slab_name: str = "Losa L-1"


@dataclass
class Study:
    """Sesión completa: metadatos, norma, unidades y estado de cada panel."""
    info: ProjectInfo = field(default_factory=ProjectInfo)
    unit_system: UnitSystem = UnitSystem.SI
    panels: Dict[str, dict] = field(default_factory=dict)
    code: DesignCode = DEFAULT_CODE


class StudyFileError(Exception):
    """El archivo no es un estudio válido de la calculadora."""


def save_study(path, study: Study) -> None:
    payload = {
        "formato": FILE_FORMAT,
        "version": FILE_VERSION,
        "unidades": study.unit_system.name,
        "norma": study.code.name,
        "cajetin": asdict(study.info),
        "paneles": study.panels,
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_study(path) -> Study:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StudyFileError(f"El archivo no es JSON válido: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("formato") != FILE_FORMAT:
        raise StudyFileError(
            "El archivo no es un estudio de Beam Calculator."
        )
    if payload.get("version", 0) > FILE_VERSION:
        raise StudyFileError(
            f"El archivo fue creado con una versión más nueva "
            f"(v{payload['version']}); esta instalación lee hasta v{FILE_VERSION}."
        )

    try:
        unit_system = UnitSystem[payload.get("unidades", "SI")]
    except KeyError:
        unit_system = UnitSystem.SI

    # Los archivos v1 no traen norma: son de cuando sólo existía ACI 318-19.
    try:
        code = DesignCode[payload.get("norma", DEFAULT_CODE.name)]
    except KeyError:
        code = DEFAULT_CODE

    cajetin = payload.get("cajetin") or {}
    conocidos = {f for f in ProjectInfo.__dataclass_fields__}
    info = ProjectInfo(**{k: v for k, v in cajetin.items() if k in conocidos})

    return Study(
        info=info,
        unit_system=unit_system,
        panels=payload.get("paneles") or {},
        code=code,
    )
