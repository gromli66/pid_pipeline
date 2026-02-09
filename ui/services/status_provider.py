"""
Status Provider - получение обновлений статуса диаграмм.

MVP реализация: HTTP Polling каждые 2 секунды.
Потом можно заменить на WebSocket без изменения UI кода.
"""

from PySide6.QtCore import QObject, Signal, QTimer, Slot
from typing import Optional, Set

from ui.services.api_client import APIClient, DiagramStatusInfo, DiagramStatus, APIError


class StatusProvider(QObject):
    """
    Провайдер обновлений статуса диаграмм.
    
    Использует HTTP polling для получения обновлений.
    
    Signals:
        status_updated(uid, status_info): Статус диаграммы обновился
        error_occurred(uid, message): Произошла ошибка
        
    Использование:
        provider = StatusProvider(api_client)
        provider.status_updated.connect(on_status_update)
        
        # Начать отслеживание
        provider.watch(diagram_uid)
        
        # Остановить отслеживание
        provider.unwatch(diagram_uid)
    """
    
    # Сигналы
    status_updated = Signal(str, object)  # uid, DiagramStatusInfo
    error_occurred = Signal(str, str)  # uid, error_message
    
    def __init__(
        self,
        api_client: APIClient,
        poll_interval_ms: int = 2000,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        
        self.api_client = api_client
        self.poll_interval_ms = poll_interval_ms
        
        # Отслеживаемые диаграммы
        self._watched_uids: Set[str] = set()
        self._last_status: dict[str, DiagramStatus] = {}
        
        # Таймер для polling
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
    
    def watch(self, uid: str) -> None:
        """Начать отслеживание диаграммы."""
        self._watched_uids.add(uid)
        
        # Запускаем таймер если не запущен
        if not self._timer.isActive() and self._watched_uids:
            self._timer.start(self.poll_interval_ms)
    
    def unwatch(self, uid: str) -> None:
        """Остановить отслеживание диаграммы."""
        self._watched_uids.discard(uid)
        self._last_status.pop(uid, None)
        
        # Останавливаем таймер если нечего отслеживать
        if not self._watched_uids:
            self._timer.stop()
    
    def unwatch_all(self) -> None:
        """Остановить отслеживание всех диаграмм."""
        self._watched_uids.clear()
        self._last_status.clear()
        self._timer.stop()
    
    def is_watching(self, uid: str) -> bool:
        """Проверить, отслеживается ли диаграмма."""
        return uid in self._watched_uids
    
    @Slot()
    def _poll(self) -> None:
        """Опросить статусы отслеживаемых диаграмм."""
        # Копируем set чтобы избежать изменения во время итерации
        uids = list(self._watched_uids)
        
        for uid in uids:
            try:
                status_info = self.api_client.get_status(uid)
                
                # Проверяем изменился ли статус
                last_status = self._last_status.get(uid)
                if last_status != status_info.status:
                    self._last_status[uid] = status_info.status
                    self.status_updated.emit(uid, status_info)
                    
                    # Автоматически прекращаем отслеживание для финальных статусов
                    if self._is_final_status(status_info.status):
                        self.unwatch(uid)
                        
            except APIError as exc:
                self.error_occurred.emit(uid, exc.message)
    
    def _is_final_status(self, status: DiagramStatus) -> bool:
        """Проверить, является ли статус финальным (не требует polling)."""
        # Статусы, требующие действия пользователя или завершённые
        final_statuses = {
            DiagramStatus.DETECTED,  # Ждёт валидации
            DiagramStatus.VALIDATED_BBOX,  # Можно запускать следующий этап
            DiagramStatus.SEGMENTED,
            DiagramStatus.SKELETONIZED,
            DiagramStatus.CLASSIFIED,
            DiagramStatus.VALIDATED_MASKS,
            DiagramStatus.BUILT,
            DiagramStatus.VALIDATED_GRAPH,
            DiagramStatus.COMPLETED,
            DiagramStatus.ERROR,
        }
        return status in final_statuses
    
    def force_update(self, uid: str) -> Optional[DiagramStatusInfo]:
        """Принудительно обновить статус диаграммы."""
        try:
            status_info = self.api_client.get_status(uid)
            self._last_status[uid] = status_info.status
            self.status_updated.emit(uid, status_info)
            return status_info
        except APIError as exc:
            self.error_occurred.emit(uid, exc.message)
            return None
