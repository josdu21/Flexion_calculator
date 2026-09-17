"""Diálogo para editar los datos del cajetín de la memoria."""
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from core.project import ProjectInfo


class ProjectDialog(QDialog):
    """Edita un :class:`~core.project.ProjectInfo` y lo devuelve en `values()`."""

    def __init__(self, info: ProjectInfo, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datos del proyecto")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel(
            "Estos datos encabezan la memoria de cálculo exportada. "
            "La fecha, el tipo de elemento y la norma se generan solos."
        )
        hint.setObjectName("infoLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.project_edit = QLineEdit(info.project)
        self.designer_edit = QLineEdit(info.designer)
        self.reviewer_edit = QLineEdit(info.reviewer)
        self.revision_edit = QLineEdit(info.revision)
        self.revision_edit.setPlaceholderText("Rev. A")
        self.beam_edit = QLineEdit(info.beam_name)
        self.slab_edit = QLineEdit(info.slab_name)

        general = QGroupBox("Proyecto")
        general_form = QFormLayout(general)
        general_form.addRow("Proyecto:", self.project_edit)
        general_form.addRow("Diseñador:", self.designer_edit)
        general_form.addRow("Revisor:", self.reviewer_edit)
        general_form.addRow("Revisión:", self.revision_edit)
        layout.addWidget(general)

        elements = QGroupBox("Nombre de los elementos")
        elements_form = QFormLayout(elements)
        elements_form.addRow("Viga:", self.beam_edit)
        elements_form.addRow("Losa:", self.slab_edit)
        layout.addWidget(elements)

        notes = QGroupBox("Notas")
        notes_layout = QVBoxLayout(notes)
        self.notes_edit = QPlainTextEdit(info.notes)
        self.notes_edit.setPlaceholderText(
            "Observaciones que aparecerán al pie del cajetín."
        )
        self.notes_edit.setMinimumHeight(70)
        notes_layout.addWidget(self.notes_edit)
        layout.addWidget(notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.project_edit.setFocus()

    def values(self) -> ProjectInfo:
        return ProjectInfo(
            project=self.project_edit.text().strip() or "Proyecto sin título",
            designer=self.designer_edit.text().strip(),
            reviewer=self.reviewer_edit.text().strip(),
            revision=self.revision_edit.text().strip(),
            notes=self.notes_edit.toPlainText().strip(),
            beam_name=self.beam_edit.text().strip() or "Viga V-1",
            slab_name=self.slab_edit.text().strip() or "Losa L-1",
        )
