"""
CVAT API - интеграция с CVAT.
"""

import json
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus, Artifact, ArtifactType
from app.config import settings

router = APIRouter()

# Thread pool для синхронных операций с CVAT
_executor = ThreadPoolExecutor(max_workers=4)


def parse_coco_annotations(coco_json: dict) -> Tuple[List[Dict], Dict[int, str]]:
    """
    Парсинг COCO JSON в список аннотаций.
    
    Args:
        coco_json: COCO формат JSON
        
    Returns:
        Tuple (annotations, category_map)
        - annotations: список dict с class_id, x_center, y_center, width, height
        - category_map: dict category_id → name
    """
    # Получаем размеры изображения
    images = coco_json.get("images", [])
    if not images:
        return [], {}
    
    image_info = images[0]
    img_width = image_info.get("width", 1)
    img_height = image_info.get("height", 1)
    
    # Маппинг категорий
    categories = coco_json.get("categories", [])
    category_map = {cat["id"]: cat["name"] for cat in categories}
    
    # Парсим аннотации
    annotations = []
    for ann in coco_json.get("annotations", []):
        bbox = ann.get("bbox", [0, 0, 0, 0])  # [x, y, width, height]
        category_id = ann.get("category_id", 0)
        
        # COCO bbox → YOLO normalized
        x, y, w, h = bbox
        x_center = (x + w / 2) / img_width
        y_center = (y + h / 2) / img_height
        width = w / img_width
        height = h / img_height
        
        annotations.append({
            "class_id": category_id - 1,  # COCO 1-based → 0-based
            "class_name": category_map.get(category_id, f"class_{category_id}"),
            "x_center": x_center,
            "y_center": y_center,
            "width": width,
            "height": height,
        })
    
    return annotations, category_map


def annotations_to_yolo_txt(annotations: List[Dict]) -> str:
    """Конвертация аннотаций в YOLO формат."""
    lines = []
    for ann in annotations:
        line = "{} {:.6f} {:.6f} {:.6f} {:.6f}".format(
            ann["class_id"],
            ann["x_center"],
            ann["y_center"],
            ann["width"],
            ann["height"],
        )
        lines.append(line)
    return "\n".join(lines)


def _fetch_cvat_annotations_sync(
    task_id: int,
    output_dir: Path,
) -> Tuple[Path, Path, int]:
    """
    Синхронная функция для получения аннотаций из CVAT.
    
    Returns:
        Tuple (coco_path, yolo_path, annotation_count)
    """
    from app.services.cvat_client import CVATClient
    
    cvat_client = CVATClient()
    
    # Авторизация если нужно
    cvat_username = os.getenv("CVAT_USERNAME")
    cvat_password = os.getenv("CVAT_PASSWORD")
    if cvat_username and cvat_password:
        cvat_client.login(cvat_username, cvat_password)
    
    # Экспортируем аннотации в COCO формате
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir) / "annotations.zip"
        cvat_client.export_annotations(
            task_id=task_id,
            format_name="COCO 1.0",
            output_path=zip_path,
        )
        
        # Распаковываем ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)
        
        # Ищем JSON файл
        coco_json_path = None
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                if f.endswith('.json'):
                    coco_json_path = Path(root) / f
                    break
            if coco_json_path:
                break
        
        if not coco_json_path or not coco_json_path.exists():
            raise ValueError("COCO JSON not found in exported archive")
        
        # Парсим COCO
        with open(coco_json_path, 'r', encoding='utf-8') as f:
            coco_data = json.load(f)
        
        annotations, _ = parse_coco_annotations(coco_data)
        annotation_count = len(annotations)
        
        # Создаём выходную директорию
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем COCO JSON
        coco_output = output_dir / "coco_validated.json"
        with open(coco_output, 'w', encoding='utf-8') as f:
            json.dump(coco_data, f, ensure_ascii=False, indent=2)
        
        # Сохраняем YOLO txt
        yolo_output = output_dir / "yolo_validated.txt"
        yolo_txt = annotations_to_yolo_txt(annotations)
        yolo_output.write_text(yolo_txt)
        
        return coco_output, yolo_output, annotation_count


@router.post("/{uid}/open-validation")
async def open_cvat_validation(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Открыть валидацию в CVAT.
    Возвращает URL для открытия в браузере.
    """
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if diagram.status != DiagramStatus.DETECTED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot open CVAT: status is '{diagram.status.value}', expected 'detected'"
        )
    
    if not diagram.cvat_task_id or not diagram.cvat_job_id:
        raise HTTPException(
            status_code=400,
            detail="CVAT task not created yet"
        )
    
    # Обновляем статус
    diagram.status = DiagramStatus.VALIDATING_BBOX
    await db.commit()
    
    # Формируем URL
    cvat_url = f"{settings.CVAT_URL}/tasks/{diagram.cvat_task_id}/jobs/{diagram.cvat_job_id}"
    
    return {
        "status": "validating_bbox",
        "cvat_url": cvat_url,
        "cvat_task_id": diagram.cvat_task_id,
        "cvat_job_id": diagram.cvat_job_id,
    }


@router.post("/{uid}/fetch-annotations")
async def fetch_cvat_annotations(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Получить аннотации из CVAT и сохранить как валидированные.
    
    Этапы:
    1. Экспорт аннотаций из CVAT (COCO формат)
    2. Сохранение coco_validated.json
    3. Конвертация в yolo_validated.txt
    4. Создание артефактов в БД
    5. Обновление статуса → validated_bbox
    """
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if diagram.status != DiagramStatus.VALIDATING_BBOX:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot fetch annotations: status is '{diagram.status.value}', expected 'validating_bbox'"
        )
    
    if not diagram.cvat_task_id:
        raise HTTPException(
            status_code=400,
            detail="CVAT task not found"
        )
    
    # Путь к директории detection
    storage_path = Path(settings.STORAGE_PATH)
    detection_dir = storage_path / str(diagram.uid) / "detection"
    
    try:
        # Выполняем синхронную операцию в thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        
        coco_path, yolo_path, annotation_count = await loop.run_in_executor(
            _executor,
            _fetch_cvat_annotations_sync,
            diagram.cvat_task_id,
            detection_dir,
        )
        
        # Создаём артефакт COCO_VALIDATED
        artifact_coco = Artifact(
            diagram_uid=str(uid),
            artifact_type=ArtifactType.COCO_VALIDATED,
            file_path=str(coco_path.relative_to(storage_path)),
            file_size=coco_path.stat().st_size,
        )
        db.add(artifact_coco)
        
        # Создаём артефакт YOLO_VALIDATED
        artifact_yolo = Artifact(
            diagram_uid=str(uid),
            artifact_type=ArtifactType.YOLO_VALIDATED,
            file_path=str(yolo_path.relative_to(storage_path)),
            file_size=yolo_path.stat().st_size,
        )
        db.add(artifact_yolo)
        
        # Обновляем диаграмму
        diagram.status = DiagramStatus.VALIDATED_BBOX
        diagram.validated_detection_count = annotation_count
        
        await db.commit()
        
        return {
            "status": "validated_bbox",
            "annotation_count": annotation_count,
            "coco_path": str(coco_path.relative_to(storage_path)),
            "yolo_path": str(yolo_path.relative_to(storage_path)),
        }
        
    except Exception as exc:
        # Откатываем статус при ошибке
        diagram.status = DiagramStatus.ERROR
        diagram.error_message = str(exc)[:500]
        diagram.error_stage = "fetching_annotations"
        await db.commit()
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch annotations: {exc}"
        )


@router.get("/{uid}/cvat-url")
async def get_cvat_url(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Получить URL CVAT задачи."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if not diagram.cvat_task_id:
        raise HTTPException(status_code=400, detail="CVAT task not created")
    
    cvat_url = f"{settings.CVAT_URL}/tasks/{diagram.cvat_task_id}/jobs/{diagram.cvat_job_id}"
    
    return {"cvat_url": cvat_url}


@router.post("/{uid}/retry-fetch")
async def retry_fetch_annotations(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Повторить получение аннотаций после ошибки."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if diagram.status != DiagramStatus.ERROR:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry: status is '{diagram.status.value}', expected 'error'"
        )
    
    if diagram.error_stage != "fetching_annotations":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry fetch: error_stage is '{diagram.error_stage}'"
        )
    
    # Сбрасываем на validating_bbox для повторной попытки
    diagram.status = DiagramStatus.VALIDATING_BBOX
    diagram.error_message = None
    diagram.error_stage = None
    await db.commit()
    
    return {
        "status": "validating_bbox",
        "message": "Ready for retry. Call fetch-annotations again.",
    }
