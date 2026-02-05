"""
Diagram Schemas - Pydantic модели для API.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import DiagramStatus


class DiagramUploadResponse(BaseModel):
    """Ответ на загрузку диаграммы."""
    uid: UUID
    number: int
    project_code: str
    status: DiagramStatus
    filename: str


class DiagramStatusResponse(BaseModel):
    """Ответ для polling статуса."""
    status: DiagramStatus
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    cvat_task_id: Optional[int] = None
    cvat_job_id: Optional[int] = None
    detection_count: Optional[int] = None
    updated_at: datetime


class DiagramResponse(BaseModel):
    """Полная информация о диаграмме."""
    model_config = ConfigDict(from_attributes=True)
    
    uid: UUID
    number: int
    project_code: str
    original_filename: str
    status: DiagramStatus
    
    error_message: Optional[str] = None
    error_stage: Optional[str] = None
    
    cvat_task_id: Optional[int] = None
    cvat_job_id: Optional[int] = None
    
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    
    detection_count: Optional[int] = None
    validated_detection_count: Optional[int] = None
    segmentation_pixels: Optional[int] = None
    junction_count: Optional[int] = None
    bridge_count: Optional[int] = None
    node_count: Optional[int] = None
    edge_count: Optional[int] = None
    
    created_at: datetime
    updated_at: datetime


class DiagramListResponse(BaseModel):
    """Список диаграмм с пагинацией."""
    items: List[DiagramResponse]
    total: int
    skip: int
    limit: int
