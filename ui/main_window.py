"""Ventana principal de Beam Calculator.

Dos pantallas:

* **Inicio**: datos del proyecto, norma y unidades, y la elección del elemento
  a diseñar (viga o losa en una dirección).
* **Espacio de trabajo** del elemento elegido, con una pestaña por tarea:
  Geometría, Flexión y Cortante (y torsión en viga). La geometría se define una
  sola vez y la leen los análisis, así que ningún formulario obliga a
  desplazarse entre datos que no le corresponden.
"""
import os
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QPushButton, QLabel, QComboBox, QStatusBar, QFrame, QSplitter,
    QFileDialog, QMessageBox, QStackedWidget, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy,
)
from PyQt6.QtGui import QColor
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
from ui.geometry_panel import SHAPE_TAG, GeometryPanel
from ui.home_widgets import (
    ElementCard, RecentStudies, SegmentedControl, relative_date,
)
from ui.input_panel import InputPanel
from ui.results_panel import ResultsPanel
from ui.shear_input_panel import BeamShearInputPanel, SlabShearInputPanel
from ui.shear_results_panel import ShearResultsPanel
from ui.theme import PALETTE, build_stylesheet


APP_TITLE = f"{APP_NAME} {__version__} — Flexión, Cortante y Torsión"

PAGE_HOME, PAGE_WORKSPACE = 0, 1
TAB_GEOMETRY, TAB_FLEXURE, TAB_SHEAR = 0, 1, 2

# Los cuatro análisis, en el orden que usan select_analysis() y la barra de
# estado: (es_viga, es_flexión).
ANALYSES = ((True, True), (True, False), (False, True), (False, False))


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
        self.recent_studies = RecentStudies()
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
        self.pages = QStackedWidget()
        self.pages.addWidget(self._make_home())
        self.pages.addWidget(self._make_workspace())
        self.setCentralWidget(self.pages)

        self.setStatusBar(QStatusBar())
        self.statusBar().addPermanentWidget(QLabel(
            f'<span style="color:{PALETTE.accent}">●</span>&nbsp; '
            'Actualización automática&nbsp;&nbsp;'))
        self.statusBar().showMessage("Elegí el elemento a diseñar.")

    # ---- Inicio (diseño 1c) ----

    def _make_home(self) -> QWidget:
        """Proyecto en un panel lateral; a la derecha, qué diseñar y recientes."""
        pagina = QWidget()
        fila = QHBoxLayout(pagina)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)
        fila.addWidget(self._make_home_aside())
        fila.addWidget(self._make_home_main(), 1)
        return pagina

    def _field(self, caption: str, widget: QWidget) -> QWidget:
        """Rótulo arriba y campo abajo (el ``.field`` de Nocturne)."""
        caja = QWidget()
        caja.setObjectName("fieldBox")
        v = QVBoxLayout(caja)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        rotulo = QLabel(caption)
        rotulo.setObjectName("fieldCaption")
        rotulo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        rotulo.setBuddy(widget)
        v.addWidget(rotulo)
        v.addWidget(widget)
        return caja

    def _make_home_aside(self) -> QWidget:
        aside = QFrame()
        aside.setObjectName("homeAside")
        aside.setFixedWidth(320)
        col = QVBoxLayout(aside)
        col.setContentsMargins(22, 22, 22, 22)
        col.setSpacing(14)

        marca = QVBoxLayout()
        marca.setSpacing(2)
        titulo = QLabel(APP_NAME)
        titulo.setObjectName("brandTitle")
        version = QLabel(f"v{__version__} · Diseño de refuerzo")
        version.setObjectName("brandVersion")
        marca.addWidget(titulo)
        marca.addWidget(version)
        col.addLayout(marca)
        col.addSpacing(8)

        kicker = QLabel("INFORMACIÓN DEL PROYECTO")
        kicker.setObjectName("kicker")
        col.addWidget(kicker)

        self.project_edit = QLineEdit()
        self.designer_edit = QLineEdit()
        self.reviewer_edit = QLineEdit()
        self.revision_edit = QLineEdit()
        self.revision_edit.setPlaceholderText("Rev. A")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "Observaciones que aparecerán al pie del cajetín de la memoria."
        )
        self.notes_edit.setMinimumHeight(70)
        self.notes_edit.setMaximumHeight(96)

        self.unit_combo = QComboBox()
        for system in UnitSystem:
            self.unit_combo.addItem(system.value, system)
        self.unit_combo.setCurrentText(UnitSystem.SI.value)
        self.unit_combo.setAccessibleName("Sistema de unidades")
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)

        col.addWidget(self._field("Proyecto", self.project_edit))
        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(14)
        grilla.addWidget(self._field("Diseñador", self.designer_edit), 0, 0)
        grilla.addWidget(self._field("Revisor", self.reviewer_edit), 0, 1)
        grilla.addWidget(self._field("Revisión", self.revision_edit), 1, 0)
        grilla.addWidget(self._field("Unidades", self.unit_combo), 1, 1)
        col.addLayout(grilla)

        # La normativa se elige con un segmentado; el combo sigue existiendo
        # (oculto) como modelo único, así el resto del código no cambia.
        self.code_combo = QComboBox(aside)
        for norma in DesignCode:
            self.code_combo.addItem(spec(norma).label, norma)
        self.code_combo.setCurrentIndex(self.code_combo.findData(DEFAULT_CODE))
        self.code_combo.setAccessibleName("Norma de diseño")
        self.code_combo.hide()
        self.code_selector = SegmentedControl(
            [("ACI 318-19", DesignCode.ACI_318_19),
             ("AASHTO 2020", DesignCode.AASHTO_LRFD_2020)])
        self.code_selector.setToolTip(
            "Norma con la que se calculan todos los análisis y que se "
            "registra en la memoria"
        )
        self.code_selector.set_value(DEFAULT_CODE)
        self.code_selector.changed.connect(
            lambda norma: self.code_combo.setCurrentIndex(
                self.code_combo.findData(norma)))
        self.code_combo.currentIndexChanged.connect(self._on_code_changed)
        col.addWidget(self._field("Normativa", self.code_selector))

        col.addWidget(self._field("Notas", self.notes_edit))
        col.addStretch()

        botones = QHBoxLayout()
        botones.setSpacing(8)
        self.open_button = QPushButton("Abrir estudio")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.setToolTip("Abrir un estudio guardado (Ctrl+O)")
        self.open_button.setShortcut("Ctrl+O")
        self.open_button.clicked.connect(self._open_study)
        self.home_save_button = QPushButton("Guardar estudio")
        self.home_save_button.clicked.connect(self._save_study)
        botones.addWidget(self.open_button, 1)
        botones.addWidget(self.home_save_button, 1)
        col.addLayout(botones)
        return aside

    def _make_home_main(self) -> QWidget:
        principal = QWidget()
        col = QVBoxLayout(principal)
        col.setContentsMargins(40, 30, 40, 24)
        col.setSpacing(22)

        pregunta = QLabel("¿Qué vas a diseñar?")
        pregunta.setObjectName("homeHeading")
        col.addWidget(pregunta)

        tarjetas = QVBoxLayout()
        tarjetas.setSpacing(10)
        self.beam_card = ElementCard(
            "viga", "Viga",
            "Flexión, cortante y torsión. Secciones rectangular, T y L; "
            "momento positivo o negativo.")
        self.slab_card = ElementCard(
            "losa", "Losa en una dirección",
            "Flexión y cortante por franja de 1 m de ancho.")
        self.beam_name_edit = self.beam_card.name_edit
        self.slab_name_edit = self.slab_card.name_edit
        self.beam_card.clicked.connect(lambda: self.open_element(True))
        self.slab_card.clicked.connect(lambda: self.open_element(False))
        for tarjeta in (self.beam_card, self.slab_card):
            tarjeta.setMaximumWidth(640)
            tarjetas.addWidget(tarjeta)
        col.addLayout(tarjetas)

        col.addSpacing(10)
        recientes = QLabel("Estudios recientes")
        recientes.setObjectName("sectionHeading")
        col.addWidget(recientes)
        self.recent_table = QTableWidget(0, 4)
        self.recent_table.setObjectName("recentTable")
        self.recent_table.setHorizontalHeaderLabels(
            ["ESTUDIO", "ELEMENTO", "NORMATIVA", "MODIFICADO"])
        self.recent_table.setMaximumWidth(640)
        self.recent_table.verticalHeader().hide()
        self.recent_table.setShowGrid(False)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.recent_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.recent_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.recent_table.setToolTip("Doble clic o Enter para abrir")
        cabecera = self.recent_table.horizontalHeader()
        cabecera.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            cabecera.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_table.itemActivated.connect(self._on_recent_activated)
        col.addWidget(self.recent_table, 1)
        self.recent_empty = QLabel(
            "Todavía no hay estudios. Los que abras o guardes aparecen acá.")
        self.recent_empty.setObjectName("emptyNote")
        col.addWidget(self.recent_empty)
        col.addStretch()

        self._fill_project_fields()
        for campo in (self.project_edit, self.designer_edit, self.reviewer_edit,
                      self.revision_edit, self.beam_name_edit, self.slab_name_edit):
            campo.textChanged.connect(self._on_project_edited)
        self.notes_edit.textChanged.connect(self._on_project_edited)
        self._refresh_recent()
        return principal

    # ---- estudios recientes ----

    def _refresh_recent(self):
        entradas = self.recent_studies.entries()
        tabla = self.recent_table
        tabla.setRowCount(len(entradas))
        for fila, e in enumerate(entradas):
            valores = (e.get("estudio", ""), e.get("elemento", ""),
                       e.get("norma", ""), relative_date(e.get("fecha")))
            for col, texto in enumerate(valores):
                celda = QTableWidgetItem(texto)
                celda.setData(Qt.ItemDataRole.UserRole, e["path"])
                celda.setToolTip(e["path"])
                if col == 3:
                    celda.setForeground(QColor(PALETTE.text_muted))
                tabla.setItem(fila, col, celda)
        tabla.setVisible(bool(entradas))
        self.recent_empty.setVisible(not entradas)

    def _element_summary(self) -> str:
        """Elemento que se registra en la lista de recientes."""
        is_beam, _ = self._active_context()
        if not is_beam and self.pages.currentIndex() == PAGE_WORKSPACE:
            return self.project_info.slab_name
        corto = {"RECTANGULAR": "Rect.", "T": "T", "L": "L"}[
            self.beam_geometry.section_shape().name]
        return f"{self.project_info.beam_name} · {corto}"

    def _remember_recent(self, path: str):
        self.recent_studies.remember(
            path, self.project_info.project, self._element_summary(),
            spec(self.current_code).label)
        self._refresh_recent()

    def _on_recent_activated(self, item):
        ruta = item.data(Qt.ItemDataRole.UserRole)
        if ruta:
            self.open_study_file(ruta)

    # ---- Espacio de trabajo ----

    def _make_workspace(self) -> QWidget:
        pagina = QWidget()
        raiz = QVBoxLayout(pagina)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        barra = QFrame()
        barra.setObjectName("headerFrame")
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(20, 12, 20, 12)
        self.home_button = QPushButton("←")
        self.home_button.setObjectName("iconButton")
        self.home_button.setAccessibleName("Volver al inicio")
        self.home_button.setToolTip("Volver a la pantalla de inicio (Alt+Inicio)")
        self.home_button.setShortcut("Alt+Home")
        self.home_button.clicked.connect(self.go_home)
        bl.addWidget(self.home_button)
        identidad = QVBoxLayout()
        identidad.setSpacing(2)
        titulo = QHBoxLayout()
        titulo.setSpacing(10)
        self.element_title = QLabel()
        self.element_title.setObjectName("headerTitle")
        # Etiqueta con la forma de la sección (o «Franja de 1 m» en losa).
        self.shape_tag = QLabel()
        self.shape_tag.setObjectName("tag")
        titulo.addWidget(self.element_title)
        titulo.addWidget(self.shape_tag, 0, Qt.AlignmentFlag.AlignVCenter)
        titulo.addStretch()
        self.context_label = QLabel()
        self.context_label.setObjectName("headerSubtitle")
        identidad.addLayout(titulo)
        identidad.addWidget(self.context_label)
        bl.addSpacing(12)
        bl.addLayout(identidad)
        bl.addStretch()

        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("secondaryButton")
        self.save_button.setToolTip("Guardar el estudio completo (Ctrl+S)")
        self.save_button.setShortcut("Ctrl+S")
        self.save_button.clicked.connect(self._save_study)
        bl.addWidget(self.save_button)
        self.report_button = QPushButton("Exportar memoria")
        self.report_button.setShortcut("Ctrl+E")
        self.report_button.clicked.connect(self._export_report)
        bl.addWidget(self.report_button)
        raiz.addWidget(barra)

        cuerpo = QWidget()
        cl = QVBoxLayout(cuerpo)
        cl.setContentsMargins(20, 12, 20, 12)
        self.element_stack = QStackedWidget()
        self.beam_tabs = self._make_element_tabs(is_slab=False)
        self.slab_tabs = self._make_element_tabs(is_slab=True)
        self.element_stack.addWidget(self.beam_tabs)
        self.element_stack.addWidget(self.slab_tabs)
        cl.addWidget(self.element_stack)
        raiz.addWidget(cuerpo, 1)
        return pagina

    def _make_element_tabs(self, is_slab: bool) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("analysisTabs")
        tabs.setDocumentMode(True)

        geometry = GeometryPanel(self.current_unit_system, is_slab=is_slab)
        flex_in = InputPanel(self.current_unit_system, is_slab=is_slab,
                             design_code=self.current_code, geometry=geometry)
        flex_out = ResultsPanel(self.current_unit_system)
        if is_slab:
            shear_in = SlabShearInputPanel(self.current_unit_system,
                                           design_code=self.current_code,
                                           geometry=geometry)
        else:
            shear_in = BeamShearInputPanel(self.current_unit_system,
                                           design_code=self.current_code,
                                           geometry=geometry)
        shear_out = ShearResultsPanel(self.current_unit_system, is_slab=is_slab)

        if is_slab:
            self.slab_geometry = geometry
            self.slab_flex_inputs, self.slab_flex_results = flex_in, flex_out
            self.slab_shear_inputs, self.slab_shear_results = shear_in, shear_out
            flex_calc, shear_calc = self.calculate_slab_flex, self.calculate_slab_shear
        else:
            self.beam_geometry = geometry
            self.beam_flex_inputs, self.beam_flex_results = flex_in, flex_out
            self.beam_shear_inputs, self.beam_shear_results = shear_in, shear_out
            flex_calc, shear_calc = self.calculate_beam_flex, self.calculate_beam_shear

        # La geometría alimenta a los dos análisis; la flexión ya recalcula el
        # cortante porque éste toma de ella d, a y el acero longitudinal.
        geometry.values_changed.connect(flex_calc)
        geometry.shape_changed.connect(self._on_analysis_changed)
        geometry.continue_requested.connect(
            lambda: tabs.setCurrentIndex(TAB_FLEXURE))
        flex_in.values_changed.connect(flex_calc)
        shear_in.values_changed.connect(shear_calc)

        # Pestañas numeradas: el orden es el del trabajo.
        tabs.addTab(geometry, "①  Geometría y sección" if not is_slab
                    else "①  Geometría")
        tabs.addTab(self._split(flex_in, flex_out), "②  Flexión")
        tabs.addTab(self._split(shear_in, shear_out),
                    "③  Cortante / torsión" if not is_slab else "③  Cortante")
        tabs.currentChanged.connect(self._on_analysis_changed)
        return tabs

    def _split(self, inputs, results) -> QWidget:
        sub = QWidget()
        layout = QHBoxLayout(sub)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        izquierda = QWidget()
        izquierda.setMinimumWidth(350)
        izquierda.setMaximumWidth(460)
        il = QVBoxLayout(izquierda)
        il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(inputs)

        derecha = QWidget()
        dl = QVBoxLayout(derecha)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(results)

        splitter.addWidget(izquierda)
        splitter.addWidget(derecha)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 810])
        layout.addWidget(splitter)
        return sub

    # ------------------------------------------------------------
    #                        Navegación
    # ------------------------------------------------------------

    def open_element(self, is_beam: bool):
        """Abre el espacio de trabajo de la viga o de la losa."""
        self.element_stack.setCurrentWidget(
            self.beam_tabs if is_beam else self.slab_tabs)
        self.pages.setCurrentIndex(PAGE_WORKSPACE)
        self._on_analysis_changed()

    def go_home(self):
        self.pages.setCurrentIndex(PAGE_HOME)
        self.statusBar().showMessage("Elegí el elemento a diseñar.")

    def select_analysis(self, index: int):
        """Muestra uno de los cuatro análisis (orden de :data:`ANALYSES`)."""
        is_beam, is_flex = ANALYSES[index]
        self.open_element(is_beam)
        tabs = self.beam_tabs if is_beam else self.slab_tabs
        tabs.setCurrentIndex(TAB_FLEXURE if is_flex else TAB_SHEAR)

    def current_tab_widget(self) -> QWidget:
        tabs = self.element_stack.currentWidget()
        return tabs.currentWidget()

    def _active_context(self):
        """(es_viga, es_flexión) del espacio de trabajo visible."""
        tabs = self.element_stack.currentWidget()
        return tabs is self.beam_tabs, tabs.currentIndex() != TAB_SHEAR

    def _on_analysis_changed(self):
        is_beam, _ = self._active_context()
        nombre = self.project_info.beam_name if is_beam else self.project_info.slab_name
        tipo = "Viga" if is_beam else "Losa en una dirección"
        self.element_title.setText(nombre)
        self.shape_tag.setText(
            SHAPE_TAG[self.beam_geometry.section_shape()] if is_beam
            else "Franja de 1 m")
        self.context_label.setText(
            f"{tipo}  ·  {self.project_info.project}  ·  "
            f"{spec(self.current_code).label}"
            f"  ·  {self.current_unit_system.value}"
        )
        alcance = (f"{nombre} — flexión, cortante y torsión" if is_beam
                   else f"{nombre} — flexión y cortante")
        self.report_button.setToolTip(
            f"Exportar memoria: {alcance}, según "
            f"{spec(self.current_code).label} (Ctrl+E)"
        )
        if self.pages.currentIndex() == PAGE_WORKSPACE:
            tabs = self.element_stack.currentWidget()
            self.statusBar().showMessage(
                f"{tipo} · {tabs.tabText(tabs.currentIndex())}")

    # ------------------------------------------------------------
    #                     Datos del proyecto
    # ------------------------------------------------------------

    def _fill_project_fields(self):
        info = self.project_info
        campos = ((self.project_edit, info.project),
                  (self.designer_edit, info.designer),
                  (self.reviewer_edit, info.reviewer),
                  (self.revision_edit, info.revision),
                  (self.beam_name_edit, info.beam_name),
                  (self.slab_name_edit, info.slab_name))
        for campo, valor in campos:
            with QSignalBlocker(campo):
                campo.setText(valor)
        with QSignalBlocker(self.notes_edit):
            self.notes_edit.setPlainText(info.notes)

    def _on_project_edited(self):
        self.project_info = ProjectInfo(
            project=self.project_edit.text().strip() or "Proyecto sin título",
            designer=self.designer_edit.text().strip(),
            reviewer=self.reviewer_edit.text().strip(),
            revision=self.revision_edit.text().strip(),
            notes=self.notes_edit.toPlainText().strip(),
            beam_name=self.beam_name_edit.text().strip() or "Viga V-1",
            slab_name=self.slab_name_edit.text().strip() or "Losa L-1",
        )
        self._on_analysis_changed()

    # ------------------------------------------------------------
    #                     Cambio de unidades
    # ------------------------------------------------------------

    def _on_unit_changed(self):
        self._initializing = True
        self.current_unit_system = self.unit_combo.currentData()
        try:
            # La geometría primero: los demás paneles leen de ella.
            for panel in (self.beam_geometry, self.slab_geometry,
                          self.beam_flex_inputs, self.slab_flex_inputs,
                          self.beam_shear_inputs, self.slab_shear_inputs,
                          self.beam_flex_results, self.slab_flex_results,
                          self.beam_shear_results, self.slab_shear_results):
                panel.update_unit_system(self.current_unit_system)
        finally:
            self._initializing = False
        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self._on_analysis_changed()
        self.statusBar().showMessage(
            f"Sistema cambiado a: {self.current_unit_system.value}", 3000
        )

    # ------------------------------------------------------------
    #                      Cambio de normativa
    # ------------------------------------------------------------

    def _on_code_changed(self):
        self.current_code = self.code_combo.currentData()
        self.code_selector.set_value(self.current_code)
        for panel in (self.beam_flex_inputs, self.slab_flex_inputs,
                      self.beam_shear_inputs, self.slab_shear_inputs,
                      self.beam_geometry, self.slab_geometry):
            panel.set_design_code(self.current_code)
        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self._on_analysis_changed()
        self.statusBar().showMessage(
            f"Norma cambiada a: {spec(self.current_code).label}", 4000
        )

    # ------------------------------------------------------------
    #                       Cálculos
    # ------------------------------------------------------------

    def _show_calculation_status(self, is_beam, message, timeout):
        # Sólo en la pestaña del análisis que se recalculó: en Geometría la
        # barra de estado sigue diciendo dónde está el usuario.
        tabs = self.element_stack.currentWidget()
        activo_viga = tabs is self.beam_tabs
        es_flexion = "flexión" in message
        pestaña = TAB_FLEXURE if es_flexion else TAB_SHEAR
        if (self.pages.currentIndex() == PAGE_WORKSPACE
                and activo_viga == is_beam and tabs.currentIndex() == pestaña):
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
        La forma de la sección y el signo del momento viajan por el mismo camino.
        """
        flexion = self._beam_flex_design()
        values = self.beam_shear_inputs.get_values()
        values["d_mm"] = flexion.d_mm
        values["section_shape"] = flexion.section_shape
        values["bf_mm"] = flexion.bf_mm
        values["hf_mm"] = flexion.hf_mm
        values["negative_moment"] = flexion.negative_moment
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
            self._show_calculation_status(
                True, f"Viga (flexión) • Estado: {result.status}", 3000)
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
            self._show_calculation_status(
                False, f"Losa (flexión) • Estado: {result.status}", 3000)
        except Exception as e:
            self.slab_flex_results.clear()
            self.statusBar().showMessage(f"Error en losa (flexión): {e}", 5000)
            return
        # La cuantía longitudinal entra en Vc: mantener ambos en sincronía.
        self.calculate_slab_shear()

    def calculate_beam_shear(self):
        if self._initializing:
            return
        self.beam_shear_inputs.set_section_shape(
            self.beam_geometry.section_shape()
        )
        try:
            result = self._beam_shear_design()
            self.beam_shear_results.display_results(result)
            label = "cortante + torsión" if result.torsion_active else "cortante"
            self._show_calculation_status(
                True, f"Viga ({label}) • Estado: {result.status}", 3000)
        except Exception as e:
            self.beam_shear_results.clear()
            self.statusBar().showMessage(f"Error en viga (cortante): {e}", 5000)

    def calculate_slab_shear(self):
        if self._initializing:
            return
        try:
            result = self._slab_shear_check()
            self.slab_shear_results.display_results(result)
            self._show_calculation_status(
                False, f"Losa (cortante) • Estado: {result.status}", 3000)
        except Exception as e:
            self.slab_shear_results.clear()
            self.statusBar().showMessage(f"Error en losa (cortante): {e}", 5000)

    # ------------------------------------------------------------
    #                    Archivo del estudio
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
        self._remember_recent(file_path)
        self.statusBar().showMessage(f"Estudio guardado en: {file_path}", 6000)

    def _open_study(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Abrir estudio", os.path.expanduser("~"), FILE_FILTER
        )
        if file_path:
            self.open_study_file(file_path)

    def open_study_file(self, file_path: str) -> bool:
        """Carga un estudio desde disco; lo registra entre los recientes."""
        try:
            study = load_study(file_path)
        except (StudyFileError, OSError) as e:
            QMessageBox.critical(self, "Error al abrir", f"No se pudo abrir:\n\n{e}")
            self.recent_studies.forget(file_path)
            self._refresh_recent()
            return False

        self.project_info = study.info
        self._fill_project_fields()
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
            # La flexión lleva la geometría del elemento, así que se carga
            # después del cortante para que sea ella la que quede.
            for key in ("viga_cortante", "losa_cortante",
                        "viga_flexion", "losa_flexion"):
                if key in study.panels:
                    self._panels()[key].set_state(study.panels[key])
        finally:
            self._initializing = False

        self.calculate_beam_flex()
        self.calculate_slab_flex()
        self.current_path = file_path
        self._refresh_title()
        self._on_analysis_changed()
        self._remember_recent(file_path)
        self.statusBar().showMessage(f"Estudio abierto: {file_path}", 6000)
        return True

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
            suggested_path = os.path.join(os.path.expanduser("~"), default_name)

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
