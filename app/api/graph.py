"""
Graph API - построение графа и FXML (Phase 5).
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/build")
async def start_graph_building(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Запустить построение графа."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # TODO: Phase 5
    return {"status": "not_implemented", "message": "Graph building will be implemented in Phase 5"}


@router.post("/{uid}/generate-fxml")
async def generate_fxml(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Сгенерировать FXML."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # TODO: Phase 5
    return {"status": "not_implemented", "message": "FXML generation will be implemented in Phase 5"}