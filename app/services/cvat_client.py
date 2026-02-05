"""
CVAT Client - взаимодействие с CVAT API.

Синхронная версия для использования в Celery workers.

Функции:
- Создание проекта с метками
- Создание task и загрузка изображения
- Импорт аннотаций (YOLO формат)
- Экспорт аннотаций
"""

import httpx
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from app.config import settings


@dataclass
class CVATLabel:
    """Метка для CVAT проекта."""
    name: str
    color: Optional[str] = None
    attributes: Optional[List[dict]] = None


class CVATClient:
    """
    Синхронный клиент для CVAT API.
    
    Использование:
        client = CVATClient()
        client.login("admin", "password")
        
        # Или с токеном (из settings.CVAT_TOKEN)
        client = CVATClient()  # токен берётся автоматически
        
        # Создать проект
        project_id = client.create_project("My Project", labels)
        
        # Создать task с изображением
        task_id, job_id = client.create_task(
            project_id=project_id,
            name="Task 1",
            image_path="path/to/image.png"
        )
        
        # Импортировать аннотации
        client.import_annotations(task_id, "path/to/annotations.zip", "YOLO 1.1")
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Args:
            base_url: URL CVAT сервера (default: settings.CVAT_URL)
            token: API токен (default: settings.CVAT_TOKEN)
            timeout: Таймаут запросов в секундах
        """
        self.base_url = (base_url or settings.CVAT_URL).rstrip("/")
        self.token = token or settings.CVAT_TOKEN
        self.timeout = timeout
        self._session_token: Optional[str] = None
        self._csrf_token: Optional[str] = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Получить заголовки для запросов."""
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        elif self._session_token:
            headers["Authorization"] = f"Token {self._session_token}"
        
        if self._csrf_token:
            headers["X-CSRFToken"] = self._csrf_token
        
        return headers
    
    def login(self, username: str, password: str) -> str:
        """
        Авторизация в CVAT.
        
        Returns:
            Session token
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
            )
            response.raise_for_status()
            
            data = response.json()
            self._session_token = data.get("key")
            
            # Получаем CSRF token из cookies
            if "csrftoken" in response.cookies:
                self._csrf_token = response.cookies["csrftoken"]
            
            return self._session_token
    
    def get_projects(self) -> List[dict]:
        """Получить список проектов."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/projects",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json().get("results", [])
    
    def get_project_by_name(self, name: str) -> Optional[dict]:
        """Найти проект по имени."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/projects",
                headers=self._get_headers(),
                params={"search": name},
            )
            response.raise_for_status()
            
            results = response.json().get("results", [])
            for project in results:
                if project.get("name") == name:
                    return project
            return None
    
    def create_project(
        self,
        name: str,
        labels: List[CVATLabel],
    ) -> int:
        """
        Создать проект в CVAT.
        
        Args:
            name: Имя проекта
            labels: Список меток
            
        Returns:
            ID созданного проекта
        """
        # Формируем labels для API
        labels_data = []
        for label in labels:
            label_dict = {"name": label.name}
            if label.color:
                label_dict["color"] = label.color
            if label.attributes:
                label_dict["attributes"] = label.attributes
            labels_data.append(label_dict)
        
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/projects",
                headers=self._get_headers(),
                json={
                    "name": name,
                    "labels": labels_data,
                },
            )
            response.raise_for_status()
            
            return response.json()["id"]
    
    def get_or_create_project(
        self,
        name: str,
        labels: List[CVATLabel],
    ) -> int:
        """
        Получить существующий проект или создать новый.
        
        Returns:
            ID проекта
        """
        existing = self.get_project_by_name(name)
        if existing:
            return existing["id"]
        return self.create_project(name, labels)
    
    def create_task(
        self,
        project_id: int,
        name: str,
        image_path: Path,
    ) -> Tuple[int, int]:
        """
        Создать task и загрузить изображение.
        
        Args:
            project_id: ID проекта
            name: Имя task
            image_path: Путь к изображению
            
        Returns:
            Tuple (task_id, job_id)
        """
        image_path = Path(image_path)
        
        with httpx.Client(timeout=self.timeout * 2) as client:
            # 1. Создаём task
            response = client.post(
                f"{self.base_url}/api/tasks",
                headers=self._get_headers(),
                json={
                    "name": name,
                    "project_id": project_id,
                },
            )
            response.raise_for_status()
            task_id = response.json()["id"]
            
            # 2. Загружаем изображение
            headers = self._get_headers()
            headers.pop("Content-Type", None)  # Убираем для multipart
            
            with open(image_path, "rb") as f:
                files = {"client_files[0]": (image_path.name, f, "image/png")}
                response = client.post(
                    f"{self.base_url}/api/tasks/{task_id}/data",
                    headers=headers,
                    files=files,
                    data={"image_quality": 70},
                )
                response.raise_for_status()
            
            # 3. Ждём создания job
            job_id = self._wait_for_job(client, task_id)
            
            return task_id, job_id
    
    def _wait_for_job(
        self,
        client: httpx.Client,
        task_id: int,
        max_attempts: int = 30,
        delay: float = 1.0,
    ) -> int:
        """Дождаться создания job для task."""
        for _ in range(max_attempts):
            response = client.get(
                f"{self.base_url}/api/jobs",
                headers=self._get_headers(),
                params={"task_id": task_id},
            )
            response.raise_for_status()
            
            jobs = response.json().get("results", [])
            if jobs:
                return jobs[0]["id"]
            
            time.sleep(delay)
        
        raise TimeoutError(f"Job for task {task_id} not created after {max_attempts} attempts")
    
    def import_annotations(
        self,
        task_id: int,
        annotations_path: Path,
        format_name: str = "YOLO 1.1",
    ) -> None:
        """
        Импортировать аннотации в task.
        
        Args:
            task_id: ID task
            annotations_path: Путь к ZIP архиву с аннотациями
            format_name: Формат аннотаций ("YOLO 1.1" или "COCO 1.0")
        """
        annotations_path = Path(annotations_path)
        
        with httpx.Client(timeout=self.timeout * 2) as client:
            headers = self._get_headers()
            headers.pop("Content-Type", None)
            
            with open(annotations_path, "rb") as f:
                files = {"annotation_file": (annotations_path.name, f, "application/zip")}
                response = client.put(
                    f"{self.base_url}/api/tasks/{task_id}/annotations",
                    headers=headers,
                    files=files,
                    params={"format": format_name},
                )
                response.raise_for_status()
    
    def export_annotations(
        self,
        task_id: int,
        format_name: str = "COCO 1.0",
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Экспортировать аннотации из task.
        
        Args:
            task_id: ID task
            format_name: Формат аннотаций ("YOLO 1.1" или "COCO 1.0")
            output_path: Путь для сохранения (опционально)
            
        Returns:
            Путь к скачанному файлу
        """
        with httpx.Client(timeout=self.timeout * 3) as client:
            # Запрос на экспорт
            response = client.get(
                f"{self.base_url}/api/tasks/{task_id}/annotations",
                headers=self._get_headers(),
                params={"format": format_name, "action": "download"},
                follow_redirects=True,
            )
            response.raise_for_status()
            
            # Сохраняем файл
            if output_path is None:
                output_path = Path(f"task_{task_id}_annotations.zip")
            
            output_path = Path(output_path)
            output_path.write_bytes(response.content)
            
            return output_path
    
    def get_task_status(self, task_id: int) -> str:
        """Получить статус task."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/tasks/{task_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json().get("status", "unknown")
    
    def get_task_url(self, task_id: int, job_id: int) -> str:
        """Получить URL для открытия task в браузере."""
        return f"{self.base_url}/tasks/{task_id}/jobs/{job_id}"


def create_labels_from_config(project_config) -> List[CVATLabel]:
    """
    Создать список меток из конфигурации проекта.
    
    Args:
        project_config: ProjectConfig из project_loader
        
    Returns:
        Список CVATLabel
    """
    return [
        CVATLabel(name=cls.name)
        for cls in project_config.classes
    ]
