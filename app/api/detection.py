"""
Detection API - YOLO детекция.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/detect")
async def start_detection(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """
    Запустить YOLO детекцию.
    
    1. Проверяет status == uploaded
    2. Обновляет status = detecting
    3. Запускает Celery task
    """
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if diagram.status != DiagramStatus.UPLOADED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start detection: status is '{diagram.status.value}', expected 'uploaded'"
        )
    
    # Обновляем статус ПЕРЕД запуском task (короткая транзакция)
    # ⚠️ НЕ оборачивать Celery send_task в ту же транзакцию!
    diagram.status = DiagramStatus.DETECTING
    await db.commit()
    
    # Запускаем Celery task ВНЕ транзакции
    from worker.celery_app import celery_app
    task = celery_app.send_task(
        "worker.tasks.detection.task_detect_yolo",
        args=[str(uid)],
        kwargs={"project_code": diagram.project_code or "thermohydraulics"}
    )
    
    return {
        "status": "detecting",
        "task_id": task.id,
        "uid": str(uid),
    }


@router.post("/{uid}/retry")
async def retry_detection(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Повторить детекцию после ошибки."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    if diagram.status != DiagramStatus.ERROR:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry: status is '{diagram.status.value}', expected 'error'"
        )
    
    if diagram.error_stage != "detecting":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry detection: error_stage is '{diagram.error_stage}'"
        )
    
    # Сбрасываем ошибку
    diagram.status = DiagramStatus.DETECTING
    diagram.error_message = None
    diagram.error_stage = None
    await db.commit()
    
    # Запускаем Celery task
    from worker.celery_app import celery_app
    task = celery_app.send_task(
        "worker.tasks.detection.task_detect_yolo",
        args=[str(uid)]
    )
    
    return {
        "status": "detecting",
        "task_id": task.id,
        "uid": str(uid),
    }