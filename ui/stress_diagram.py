"""Diagrama de esfuerzos para sección a flexión (ACI 318).

Muestra:
- Sección transversal (b × h)
- Bloque de Whitney (área de compresión a = β₁·c)
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

from core.flexion import FlexionDesignResult
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

        avail_h = H - 2 * margin - 50

        scale_h = avail_h
        h_mm = max(r.h_mm, 1.0)
        scale = scale_h / h_mm

        b_px = min(r.b_mm * scale, section_panel_w - 40)
        h_px = h_mm * scale

        sec_x = margin + (section_panel_w - b_px) / 2
        sec_y = margin + 10

        # 1) Sección de concreto
        self._draw_section(painter, sec_x, sec_y, b_px, h_px, scale, r)

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
            "Sección transversal  ←→  Diagrama de esfuerzos (Bloque de Whitney – ACI 318)"
        )

    def _draw_section(self, p: QPainter, x: float, y: float, b_px: float, h_px: float,
                       scale: float, r: FlexionDesignResult):
        # Concreto
        p.setPen(QPen(_qc(PALETTE.concrete_edge), 1.5))
        p.setBrush(QBrush(_qc(PALETTE.concrete)))
        p.drawRect(QRectF(x, y, b_px, h_px))

        # Bloque de Whitney (área de compresión)
        a_px = min(r.a_mm * scale, h_px)
        if a_px > 0:
            p.setPen(QPen(_qc(PALETTE.compression), 1.2))
            p.setBrush(QBrush(_qc(PALETTE.compression, 170)))
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

        # Acero de tensión: dibujar lechos reales según configuración
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
                # Espaciado: distribuir n barras dentro de b_px con recubrimiento
                cover_px = (self.result.cover_mm + r.reinforcement.stirrup_diameter_mm) * scale
                avail_w = b_px - 2 * cover_px - 2 * bar_radius
                if n > 1:
                    step = avail_w / (n - 1)
                    for i in range(n):
                        cx = x + cover_px + bar_radius + i * step
                        p.drawEllipse(QPointF(cx, layer_y_px), bar_radius, bar_radius)
                else:
                    cx = x + b_px / 2
                    p.drawEllipse(QPointF(cx, layer_y_px), bar_radius, bar_radius)
        else:
            # Fallback genérico
            d_px = r.d_mm * scale
            steel_y = y + d_px
            for i in range(4):
                cx = x + (i + 1) * (b_px / 5)
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

        # Cota del ancho b
        p.setPen(QPen(_qc(PALETTE.dim_lines), 1))
        p.setFont(QFont("Sans", 8))
        dim_y = y + h_px + 28
        p.drawLine(QPointF(x, dim_y), QPointF(x + b_px, dim_y))
        p.drawLine(QPointF(x, dim_y - 4), QPointF(x, dim_y + 4))
        p.drawLine(QPointF(x + b_px, dim_y - 4), QPointF(x + b_px, dim_y + 4))
        b_text = cv.format_length(r.b_mm, decimals=1) + " (b)"
        p.drawText(QRectF(x, dim_y + 4, b_px, 14),
                   int(Qt.AlignmentFlag.AlignCenter), b_text)

    def _draw_stress_blocks(self, p: QPainter, x: float, y: float, w: float,
                             h_px: float, scale: float, r: FlexionDesignResult):
        """Dibuja el diagrama de esfuerzos/fuerzas a la derecha."""
        ref_x = x + w * 0.45
        a_px = min(r.a_mm * scale, h_px)
        stress_block_w = w * 0.35

        # Bloque de compresión (esfuerzo uniforme 0.85·f'c)
        if a_px > 0:
            p.setPen(QPen(_qc(PALETTE.compression), 1.5))
            p.setBrush(QBrush(_qc(PALETTE.compression, 170)))
            block_rect = QRectF(ref_x - stress_block_w, y, stress_block_w, a_px)
            p.drawRect(block_rect)

            # Etiqueta 0.85·f'c
            p.setPen(_qc(PALETTE.text_primary))
            p.setFont(QFont("Sans", 8, QFont.Weight.Bold))
            p.drawText(
                QRectF(ref_x - stress_block_w, y - 14, stress_block_w, 12),
                int(Qt.AlignmentFlag.AlignCenter),
                "0.85·f'c"
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
