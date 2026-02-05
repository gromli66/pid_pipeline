"""
Diagrams API - CRUD операции с диаграммами.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus, Artifact, ArtifactType, Project
from app.schemas.diagram import (
    DiagramResponse,
    DiagramListResponse,
    DiagramStatusResponse,
    DiagramUploadResponse,
)
from app.services.storage import StorageService
from app.services.project_loader import get_project_loader, ProjectLoader

router = APIRouter()


@router.post("/upload", response_model=DiagramUploadResponse)
async def upload_diagram(
    file: UploadFile = File(...),
    project_code: str = Form(..., description="Код проекта"),
    db: AsyncSession = Depends(get_async_db),
    loader: ProjectLoader = Depends(get_project_loader),
):
    """
    Загрузить новую диаграмму.
    
    Требует указания project_code.
    """
    # Проверка проекта
    config = loader.load(project_code)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown project: {project_code}")
    
    # Проверяем/создаём проект в БД
    result = await db.execute(select(Project).where(Project.code == project_code))
    project = result.scalar_one_or_none()
    
    if not project:
        project = Project(
            code=config.code,
            name=config.name,
            cvat_project_name=config.cvat_project_name,
            config_path=config.config_path,
        )
        db.add(project)
        await db.flush()
    
    # Проверка типа файла
    allowed_types = {"image/png", "image/jpeg", "image/tiff"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {allowed_types}")
    
    # Следующий номер
    result = await db.execute(select(func.max(Diagram.number)))
    max_number = result.scalar() or 0
    
    # Создаём диаграмму
    diagram = Diagram(
        number=max_number + 1,
        project_code=project_code,
        original_filename=file.filename,
        status=DiagramStatus.UPLOADED,
    )
    db.add(diagram)
    await db.flush()
    
    # Сохраняем файл
    storage = StorageService()
    file_path, file_size, dimensions = await storage.save_upload(diagram.uid, file, "original")
    
    diagram.image_width = dimensions[0] if dimensions else None
    diagram.image_height = dimensions[1] if dimensions else None
    
    # Артефакт
    artifact = Artifact(
        diagram_uid=diagram.uid,
        artifact_type=ArtifactType.ORIGINAL_IMAGE,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
    )
    db.add(artifact)
    
    await db.commit()
    await db.refresh(diagram)
    
    return DiagramUploadResponse(
        uid=diagram.uid,
        number=diagram.number,
        project_code=diagram.project_code,
        status=diagram.status,
        filename=diagram.original_filename,
    )


@router.get("/", response_model=DiagramListResponse)
async def list_diagrams(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_code: Optional[str] = Query(None, description="Фильтр по проекту"),
    status: Optional[DiagramStatus] = None,
    db: AsyncSession = Depends(get_async_db),
):
    """Получить список диаграмм."""
    query = select(Diagram).order_by(Diagram.number.desc())
    
    if project_code:
        query = query.where(Diagram.project_code == project_code)
    if status:
        query = query.where(Diagram.status == status)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    diagrams = result.scalars().all()
    
    return DiagramListResponse(
        items=[DiagramResponse.model_validate(d) for d in diagrams],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{uid}", response_model=DiagramResponse)
async def get_diagram(uid: UUID, db: AsyncSession = Depends(get_async_db)):
    """Получить диаграмму по UID."""
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    return DiagramResponse.model_validate(diagram)


@router.get("/{uid}/status", response_model=DiagramStatusResponse)
async def get_diagram_status(uid: UUID, db: AsyncSession = Depends(get_async_db)):
    """Статус диаграммы для polling."""
    result = await db.execute(
        select(
            Diagram.status,
            Diagram.error_message,
            Diagram.error_stage,
            Diagram.cvat_task_id,
            Diagram.cvat_job_id,
            Diagram.detection_count,
            Diagram.updated_at,
        ).where(Diagram.uid == uid)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    return DiagramStatusResponse(
        status=row.status,
        error_message=row.error_message,
        error_stage=row.error_stage,
        cvat_task_id=row.cvat_task_id,
        cvat_job_id=row.cvat_job_id,
        detection_count=row.detection_count,
        updated_at=row.updated_at,
    )


@router.delete("/{uid}")
async def delete_diagram(uid: UUID, db: AsyncSession = Depends(get_async_db)):
    """Удалить диаграмму."""
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    storage = StorageService()
    await storage.delete_diagram_folder(uid)
    
    await db.delete(diagram)
    await db.commit()
    
    return {"status": "deleted", "uid": str(uid)}
