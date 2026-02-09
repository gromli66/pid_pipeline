# 9. Разработка

## 9.1 Настройка окружения разработки

### Вариант 1: Всё в Docker (рекомендуется)

```powershell
# Запустить все сервисы
docker-compose up -d

# Применить миграции
docker exec -it pid_api alembic upgrade head

# Код автоматически перезагружается благодаря bind mounts
```

### Вариант 2: Гибридный (API локально, остальное в Docker)

```powershell
# 1. Запустить инфраструктуру
docker-compose up -d postgres redis cvat_server cvat_ui traefik cvat_opa cvat_db cvat_redis_inmem cvat_redis_ondisk

# 2. Создать venv
python -m venv .venv
.venv\Scripts\activate

# 3. Установить PyTorch
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124

# 4. Установить зависимости
pip install -r requirements/api.txt

# 5. Запустить API
uvicorn app.main:app --reload --port 8000
```

---

## 9.2 Работа с миграциями

### Создание миграции

После изменения моделей в `app/models/`:

```powershell
# Через Docker (рекомендуется)
docker exec -it pid_api alembic revision --autogenerate -m "Add new field"

# Локально (если API запущен локально)
alembic revision --autogenerate -m "Add new field"
```

### Применение миграций

```powershell
# Через Docker
docker exec -it pid_api alembic upgrade head

# Локально
alembic upgrade head
```

### Откат миграции

```powershell
# Откатить последнюю
docker exec -it pid_api alembic downgrade -1

# Откатить до конкретной
docker exec -it pid_api alembic downgrade 6d4b720721f2
```

### Просмотр истории

```powershell
# Текущая версия
docker exec -it pid_api alembic current

# История миграций
docker exec -it pid_api alembic history
```

### Важно!

- Файлы миграций создаются в `alembic/versions/`
- **Коммитьте их в git** — они нужны на всех машинах
- При первом запуске на новой машине — только `alembic upgrade head`

---

## 9.3 Добавление нового API endpoint

### Шаг 1: Создать файл в `app/api/`

```python
# app/api/my_feature.py
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_async_db
from app.models import Diagram, DiagramStatus

router = APIRouter()


@router.post("/{uid}/my-action")
async def my_action(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    """Описание endpoint."""
    result = await db.execute(select(Diagram).where(Diagram.uid == uid))
    diagram = result.scalar_one_or_none()
    
    if not diagram:
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    # Логика...
    
    return {"status": "ok", "uid": str(uid)}
```

### Шаг 2: Зарегистрировать в `app/main.py`

```python
from app.api import my_feature

app.include_router(
    my_feature.router,
    prefix="/api/my-feature",
    tags=["My Feature"]
)
```

---

## 9.4 Добавление Celery задачи

### Шаг 1: Создать файл в `worker/tasks/`

```python
# worker/tasks/my_task.py
import os
import sys
from pathlib import Path

from worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="worker.tasks.my_task.task_my_action",
    max_retries=2,
    default_retry_delay=60,
    time_limit=1800,
)
def task_my_action(self, diagram_uid: str):
    """
    Описание задачи.
    """
    # Добавляем пути для импорта
    sys.path.insert(0, "/app")
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models import Diagram, DiagramStatus
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        diagram = db.query(Diagram).filter(Diagram.uid == diagram_uid).first()
        if not diagram:
            raise ValueError(f"Diagram {diagram_uid} not found")
        
        # Логика...
        
        diagram.status = DiagramStatus.COMPLETED
        db.commit()
        
        return {"status": "success", "diagram_uid": diagram_uid}
        
    except Exception as exc:
        # Обработка ошибок
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
        
    finally:
        db.close()
```

### Шаг 2: Добавить в `worker/celery_app.py`

```python
celery_app = Celery(
    include=[
        "worker.tasks.detection",
        "worker.tasks.segmentation",
        "worker.tasks.my_task",  # ← Добавить
    ]
)
```

### Шаг 3: Вызов из API

```python
from worker.celery_app import celery_app

task = celery_app.send_task(
    "worker.tasks.my_task.task_my_action",
    args=[str(uid)],
)
```

---

## 9.5 Добавление модели БД

### Шаг 1: Создать модель

```python
# app/models/my_model.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class MyModel(Base):
    __tablename__ = "my_models"
    
    id = Column(Integer, primary_key=True)
    diagram_uid = Column(UUID(as_uuid=True), ForeignKey("diagrams.uid"))
    name = Column(String(100))
    
    diagram = relationship("Diagram", back_populates="my_models")
```

### Шаг 2: Добавить в `app/models/__init__.py`

```python
from app.models.my_model import MyModel
```

### Шаг 3: Добавить в `alembic/env.py`

```python
from app.models import Diagram, Artifact, ProcessingStage, Project, MyModel
```

### Шаг 4: Создать миграцию

```powershell
docker exec -it pid_api alembic revision --autogenerate -m "Add MyModel"
docker exec -it pid_api alembic upgrade head
```

---

## 9.6 Тестирование

### Структура тестов

```
tests/
├── conftest.py              # Фикстуры pytest
├── test_api/
│   ├── test_diagrams.py
│   └── test_detection.py
├── test_worker/
│   └── test_tasks.py
└── test_ui/
```

### Запуск тестов

```powershell
# Все тесты
pytest

# С coverage
pytest --cov=app --cov=worker

# Конкретный файл
pytest tests/test_api/test_diagrams.py -v
```

### Пример теста API

```python
# tests/test_api/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

---

## 9.7 Логирование

### В API

```python
import structlog
logger = structlog.get_logger()

logger.info("Processing diagram", uid=str(uid), status=diagram.status.value)
logger.error("Failed to process", error=str(exc), exc_info=True)
```

### В Worker

```python
print(f"🔍 Starting detection for {diagram_uid}")
print(f"✅ Detected {count} objects")
print(f"❌ Error: {exc}")
```

### Просмотр логов

```powershell
# API логи
docker logs -f pid_api

# Worker логи
docker logs -f pid_worker

# Последние 100 строк
docker logs --tail 100 pid_api
```

---

## 9.8 Отладка

### Отладка API

```powershell
# Включить debug режим (в .env)
LOG_LEVEL=DEBUG

# Перезапустить
docker-compose restart api
```

### Отладка Worker

```powershell
# Логи в реальном времени
docker logs -f pid_worker

# Выполнить задачу вручную
docker exec -it pid_worker python -c "
from worker.tasks.detection import task_detect_yolo
result = task_detect_yolo('your-uuid-here')
print(result)
"
```

### Отладка БД

```powershell
# Подключиться к PostgreSQL
docker exec -it pid_postgres psql -U pid_user -d pid_pipeline

# SQL запросы
SELECT * FROM diagrams ORDER BY created_at DESC LIMIT 5;
SELECT * FROM artifacts WHERE diagram_uid = 'xxx';
```

---

## 9.9 Полезные команды

### Docker

```powershell
# Статус контейнеров
docker ps

# Логи конкретного сервиса
docker logs -f pid_api

# Зайти в контейнер
docker exec -it pid_api bash

# Перезапустить сервис
docker-compose restart api

# Пересобрать и запустить
docker-compose up -d --build api
```

### Alembic

```powershell
# Создать миграцию
docker exec -it pid_api alembic revision --autogenerate -m "Description"

# Применить
docker exec -it pid_api alembic upgrade head

# Текущая версия
docker exec -it pid_api alembic current

# История
docker exec -it pid_api alembic history
```

### PostgreSQL

```powershell
# Подключиться
docker exec -it pid_postgres psql -U pid_user -d pid_pipeline

# Список таблиц
\dt

# Описание таблицы
\d diagrams

# Выход
\q
```

### Redis

```powershell
# Redis CLI
docker exec -it pid_redis redis-cli

# Просмотр ключей
KEYS *

# Очистить очереди Celery
FLUSHALL
```

### Celery

```powershell
# Статус воркеров
docker exec -it pid_worker celery -A worker.celery_app status

# Активные задачи
docker exec -it pid_worker celery -A worker.celery_app inspect active

# Очистить очередь
docker exec -it pid_worker celery -A worker.celery_app purge
```

---

## 9.10 Git Workflow

### Ветки

- `main` — стабильная версия
- `develop` — текущая разработка
- `feature/xxx` — новые функции
- `fix/xxx` — исправления

### Коммиты

```
feat(api): add segmentation endpoint
fix(worker): handle timeout in detection
docs(readme): update installation guide
refactor(models): rename Diagram fields
chore(deps): update dependencies
```

### Перед коммитом

```powershell
# Проверить что тесты проходят
pytest

# Проверить линтинг
ruff check app/ worker/

# Проверить что миграции закоммичены
git status alembic/versions/
```
