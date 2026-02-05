#!/usr/bin/env python3
"""
Инициализация базы данных.

Создаёт все таблицы включая projects.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from app.config import settings
from app.db.base import Base

# Импортируем все модели чтобы они зарегистрировались
from app.models import Project, Diagram, Artifact, ProcessingStage


def init_db(drop: bool = False):
    """
    Создать таблицы в БД.
    
    Args:
        drop: Удалить существующие таблицы перед созданием
    """
    # Синхронный engine для создания таблиц
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql://", "postgresql://")
    engine = create_engine(sync_url)
    
    print("🗄️ Creating database tables...")
    
    if drop:
        print("⚠️ Dropping existing tables...")
        Base.metadata.drop_all(bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    print("✅ Database tables created successfully!")
    print()
    print("Tables:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")


if __name__ == "__main__":
    drop_flag = "--drop" in sys.argv
    init_db(drop=drop_flag)
