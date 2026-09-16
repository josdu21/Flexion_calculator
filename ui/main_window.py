"""Ventana principal de la Calculadora de Acero (Flexión + Cortante + Torsión)."""
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QStatusBar, QFrame, QSplitter,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QSignalBlocker

from core.units import UnitSystem
from core.flexion import BeamSection
from core.shear import SlabShearCheck
from core.torsion import BeamShearTorsionDesign
from core.report import (
    generate_html_report,
    generate_shear_torsion_beam_html_report,
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
            "Calculadora de Acero por Flexión, Cortante y Torsión — ACI 318-19"
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
        self._on_analysis_changed()

    # ------------------------------------------------------------
    #                      Construcción de UI
    # ------------------------------------------------------------

    def _init_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Una sola barra para identidad, unidades y exportación.
        header = QFrame()
        header.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)
        identity = QVBoxLayout()
        title = QLabel("Calculadora de acero")
        title.setObjectName("headerTitle")
        subtitle = QLabel("ACI 318-19  /  Diseño de refuerzo")
        subtitle.setObjectName("headerSubtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        header_layout.addLayout(identity)
        header_layout.addStretch()
        unit_label = QLabel("Unidades")
        header_layout.addWidget(unit_label)
        self.unit_combo = QComboBox()
        for system in UnitSystem:
            self.unit_combo.addItem(system.value, system)
        self.unit_combo.setCurrentText(UnitSystem.SI.value)
        self.unit_combo.setAccessibleName("Sistema de unidades")
        unit_label.setBuddy(self.unit_combo)
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)
        header_layout.addWidget(self.unit_combo)
        self.report_button = QPushButton("Exportar memoria")
        self.report_button.setToolTip("Guardar la memoria HTML del análisis activo (Ctrl+E)")
        self.report_button.setShortcut("Ctrl+E")
        self.report_button.clicked.connect(self._export_report)
        header_layout.addWidget(self.report_button)
        root.addWidget(header)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(20, 16, 20, 12)
        workspace_layout.setSpacing(12)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("analysisTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._make_flexion_view(False), "Viga · Flexión")
        self.tabs.addTab(self._make_shear_view(False), "Viga · Cortante / torsión")
        self.tabs.addTab(self._make_flexion_view(True), "Losa · Flexión")
        self.tabs.addTab(self._make_shear_view(True), "Losa · Cortante")
        self.tabs.currentChanged.connect(self._on_analysis_changed)
        workspace_layout.addWidget(self.tabs)
        root.addWidget(workspace, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().addPermanentWidget(QLabel("Actualización automática  ·  "))
        self.statusBar().showMessage("Modifica los datos para explorar el diseño.")
        self._connect_shared_sections()
        self._on_analysis_changed()

        self.setCentralWidget(central)

    def _make_flexion_view(self, is_slab: bool) -> QWidget:
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

    def _make_shear_view(self, is_slab: bool) -> QWidget:
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
        input_container.setMinimumWidth(350)
        input_container.setMaximumWidth(460)
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
        splitter.setSizes([390, 810])

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
        self._connect_shared_sections()
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
        """Contexto de las cuatro vistas de análisis, en orden de navegación."""
        return ((True, True), (True, False), (False, True), (False, False))[
            self.tabs.currentIndex()
        ]

    def _on_analysis_changed(self):
        self.report_button.setToolTip(
            f"Exportar memoria: {self.tabs.tabText(self.tabs.currentIndex())} (Ctrl+E)"
        )
        self.statusBar().showMessage(self.tabs.tabText(self.tabs.currentIndex()))

    def _connect_shared_sections(self):
        """Una edición de sección se aplica a ambos análisis del elemento."""
        for flex, shear, flex_calc, shear_calc in (
            (self.beam_flex_inputs, self.beam_shear_inputs,
             self.calculate_beam_flex, self.calculate_beam_shear),
            (self.slab_flex_inputs, self.slab_shear_inputs,
             self.calculate_slab_flex, self.calculate_slab_shear),
        ):
            for name in ("b_spinbox", "h_spinbox", "cover_spinbox", "fc_spinbox"):
                left, right = getattr(flex, name, None), getattr(shear, name, None)
                if left is None or right is None:
                    continue
                with QSignalBlocker(right):
                    right.setValue(left.value())
                left.valueChanged.connect(
                    lambda value, target=right, calc=shear_calc:
                    self._set_shared_value(target, value, calc)
                )
                right.valueChanged.connect(
                    lambda value, target=left, calc=flex_calc:
                    self._set_shared_value(target, value, calc)
                )

    def _set_shared_value(self, target, value, calculate):
        with QSignalBlocker(target):
            target.setValue(value)
        calculate()

    def _show_calculation_status(self, index, message, timeout):
        if self.tabs.currentIndex() == index:
            self.statusBar().showMessage(message, timeout)

    def calculate_beam_flex(self):
        if self._initializing:
            return
        try:
            values = self.beam_flex_inputs.get_values()
            result = BeamSection(**values).design()
            self.beam_flex_results.display_results(result)
            self._show_calculation_status(0,
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
            self._show_calculation_status(2,
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
            result = BeamShearTorsionDesign(**values).design()
            self.beam_shear_results.display_results(result)
            label = "cortante + torsión" if result.torsion_active else "cortante"
            self._show_calculation_status(1,
                f"Viga ({label}) • Estado: {result.status}", 3000
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
            self._show_calculation_status(3,
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
                    result = BeamShearTorsionDesign(**values).design()
                    html = generate_shear_torsion_beam_html_report(
                        result=result,
                        unit_system=self.current_unit_system,
                        project_name="Proyecto",
                        element_name="Viga V-1",
                    )
                    file_prefix = (
                        "memoria_cortante_torsion_viga" if result.torsion_active
                        else "memoria_cortante_viga"
                    )
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
                return

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
