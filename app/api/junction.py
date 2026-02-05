"""
Junction API - классификация перекрёстков (Phase 4).
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/classify")
async def start_junction_classification(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Запустить классификацию перекрёстков."""
    
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # TODO: Phase 4
    return {"status": "not_implemented", "message": "Junction classification will be implemented in Phase 4"}