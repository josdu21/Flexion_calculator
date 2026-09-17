"""Sube la versión en los dos lugares que la declaran y prepara el CHANGELOG.

    python packaging/bump_version.py 2.1.0

Toca `core/version.py` (la que lee la app) y `packaging/version.txt` (la que
leen el build y el instalador, que no ejecutan Python), y agrega el encabezado
de la nueva versión al CHANGELOG. No commitea ni etiqueta: imprime los comandos
para que los revises antes.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VERSION_PY = RAIZ / "core" / "version.py"
VERSION_TXT = RAIZ / "packaging" / "version.txt"
CHANGELOG = RAIZ / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def version_actual() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"',
                  VERSION_PY.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"No encontré __version__ en {VERSION_PY}")
    return m.group(1)


def como_tupla(v: str):
    return tuple(int(p) for p in v.split("."))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Uso: python {Path(__file__).name} <x.y.z>")

    nueva = sys.argv[1].lstrip("v")
    if not SEMVER.match(nueva):
        raise SystemExit(f"'{nueva}' no es una versión semántica x.y.z")

    actual = version_actual()
    if como_tupla(nueva) <= como_tupla(actual):
        raise SystemExit(
            f"La versión {nueva} no es posterior a la actual ({actual})."
        )

    VERSION_PY.write_text(
        re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{nueva}"',
               VERSION_PY.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    VERSION_TXT.write_text(f"{nueva}\n", encoding="utf-8")

    texto = CHANGELOG.read_text(encoding="utf-8")
    marca = f"## [{actual}]"
    if marca in texto:
        texto = texto.replace(
            marca,
            f"## [{nueva}]\n\n### Agregado\n\n- \n\n### Cambiado\n\n- \n\n"
            f"### Corregido\n\n- \n\n{marca}",
            1,
        )
        CHANGELOG.write_text(texto, encoding="utf-8")

    print(f"{actual} -> {nueva}")
    print(f"  {VERSION_PY.relative_to(RAIZ)}")
    print(f"  {VERSION_TXT.relative_to(RAIZ)}")
    print(f"  {CHANGELOG.relative_to(RAIZ)} (completá la entrada nueva)")
    print()
    print("Después de revisar y completar el CHANGELOG:")
    print(f"  git commit -am \"chore: versión {nueva}\"")
    print(f"  git tag v{nueva}")
    print(f"  git push && git push --tags")


if __name__ == "__main__":
    main()
