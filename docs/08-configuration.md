# 8. Конфигурация

## 8.1 Переменные окружения

Все настройки хранятся в файле `.env` и читаются через `pydantic-settings`.

### Файл `.env.example`

```env
# =============================================================================
# P&ID Pipeline Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# Database (PostgreSQL)
# -----------------------------------------------------------------------------
DB_USER=pid_user
DB_PASSWORD=change_me_secure_password
DB_NAME=pid_pipeline
DB_HOST=postgres
DB_PORT=5432

DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# -----------------------------------------------------------------------------
# Redis (Celery Broker)
# -----------------------------------------------------------------------------
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

CELERY_BROKER_URL=redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
CELERY_RESULT_BACKEND=redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}

# -----------------------------------------------------------------------------
# CVAT Integration
# -----------------------------------------------------------------------------
CVAT_URL=http://localhost:8080
CVAT_TOKEN=your_cvat_api_token_here
CVAT_PROJECT_ID=1
CVAT_NETWORK_NAME=cvat_cvat

# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------
STORAGE_PATH=/storage/diagrams

# -----------------------------------------------------------------------------
# ML Models
# -----------------------------------------------------------------------------
YOLO_WEIGHTS=/models/yolo/best.pt
U2NET_WEIGHTS=/models/u2net/best.pth
JUNCTION_WEIGHTS=/models/junction/best.pth

# -----------------------------------------------------------------------------
# Celery Worker
# -----------------------------------------------------------------------------
CELERY_TASK_TIME_LIMIT=3600
CELERY_CONCURRENCY=2

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true

# -----------------------------------------------------------------------------
# UI Settings
# -----------------------------------------------------------------------------
STATUS_POLL_INTERVAL=2000
STATUS_PROVIDER=polling

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL=INFO
```

---

## 8.2 Описание параметров

### Database

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `DB_USER` | string | pid_user | Пользователь PostgreSQL |
| `DB_PASSWORD` | string | - | Пароль (обязательный) |
| `DB_NAME` | string | pid_pipeline | Имя базы данных |
| `DB_HOST` | string | postgres | Хост (postgres в Docker) |
| `DB_PORT` | int | 5432 | Порт |
| `DATABASE_URL` | string | - | Полный connection string |

### Redis / Celery

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `REDIS_HOST` | string | redis | Хост Redis |
| `REDIS_PORT` | int | 6379 | Порт Redis |
| `CELERY_BROKER_URL` | string | - | URL брокера |
| `CELERY_RESULT_BACKEND` | string | - | URL backend результатов |
| `CELERY_TASK_TIME_LIMIT` | int | 3600 | Макс. время задачи (сек) |
| `CELERY_CONCURRENCY` | int | 2 | Кол-во worker процессов |

### CVAT

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `CVAT_URL` | string | http://localhost:8080 | URL CVAT сервера |
| `CVAT_TOKEN` | string | - | API токен (обязательный) |
| `CVAT_PROJECT_ID` | int | 1 | ID проекта в CVAT |
| `CVAT_NETWORK_NAME` | string | cvat_cvat | Имя Docker сети CVAT |

### Storage

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `STORAGE_PATH` | string | /storage/diagrams | Путь к хранилищу |

### ML Models

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `YOLO_WEIGHTS` | string | /models/yolo/best.pt | Путь к весам YOLO |
| `U2NET_WEIGHTS` | string | /models/u2net/best.pth | Путь к весам U2-Net++ |
| `JUNCTION_WEIGHTS` | string | /models/junction/best.pth | Путь к весам Junction CNN |

### API

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `API_HOST` | string | 0.0.0.0 | Хост API сервера |
| `API_PORT` | int | 8000 | Порт API |
| `API_DEBUG` | bool | false | Debug режим |

### UI

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `STATUS_POLL_INTERVAL` | int | 2000 | Интервал polling (мс) |
| `STATUS_PROVIDER` | string | polling | Провайдер: polling/websocket |

### Logging

| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| `LOG_LEVEL` | string | INFO | Уровень логирования |

---

## 8.3 Класс Settings

**Файл:** `app/config.py`

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://pid_user:changeme@localhost:5433/pid_pipeline"
    )
    
    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6380/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6380/0")
    CELERY_TASK_TIME_LIMIT: int = Field(default=3600)
    
    # CVAT
    CVAT_URL: str = Field(default="http://localhost:8080")
    CVAT_TOKEN: str | None = Field(default=None)
    CVAT_PROJECT_ID: int = Field(default=1)
    
    # Storage
    STORAGE_PATH: str = Field(default="./storage/diagrams")
    
    # ML Models
    YOLO_WEIGHTS: str = Field(default="./models/yolo/best.pt")
    U2NET_WEIGHTS: str = Field(default="./models/u2net/best.pth")
    JUNCTION_WEIGHTS: str = Field(default="./models/junction/best.pth")
    
    # API
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### Использование

```python
from app.config import settings

# Доступ к настройкам
database_url = settings.DATABASE_URL
cvat_token = settings.CVAT_TOKEN
```

---

## 8.4 Docker Compose конфигурация

### Переопределение через environment

```yaml
# docker-compose.yml
services:
  api:
    environment:
      - DATABASE_URL=postgresql://...
      - CVAT_URL=${CVAT_URL:-http://localhost:8080}
```

### docker-compose.override.yml

Для локальных настроек создайте `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  api:
    volumes:
      - ./app:/app/app  # Live reload
    environment:
      - API_DEBUG=true
      - LOG_LEVEL=DEBUG
  
  worker:
    environment:
      - LOG_LEVEL=DEBUG
```

---

## 8.5 Конфигурации для разных окружений

### Development

```env
# .env.dev
API_DEBUG=true
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://pid_user:devpass@localhost:5433/pid_pipeline
STORAGE_PATH=./storage/diagrams
```

### Production

```env
# .env.prod
API_DEBUG=false
LOG_LEVEL=WARNING
DATABASE_URL=postgresql://pid_user:SECURE_PASS@db.production.com:5432/pid_pipeline
STORAGE_PATH=/mnt/storage/diagrams
```

### Testing

```env
# .env.test
DATABASE_URL=postgresql://test_user:test@localhost:5433/pid_pipeline_test
STORAGE_PATH=./test_storage
```

---

## 8.6 Валидация конфигурации

### Проверка при запуске

```python
# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Проверка обязательных настроек
    if not settings.CVAT_TOKEN:
        print("⚠️ Warning: CVAT_TOKEN not set")
    
    if not Path(settings.STORAGE_PATH).exists():
        Path(settings.STORAGE_PATH).mkdir(parents=True)
        print(f"📁 Created storage directory: {settings.STORAGE_PATH}")
    
    yield
```

### Скрипт проверки

```python
# scripts/check_config.py
from app.config import settings

def check_config():
    errors = []
    
    # Database
    if "changeme" in settings.DATABASE_URL:
        errors.append("DATABASE_URL contains default password")
    
    # CVAT
    if not settings.CVAT_TOKEN:
        errors.append("CVAT_TOKEN is not set")
    
    # Models
    from pathlib import Path
    if not Path(settings.YOLO_WEIGHTS).exists():
        errors.append(f"YOLO weights not found: {settings.YOLO_WEIGHTS}")
    
    if errors:
        print("❌ Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("✅ Configuration OK")
    return True

if __name__ == "__main__":
    check_config()
```

---

## 8.7 Секреты

### Не коммитить в git

```gitignore
# .gitignore
.env
.env.prod
.env.local
```

### Использование Docker secrets (production)

```yaml
# docker-compose.prod.yml
services:
  api:
    secrets:
      - db_password
      - cvat_token
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
  cvat_token:
    file: ./secrets/cvat_token.txt
```
