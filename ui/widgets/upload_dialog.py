"""
Upload Dialog - диалог загрузки новой диаграммы.
"""

from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QFileDialog,
)


class UploadDialog(QDialog):
    """Диалог выбора файла и проекта для загрузки."""

    def __init__(self, projects: List[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Загрузить диаграмму")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        # Файл
        self.file_input = QLineEdit()
        self.file_input.setReadOnly(True)
        self.file_input.setPlaceholderText("Выберите файл...")

        btn_browse = QPushButton("📁")
        btn_browse.setFixedWidth(30)
        btn_browse.clicked.connect(self._browse_file)

        from PySide6.QtWidgets import QHBoxLayout, QWidget
        file_widget = QWidget()
        file_layout = QHBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(btn_browse)

        layout.addRow("Файл:", file_widget)

        # Проект
        self.project_combo = QComboBox()
        for proj in projects:
            self.project_combo.addItem(proj["name"], proj["code"])
        layout.addRow("Проект:", self.project_combo)

        # Кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.tiff *.tif)"
        )
        if file_path:
            self.file_input.setText(file_path)

    def get_values(self) -> tuple:
        """Вернуть (file_path, project_code)."""
        return Path(self.file_input.text()), self.project_combo.currentData()
