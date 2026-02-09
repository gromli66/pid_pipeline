"""
Main Window - главное окно P&ID Pipeline.

Тонкий координатор: toolbar, statusbar, табы.
Вся логика таблицы — в DiagramListWidget.
"""

from pathlib import Path
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QStatusBar, QToolBar, QProgressBar, QFrame,
    QHBoxLayout, QTabWidget, QDialog,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QAction

from ui.services.api_client import APIClient, APIError, DiagramStatus
from ui.services.status_provider import StatusProvider
from ui.widgets.diagram_list import DiagramListWidget
from ui.widgets.upload_dialog import UploadDialog
from ui.windows.cvat_window import CVATWindow


class MainWindow(QMainWindow):
    """Главное окно приложения с табами."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("P&ID Pipeline")
        self.setMinimumSize(1200, 700)

        # Shared services
        self.api_client = APIClient("http://localhost:8000")
        self.status_provider = StatusProvider(self.api_client, parent=self)
        self.status_provider.status_updated.connect(self._on_status_updated)
        self.status_provider.error_occurred.connect(self._on_status_error)

        # State
        self._projects: list = []
        self._cvat_windows: Dict[str, CVATWindow] = {}

        # UI
        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()

        # Load data
        QTimer.singleShot(100, self._load_initial_data)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        # === Прогресс-бар ===
        self.progress_frame = QFrame()
        progress_layout = QHBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 5)

        self.progress_label = QLabel("Обработка...")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setMaximumWidth(200)
        progress_layout.addWidget(self.progress_bar)

        progress_layout.addStretch()
        self.progress_frame.hide()
        layout.addWidget(self.progress_frame)

        # === Табы ===
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Таб 1: Список диаграмм
        self.diagram_list = DiagramListWidget(
            api_client=self.api_client,
            status_provider=self.status_provider,
        )
        self.tabs.addTab(self.diagram_list, "📋 Диаграммы")

        # Подключаем сигналы DiagramListWidget
        self.diagram_list.status_message.connect(self._on_status_message)
        self.diagram_list.show_progress.connect(self._show_progress)
        self.diagram_list.hide_progress.connect(self._hide_progress)
        self.diagram_list.open_cvat_requested.connect(self._open_cvat)
        self.diagram_list.confirm_validation_requested.connect(self._confirm_validation)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        action_upload = QAction("📁 Загрузить", self)
        action_upload.triggered.connect(self._on_upload_clicked)
        toolbar.addAction(action_upload)

        toolbar.addSeparator()

        action_refresh = QAction("🔄 Обновить", self)
        action_refresh.triggered.connect(self.diagram_list.load_diagrams)
        toolbar.addAction(action_refresh)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        self.connection_label = QLabel()
        self.statusbar.addPermanentWidget(self.connection_label)

        self._check_connection()

    # === Connection ===

    def _check_connection(self):
        try:
            if self.api_client.health_check():
                self.connection_label.setText("🟢 API")
                self.connection_label.setStyleSheet("color: green;")
            else:
                self.connection_label.setText("🔴 API недоступен")
                self.connection_label.setStyleSheet("color: red;")
        except Exception:
            self.connection_label.setText("🔴 API недоступен")
            self.connection_label.setStyleSheet("color: red;")

    # === Progress ===

    @Slot(str)
    def _show_progress(self, message: str):
        self.progress_label.setText(message)
        self.progress_frame.show()

    @Slot()
    def _hide_progress(self):
        self.progress_frame.hide()

    # === Data loading ===

    def _load_initial_data(self):
        self._load_projects()
        self.diagram_list.load_diagrams()

    def _load_projects(self):
        try:
            self._projects = self.api_client.list_projects()
        except APIError:
            self._projects = [{"code": "thermohydraulics", "name": "Термогидравлика"}]

        self.diagram_list.set_projects(self._projects)

    # === Upload ===

    @Slot()
    def _on_upload_clicked(self):
        if not self._projects:
            self._projects = [{"code": "thermohydraulics", "name": "Термогидравлика"}]

        dialog = UploadDialog(self._projects, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        file_path, project_code = dialog.get_values()

        if not file_path or not str(file_path):
            QMessageBox.warning(self, "Ошибка", "Файл не выбран")
            return

        try:
            self._show_progress("Загрузка файла...")
            info = self.api_client.upload_diagram(file_path, project_code)
            self._hide_progress()
            self.statusbar.showMessage(f"Загружено: {info.filename}", 3000)
            self.diagram_list.load_diagrams()
        except APIError as exc:
            self._hide_progress()
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить:\n{exc.message}")

    # === CVAT ===

    @Slot(str)
    def _open_cvat(self, uid: str):
        """Открыть CVAT. Создаст task если его нет."""
        try:
            diagram = self.api_client.get_diagram(uid)

            # Если нет CVAT task — создаём автоматически
            if not diagram.cvat_task_id:
                self._show_progress("Создание CVAT task...")
                try:
                    self.api_client.create_cvat_task(uid)
                    self._hide_progress()
                    diagram = self.api_client.get_diagram(uid)
                except APIError as exc:
                    self._hide_progress()
                    if "not found" in exc.message.lower() or "image not found" in exc.message.lower():
                        QMessageBox.warning(self, "Ошибка", "Оригинальное изображение не найдено.")
                    else:
                        QMessageBox.warning(self, "Ошибка", f"Не удалось создать CVAT task:\n{exc.message}")
                    return

            # Переводим в VALIDATING если нужно
            if diagram.status == DiagramStatus.DETECTED:
                result = self.api_client.open_cvat_validation(uid)
                cvat_url = result.get("cvat_url")
            else:
                cvat_url = self.api_client.get_cvat_url(uid)

            if not cvat_url:
                QMessageBox.warning(self, "Ошибка", "CVAT URL не найден")
                return

            # Проверяем существующее окно
            if uid in self._cvat_windows:
                self._cvat_windows[uid].activateWindow()
                self._cvat_windows[uid].raise_()
                return

            # Создаём CVAT окно
            cvat_window = CVATWindow(
                diagram_uid=uid,
                cvat_url=cvat_url,
                diagram_name=diagram.filename,
                cvat_task_id=diagram.cvat_task_id,
                cvat_job_id=diagram.cvat_job_id,
                parent=None,
            )

            cvat_window.validation_confirmed.connect(self._on_cvat_validation_confirmed)
            cvat_window.window_closed.connect(self._on_cvat_window_closed)

            self._cvat_windows[uid] = cvat_window
            cvat_window.show()

            self.diagram_list.load_diagrams()

        except APIError as exc:
            if "not found" in exc.message.lower() or "image not found" in exc.message.lower():
                QMessageBox.warning(self, "Ошибка", "Оригинальное изображение не найдено.")
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось открыть CVAT:\n{exc.message}")

    @Slot(str)
    def _on_cvat_validation_confirmed(self, uid: str):
        self._confirm_validation(uid)
        if uid in self._cvat_windows:
            self._cvat_windows[uid].close()

    @Slot(str)
    def _on_cvat_window_closed(self, uid: str):
        self._cvat_windows.pop(uid, None)

    @Slot(str)
    def _confirm_validation(self, uid: str):
        try:
            self._show_progress("Получение аннотаций из CVAT...")
            result = self.api_client.fetch_cvat_annotations(uid)
            self._hide_progress()

            count = result.get("annotation_count", 0)
            self.statusbar.showMessage(f"✅ Получено {count} валидированных аннотаций", 5000)

            self.diagram_list.load_diagrams()

        except APIError as exc:
            self._hide_progress()
            QMessageBox.warning(self, "Ошибка", f"Не удалось получить аннотации:\n{exc.message}")

    # === Status Provider callbacks ===

    @Slot(str, int)
    def _on_status_message(self, message: str, timeout_ms: int):
        self.statusbar.showMessage(message, timeout_ms)

    @Slot(str, object)
    def _on_status_updated(self, uid: str, status_info):
        self.diagram_list.load_diagrams()

    @Slot(str, str)
    def _on_status_error(self, uid: str, error_message: str):
        self.statusbar.showMessage(f"Ошибка: {error_message}", 5000)
