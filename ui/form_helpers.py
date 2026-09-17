"""Contenedores de lectura continua, detalles bajo demanda y carga de estado."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QScrollArea, QFrame, QPushButton, QVBoxLayout, QWidget,
    QBoxLayout, QLayout, QSizePolicy,
)


def set_si(spinbox, si_value, to_user_factor) -> None:
    """Escribe en el spinbox un valor guardado en SI, en la unidad del usuario.

    Los valores fuera del rango del control se recortan en vez de descartarse,
    para que abrir un estudio nunca falle silenciosamente.
    """
    if spinbox is None or si_value is None:
        return
    value = si_value / to_user_factor if to_user_factor else si_value
    spinbox.setValue(max(spinbox.minimum(), min(spinbox.maximum(), value)))


def set_choice(combo, data) -> None:
    """Selecciona en el combo el ítem cuyo userData coincide; si no está, no toca."""
    if combo is None or data is None:
        return
    index = combo.findData(data)
    if index >= 0:
        combo.setCurrentIndex(index)


def scroll_form(*groups) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(group_page(*groups))
    return scroll


class DetailsSection(QWidget):
    """Desplegable accesible por teclado que no desactiva sus controles."""

    def __init__(self, title, *groups, expanded=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.toggle = QPushButton()
        self.toggle.setObjectName("detailsToggle")
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(title)
        self.content = group_page(*groups)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self.content.setVisible)
        self.toggle.toggled.connect(
            lambda checked: self.toggle.setText(f"{'−' if checked else '+'}  {title}")
        )
        self.toggle.setChecked(expanded)
        self.content.setVisible(expanded)
        self.toggle.setText(f"{'−' if expanded else '+'}  {title}")


class ResponsiveColumns(QWidget):
    """Apila las tarjetas cuando el panel de resultados pierde anchura."""

    def __init__(self, *widgets):
        super().__init__()
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSpacing(8)
        self.columns.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for widget in widgets:
            self.columns.addWidget(widget, 1)

    def resizeEvent(self, event):
        self.columns.setDirection(
            QBoxLayout.Direction.TopToBottom if event.size().width() < 640
            else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)


def group_page(*groups) -> QWidget:
    """Página con los grupos apilados y alineados arriba."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(2, 10, 2, 4)
    layout.setSpacing(10)
    for group in groups:
        layout.addWidget(group)
    layout.addStretch()
    return page
