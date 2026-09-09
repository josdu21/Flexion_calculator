"""Helpers compartidos para armar paneles con pestañas internas.

Los grupos se reparten en pestañas en lugar de apilarse en una sola columna,
de modo que cada panel muestre dos o tres grupos a la vez.
"""
from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


def make_panel_tabs() -> QTabWidget:
    """Pestañas internas de un panel (tercer nivel de navegación).

    Se estilizan aparte (``#panelTabs``) para que se lean como una subdivisión
    del panel y no compitan con las pestañas de Viga/Losa y Flexión/Cortante.
    """
    tabs = QTabWidget()
    tabs.setObjectName("panelTabs")
    tabs.setDocumentMode(True)
    return tabs


def tab_page(*groups) -> QWidget:
    """Página con los grupos apilados y alineados arriba."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(2, 10, 2, 4)
    layout.setSpacing(10)
    for group in groups:
        layout.addWidget(group)
    layout.addStretch()
    return page
