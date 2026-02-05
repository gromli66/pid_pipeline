"""
Validation API - валидация масок и графа (Phase 4-5).
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/masks/start")
async def start_mask_validation(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Начать валидацию масок."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # TODO: Phase 4
    return {"status": "not_implemented", "message": "Mask validation will be implemented in Phase 4"}


@router.post("/{uid}/masks/save")
async def save_validated_masks(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Сохранить валидированные маски."""
    # TODO: Phase 4
    return {"status": "not_implemented"}


@router.post("/{uid}/graph/start")
async def start_graph_validation(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Начать валидацию графа."""
    # TODO: Phase 5
    return {"status": "not_implemented"}


@router.post("/{uid}/graph/save")
async def save_validated_graph(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Сохранить валидированный граф."""
    # TODO: Phase 5
    return {"status": "not_implemented"}