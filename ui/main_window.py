"""Ventana principal de la Calculadora de Acero (Flexión + Cortante)."""
import os
import tempfile
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QStatusBar, QFrame, QSplitter,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt

from core.units import UnitSystem
from core.flexion import BeamSection
from core.shear import BeamShearDesign, SlabShearCheck
from core.report import (
    generate_html_report,
    generate_shear_beam_html_report,
    generate_shear_slab_html_report,
)
from ui.input_panel import InputPanel
from ui.results_panel import ResultsPanel
from ui.shear_input_panel import BeamShearInputPanel, SlabShearInputPanel
from ui.shear_results_panel import ShearResultsPanel
from ui.theme import build_stylesheet


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_unit_system = UnitSystem.SI
        self._initializing = True
        self._init_ui()
        self.setWindowTitle(
            "Calculadora de Acero por Flexión y Cortante — ACI 318-19"
        )
        self.resize(1240, 800)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(build_stylesheet())

        # Primer cálculo
        self._initializing = False
        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self.calculate_beam_shear()
        self.calculate_slab_shear()

    # ------------------------------------------------------------
    #                      Construcción de UI
    # ------------------------------------------------------------

    def _init_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 8, 0, 8)
        header_layout.setSpacing(0)

        title = QLabel("🏗  Calculadora de Acero — Flexión y Cortante")
        title.setObjectName("headerTitle")
        header_layout.addWidget(title)

        subtitle = QLabel("Diseño de vigas y losas según ACI 318-19")
        subtitle.setObjectName("headerSubtitle")
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # Barra de control
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

        # Tabs principales (Viga / Losa) con sub-pestañas internas
        tabs_container = QWidget()
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(12, 0, 12, 12)

        self.tabs = QTabWidget()

        self.beam_tab = self._make_element_tab(is_slab=False)
        self.tabs.addTab(self.beam_tab, "🟦  Viga")

        self.slab_tab = self._make_element_tab(is_slab=True)
        self.tabs.addTab(self.slab_tab, "🟩  Losa (franja unitaria)")

        tabs_layout.addWidget(self.tabs)
        root.addWidget(tabs_container, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo. Modifica los datos para recalcular.")

        self.setCentralWidget(central)

    def _make_element_tab(self, is_slab: bool) -> QWidget:
        """Construye una pestaña 'Viga' o 'Losa' con sub-pestañas Flexión/Cortante."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(6)

        sub_tabs = QTabWidget()
        sub_tabs.addTab(self._make_flexion_subtab(is_slab), "Flexión")
        sub_tabs.addTab(self._make_shear_subtab(is_slab), "Cortante")
        layout.addWidget(sub_tabs)

        if is_slab:
            self.slab_subtabs = sub_tabs
        else:
            self.beam_subtabs = sub_tabs
        return tab

    def _make_flexion_subtab(self, is_slab: bool) -> QWidget:
        sub = QWidget()
        sub_layout = QHBoxLayout(sub)
        sub_layout.setContentsMargins(8, 8, 8, 8)
        sub_layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        inputs = InputPanel(self.current_unit_system, is_slab=is_slab)
        results = ResultsPanel(self.current_unit_system)

        if is_slab:
            self.slab_flex_inputs = inputs
            self.slab_flex_results = results
            inputs.values_changed.connect(self.calculate_slab_flex)
        else:
            self.beam_flex_inputs = inputs
            self.beam_flex_results = results
            inputs.values_changed.connect(self.calculate_beam_flex)

        self._wrap_in_splitter(splitter, inputs, results)
        sub_layout.addWidget(splitter)
        return sub

    def _make_shear_subtab(self, is_slab: bool) -> QWidget:
        sub = QWidget()
        sub_layout = QHBoxLayout(sub)
        sub_layout.setContentsMargins(8, 8, 8, 8)
        sub_layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        if is_slab:
            inputs = SlabShearInputPanel(self.current_unit_system)
            results = ShearResultsPanel(self.current_unit_system, is_slab=True)
            self.slab_shear_inputs = inputs
            self.slab_shear_results = results
            inputs.values_changed.connect(self.calculate_slab_shear)
        else:
            inputs = BeamShearInputPanel(self.current_unit_system)
            results = ShearResultsPanel(self.current_unit_system, is_slab=False)
            self.beam_shear_inputs = inputs
            self.beam_shear_results = results
            inputs.values_changed.connect(self.calculate_beam_shear)

        self._wrap_in_splitter(splitter, inputs, results)
        sub_layout.addWidget(splitter)
        return sub

    def _wrap_in_splitter(self, splitter, inputs, results):
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

    # ------------------------------------------------------------
    #                     Cambio de unidades
    # ------------------------------------------------------------

    def _on_unit_changed(self):
        self._initializing = True
        self.current_unit_system = self.unit_combo.currentData()
        try:
            for panel in (self.beam_flex_inputs, self.slab_flex_inputs,
                          self.beam_shear_inputs, self.slab_shear_inputs):
                panel.update_unit_system(self.current_unit_system)
            for panel in (self.beam_flex_results, self.slab_flex_results,
                          self.beam_shear_results, self.slab_shear_results):
                panel.update_unit_system(self.current_unit_system)
        finally:
            self._initializing = False
        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self.calculate_beam_shear()
        self.calculate_slab_shear()
        self.statusBar().showMessage(
            f"Sistema cambiado a: {self.current_unit_system.value}", 3000
        )

    # ------------------------------------------------------------
    #                       Cálculos
    # ------------------------------------------------------------

    def _active_context(self):
        """Devuelve (is_beam, is_flexion) según el tab activo."""
        is_beam = self.tabs.currentIndex() == 0
        subtabs = self.beam_subtabs if is_beam else self.slab_subtabs
        is_flexion = subtabs.currentIndex() == 0
        return is_beam, is_flexion

    def _calculate_current(self):
        is_beam, is_flexion = self._active_context()
        if is_beam and is_flexion:
            self.calculate_beam_flex()
        elif is_beam and not is_flexion:
            self.calculate_beam_shear()
        elif not is_beam and is_flexion:
            self.calculate_slab_flex()
        else:
            self.calculate_slab_shear()

    def calculate_beam_flex(self):
        if self._initializing:
            return
        try:
            values = self.beam_flex_inputs.get_values()
            result = BeamSection(**values).design()
            self.beam_flex_results.display_results(result)
            self.statusBar().showMessage(
                f"Viga (flexión) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.beam_flex_results.clear()
            self.statusBar().showMessage(f"Error en viga (flexión): {e}", 5000)

    def calculate_slab_flex(self):
        if self._initializing:
            return
        try:
            values = self.slab_flex_inputs.get_values()
            result = BeamSection(**values).design()
            self.slab_flex_results.display_results(result)
            self.statusBar().showMessage(
                f"Losa (flexión) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.slab_flex_results.clear()
            self.statusBar().showMessage(f"Error en losa (flexión): {e}", 5000)

    def calculate_beam_shear(self):
        if self._initializing:
            return
        try:
            values = self.beam_shear_inputs.get_values()
            result = BeamShearDesign(**values).design()
            self.beam_shear_results.display_results(result)
            self.statusBar().showMessage(
                f"Viga (cortante) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.beam_shear_results.clear()
            self.statusBar().showMessage(f"Error en viga (cortante): {e}", 5000)

    def calculate_slab_shear(self):
        if self._initializing:
            return
        try:
            values = self.slab_shear_inputs.get_values()
            result = SlabShearCheck(**values).check()
            self.slab_shear_results.display_results(result)
            self.statusBar().showMessage(
                f"Losa (cortante) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.slab_shear_results.clear()
            self.statusBar().showMessage(f"Error en losa (cortante): {e}", 5000)

    # ------------------------------------------------------------
    #                       Memoria HTML
    # ------------------------------------------------------------

    def _export_report(self):
        try:
            is_beam, is_flexion = self._active_context()

            if is_flexion:
                inputs = self.beam_flex_inputs if is_beam else self.slab_flex_inputs
                values = inputs.get_values()
                result = BeamSection(**values).design()
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
                file_prefix = "memoria_flexion_viga" if is_beam else "memoria_flexion_losa"
            else:
                if is_beam:
                    values = self.beam_shear_inputs.get_values()
                    result = BeamShearDesign(**values).design()
                    html = generate_shear_beam_html_report(
                        result=result,
                        unit_system=self.current_unit_system,
                        project_name="Proyecto",
                        element_name="Viga V-1",
                    )
                    file_prefix = "memoria_cortante_viga"
                else:
                    values = self.slab_shear_inputs.get_values()
                    result = SlabShearCheck(**values).check()
                    html = generate_shear_slab_html_report(
                        result=result,
                        unit_system=self.current_unit_system,
                        project_name="Proyecto",
                        element_name="Losa L-1",
                    )
                    file_prefix = "memoria_cortante_losa"

            default_name = f"{file_prefix}.html"
            home = os.path.expanduser("~")
            suggested_path = os.path.join(home, default_name)

            file_path, _ = QFileDialog.getSaveFileName(
                self, "Guardar memoria de cálculo",
                suggested_path,
                "HTML Files (*.html);;Todos los archivos (*)"
            )

            if not file_path:
                fd, file_path = tempfile.mkstemp(suffix=".html", prefix=f"{file_prefix}_")
                os.close(fd)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)

            webbrowser.open(f"file://{file_path}")
            self.statusBar().showMessage(
                f"Memoria guardada en: {file_path}", 6000
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Error al generar memoria",
                f"Ocurrió un error:\n\n{e}"
            )
