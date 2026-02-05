"""
Storage Service - работа с файловым хранилищем.
"""

import os
import shutil
import aiofiles
import aiofiles.os
from pathlib import Path
from typing import Tuple, Optional
from uuid import UUID

from fastapi import UploadFile
from PIL import Image
import io

from app.config import settings


class StorageService:
    """
    Сервис для работы с файловым хранилищем.
    
    Структура:
        storage/diagrams/{uid}/
            ├── original/
            ├── detection/
            ├── segmentation/
            ├── skeleton/
            ├── junction/
            ├── graph/
            └── output/
    """
    
    def __init__(self, base_path: Optional[str] = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)
    
    def get_diagram_path(self, uid: UUID) -> Path:
        """Получить путь к папке диаграммы."""
        return self.base_path / str(uid)
    
    def get_stage_path(self, uid: UUID, stage: str) -> Path:
        """Получить путь к папке этапа."""
        return self.get_diagram_path(uid) / stage
    
    async def ensure_dir(self, path: Path) -> None:
        """Создать директорию если не существует."""
        os.makedirs(path, exist_ok=True)
    
    async def save_upload(
        self,
        uid: UUID,
        file: UploadFile,
        stage: str = "original",
        filename: Optional[str] = None,
    ) -> Tuple[str, int, Optional[Tuple[int, int]]]:
        """
        Сохранить загруженный файл.
        
        Returns:
            (relative_path, file_size, (width, height) or None)
        """
        stage_path = self.get_stage_path(uid, stage)
        await self.ensure_dir(stage_path)
        
        # Определяем имя файла
        if filename is None:
            ext = Path(file.filename).suffix if file.filename else ".png"
            filename = f"image{ext}"
        
        file_path = stage_path / filename
        
        # Читаем содержимое
        content = await file.read()
        file_size = len(content)
        
        # Сохраняем файл
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Получаем размеры изображения
        dimensions = None
        try:
            img = Image.open(io.BytesIO(content))
            dimensions = img.size  # (width, height)
        except Exception:
            pass
        
        # Возвращаем относительный путь
        relative_path = str(file_path.relative_to(self.base_path))
        
        return relative_path, file_size, dimensions
    
    async def save_file(
        self,
        uid: UUID,
        stage: str,
        filename: str,
        content: bytes,
    ) -> Tuple[str, int]:
        """Сохранить файл с контентом."""
        stage_path = self.get_stage_path(uid, stage)
        await self.ensure_dir(stage_path)
        
        file_path = stage_path / filename
        
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        relative_path = str(file_path.relative_to(self.base_path))
        return relative_path, len(content)
    
    async def save_text(
        self,
        uid: UUID,
        stage: str,
        filename: str,
        content: str,
    ) -> Tuple[str, int]:
        """Сохранить текстовый файл."""
        return await self.save_file(uid, stage, filename, content.encode('utf-8'))
    
    async def read_file(self, uid: UUID, stage: str, filename: str) -> bytes:
        """Прочитать файл."""
        file_path = self.get_stage_path(uid, stage) / filename
        async with aiofiles.open(file_path, 'rb') as f:
            return await f.read()
    
    async def read_text(self, uid: UUID, stage: str, filename: str) -> str:
        """Прочитать текстовый файл."""
        content = await self.read_file(uid, stage, filename)
        return content.decode('utf-8')
    
    async def file_exists(self, uid: UUID, stage: str, filename: str) -> bool:
        """Проверить существование файла."""
        file_path = self.get_stage_path(uid, stage) / filename
        return file_path.exists()
    
    async def get_full_path(self, uid: UUID, stage: str, filename: str) -> Path:
        """Получить полный путь к файлу."""
        return self.get_stage_path(uid, stage) / filename
    
    async def delete_diagram_folder(self, uid: UUID) -> None:
        """Удалить папку диаграммы со всеми файлами."""
        diagram_path = self.get_diagram_path(uid)
        if diagram_path.exists():
            shutil.rmtree(diagram_path)
    
    async def list_files(self, uid: UUID, stage: str) -> list:
        """Получить список файлов в папке этапа."""
        stage_path = self.get_stage_path(uid, stage)
        if not stage_path.exists():
            return []
        return [f.name for f in stage_path.iterdir() if f.is_file()]