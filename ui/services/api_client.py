"""
API Client - HTTP клиент для взаимодействия с backend.

Persistent connection + retry при потере связи.
"""

import httpx
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DiagramStatus(str, Enum):
    """Статусы диаграммы (зеркало backend)."""
    UPLOADED = "uploaded"
    DETECTING = "detecting"
    DETECTED = "detected"
    VALIDATING_BBOX = "validating_bbox"
    VALIDATED_BBOX = "validated_bbox"
    SEGMENTING = "segmenting"
    SEGMENTED = "segmented"
    SKELETONIZING = "skeletonizing"
    SKELETONIZED = "skeletonized"
    CLASSIFYING_JUNCTIONS = "classifying_junctions"
    CLASSIFIED = "classified"
    VALIDATING_MASKS = "validating_masks"
    VALIDATED_MASKS = "validated_masks"
    BUILDING_GRAPH = "building_graph"
    BUILT = "built"
    VALIDATING_GRAPH = "validating_graph"
    VALIDATED_GRAPH = "validated_graph"
    GENERATING_FXML = "generating_fxml"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class DiagramInfo:
    """Информация о диаграмме."""
    uid: str
    number: int
    project_code: str
    status: DiagramStatus
    filename: str
    detection_count: Optional[int] = None
    validated_detection_count: Optional[int] = None
    cvat_task_id: Optional[int] = None
    cvat_job_id: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class DiagramStatusInfo:
    """Статус диаграммы."""
    status: DiagramStatus
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    cvat_task_id: Optional[int] = None
    cvat_job_id: Optional[int] = None
    detection_count: Optional[int] = None
    updated_at: Optional[str] = None


class APIError(Exception):
    """Ошибка API."""
    def __init__(self, message: str, status_code: int = 0):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class APIClient:
    """
    HTTP клиент для P&ID Pipeline API.

    Persistent connection с автоматическим retry при потере связи.

    Использование:
        client = APIClient("http://localhost:8000")

        # Загрузить диаграмму
        info = client.upload_diagram("path/to/image.png", "thermohydraulics")

        # Запустить детекцию
        client.start_detection(info.uid)

        # Получить статус
        status = client.get_status(info.uid)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Persistent client с connection pooling
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    def close(self):
        """Закрыть HTTP соединения."""
        self._client.close()

    def _request(
        self,
        method: str,
        endpoint: str,
        retries: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Выполнить HTTP запрос с retry при потере соединения."""
        max_retries = retries if retries is not None else self.max_retries

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.request(method, endpoint, **kwargs)

                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        message = error_data.get("detail", str(error_data))
                    except Exception:
                        message = response.text or f"HTTP {response.status_code}"
                    raise APIError(message, response.status_code)

                return response.json()

            except httpx.RequestError as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = self.retry_delay * (2 ** attempt)  # exponential backoff
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.1f}s: {exc}"
                    )
                    time.sleep(delay)
                    # Пересоздаём client при connection reset
                    try:
                        self._client.close()
                    except Exception:
                        pass
                    self._client = httpx.Client(
                        base_url=self.base_url,
                        timeout=self.timeout,
                        limits=httpx.Limits(
                            max_connections=10,
                            max_keepalive_connections=5,
                        ),
                    )

        raise APIError(f"Connection failed after {max_retries + 1} attempts: {last_error}")

    def _request_raw(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> httpx.Response:
        """Выполнить HTTP запрос и вернуть raw response (для скачивания файлов)."""
        try:
            response = self._client.request(method, endpoint, **kwargs)

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    message = error_data.get("detail", str(error_data))
                except Exception:
                    message = response.text or f"HTTP {response.status_code}"
                raise APIError(message, response.status_code)

            return response

        except httpx.RequestError as exc:
            raise APIError(f"Connection error: {exc}")

    # === Health ===

    def health_check(self) -> bool:
        """Проверить доступность API."""
        try:
            result = self._request("GET", "/health", retries=0)
            return result.get("status") in ("healthy", "degraded")
        except (APIError, Exception):
            return False

    # === Diagrams ===

    def upload_diagram(
        self,
        file_path: Path,
        project_code: str = "thermohydraulics",
    ) -> DiagramInfo:
        """Загрузить диаграмму."""
        file_path = Path(file_path)

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "image/png")}
            data = {"project_code": project_code}

            result = self._request(
                "POST",
                "/api/diagrams/upload",
                files=files,
                data=data,
            )

        return DiagramInfo(
            uid=result["uid"],
            number=result["number"],
            project_code=result["project_code"],
            status=DiagramStatus(result["status"]),
            filename=result["filename"],
        )

    def list_diagrams(
        self,
        project_code: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[DiagramInfo]:
        """Получить список диаграмм."""
        params = {"skip": skip, "limit": limit}
        if project_code:
            params["project_code"] = project_code
        if status:
            params["status"] = status

        result = self._request("GET", "/api/diagrams/", params=params)

        # API возвращает {"items": [...], "total": ...}
        items = result.get("items", []) if isinstance(result, dict) else result

        diagrams = []
        for item in items:
            diagrams.append(DiagramInfo(
                uid=item["uid"],
                number=item["number"],
                project_code=item["project_code"],
                status=DiagramStatus(item["status"]),
                filename=item["original_filename"],
                detection_count=item.get("detection_count"),
                cvat_task_id=item.get("cvat_task_id"),
                cvat_job_id=item.get("cvat_job_id"),
                error_message=item.get("error_message"),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
            ))

        return diagrams

    def get_diagram(self, uid: str) -> DiagramInfo:
        """Получить информацию о диаграмме."""
        result = self._request("GET", f"/api/diagrams/{uid}")

        return DiagramInfo(
            uid=result["uid"],
            number=result["number"],
            project_code=result["project_code"],
            status=DiagramStatus(result["status"]),
            filename=result["original_filename"],
            detection_count=result.get("detection_count"),
            validated_detection_count=result.get("validated_detection_count"),
            cvat_task_id=result.get("cvat_task_id"),
            cvat_job_id=result.get("cvat_job_id"),
            error_message=result.get("error_message"),
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
        )

    def get_status(self, uid: str) -> DiagramStatusInfo:
        """Получить статус диаграммы."""
        result = self._request("GET", f"/api/diagrams/{uid}/status", retries=1)

        return DiagramStatusInfo(
            status=DiagramStatus(result["status"]),
            error_message=result.get("error_message"),
            error_stage=result.get("error_stage"),
            cvat_task_id=result.get("cvat_task_id"),
            cvat_job_id=result.get("cvat_job_id"),
            detection_count=result.get("detection_count"),
            updated_at=result.get("updated_at"),
        )

    def delete_diagram(self, uid: str) -> bool:
        """Удалить диаграмму."""
        self._request("DELETE", f"/api/diagrams/{uid}")
        return True

    # === Download ===

    def download_artifact(self, uid: str, artifact_type: str, dest_path: Path) -> Path:
        """
        Скачать артефакт через API (не обращается к filesystem напрямую).

        Args:
            uid: UUID диаграммы
            artifact_type: Тип артефакта (original_image, yolo_predicted, yolo_validated, coco_validated)
            dest_path: Путь для сохранения файла

        Returns:
            Path к сохранённому файлу
        """
        response = self._request_raw(
            "GET",
            f"/api/diagrams/{uid}/download/{artifact_type}",
            timeout=120.0,
        )

        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(response.content)

        return dest_path

    # === Detection ===

    def start_detection(self, uid: str) -> Dict[str, Any]:
        """Запустить YOLO детекцию."""
        return self._request("POST", f"/api/detection/{uid}/detect")

    # === CVAT ===

    def open_cvat_validation(self, uid: str) -> Dict[str, Any]:
        """Открыть валидацию в CVAT."""
        return self._request("POST", f"/api/cvat/{uid}/open-validation")

    def fetch_cvat_annotations(self, uid: str) -> Dict[str, Any]:
        """Получить валидированные аннотации из CVAT."""
        return self._request("POST", f"/api/cvat/{uid}/fetch-annotations")

    def get_cvat_url(self, uid: str) -> str:
        """Получить URL CVAT задачи."""
        result = self._request("GET", f"/api/cvat/{uid}/cvat-url")
        return result.get("cvat_url", "")

    def create_cvat_task(self, uid: str) -> Dict[str, Any]:
        """Создать CVAT task для диаграммы."""
        return self._request("POST", f"/api/cvat/{uid}/create-task")

    # === Segmentation / Skeleton ===

    def start_segmentation(self, uid: str) -> Dict[str, Any]:
        """Запустить сегментацию."""
        return self._request("POST", f"/api/segmentation/{uid}/segment")

    def start_skeletonization(self, uid: str) -> Dict[str, Any]:
        """Запустить скелетизацию."""
        return self._request("POST", f"/api/skeleton/{uid}/skeletonize")

    # === Projects ===

    def list_projects(self) -> List[Dict[str, Any]]:
        """Получить список проектов."""
        try:
            result = self._request("GET", "/api/projects/")
            return result.get("items", result) if isinstance(result, dict) else result
        except APIError:
            # Fallback если API проектов не работает
            return [{"code": "thermohydraulics", "name": "Термогидравлика"}]

    # === Operations ===

    def retry_operation(self, uid: str) -> Dict[str, Any]:
        """Повторить операцию после ошибки."""
        return self._request("POST", f"/api/diagrams/{uid}/retry")

    def reupload_original(self, uid: str, file_path: Path) -> Dict[str, Any]:
        """Перезагрузить оригинальное изображение."""
        file_path = Path(file_path)

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "image/png")}

            return self._request(
                "POST",
                f"/api/diagrams/{uid}/reupload-original",
                files=files,
            )
