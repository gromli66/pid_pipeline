"""
Diagram List Widget - таблица диаграмм с фильтрами и действиями.
"""

import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QFileDialog, QMessageBox, QHeaderView, QComboBox,
    QFrame, QLineEdit, QMenu,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QCursor

from ui.services.api_client import APIClient, DiagramInfo, DiagramStatus, APIError
from ui.services.status_provider import StatusProvider


# Цвета статусов
STATUS_COLORS = {
    DiagramStatus.UPLOADED: "#9E9E9E",
    DiagramStatus.DETECTING: "#2196F3",
    DiagramStatus.DETECTED: "#FF9800",
    DiagramStatus.VALIDATING_BBOX: "#FF9800",
    DiagramStatus.VALIDATED_BBOX: "#4CAF50",
    DiagramStatus.SEGMENTING: "#2196F3",
    DiagramStatus.SEGMENTED: "#4CAF50",
    DiagramStatus.SKELETONIZING: "#2196F3",
    DiagramStatus.SKELETONIZED: "#4CAF50",
    DiagramStatus.CLASSIFYING_JUNCTIONS: "#2196F3",
    DiagramStatus.CLASSIFIED: "#4CAF50",
    DiagramStatus.VALIDATING_MASKS: "#FF9800",
    DiagramStatus.VALIDATED_MASKS: "#4CAF50",
    DiagramStatus.BUILDING_GRAPH: "#2196F3",
    DiagramStatus.BUILT: "#4CAF50",
    DiagramStatus.VALIDATING_GRAPH: "#FF9800",
    DiagramStatus.VALIDATED_GRAPH: "#4CAF50",
    DiagramStatus.GENERATING_FXML: "#2196F3",
    DiagramStatus.COMPLETED: "#8BC34A",
    DiagramStatus.ERROR: "#F44336",
}

STATUS_LABELS = {
    DiagramStatus.UPLOADED: "Загружено",
    DiagramStatus.DETECTING: "⏳ Детекция...",
    DiagramStatus.DETECTED: "🔍 Детекция завершена",
    DiagramStatus.VALIDATING_BBOX: "🏷️ Валидация bbox",
    DiagramStatus.VALIDATED_BBOX: "✓ Bbox валидированы",
    DiagramStatus.SEGMENTING: "⏳ Сегментация...",
    DiagramStatus.SEGMENTED: "Сегментировано",
    DiagramStatus.SKELETONIZING: "⏳ Скелетизация...",
    DiagramStatus.SKELETONIZED: "Скелетизировано",
    DiagramStatus.CLASSIFYING_JUNCTIONS: "⏳ Классификация...",
    DiagramStatus.CLASSIFIED: "Классифицировано",
    DiagramStatus.VALIDATING_MASKS: "Валидация масок",
    DiagramStatus.VALIDATED_MASKS: "Маски валидированы",
    DiagramStatus.BUILDING_GRAPH: "⏳ Построение графа...",
    DiagramStatus.BUILT: "Граф построен",
    DiagramStatus.VALIDATING_GRAPH: "Валидация графа",
    DiagramStatus.VALIDATED_GRAPH: "Граф валидирован",
    DiagramStatus.GENERATING_FXML: "⏳ Генерация FXML...",
    DiagramStatus.COMPLETED: "✓ Завершено",
    DiagramStatus.ERROR: "✗ Ошибка",
}

STATUS_ORDER = {
    DiagramStatus.UPLOADED: 0,
    DiagramStatus.DETECTING: 1,
    DiagramStatus.DETECTED: 2,
    DiagramStatus.VALIDATING_BBOX: 3,
    DiagramStatus.VALIDATED_BBOX: 4,
    DiagramStatus.SEGMENTING: 5,
    DiagramStatus.SEGMENTED: 6,
    DiagramStatus.SKELETONIZING: 7,
    DiagramStatus.SKELETONIZED: 8,
    DiagramStatus.CLASSIFYING_JUNCTIONS: 9,
    DiagramStatus.CLASSIFIED: 10,
    DiagramStatus.VALIDATING_MASKS: 11,
    DiagramStatus.VALIDATED_MASKS: 12,
    DiagramStatus.BUILDING_GRAPH: 13,
    DiagramStatus.BUILT: 14,
    DiagramStatus.VALIDATING_GRAPH: 15,
    DiagramStatus.VALIDATED_GRAPH: 16,
    DiagramStatus.GENERATING_FXML: 17,
    DiagramStatus.COMPLETED: 18,
    DiagramStatus.ERROR: 99,
}


class DiagramListWidget(QWidget):
    """
    Виджет со списком диаграмм: таблица, фильтры, действия.

    Signals:
        status_message(str, int): сообщение для statusbar (текст, timeout_ms)
        show_progress(str): показать прогресс-бар
        hide_progress(): скрыть прогресс-бар
        open_cvat_requested(str): запрос на открытие CVAT для uid
        confirm_validation_requested(str): запрос на подтверждение валидации
    """

    # Сигналы для координации с MainWindow
    status_message = Signal(str, int)
    show_progress = Signal(str)
    hide_progress = Signal()
    open_cvat_requested = Signal(str)
    confirm_validation_requested = Signal(str)

    # Колонки таблицы
    COL_FILE = 0
    COL_PROJECT = 1
    COL_STATUS = 2
    COL_DATE = 3
    COL_ACTIONS = 4
    COL_DOWNLOAD = 5
    COL_DELETE = 6

    def __init__(
        self,
        api_client: APIClient,
        status_provider: StatusProvider,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.api_client = api_client
        self.status_provider = status_provider

        self._diagrams: List[DiagramInfo] = []
        self._projects: List[dict] = []

        # Сортировка
        self._sort_column = self.COL_DATE
        self._sort_ascending = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # === Поиск и фильтры ===
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(0, 0, 0, 10)

        # Поиск
        filter_layout.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по имени файла...")
        self.search_input.setMaximumWidth(300)
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_input)

        filter_layout.addSpacing(20)

        # Фильтр по проекту
        filter_layout.addWidget(QLabel("Проект:"))
        self.project_filter = QComboBox()
        self.project_filter.addItem("Все", None)
        self.project_filter.setMinimumWidth(150)
        self.project_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.project_filter)

        filter_layout.addSpacing(10)

        # Фильтр по статусу
        filter_layout.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("Все", None)
        self.status_filter.addItem("Загружено", DiagramStatus.UPLOADED)
        self.status_filter.addItem("Детекция", DiagramStatus.DETECTING)
        self.status_filter.addItem("Требует валидации", DiagramStatus.DETECTED)
        self.status_filter.addItem("Валидация bbox", DiagramStatus.VALIDATING_BBOX)
        self.status_filter.addItem("Bbox валидированы", DiagramStatus.VALIDATED_BBOX)
        self.status_filter.addItem("Завершено", DiagramStatus.COMPLETED)
        self.status_filter.addItem("Ошибка", DiagramStatus.ERROR)
        self.status_filter.setMinimumWidth(150)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.status_filter)

        filter_layout.addStretch()
        layout.addWidget(filter_frame)

        # === Таблица ===
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Файл", "Проект", "Статус", "Дата", "Действия", "📥", "🗑️"
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_FILE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_PROJECT, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_DATE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_DOWNLOAD, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_DELETE, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(self.COL_PROJECT, 140)
        self.table.setColumnWidth(self.COL_STATUS, 180)
        self.table.setColumnWidth(self.COL_DATE, 80)
        self.table.setColumnWidth(self.COL_ACTIONS, 200)
        self.table.setColumnWidth(self.COL_DOWNLOAD, 40)
        self.table.setColumnWidth(self.COL_DELETE, 40)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        header.sectionClicked.connect(self._on_header_clicked)

        layout.addWidget(self.table)

    # === Public API ===

    def set_projects(self, projects: List[dict]):
        """Обновить список проектов для фильтра."""
        self._projects = projects

        self.project_filter.blockSignals(True)
        current = self.project_filter.currentData()
        self.project_filter.clear()
        self.project_filter.addItem("Все", None)
        for proj in projects:
            self.project_filter.addItem(proj["name"], proj["code"])
        # Восстановить выбор
        for i in range(self.project_filter.count()):
            if self.project_filter.itemData(i) == current:
                self.project_filter.setCurrentIndex(i)
                break
        self.project_filter.blockSignals(False)

    @Slot()
    def load_diagrams(self):
        """Загрузить список диаграмм из API."""
        try:
            self._diagrams = self.api_client.list_diagrams()
            self._apply_filters()
            self.status_message.emit(f"Загружено {len(self._diagrams)} диаграмм", 3000)
        except APIError as exc:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить список:\n{exc.message}")

    # === Фильтры и сортировка ===

    @Slot()
    def _on_search_changed(self):
        self._apply_filters()

    @Slot()
    def _apply_filters(self):
        """Применить фильтры и обновить таблицу."""
        search_text = self.search_input.text().lower().strip()
        project_code = self.project_filter.currentData()
        status_filter = self.status_filter.currentData()

        filtered = []
        for d in self._diagrams:
            if search_text and search_text not in d.filename.lower():
                continue
            if project_code and d.project_code != project_code:
                continue
            if status_filter and d.status != status_filter:
                continue
            filtered.append(d)

        filtered = self._sort_diagrams(filtered)
        self._update_table(filtered)

    def _sort_diagrams(self, diagrams: list) -> list:
        reverse = not self._sort_ascending

        if self._sort_column == self.COL_FILE:
            return sorted(diagrams, key=lambda d: d.filename.lower(), reverse=reverse)
        elif self._sort_column == self.COL_PROJECT:
            return sorted(diagrams, key=lambda d: d.project_code, reverse=reverse)
        elif self._sort_column == self.COL_STATUS:
            return sorted(diagrams, key=lambda d: STATUS_ORDER.get(d.status, 50), reverse=reverse)
        elif self._sort_column == self.COL_DATE:
            return sorted(diagrams, key=lambda d: d.created_at or "", reverse=reverse)
        return diagrams

    @Slot(int)
    def _on_header_clicked(self, column: int):
        if column in (self.COL_FILE, self.COL_PROJECT, self.COL_STATUS, self.COL_DATE):
            if self._sort_column == column:
                self._sort_ascending = not self._sort_ascending
            else:
                self._sort_column = column
                self._sort_ascending = True
            self._apply_filters()

    # === Таблица ===

    def _update_table(self, diagrams: list):
        self.table.setRowCount(len(diagrams))

        for row, diagram in enumerate(diagrams):
            # Файл
            item = QTableWidgetItem(diagram.filename)
            item.setData(Qt.ItemDataRole.UserRole, diagram.uid)
            self.table.setItem(row, self.COL_FILE, item)

            # Проект
            project_name = diagram.project_code
            for p in self._projects:
                if p["code"] == diagram.project_code:
                    project_name = p["name"]
                    break
            self.table.setItem(row, self.COL_PROJECT, QTableWidgetItem(project_name))

            # Статус
            status_text = STATUS_LABELS.get(diagram.status, diagram.status.value)
            status_item = QTableWidgetItem(status_text)
            status_color = STATUS_COLORS.get(diagram.status, "#000000")
            status_item.setForeground(QColor(status_color))
            status_item.setToolTip(diagram.error_message or "")
            self.table.setItem(row, self.COL_STATUS, status_item)

            # Дата
            date_str = ""
            if diagram.created_at:
                try:
                    dt = datetime.fromisoformat(diagram.created_at.replace("Z", "+00:00"))
                    date_str = dt.strftime("%d.%m.%y")
                except Exception:
                    date_str = diagram.created_at[:10]
            self.table.setItem(row, self.COL_DATE, QTableWidgetItem(date_str))

            # Действия
            actions_widget = self._create_actions_widget(diagram)
            self.table.setCellWidget(row, self.COL_ACTIONS, actions_widget)

            # Скачать
            btn_download = QPushButton("📥")
            btn_download.setFixedWidth(30)
            btn_download.setToolTip("Скачать файлы")
            btn_download.clicked.connect(lambda checked, uid=diagram.uid: self._show_download_menu(uid))
            self.table.setCellWidget(row, self.COL_DOWNLOAD, btn_download)

            # Удалить
            btn_delete = QPushButton("🗑️")
            btn_delete.setFixedWidth(30)
            btn_delete.setToolTip("Удалить диаграмму")
            btn_delete.clicked.connect(
                lambda checked, uid=diagram.uid, name=diagram.filename: self._delete_diagram(uid, name)
            )
            self.table.setCellWidget(row, self.COL_DELETE, btn_delete)

            # Отслеживание статуса
            if self._is_processing_status(diagram.status):
                self.status_provider.watch(diagram.uid)

    def _is_processing_status(self, status: DiagramStatus) -> bool:
        return status in {
            DiagramStatus.DETECTING,
            DiagramStatus.SEGMENTING,
            DiagramStatus.SKELETONIZING,
            DiagramStatus.CLASSIFYING_JUNCTIONS,
            DiagramStatus.BUILDING_GRAPH,
            DiagramStatus.GENERATING_FXML,
        }

    def _create_actions_widget(self, diagram: DiagramInfo) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        status = diagram.status

        if status == DiagramStatus.UPLOADED:
            btn = QPushButton("🔍 Детекция")
            btn.clicked.connect(lambda checked, uid=diagram.uid: self._start_detection(uid))
            layout.addWidget(btn)

        elif status == DiagramStatus.DETECTING:
            label = QLabel("⏳ Обработка...")
            label.setStyleSheet("color: #2196F3;")
            layout.addWidget(label)

        elif status in (DiagramStatus.DETECTED, DiagramStatus.VALIDATING_BBOX):
            btn = QPushButton("🏷️ CVAT")
            btn.setStyleSheet("background-color: #FF9800; color: white;")
            btn.clicked.connect(lambda checked, uid=diagram.uid: self.open_cvat_requested.emit(uid))
            layout.addWidget(btn)

            if status == DiagramStatus.VALIDATING_BBOX:
                btn_confirm = QPushButton("✅ Подтвердить")
                btn_confirm.setStyleSheet("background-color: #4CAF50; color: white;")
                btn_confirm.clicked.connect(
                    lambda checked, uid=diagram.uid: self.confirm_validation_requested.emit(uid)
                )
                layout.addWidget(btn_confirm)

        elif status == DiagramStatus.VALIDATED_BBOX:
            btn = QPushButton("▶️ Сегментация")
            btn.clicked.connect(lambda checked, uid=diagram.uid: self._start_segmentation(uid))
            layout.addWidget(btn)

        elif status == DiagramStatus.ERROR:
            error_msg = (diagram.error_message or "").lower()
            if "not found" in error_msg or "image not found" in error_msg or "file not found" in error_msg:
                btn_upload = QPushButton("📁 Загрузить оригинал")
                btn_upload.setStyleSheet("background-color: #2196F3; color: white;")
                btn_upload.clicked.connect(lambda checked, uid=diagram.uid: self._handle_missing_original(uid))
                layout.addWidget(btn_upload)

                btn_del = QPushButton("🗑️ Удалить")
                btn_del.setStyleSheet("background-color: #F44336; color: white;")
                btn_del.clicked.connect(
                    lambda checked, uid=diagram.uid, name=diagram.filename: self._delete_diagram(uid, name)
                )
                layout.addWidget(btn_del)
            else:
                btn = QPushButton("🔄 Повторить")
                btn.setToolTip(f"Ошибка: {diagram.error_message or 'Unknown'}")
                btn.setStyleSheet("background-color: #F44336; color: white;")
                btn.clicked.connect(lambda checked, uid=diagram.uid: self._retry_operation(uid))
                layout.addWidget(btn)

        layout.addStretch()
        return widget

    # === Действия ===

    def _start_detection(self, uid: str):
        try:
            self.show_progress.emit("Запуск детекции...")
            self.api_client.start_detection(uid)
            self.hide_progress.emit()
            self.status_message.emit("Детекция запущена", 3000)
            self.status_provider.watch(uid)
            self.load_diagrams()
        except APIError as exc:
            self.hide_progress.emit()
            if "not found" in exc.message.lower() or "image not found" in exc.message.lower():
                self._handle_missing_original(uid)
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось запустить детекцию:\n{exc.message}")

    def _handle_missing_original(self, uid: str):
        reply = QMessageBox.question(
            self,
            "Оригинал не найден",
            "Оригинальное изображение не найдено.\n\nЧто сделать?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Open:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Выберите оригинал", "",
                "Images (*.png *.jpg *.jpeg *.tiff *.tif)"
            )
            if file_path:
                try:
                    self.show_progress.emit("Загрузка оригинала...")
                    self.api_client.reupload_original(uid, Path(file_path))
                    self.hide_progress.emit()
                    self.status_message.emit("Оригинал загружен", 3000)
                    self.load_diagrams()
                except APIError as exc:
                    self.hide_progress.emit()
                    QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить:\n{exc.message}")

        elif reply == QMessageBox.StandardButton.Discard:
            self._delete_diagram(uid, "диаграмму")

    def _retry_operation(self, uid: str):
        try:
            self.show_progress.emit("Сброс статуса...")
            self.api_client.retry_operation(uid)
            self.hide_progress.emit()
            self.status_message.emit("Статус сброшен", 3000)
            self.load_diagrams()
        except APIError as exc:
            self.hide_progress.emit()
            if "not found" in exc.message.lower() or "image not found" in exc.message.lower():
                self._handle_missing_original(uid)
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось сбросить статус:\n{exc.message}")

    def _start_segmentation(self, uid: str):
        try:
            self.show_progress.emit("Запуск сегментации...")
            self.api_client.start_segmentation(uid)
            self.hide_progress.emit()
            self.status_message.emit("Сегментация запущена", 3000)
            self.status_provider.watch(uid)
            self.load_diagrams()
        except APIError as exc:
            self.hide_progress.emit()
            QMessageBox.warning(self, "Ошибка", f"Не удалось запустить сегментацию:\n{exc.message}")

    def _delete_diagram(self, uid: str, name: str):
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить '{name}'?\n\n"
            f"Будут удалены все связанные файлы и данные.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self.show_progress.emit("Удаление...")
            self.api_client.delete_diagram(uid)
            self.hide_progress.emit()
            self.status_message.emit(f"Удалено: {name}", 3000)
            self.load_diagrams()
        except APIError as exc:
            self.hide_progress.emit()
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить:\n{exc.message}")

    # === Скачивание ===

    def _show_download_menu(self, uid: str):
        menu = QMenu(self)

        menu.addAction("📄 Оригинал", lambda: self._download_file(uid, "original"))
        menu.addSeparator()
        menu.addAction("📝 YOLO predicted.txt", lambda: self._download_file(uid, "yolo_predicted"))
        menu.addAction("📝 YOLO validated.txt", lambda: self._download_file(uid, "yolo_validated"))
        menu.addAction("📋 COCO validated.json", lambda: self._download_file(uid, "coco_validated"))
        menu.addSeparator()
        menu.addAction("📦 Всё (ZIP)", lambda: self._download_file(uid, "all"))

        menu.exec(QCursor.pos())

    def _download_file(self, uid: str, file_type: str):
        """Скачать файл через API."""
        try:
            diagram = self.api_client.get_diagram(uid)

            if file_type == "all":
                self._download_all_as_zip(uid, diagram.filename)
                return

            type_map = {
                "original": ("original_image", diagram.filename),
                "yolo_predicted": ("yolo_predicted", f"{diagram.filename}_predicted.txt"),
                "yolo_validated": ("yolo_validated", f"{diagram.filename}_validated.txt"),
                "coco_validated": ("coco_validated", f"{diagram.filename}_validated.json"),
            }

            if file_type not in type_map:
                return

            artifact_type, default_name = type_map[file_type]

            dest, _ = QFileDialog.getSaveFileName(
                self, "Сохранить как", default_name
            )

            if dest:
                self.show_progress.emit("Скачивание...")
                self.api_client.download_artifact(uid, artifact_type, Path(dest))
                self.hide_progress.emit()
                self.status_message.emit(f"Сохранено: {Path(dest).name}", 3000)

        except APIError as exc:
            self.hide_progress.emit()
            QMessageBox.warning(self, "Ошибка", f"Не удалось скачать:\n{exc.message}")
        except Exception as exc:
            self.hide_progress.emit()
            QMessageBox.warning(self, "Ошибка", f"Не удалось скачать:\n{exc}")

    def _download_all_as_zip(self, uid: str, filename: str):
        """Скачать все файлы как ZIP через API."""
        import zipfile
        import tempfile

        dest, _ = QFileDialog.getSaveFileName(
            self, "Сохранить ZIP как", f"{filename}.zip", "ZIP (*.zip)"
        )

        if not dest:
            return

        try:
            self.show_progress.emit("Скачивание файлов...")

            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
                artifact_types = [
                    ("original_image", f"original_{filename}"),
                    ("yolo_predicted", "yolo_predicted.txt"),
                    ("yolo_validated", "yolo_validated.txt"),
                    ("coco_validated", "coco_validated.json"),
                ]

                with tempfile.TemporaryDirectory() as temp_dir:
                    for artifact_type, arc_name in artifact_types:
                        try:
                            tmp_path = Path(temp_dir) / arc_name
                            self.api_client.download_artifact(uid, artifact_type, tmp_path)
                            zf.write(tmp_path, arc_name)
                        except APIError:
                            pass

            self.hide_progress.emit()
            self.status_message.emit(f"Сохранено: {Path(dest).name}", 3000)

        except Exception as exc:
            self.hide_progress.emit()
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать ZIP:\n{exc}")
