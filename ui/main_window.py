"""Ventana principal de Beam Calculator (Flexión + Cortante + Torsión)."""
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QStatusBar, QFrame, QSplitter,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QSignalBlocker

from core.version import APP_NAME, APP_TAGLINE, __version__
from core.units import UnitSystem
from core.design_code import (
    DEFAULT_CODE, DesignCode, beam_shear_design, flexure_design,
    slab_shear_check, spec,
)
from core.report import generate_beam_report, generate_slab_report
from core.project import (
    FILE_FILTER, ProjectInfo, Study, StudyFileError, load_study, save_study,
)
from ui.input_panel import InputPanel
from ui.project_dialog import ProjectDialog
from ui.results_panel import ResultsPanel
from ui.shear_input_panel import BeamShearInputPanel, SlabShearInputPanel
from ui.shear_results_panel import ShearResultsPanel
from ui.theme import build_stylesheet


APP_TITLE = f"{APP_NAME} {__version__} — Flexión, Cortante y Torsión"


def _slug(name: str) -> str:
    """Nombre de elemento convertido en un nombre de archivo seguro."""
    limpio = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return limpio.lower() or "elemento"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_unit_system = UnitSystem.SI
        self.current_code = DEFAULT_CODE
        self.project_info = ProjectInfo()
        self.current_path = None
        self._initializing = True
        self._init_ui()
        self._refresh_title()
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
        title = QLabel(APP_NAME)
        title.setObjectName("headerTitle")
        subtitle = QLabel(f"v{__version__}  /  {APP_TAGLINE}")
        subtitle.setObjectName("headerSubtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        header_layout.addLayout(identity)
        header_layout.addStretch()
        code_label = QLabel("Normativa")
        header_layout.addWidget(code_label)
        self.code_combo = QComboBox()
        for norma in DesignCode:
            self.code_combo.addItem(spec(norma).label, norma)
        self.code_combo.setCurrentIndex(self.code_combo.findData(DEFAULT_CODE))
        self.code_combo.setAccessibleName("Norma de diseño")
        self.code_combo.setToolTip(
            "Norma con la que se calculan los cuatro análisis y que se "
            "registra en la memoria"
        )
        code_label.setBuddy(self.code_combo)
        self.code_combo.currentIndexChanged.connect(self._on_code_changed)
        header_layout.addWidget(self.code_combo)

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
        self.project_button = QPushButton("Datos del proyecto")
        self.project_button.setToolTip(
            "Proyecto, diseñador, revisor, revisión y notas del cajetín (Ctrl+I)"
        )
        self.project_button.setShortcut("Ctrl+I")
        self.project_button.clicked.connect(self._edit_project_info)
        header_layout.addWidget(self.project_button)

        self.open_button = QPushButton("Abrir")
        self.open_button.setToolTip("Abrir un estudio guardado (Ctrl+O)")
        self.open_button.setShortcut("Ctrl+O")
        self.open_button.clicked.connect(self._open_study)
        header_layout.addWidget(self.open_button)

        self.save_button = QPushButton("Guardar")
        self.save_button.setToolTip("Guardar el estudio completo (Ctrl+S)")
        self.save_button.setShortcut("Ctrl+S")
        self.save_button.clicked.connect(self._save_study)
        header_layout.addWidget(self.save_button)

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

        inputs = InputPanel(self.current_unit_system, is_slab=is_slab,
                            design_code=self.current_code)
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
            inputs = SlabShearInputPanel(self.current_unit_system,
                                         design_code=self.current_code)
            results = ShearResultsPanel(self.current_unit_system, is_slab=True)
            self.slab_shear_inputs = inputs
            self.slab_shear_results = results
            inputs.values_changed.connect(self.calculate_slab_shear)
        else:
            inputs = BeamShearInputPanel(self.current_unit_system,
                                         design_code=self.current_code)
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
    #                      Cambio de normativa
    # ------------------------------------------------------------

    def _on_code_changed(self):
        self.current_code = self.code_combo.currentData()
        for panel in (self.beam_flex_inputs, self.slab_flex_inputs,
                      self.beam_shear_inputs, self.slab_shear_inputs):
            panel.set_design_code(self.current_code)
        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self.calculate_beam_shear()
        self.calculate_slab_shear()
        self._on_analysis_changed()
        self.statusBar().showMessage(
            f"Norma cambiada a: {spec(self.current_code).label}", 4000
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
        is_beam, _ = self._active_context()
        if is_beam:
            alcance = f"{self.project_info.beam_name} — flexión, cortante y torsión"
        else:
            alcance = f"{self.project_info.slab_name} — flexión y cortante"
        self.report_button.setToolTip(
            f"Exportar memoria: {alcance}, según "
            f"{spec(self.current_code).label} (Ctrl+E)"
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

    def _beam_flex_design(self):
        """Diseño a flexión de la viga, usado también por el análisis de cortante."""
        return flexure_design(
            self.current_code, **self.beam_flex_inputs.get_values()
        )

    def _slab_flex_design(self):
        """Diseño a flexión de la losa, usado también por el análisis de cortante."""
        return flexure_design(
            self.current_code, **self.slab_flex_inputs.get_values()
        )

    def _beam_shear_design(self):
        """Cortante/torsión de la viga alimentado por el diseño a flexión.

        AASHTO necesita además el bloque de compresión (para d_v) y el momento
        con el acero longitudinal (para la revisión de §5.7.3.5); todo eso sale
        del mismo diseño a flexión, así que no se le pide nada extra al usuario.
        """
        flexion = self._beam_flex_design()
        values = self.beam_shear_inputs.get_values()
        values["d_mm"] = flexion.d_mm
        values["a_mm"] = flexion.a_mm
        values["mu_nmm"] = flexion.mu_demand_knm * 1e6
        values["as_long_mm2"] = flexion.as_provided_cm2 * 100.0
        return beam_shear_design(self.current_code, **values)

    def _slab_shear_check(self):
        """Cortante de la losa alimentado por el diseño a flexión de la franja."""
        flexion = self._slab_flex_design()
        values = self.slab_shear_inputs.get_values()
        values["as_long_mm2"] = flexion.as_provided_cm2 * 100.0
        values["a_mm"] = flexion.a_mm
        return slab_shear_check(self.current_code, **values)

    def calculate_beam_flex(self):
        if self._initializing:
            return
        try:
            result = self._beam_flex_design()
            self.beam_flex_results.display_results(result)
            self._show_calculation_status(0,
                f"Viga (flexión) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.beam_flex_results.clear()
            self.statusBar().showMessage(f"Error en viga (flexión): {e}", 5000)
            return
        # El peralte efectivo alimenta el cortante: mantener ambos en sincronía.
        self.calculate_beam_shear()

    def calculate_slab_flex(self):
        if self._initializing:
            return
        try:
            result = self._slab_flex_design()
            self.slab_flex_results.display_results(result)
            self._show_calculation_status(2,
                f"Losa (flexión) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.slab_flex_results.clear()
            self.statusBar().showMessage(f"Error en losa (flexión): {e}", 5000)
            return
        # La cuantía longitudinal entra en Vc: mantener ambos en sincronía.
        self.calculate_slab_shear()

    def calculate_beam_shear(self):
        if self._initializing:
            return
        try:
            result = self._beam_shear_design()
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
            result = self._slab_shear_check()
            self.slab_shear_results.display_results(result)
            self._show_calculation_status(3,
                f"Losa (cortante) • Estado: {result.status}", 3000
            )
        except Exception as e:
            self.slab_shear_results.clear()
            self.statusBar().showMessage(f"Error en losa (cortante): {e}", 5000)

    # ------------------------------------------------------------
    #              Datos del proyecto y archivo del estudio
    # ------------------------------------------------------------

    def _panels(self):
        """Paneles de entrada, con la clave que los identifica en el archivo."""
        return {
            "viga_flexion": self.beam_flex_inputs,
            "viga_cortante": self.beam_shear_inputs,
            "losa_flexion": self.slab_flex_inputs,
            "losa_cortante": self.slab_shear_inputs,
        }

    def _refresh_title(self):
        nombre = os.path.basename(self.current_path) if self.current_path else None
        self.setWindowTitle(f"{nombre} — {APP_TITLE}" if nombre else APP_TITLE)

    def _edit_project_info(self):
        dialog = ProjectDialog(self.project_info, self)
        if dialog.exec():
            self.project_info = dialog.values()
            self._on_analysis_changed()
            self.statusBar().showMessage("Datos del proyecto actualizados", 3000)

    def _save_study(self):
        suggested = self.current_path or os.path.join(
            os.path.expanduser("~"), "estudio.json"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar estudio", suggested, FILE_FILTER
        )
        if not file_path:
            return
        try:
            save_study(file_path, Study(
                info=self.project_info,
                unit_system=self.current_unit_system,
                panels={k: p.get_state() for k, p in self._panels().items()},
                code=self.current_code,
            ))
        except OSError as e:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar:\n\n{e}")
            return
        self.current_path = file_path
        self._refresh_title()
        self.statusBar().showMessage(f"Estudio guardado en: {file_path}", 6000)

    def _open_study(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir estudio", os.path.expanduser("~"), FILE_FILTER
        )
        if not file_path:
            return
        try:
            study = load_study(file_path)
        except (StudyFileError, OSError) as e:
            QMessageBox.critical(self, "Error al abrir", f"No se pudo abrir:\n\n{e}")
            return

        self.project_info = study.info
        # Cambiar de unidades reconstruye los campos, así que va antes de cargarlos.
        if study.unit_system != self.current_unit_system:
            self.unit_combo.setCurrentIndex(
                self.unit_combo.findData(study.unit_system)
            )
        # La norma decide qué campos se muestran: también va antes de cargar.
        if study.code != self.current_code:
            self.code_combo.setCurrentIndex(self.code_combo.findData(study.code))

        self._initializing = True
        try:
            for key, panel in self._panels().items():
                if key in study.panels:
                    panel.set_state(study.panels[key])
        finally:
            self._initializing = False

        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self.current_path = file_path
        self._refresh_title()
        self._on_analysis_changed()
        self.statusBar().showMessage(f"Estudio abierto: {file_path}", 6000)

    # ------------------------------------------------------------
    #                       Memoria HTML
    # ------------------------------------------------------------

    def _export_report(self):
        try:
            is_beam, _ = self._active_context()

            # Una sola memoria por elemento: la viga cubre flexión, cortante y
            # torsión; la losa cubre flexión y cortante.
            if is_beam:
                html = generate_beam_report(
                    flexion=self._beam_flex_design(),
                    shear=self._beam_shear_design(),
                    unit_system=self.current_unit_system,
                    info=self.project_info,
                )
                nombre = self.project_info.beam_name
            else:
                html = generate_slab_report(
                    flexion=self._slab_flex_design(),
                    shear=self._slab_shear_check(),
                    unit_system=self.current_unit_system,
                    info=self.project_info,
                )
                nombre = self.project_info.slab_name

            default_name = f"memoria_{_slug(nombre)}.html"
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
