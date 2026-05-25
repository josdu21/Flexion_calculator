"""Ventana principal de la Calculadora de Acero por Flexión."""
import os
import tempfile
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QStatusBar, QFrame, QSplitter,
    QApplication, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

from core.units import UnitSystem
from core.flexion import BeamSection
from core.report import generate_html_report
from ui.input_panel import InputPanel
from ui.results_panel import ResultsPanel
from ui.theme import build_stylesheet


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_unit_system = UnitSystem.SI
        self._initializing = True
        self._init_ui()
        self.setWindowTitle("Calculadora de Acero por Flexión — ACI 318-19")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(build_stylesheet())

        # Ejecutar primer cálculo
        self._initializing = False
        self.calculate_beam()
        self.calculate_slab()

    def _init_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 8, 0, 8)
        header_layout.setSpacing(0)

        title = QLabel("🏗  Calculadora de Acero por Flexión")
        title.setObjectName("headerTitle")
        header_layout.addWidget(title)

        subtitle = QLabel("Diseño de vigas y losas según ACI 318-19")
        subtitle.setObjectName("headerSubtitle")
        header_layout.addWidget(subtitle)

        root.addWidget(header)

        # --- Barra de control ---
        control_bar = QFrame()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(16, 10, 16, 10)

        control_layout.addWidget(QLabel("Sistema de unidades:"))
        self.unit_combo = QComboBox()
        for system in UnitSystem:
            self.unit_combo.addItem(system.value, system)
        self.unit_combo.setCurrentText(UnitSystem.SI.value)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        self.unit_combo.setMinimumWidth(200)
        control_layout.addWidget(self.unit_combo)

        control_layout.addStretch()

        self.calc_button = QPushButton("⚙  Recalcular")
        self.calc_button.setObjectName("calcButton")
        self.calc_button.clicked.connect(self._calculate_current)
        control_layout.addWidget(self.calc_button)

        self.report_button = QPushButton("📄  Memoria de cálculo")
        self.report_button.clicked.connect(self._export_report)
        control_layout.addWidget(self.report_button)

        root.addWidget(control_bar)

        # --- Tabs ---
        tabs_container = QWidget()
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(12, 0, 12, 12)

        self.tabs = QTabWidget()

        # Tab Viga
        self.beam_tab = self._make_tab(is_slab=False)
        self.tabs.addTab(self.beam_tab, "🟦  Viga")

        # Tab Losa
        self.slab_tab = self._make_tab(is_slab=True)
        self.tabs.addTab(self.slab_tab, "🟩  Losa (franja unitaria)")

        tabs_layout.addWidget(self.tabs)
        root.addWidget(tabs_container, 1)

        # Barra de estado
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo. Modifica los datos para recalcular.")

        self.setCentralWidget(central)

    def _make_tab(self, is_slab: bool) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        inputs = InputPanel(self.current_unit_system, is_slab=is_slab)
        results = ResultsPanel(self.current_unit_system)

        # Conectar el cambio de inputs al recálculo (después de InputPanel creado)
        if is_slab:
            self.slab_inputs = inputs
            self.slab_results = results
            inputs.values_changed.connect(self.calculate_slab)
        else:
            self.beam_inputs = inputs
            self.beam_results = results
            inputs.values_changed.connect(self.calculate_beam)

        # Envolver en widgets para el splitter
        input_container = QWidget()
        input_container.setMinimumWidth(320)
        input_container.setMaximumWidth(420)
        ic_layout = QVBoxLayout(input_container)
        ic_layout.setContentsMargins(0, 0, 0, 0)
        ic_layout.addWidget(inputs)

        results_container = QWidget()
        rc_layout = QVBoxLayout(results_container)
        rc_layout.setContentsMargins(0, 0, 0, 0)
        rc_layout.addWidget(results)

        splitter.addWidget(input_container)
        splitter.addWidget(results_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 880])

        layout.addWidget(splitter)
        return tab

    def _on_unit_changed(self):
        """Cambia el sistema de unidades en ambos paneles."""
        self._initializing = True
        self.current_unit_system = self.unit_combo.currentData()
        try:
            self.beam_inputs.update_unit_system(self.current_unit_system)
            self.slab_inputs.update_unit_system(self.current_unit_system)
            self.beam_results.update_unit_system(self.current_unit_system)
            self.slab_results.update_unit_system(self.current_unit_system)
        finally:
            self._initializing = False
        # Recalcular ambos
        self.calculate_beam()
        self.calculate_slab()
        self.statusBar().showMessage(
            f"Sistema cambiado a: {self.current_unit_system.value}", 3000
        )

    def _calculate_current(self):
        """Recalcula el tab activo."""
        if self.tabs.currentIndex() == 0:
            self.calculate_beam()
        else:
            self.calculate_slab()

    def calculate_beam(self):
        if self._initializing:
            return
        try:
            values = self.beam_inputs.get_values()
            section = BeamSection(**values)
            result = section.design()
            self.beam_results.display_results(result)
            self.statusBar().showMessage(
                f"Viga calculada • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.beam_results.clear()
            self.statusBar().showMessage(f"Error en viga: {e}", 5000)

    def calculate_slab(self):
        if self._initializing:
            return
        try:
            values = self.slab_inputs.get_values()
            section = BeamSection(**values)
            result = section.design()
            self.slab_results.display_results(result)
            self.statusBar().showMessage(
                f"Losa calculada • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.slab_results.clear()
            self.statusBar().showMessage(f"Error en losa: {e}", 5000)

    def _export_report(self):
        """Genera la memoria de cálculo HTML del tab activo."""
        try:
            is_beam = self.tabs.currentIndex() == 0
            inputs = self.beam_inputs if is_beam else self.slab_inputs
            values = inputs.get_values()
            section = BeamSection(**values)
            result = section.design()

            section_type = "Viga" if is_beam else "Losa (franja unitaria)"
            element_name = "Viga V-1" if is_beam else "Losa L-1"

            html = generate_html_report(
                result=result,
                inputs_user=values,
                unit_system=self.current_unit_system,
                section_type=section_type,
                project_name="Proyecto",
                element_name=element_name,
            )

            # Sugerir nombre de archivo
            default_name = f"memoria_{section_type.split()[0].lower()}.html"
            home = os.path.expanduser("~")
            suggested_path = os.path.join(home, default_name)

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Guardar memoria de cálculo",
                suggested_path,
                "HTML Files (*.html);;Todos los archivos (*)"
            )

            if not file_path:
                # Cancelado: guardar en tmp y abrir
                fd, file_path = tempfile.mkstemp(suffix=".html", prefix="memoria_")
                os.close(fd)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)

            # Abrir en navegador
            webbrowser.open(f"file://{file_path}")

            self.statusBar().showMessage(
                f"Memoria guardada en: {file_path}", 6000
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error al generar memoria",
                f"Ocurrió un error:\n\n{e}"
            )
