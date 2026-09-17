"""Genera assets/icon.ico a partir de la paleta de la aplicación.

El ícono dibuja la sección transversal de una viga con el bloque de compresión
y el acero de tensión, que es la figura que la app misma usa en su diagrama de
esfuerzos. Sólo hace falta volver a correrlo si se cambia el diseño:

    python packaging/make_icon.py

Requiere Pillow (está en requirements-dev.txt).
"""
from pathlib import Path

from PIL import Image, ImageDraw

# Paleta tomada de ui/theme.py
FONDO = "#7cbeb5"        # accent (teal)
SECCION = "#111820"      # background oscuro
COMPRESION = "#f7768e"   # rojo
ACERO = "#e6e6e6"        # claro

# Se dibuja grande y se reduce: los bordes quedan suaves sin antialias manual.
LIENZO = 1024
TAMANOS = (256, 128, 64, 48, 32, 16)


def dibujar(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = size / 1024.0

    # Fondo redondeado
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(180 * u), fill=FONDO
    )

    # Sección de la viga
    x0, y0, x1, y1 = 300 * u, 190 * u, 724 * u, 834 * u
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(24 * u), fill=SECCION)

    # Bloque de compresión (arriba)
    margen = 54 * u
    d.rounded_rectangle(
        [x0 + margen, y0 + margen, x1 - margen, y0 + margen + 150 * u],
        radius=int(16 * u), fill=COMPRESION,
    )

    # Acero de tensión (abajo): 3 barras, o 2 en los tamaños diminutos
    radio = 46 * u
    centro_y = y1 - margen - radio
    posiciones = (
        [x0 + margen + radio, (x0 + x1) / 2, x1 - margen - radio]
        if size >= 32 else
        [x0 + margen + radio * 1.2, x1 - margen - radio * 1.2]
    )
    for cx in posiciones:
        d.ellipse(
            [cx - radio, centro_y - radio, cx + radio, centro_y + radio],
            fill=ACERO,
        )
    return img


def main() -> None:
    destino = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    destino.parent.mkdir(exist_ok=True)

    maestro = dibujar(LIENZO)
    capas = [
        (maestro if n == LIENZO else dibujar(LIENZO)).resize(
            (n, n), Image.LANCZOS
        ) if n >= 32 else dibujar(n)
        for n in TAMANOS
    ]
    capas[0].save(destino, format="ICO",
                  sizes=[(n, n) for n in TAMANOS])
    print(f"generado {destino} ({destino.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
