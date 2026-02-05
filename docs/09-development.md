# 9. Разработка

## 9.1 Настройка окружения разработки

### Шаг 1: Клонирование и настройка

```powershell
git clone <repository-url>
cd pid_pipeline

# Создать .env
copy .env.example .env
notepad .env  # Настроить параметры
```

### Шаг 2: Виртуальное окружение

```powershell
python -m venv .venv
.venv\Scripts\activate

# Установить все зависимости
pip install -r requirements/api.txt
pip install -r requirements/worker.txt
pip install -r requirements/ui.txt
pip install -r requirements/dev.txt
```

### Шаг 3: Запуск инфраструктуры

```powershell
docker-compose up -d postgres redis
```

### Шаг 4: Инициализация БД

```powershell
python scripts/init_db.py
```

---

## 9.2 Запуск компонентов

### API (с hot reload)

```powershell
uvicorn app.main:app --reload --port 8000
```

### Celery Worker

```powershell
celery -A worker.celery_app worker --loglevel=info
```

### UI (PySide6)

```powershell
python -m ui.main
```

### Все вместе (разные терминалы)

```
Terminal 1: docker-compose up postgres redis
Terminal 2: uvicorn app.main:app --reload
Terminal 3: celery -A worker.celery_app worker --loglevel=info
Terminal 4: python -m ui.main
```

---

## 9.3 Структура кода

### Добавление нового API endpoint

1. Создать/изменить файл в `app/api/`:

```python
# app/api/my_feature.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_async_db

router = APIRouter()

@router.post("/{uid}/action")
async def my_action(
    uid: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    # Логика
    return {"status": "ok"}
```

2. Зарегистрировать в `app/main.py`:

```python
from app.api import my_feature

app.include_router(
    my_feature.router,
    prefix="/api/my-feature",
    tags=["My Feature"]
)
```

### Добавление новой Celery задачи

1. Создать файл в `worker/tasks/`:

```python
# worker/tasks/my_task.py
from worker.celery_app import celery_app

@celery_app.task(bind=True, name="worker.tasks.my_task.task_name")
def task_name(self, diagram_uid: str):
    # Логика
    return {"status": "success"}
```

2. Добавить в `worker/celery_app.py`:

```python
celery_app = Celery(
    include=[
        ...
        "worker.tasks.my_task",
    ]
)
```

### Добавление новой модели БД

1. Создать модель в `app/models/`:

```python
# app/models/my_model.py
from sqlalchemy import Column, Integer, String
from app.db.base import Base

class MyModel(Base):
    __tablename__ = "my_models"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
```

2. Добавить в `app/models/__init__.py`:

```python
from app.models.my_model import MyModel
```

3. Создать миграцию:

```powershell
alembic revision --autogenerate -m "Add MyModel"
alembic upgrade head
```

---

## 9.4 Тестирование

### Структура тестов

```
tests/
├── conftest.py          # Фикстуры pytest
├── test_api/
│   ├── test_diagrams.py
│   └── test_detection.py
├── test_worker/
│   └── test_tasks.py
└── test_ui/
    └── test_widgets.py
```

### Запуск тестов

```powershell
# Все тесты
pytest

# С coverage
pytest --cov=app --cov=worker

# Конкретный файл
pytest tests/test_api/test_diagrams.py

# Verbose
pytest -v
```

### Пример теста

```python
# tests/test_api/test_diagrams.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

---

## 9.5 Code Style

### Линтинг (Ruff)

```powershell
# Проверка
ruff check app/ worker/

# Автоисправление
ruff check --fix app/ worker/
```

### Type checking (MyPy)

```powershell
mypy app/ worker/
```

### Форматирование

Используем настройки по умолчанию Ruff (совместим с Black).

---

## 9.6 Git Workflow

### Ветки

- `main` — стабильная версия
- `develop` — текущая разработка
- `feature/xxx` — новые фичи
- `bugfix/xxx` — исправления

### Коммиты

```
feat: добавлена детекция YOLO
fix: исправлена ошибка загрузки файлов
docs: обновлена документация API
refactor: рефакторинг StorageService
test: добавлены тесты для diagrams API
```

### Pull Request

1. Создать ветку от `develop`
2. Сделать изменения
3. Запустить тесты
4. Создать PR в `develop`
5. Code review
6. Merge

---

## 9.7 Debugging

### API (FastAPI)

```python
# Включить debug mode
# .env
API_DEBUG=true

# Или в коде
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Celery

```powershell
# Verbose logging
celery -A worker.celery_app worker --loglevel=debug

# Отладка конкретной задачи
python -c "from worker.tasks.detection import task_detect_yolo; task_detect_yolo('uuid')"
```

### Database

```python
# Включить SQL logging
# app/db/session.py
engine = create_engine(DATABASE_URL, echo=True)
```

### PySide6

```python
# Включить Qt debugging
import os
os.environ["QT_DEBUG_PLUGINS"] = "1"
```

---

## 9.8 Частые задачи

### Сброс базы данных

```powershell
python scripts/init_db.py --drop
```

### Очистка storage

```powershell
Remove-Item -Recurse -Force storage\diagrams\*
```

### Перезапуск worker

```powershell
# Остановить
Ctrl+C

# Очистить очереди
celery -A worker.celery_app purge

# Запустить заново
celery -A worker.celery_app worker --loglevel=info
```

### Проверка подключения к CVAT

```powershell
curl http://localhost:8080/api/server/about
```

---

## 9.9 IDE настройки

### VS Code

`.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "none",
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true
    }
}
```

### PyCharm

1. File → Settings → Project → Python Interpreter
2. Выбрать `.venv`
3. Enable Ruff plugin

---

## 9.10 Полезные команды

```powershell
# Статус Docker контейнеров
docker-compose ps

# Логи API
docker-compose logs -f api

# Подключиться к PostgreSQL
docker-compose exec postgres psql -U pid_user -d pid_pipeline

# Redis CLI
docker-compose exec redis redis-cli

# Проверить Celery workers
celery -A worker.celery_app status

# Inspect активные задачи
celery -A worker.celery_app inspect active
```л
pytest tests/test_api/test_diagrams.py

# Verbose
pytest -v
```

### Пример теста API

```python
# tests/test_api/test_diagrams.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
```

### Фикстуры

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from app.db.base import Base

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
```

---

## 9.5 Стиль кода

### Линтинг (Ruff)

```powershell
# Проверка
ruff check app/ worker/

# Автоисправление
ruff check --fix app/ worker/
```

### Форматирование

```powershell
ruff format app/ worker/
```

### Type checking (MyPy)

```powershell
mypy app/ worker/
```

---

## 9.6 Git workflow

### Ветки

- `main` — стабильная версия
- `develop` — разработка
- `feature/xxx` — новые функции
- `fix/xxx` — исправления

### Коммиты

Формат: `type(scope): description`

```
feat(api): add segmentation endpoint
fix(worker): handle timeout in detection
docs(readme): update installation guide
refactor(models): rename Diagram fields
```

---

## 9.7 Отладка

### FastAPI

```python
# Включить debug в .env
API_DEBUG=true

# Или в коде
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Celery

```powershell
# Verbose logging
celery -A worker.celery_app worker --loglevel=debug
```

### SQL queries

```python
# В session.py
engine = create_engine(url, echo=True)  # Логировать SQL
```

---

## 9.8 Частые задачи

### Сбросить БД

```powershell
python scripts/init_db.py --drop
```

### Очистить storage

```powershell
Remove-Item -Recurse -Force storage\diagrams\*
```

### Перезапустить worker

```powershell
# Очистить очередь Redis
docker-compose exec redis redis-cli FLUSHALL

# Запустить заново
celery -A worker.celery_app worker --loglevel=info
```

---

## 9.9 IDE настройки

### VS Code

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
    "python.linting.enabled": true,
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.formatOnSave": true
    }
}
```
