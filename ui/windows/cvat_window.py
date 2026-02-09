"""
CVAT Window - окно для валидации аннотаций в встроенном CVAT.
"""

from typing import Optional
import re

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QLabel, QToolBar, QStatusBar,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Signal, Slot, QUrl, QTimer


class CVATWindow(QMainWindow):
    """Окно с встроенным CVAT для валидации аннотаций."""

    validation_confirmed = Signal(str)
    window_closed = Signal(str)

    def __init__(
        self,
        diagram_uid: str,
        cvat_url: str,
        diagram_name: str = "",
        cvat_task_id: Optional[int] = None,
        cvat_job_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.diagram_uid = diagram_uid
        self.cvat_url = cvat_url
        self.diagram_name = diagram_name

        # Извлекаем task_id и job_id из URL если не переданы
        if cvat_task_id is None or cvat_job_id is None:
            cvat_task_id, cvat_job_id = self._extract_ids(cvat_url)

        self.cvat_task_id = cvat_task_id
        self.cvat_job_id = cvat_job_id
        self._is_redirecting = False

        self.setWindowTitle(f"CVAT Валидация - {diagram_name or diagram_uid[:8]}")
        self.setMinimumSize(1200, 800)

        self._setup_ui()
        self._load_cvat()

    def _extract_ids(self, url: str) -> tuple:
        """Извлечь task_id и job_id из URL."""
        task_match = re.search(r'/tasks/(\d+)', url)
        job_match = re.search(r'/jobs/(\d+)', url)

        task_id = int(task_match.group(1)) if task_match else None
        job_id = int(job_match.group(1)) if job_match else None

        return task_id, job_id

    def _setup_ui(self):
        """Настройка UI."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # === Toolbar ===
        toolbar = QToolBar("CVAT Actions")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        label = QLabel("  Отредактируйте аннотации, затем нажмите 'Подтвердить валидацию'  ")
        label.setStyleSheet("color: #666; font-size: 12px;")
        toolbar.addWidget(label)

        toolbar.addSeparator()

        btn_refresh = QPushButton("🔄 Обновить")
        btn_refresh.clicked.connect(self._on_refresh)
        toolbar.addWidget(btn_refresh)

        toolbar.addSeparator()

        self.btn_confirm = QPushButton("✅ Подтвердить валидацию")
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_confirm.clicked.connect(self._on_confirm)
        toolbar.addWidget(self.btn_confirm)

        # === WebView ===
        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view)

        # === Status Bar ===
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Загрузка CVAT...")

        # Сигналы
        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.urlChanged.connect(self._on_url_changed)

    def _load_cvat(self):
        """Загрузить CVAT страницу."""
        self.web_view.setUrl(QUrl(self.cvat_url))

    def _is_url_allowed(self, url: str) -> bool:
        """Проверить, разрешён ли URL."""
        # Разрешаем пустые и about:blank
        if not url or url == "about:blank":
            return True

        # Разрешаем только наш task/job
        if self.cvat_task_id and self.cvat_job_id:
            # Разрешённые паттерны
            allowed = [
                f"/tasks/{self.cvat_task_id}/jobs/{self.cvat_job_id}",
                f"/tasks/{self.cvat_task_id}",
            ]
            for pattern in allowed:
                if pattern in url:
                    return True

        # Запрещаем другие tasks/jobs/projects
        forbidden = ["/tasks/", "/jobs/", "/projects/", "/cloudstorages"]
        for pattern in forbidden:
            if pattern in url:
                # Но разрешаем если это наш task
                if self.cvat_task_id and f"/tasks/{self.cvat_task_id}" in url:
                    return True
                return False

        # Запрещаем главную страницу CVAT
        if url.endswith(":8080") or url.endswith(":8080/"):
            return False

        return True

    @Slot(QUrl)
    def _on_url_changed(self, url: QUrl):
        """Отслеживаем изменение URL и блокируем навигацию."""
        url_str = url.toString()

        # Избегаем рекурсии при редиректе
        if self._is_redirecting:
            return

        if not self._is_url_allowed(url_str):
            self._is_redirecting = True
            self.statusbar.showMessage("⚠️ Навигация заблокирована — работайте только с текущей задачей!", 5000)
            # Возвращаем на разрешённый URL
            self.web_view.setUrl(QUrl(self.cvat_url))
            # Сбрасываем флаг через небольшую задержку
            QTimer.singleShot(500, self._reset_redirect_flag)

    def _reset_redirect_flag(self):
        self._is_redirecting = False

    @Slot()
    def _on_refresh(self):
        """Обновить страницу."""
        self.web_view.setUrl(QUrl(self.cvat_url))

    @Slot()
    def _on_confirm(self):
        """Подтвердить валидацию."""
        self.validation_confirmed.emit(self.diagram_uid)

    @Slot()
    def _on_load_started(self):
        self.statusbar.showMessage("Загрузка...")

    @Slot(bool)
    def _on_load_finished(self, ok: bool):
        if ok:
            self.statusbar.showMessage("CVAT загружен. Отредактируйте аннотации и нажмите 'Подтвердить валидацию'")
            # Скрываем меню навигации CVAT
            self._hide_cvat_navigation()
        else:
            self.statusbar.showMessage("Ошибка загрузки CVAT")

    def _hide_cvat_navigation(self):
        """Скрыть элементы навигации CVAT через CSS."""
        script = """
        (function() {
            var style = document.createElement('style');
            style.id = 'cvat-nav-blocker';
            style.textContent = `
                /* Скрыть верхнее меню */
                .cvat-header-menu,
                header nav,
                .ant-menu-horizontal,
                a[href="/projects"],
                a[href="/tasks"],
                a[href="/jobs"],
                a[href="/cloudstorages"],
                a[href="/models"],
                a[href="/analytics"],
                /* Скрыть ссылки на другие задачи */
                .cvat-task-item-task-name a,
                .cvat-tasks-list a,
                .cvat-projects-list a {
                    pointer-events: none !important;
                    opacity: 0.5 !important;
                }
                /* Скрыть меню пользователя с выходом и настройками */
                .cvat-right-header,
                .cvat-header-menu-user-dropdown {
                    /* оставляем видимым, но можно скрыть */
                }
            `;
            
            // Удаляем старый стиль если есть
            var old = document.getElementById('cvat-nav-blocker');
            if (old) old.remove();
            
            document.head.appendChild(style);
            
            // Также перехватываем клики по меню
            document.addEventListener('click', function(e) {
                var target = e.target;
                while (target && target !== document) {
                    if (target.tagName === 'A') {
                        var href = target.getAttribute('href');
                        if (href && (href.startsWith('/projects') || href.startsWith('/tasks') || href.startsWith('/jobs') || href === '/')) {
                            e.preventDefault();
                            e.stopPropagation();
                            return false;
                        }
                    }
                    target = target.parentNode;
                }
            }, true);
        })();
        """
        self.web_view.page().runJavaScript(script)

    def closeEvent(self, event):
        """Обработка закрытия окна."""
        self.window_closed.emit(self.diagram_uid)
        super().closeEvent(event)