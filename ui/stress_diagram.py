"""Diagrama de esfuerzos para sección a flexión.

Sirve a las dos normas: el bloque rectangular equivalente tiene la misma forma
en ACI 318-19 y en AASHTO LRFD, y sólo cambia el esfuerzo uniforme (0.85·f'c en
ACI; α₁·f'c en AASHTO, que baja por encima de 70 MPa).

Dibuja la forma real de la sección: rectangular, T o L. Con ala, el bloque de
compresión se dibuja sobre el ancho que realmente comprime —el ala mientras
quepa en ella, y ala más alma cuando el eje neutro baja al alma—, que es lo
que distingue a una T de una rectangular a simple vista.

Muestra:
- Sección transversal (b × h, o b_f/b_w × h con ala)
- Bloque de compresión (área a = β₁·c)
- Eje neutro
- Acero de tensión (As)
- Vectores de fuerza: C (compresión) y T (tensión)
- Cotas de d, a, jd y magnitudes de C, T

Todos los colores se derivan del tema activo (Omarchy).
"""
import math
from typing import Optional
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPolygonF
)

from core.design_code import code_of, spec
from core.flexion import FlexionDesignResult
from core.section_geometry import SectionProfile, SectionShape
from core.units import UnitSystem, get_converter
from ui.theme import PALETTE


def _qc(hex_str: str, alpha: int = 255) -> QColor:
    """Helper para convertir hex a QColor con alpha opcional."""
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


class StressDiagramWidget(QWidget):
    """Widget que dibuja la sección y el diagrama de esfuerzos lado a lado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: Optional[FlexionDesignResult] = None
        self.unit_system: UnitSystem = UnitSystem.SI
        self.setMinimumSize(420, 280)
        self.setStyleSheet(
            f"background-color: {PALETTE.bg_input}; "
            f"border: 1px solid {PALETTE.border}; "
            f"border-radius: 6px;"
        )

    def set_result(self, result: FlexionDesignResult, unit_system: UnitSystem):
        self.result = result
        self.unit_system = unit_system
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(560, 340)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fondo según el tema
        painter.fillRect(self.rect(), _qc(PALETTE.bg_input))

        if self.result is None or self.result.status == "ERROR":
            self._draw_placeholder(painter)
            return

        self._draw_diagram(painter)

    def _draw_placeholder(self, painter: QPainter):
        painter.setPen(QPen(_qc(PALETTE.text_muted), 1))
        painter.setFont(QFont("Sans", 11))
        painter.drawText(
            self.rect(),
            int(Qt.AlignmentFlag.AlignCenter),
            "Ingresa los datos para ver\nel diagrama de esfuerzos"
        )

    def _draw_diagram(self, painter: QPainter):
        r = self.result
        W = self.width()
        H = self.height()

        margin = 30
        gap_between = 60

        available_w = W - 2 * margin - gap_between
        section_panel_w = available_w * 0.42
        stress_panel_w = available_w * 0.58

        # Debajo de la sección van, en este orden: la etiqueta de A_s, la
        # cota del ancho con su rótulo y el pie del dibujo. Reservarles poco
        # hacía que la cota se montara sobre el pie en secciones altas.
        avail_h = H - 2 * margin - 80

        h_mm = max(r.h_mm, 1.0)
        perfil = SectionProfile.create(
            shape=getattr(r, "section_shape", SectionShape.RECTANGULAR),
            bw_mm=r.b_mm, h_mm=r.h_mm,
            bf_mm=getattr(r, "bf_mm", 0.0), hf_mm=getattr(r, "hf_mm", 0.0),
        )
        # Un ala ancha no cabe a la escala del peralte: se toma la escala que
        # deja entrar la sección completa, para que el dibujo siga siendo
        # proporcional en vez de recortado.
        ancho_mm = max(perfil.bf_mm, perfil.bw_mm, 1.0)
        scale = min(avail_h / h_mm, (section_panel_w - 40) / ancho_mm)

        b_px = ancho_mm * scale
        h_px = h_mm * scale

        sec_x = margin + (section_panel_w - b_px) / 2
        sec_y = margin + 10

        # 1) Sección de concreto
        self._draw_section(painter, sec_x, sec_y, b_px, h_px, scale, r, perfil)

        # 2) Diagrama de esfuerzos
        diag_x = margin + section_panel_w + gap_between
        diag_y = sec_y
        diag_w = stress_panel_w
        self._draw_stress_blocks(painter, diag_x, diag_y, diag_w, h_px, scale, r)

        # 3) Título inferior
        painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        painter.setPen(_qc(PALETTE.text_secondary))
        painter.drawText(
            QRectF(0, H - 35, W, 25),
            int(Qt.AlignmentFlag.AlignCenter),
            "Sección transversal  ←→  Diagrama de esfuerzos "
            f"(bloque rectangular equivalente – {spec(code_of(self.result)).label})"
        )

    def _draw_section(self, p: QPainter, x: float, y: float, b_px: float, h_px: float,
                       scale: float, r: FlexionDesignResult,
                       perfil: SectionProfile):
        """Dibuja la sección de concreto, el bloque comprimido y el armado.

        ``x`` es el borde izquierdo del contorno más ancho (el ala si la hay) y
        ``b_px`` su ancho. El alma se ubica adentro: centrada en la T, pegada a
        la izquierda en la L.
        """
        bw_px = perfil.bw_mm * scale
        hf_px = perfil.hf_mm * scale
        # Dónde arranca el alma dentro del contorno del ala.
        if perfil.shape is SectionShape.T:
            web_x = x + (b_px - bw_px) / 2.0
        else:
            # Rectangular (b_px == bw_px) y L, con el ala volando a la derecha.
            web_x = x

        # Concreto
        p.setPen(QPen(_qc(PALETTE.concrete_edge), 1.5))
        p.setBrush(QBrush(_qc(PALETTE.concrete)))
        if perfil.is_flanged:
            p.drawPolygon(self._section_outline(x, y, b_px, h_px, bw_px,
                                                hf_px, web_x))
        else:
            p.drawRect(QRectF(x, y, b_px, h_px))

        # Bloque de Whitney: mientras cabe en el ala ocupa todo su ancho; si el
        # eje neutro baja al alma, el sobrante se dibuja sólo sobre el alma.
        a_px = min(r.a_mm * scale, h_px)
        if a_px > 0:
            p.setPen(QPen(_qc(PALETTE.compression), 1.2))
            p.setBrush(QBrush(_qc(PALETTE.compression, 170)))
            if perfil.is_flanged and a_px > hf_px:
                p.drawRect(QRectF(x, y, b_px, hf_px))
                p.drawRect(QRectF(web_x, y + hf_px, bw_px, a_px - hf_px))
            else:
                p.drawRect(QRectF(x, y, b_px, a_px))

        # Eje neutro
        c_px = min(r.c_mm * scale, h_px)
        if c_px > 0 and c_px < h_px:
            pen = QPen(_qc(PALETTE.neutral_axis), 1.8, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(x - 8, y + c_px), QPointF(x + b_px + 8, y + c_px))

            p.setPen(_qc(PALETTE.neutral_axis))
            p.setFont(QFont("Sans", 8, QFont.Weight.Bold))
            p.drawText(QPointF(x + b_px + 10, y + c_px + 3), "E.N.")

        # Acero de tensión: dibujar lechos reales según configuración.
        # Las barras van en el alma, no en el ala.
        cv = get_converter(self.unit_system)
        p.setPen(QPen(_qc(PALETTE.steel), 1.5))
        p.setBrush(QBrush(_qc(PALETTE.steel)))

        if r.reinforcement and r.reinforcement.layers and r.layer_y_positions_mm:
            for layer, y_from_bottom in zip(
                    r.reinforcement.layers, r.layer_y_positions_mm):
                # Convertir y desde la fibra inferior a coordenada del dibujo
                # (origen arriba: layer_y = y + (h - y_from_bottom)*scale)
                layer_y_px = y + (r.h_mm - y_from_bottom) * scale
                n = layer.n_bars
                # Radio visual proporcional al db
                bar_radius = max(3, min(10, layer.bar_diameter_mm * scale * 0.5))
                # Espaciado: distribuir n barras dentro del alma con recubrimiento
                cover_px = (self.result.cover_mm + r.reinforcement.stirrup_diameter_mm) * scale
                avail_w = bw_px - 2 * cover_px - 2 * bar_radius
                if n > 1:
                    step = avail_w / (n - 1)
                    for i in range(n):
                        cx = web_x + cover_px + bar_radius + i * step
                        p.drawEllipse(QPointF(cx, layer_y_px), bar_radius, bar_radius)
                else:
                    cx = web_x + bw_px / 2
                    p.drawEllipse(QPointF(cx, layer_y_px), bar_radius, bar_radius)
        else:
            # Fallback genérico
            d_px = r.d_mm * scale
            steel_y = y + d_px
            for i in range(4):
                cx = web_x + (i + 1) * (bw_px / 5)
                p.drawEllipse(QPointF(cx, steel_y), 5, 5)

        # Etiqueta As
        p.setPen(_qc(PALETTE.text_primary))
        p.setFont(QFont("Sans", 8))
        as_str = cv.format_area(r.as_provided_cm2)
        bars_label = ""
        if r.reinforcement and r.reinforcement.layers:
            parts = []
            for layer in r.reinforcement.layers:
                # Buscar el #de barra correspondiente al db
                db = layer.bar_diameter_mm
                from core.bar_tables import REBAR_SIZES
                num = next((rb.number for rb in REBAR_SIZES
                            if abs(rb.diameter_mm - db) < 0.1), "?")
                parts.append(f"{layer.n_bars}#{num}")
            bars_label = " (" + " + ".join(parts) + ")"
        p.drawText(QPointF(x, y + h_px + 14), f"As = {as_str}{bars_label}")

        # Cota lateral del peralte h
        self._draw_vertical_dim(
            p, x - 25, y, y + h_px,
            cv.format_length(r.h_mm, decimals=1) + "  (h)"
        )

        # Cota del ancho: con ala se acotan los dos, b_f arriba y b_w abajo.
        p.setPen(QPen(_qc(PALETTE.dim_lines), 1))
        p.setFont(QFont("Sans", 8))
        if perfil.is_flanged:
            self._draw_width_dim(p, x, b_px, y - 12,
                                 cv.format_length(perfil.bf_mm, decimals=1) + " (b_f)",
                                 texto_arriba=True)
            self._draw_width_dim(p, web_x, bw_px, y + h_px + 28,
                                 cv.format_length(perfil.bw_mm, decimals=1) + " (b_w)")
        else:
            self._draw_width_dim(p, x, b_px, y + h_px + 28,
                                 cv.format_length(r.b_mm, decimals=1) + " (b)")

    @staticmethod
    def _section_outline(x: float, y: float, b_px: float, h_px: float,
                          bw_px: float, hf_px: float,
                          web_x: float) -> QPolygonF:
        """Contorno de la sección con ala, recorrido en sentido horario."""
        return QPolygonF([
            QPointF(x, y),                            # esquina superior izquierda del ala
            QPointF(x + b_px, y),                     # superior derecha del ala
            QPointF(x + b_px, y + hf_px),             # baja por el borde del ala
            QPointF(web_x + bw_px, y + hf_px),        # entra hacia el alma
            QPointF(web_x + bw_px, y + h_px),         # baja por el alma
            QPointF(web_x, y + h_px),                 # fondo del alma
            QPointF(web_x, y + hf_px),                # sube por el alma
            QPointF(x, y + hf_px),                    # vuelve al borde del ala
        ])

    def _draw_width_dim(self, p: QPainter, x: float, ancho_px: float,
                         dim_y: float, texto: str, texto_arriba: bool = False):
        """Cota horizontal con sus dos marcas de extremo y el rótulo."""
        p.setPen(QPen(_qc(PALETTE.dim_lines), 1))
        p.drawLine(QPointF(x, dim_y), QPointF(x + ancho_px, dim_y))
        p.drawLine(QPointF(x, dim_y - 4), QPointF(x, dim_y + 4))
        p.drawLine(QPointF(x + ancho_px, dim_y - 4), QPointF(x + ancho_px, dim_y + 4))
        caja_y = dim_y - 18 if texto_arriba else dim_y + 4
        # Un alma angosta deja una caja más corta que el rótulo: se centra en
        # la cota pero se le da ancho propio para que no se recorte.
        ancho_texto = max(ancho_px, 120.0)
        p.drawText(QRectF(x + (ancho_px - ancho_texto) / 2.0, caja_y,
                          ancho_texto, 14),
                   int(Qt.AlignmentFlag.AlignCenter), texto)

    def _draw_stress_blocks(self, p: QPainter, x: float, y: float, w: float,
                             h_px: float, scale: float, r: FlexionDesignResult):
        """Dibuja el diagrama de esfuerzos/fuerzas a la derecha."""
        ref_x = x + w * 0.45
        a_px = min(r.a_mm * scale, h_px)
        stress_block_w = w * 0.35

        # Bloque de compresión (esfuerzo uniforme α₁·f'c)
        if a_px > 0:
            p.setPen(QPen(_qc(PALETTE.compression), 1.5))
            p.setBrush(QBrush(_qc(PALETTE.compression, 170)))
            block_rect = QRectF(ref_x - stress_block_w, y, stress_block_w, a_px)
            p.drawRect(block_rect)

            # ACI usa siempre 0.85; AASHTO lo reduce por encima de 70 MPa.
            alpha_1 = getattr(r, "alpha_1", 0.85)
            p.setPen(_qc(PALETTE.text_primary))
            p.setFont(QFont("Sans", 8, QFont.Weight.Bold))
            p.drawText(
                QRectF(ref_x - stress_block_w, y - 14, stress_block_w, 12),
                int(Qt.AlignmentFlag.AlignCenter),
                f"{alpha_1:.2f}·f'c"
            )

            # Vector de compresión C
            arrow_y = y + a_px / 2
            arrow_start_x = ref_x - stress_block_w / 2
            arrow_end_x = ref_x - stress_block_w - 30
            self._draw_arrow(p, arrow_start_x, arrow_y, arrow_end_x, arrow_y,
                              _qc(PALETTE.compression), thickness=2.5)

            p.setPen(_qc(PALETTE.compression))
            p.setFont(QFont("Sans", 9, QFont.Weight.Bold))
            p.drawText(QPointF(arrow_end_x - 95, arrow_y - 4), "C")
            p.drawText(QPointF(arrow_end_x - 95, arrow_y + 10),
                       f"{r.compression_kn:.1f} kN")

        # Eje neutro (verde discontinuo)
        c_px = min(r.c_mm * scale, h_px)
        if c_px > 0 and c_px < h_px:
            pen = QPen(_qc(PALETTE.neutral_axis), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(ref_x - stress_block_w - 5, y + c_px),
                       QPointF(ref_x + 40, y + c_px))

        # Línea de la sección lateral
        p.setPen(QPen(_qc(PALETTE.concrete_edge), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(ref_x, y), QPointF(ref_x, y + h_px))

        # Acero a profundidad del centroide d (esquemático)
        d_px = r.d_mm * scale
        steel_y = y + d_px
        p.setPen(QPen(_qc(PALETTE.steel), 1.5))
        p.setBrush(QBrush(_qc(PALETTE.steel)))
        # Dibujar marcador con 2 círculos esquemáticos en el centroide
        bar_r = 5
        p.drawEllipse(QPointF(ref_x - 8, steel_y), bar_r, bar_r)
        p.drawEllipse(QPointF(ref_x + 8, steel_y), bar_r, bar_r)

        # Vector de tensión T
        arrow_start_x = ref_x + 20
        arrow_end_x = ref_x + 100
        self._draw_arrow(p, arrow_start_x, steel_y, arrow_end_x, steel_y,
                          _qc(PALETTE.tension), thickness=2.5)

        p.setPen(_qc(PALETTE.tension))
        p.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        p.drawText(QPointF(arrow_end_x + 5, steel_y - 4), "T")
        p.drawText(QPointF(arrow_end_x + 5, steel_y + 10),
                   f"{r.tension_kn:.1f} kN")

        # Cota del brazo de palanca jd
        cv = get_converter(self.unit_system)
        if r.a_mm > 0:
            jd_label_x = ref_x + 38
            c_centroid_y = y + a_px / 2
            t_centroid_y = steel_y
            p.setPen(QPen(_qc(PALETTE.dim_lines), 1))
            p.drawLine(QPointF(ref_x, c_centroid_y), QPointF(jd_label_x, c_centroid_y))
            p.drawLine(QPointF(ref_x + 18, t_centroid_y), QPointF(jd_label_x, t_centroid_y))
            p.drawLine(QPointF(jd_label_x, c_centroid_y), QPointF(jd_label_x, t_centroid_y))
            p.drawLine(QPointF(jd_label_x - 4, c_centroid_y),
                       QPointF(jd_label_x + 4, c_centroid_y))
            p.drawLine(QPointF(jd_label_x - 4, t_centroid_y),
                       QPointF(jd_label_x + 4, t_centroid_y))

            mid_y = (c_centroid_y + t_centroid_y) / 2
            p.setPen(_qc(PALETTE.text_primary))
            p.setFont(QFont("Sans", 8))
            jd_text = "jd = " + cv.format_length(r.jd_mm, decimals=1)
            p.drawText(QPointF(jd_label_x + 8, mid_y), jd_text)

        # Datos inferiores
        info_y = y + h_px + 14
        p.setPen(_qc(PALETTE.text_primary))
        p.setFont(QFont("Sans", 8))
        a_text = "a = " + cv.format_length(r.a_mm, decimals=1)
        c_text = "c = " + cv.format_length(r.c_mm, decimals=1)
        p.drawText(QPointF(x + 5, info_y), a_text + "    " + c_text)

    def _draw_arrow(self, p: QPainter, x1: float, y1: float, x2: float, y2: float,
                     color: QColor, thickness: float = 2.0):
        """Dibuja una flecha (x1,y1) -> (x2,y2)."""
        pen = QPen(color, thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        angle = math.atan2(y2 - y1, x2 - x1)
        head_len = 10
        a1 = angle + math.pi - 0.5
        a2 = angle + math.pi + 0.5
        p.setBrush(QBrush(color))
        head = QPolygonF([
            QPointF(x2, y2),
            QPointF(x2 + head_len * math.cos(a1), y2 + head_len * math.sin(a1)),
            QPointF(x2 + head_len * math.cos(a2), y2 + head_len * math.sin(a2)),
        ])
        p.drawPolygon(head)

    def _draw_vertical_dim(self, p: QPainter, x: float, y1: float, y2: float, label: str):
        """Dibuja una cota vertical con etiqueta."""
        p.setPen(QPen(_qc(PALETTE.dim_lines), 1))
        p.setFont(QFont("Sans", 8))
        p.drawLine(QPointF(x, y1), QPointF(x, y2))
        p.drawLine(QPointF(x - 4, y1), QPointF(x + 4, y1))
        p.drawLine(QPointF(x - 4, y2), QPointF(x + 4, y2))
        mid_y = (y1 + y2) / 2
        p.save()
        p.translate(x - 6, mid_y)
        p.rotate(-90)
        p.setPen(_qc(PALETTE.text_primary))
        p.drawText(QRectF(-40, -10, 80, 12),
                   int(Qt.AlignmentFlag.AlignCenter), label)
        p.restore()
