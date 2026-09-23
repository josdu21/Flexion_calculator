"""Piezas de la pantalla de inicio (diseño 1c de ``UI_Design``).

* :class:`ElementCard`: tarjeta de «Viga» o «Losa» con su ícono, descripción y
  el nombre del elemento editable en la misma tarjeta.
* :class:`SegmentedControl`: selector de opciones excluyentes (la normativa).
* :class:`RecentStudies`: registro de los últimos estudios abiertos o
  guardados, en la configuración del usuario y no en el estudio.
"""
import json
import os
from datetime import date, datetime
from typing import List

from PyQt6.QtCore import QPointF, QRectF, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from ui.theme import PALETTE


# ------------------------------------------------------------ ícono

class IconTile(QWidget):
    """Cuadro de 52 px con el croquis del elemento, en el acento."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind            # "viga" | "losa"
        self.setFixedSize(52, 52)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PALETTE.accent_tint))
        p.drawRoundedRect(QRectF(0, 0, 52, 52), 8, 8)

        pen = QPen(QColor(PALETTE.accent), 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "viga":
            # Sección T con dos barras abajo.
            path = QPainterPath(QPointF(13, 14))
            for x, y in ((39, 14), (39, 20), (30, 20), (30, 39),
                         (22, 39), (22, 20), (13, 20)):
                path.lineTo(x, y)
            path.closeSubpath()
            p.drawPath(path)
            p.setBrush(QColor(PALETTE.accent))
            p.drawEllipse(QPointF(24.5, 35), 1.3, 1.3)
            p.drawEllipse(QPointF(27.5, 35), 1.3, 1.3)
        else:
            # Franja de losa con la cota de 1 m y el armado.
            p.drawRoundedRect(QRectF(11, 22, 30, 10), 1.5, 1.5)
            p.drawLine(QPointF(17, 17), QPointF(35, 17))
            p.drawLine(QPointF(17, 15), QPointF(17, 19))
            p.drawLine(QPointF(35, 15), QPointF(35, 19))
            p.setBrush(QColor(PALETTE.accent))
            for x in (18, 26, 34):
                p.drawEllipse(QPointF(x, 29), 1.2, 1.2)


# ------------------------------------------------------------ tarjeta

class ElementCard(QFrame):
    """Tarjeta clicable que abre el espacio de trabajo de un elemento."""

    clicked = pyqtSignal()

    def __init__(self, kind: str, title: str, body: str, parent=None):
        super().__init__(parent)
        self.setObjectName("elementCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Diseñar {title}")

        fila = QHBoxLayout(self)
        fila.setContentsMargins(18, 16, 18, 16)
        fila.setSpacing(18)
        fila.addWidget(IconTile(kind))

        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel(title)
        titulo.setObjectName("cardTitle")
        cuerpo = QLabel(body)
        cuerpo.setObjectName("cardBody")
        cuerpo.setWordWrap(True)
        textos.addWidget(titulo)
        textos.addWidget(cuerpo)
        fila.addLayout(textos, 1)

        nombre = QVBoxLayout()
        nombre.setSpacing(4)
        rotulo = QLabel("Nombre")
        rotulo.setObjectName("fieldCaption")
        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(130)
        self.name_edit.setAccessibleName(f"Nombre de {title.lower()}")
        rotulo.setBuddy(self.name_edit)
        nombre.addWidget(rotulo)
        nombre.addWidget(self.name_edit)
        fila.addLayout(nombre)

    def click(self):
        self.clicked.emit()

    def mouseReleaseEvent(self, event):
        # Un clic en el campo de nombre edita el nombre; en el resto, abre.
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


# ------------------------------------------------------------ segmentado

class SegmentedControl(QFrame):
    """Opciones excluyentes una al lado de la otra (el ``.seg`` de Nocturne)."""

    changed = pyqtSignal(object)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        fila = QHBoxLayout(self)
        fila.setContentsMargins(2, 2, 2, 2)
        fila.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._data = {}
        for etiqueta, dato in options:
            boton = QPushButton(etiqueta)
            boton.setObjectName("segOption")
            boton.setCheckable(True)
            self._group.addButton(boton)
            self._data[boton] = dato
            fila.addWidget(boton, 1)
        self._group.buttonClicked.connect(
            lambda b: self.changed.emit(self._data[b]))

    def buttons(self):
        return list(self._data)

    def set_value(self, dato):
        for boton, valor in self._data.items():
            if valor == dato:
                boton.setChecked(True)

    def value(self):
        boton = self._group.checkedButton()
        return self._data.get(boton)


# ------------------------------------------------------------ recientes

_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")


def relative_date(iso: str, today: date = None) -> str:
    """«Hoy», «Ayer» o «18 sep», como en el diseño."""
    try:
        dia = datetime.fromisoformat(iso).date()
    except (TypeError, ValueError):
        return ""
    today = today or date.today()
    delta = (today - dia).days
    if delta == 0:
        return "Hoy"
    if delta == 1:
        return "Ayer"
    texto = f"{dia.day} {_MESES[dia.month - 1]}"
    return texto if dia.year == today.year else f"{texto} {dia.year}"


class RecentStudies:
    """Últimos estudios abiertos o guardados, en la configuración del usuario.

    Se guardan fuera del estudio porque son del puesto de trabajo, no del
    proyecto. La variable de entorno ``BEAMCALC_SETTINGS`` apunta a un ``.ini``
    alternativo; los tests la usan para no tocar la configuración real.
    """

    KEY = "estudios_recientes"
    MAX = 8

    def __init__(self, settings: QSettings = None):
        if settings is None:
            ruta = os.environ.get("BEAMCALC_SETTINGS")
            settings = (QSettings(ruta, QSettings.Format.IniFormat) if ruta
                        else QSettings("Beam Calculator", "Beam Calculator"))
        self.settings = settings

    def _raw(self) -> List[dict]:
        try:
            datos = json.loads(self.settings.value(self.KEY, "[]") or "[]")
        except (TypeError, ValueError):
            return []
        return [d for d in datos if isinstance(d, dict) and d.get("path")]

    def _write(self, entradas: List[dict]):
        self.settings.setValue(self.KEY, json.dumps(entradas, ensure_ascii=False))
        self.settings.sync()

    def entries(self) -> List[dict]:
        """Los que todavía existen en disco, del más reciente al más viejo."""
        return [d for d in self._raw() if os.path.isfile(d["path"])]

    def remember(self, path: str, study: str, element: str, code: str):
        clave = os.path.normcase(os.path.abspath(path))
        resto = [d for d in self._raw()
                 if os.path.normcase(os.path.abspath(d["path"])) != clave]
        nueva = {
            "path": os.path.abspath(path), "estudio": study,
            "elemento": element, "norma": code,
            "fecha": datetime.now().isoformat(timespec="seconds"),
        }
        self._write([nueva] + resto[: self.MAX - 1])

    def forget(self, path: str):
        clave = os.path.normcase(os.path.abspath(path))
        self._write([d for d in self._raw()
                     if os.path.normcase(os.path.abspath(d["path"])) != clave])
