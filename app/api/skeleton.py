"""
Skeleton API - скелетизация (Phase 3).
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/skeletonize")
async def start_skeletonization(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Запустить скелетизацию."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # TODO: Phase 3
    return {"status": "not_implemented", "message": "Skeletonization will be implemented in Phase 3"}