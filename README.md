# P&ID Pipeline

Приложение для автоматической обработки P&ID диаграмм с интегрированным CVAT.

## 🏗️ Архитектура

- **FastAPI** — Backend API
- **Celery** — Фоновые задачи (ML inference на GPU)
- **PostgreSQL** — База данных (отдельная для P&ID и CVAT)
- **Redis** — Message broker
- **CVAT** — Валидация аннотаций (встроен в docker-compose)
- **PySide6** — Desktop UI (разработка)

## 📁 Структура проекта

```
pid_pipeline/
├── app/                    # FastAPI Backend
│   ├── api/                # API endpoints
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   └── services/           # Business logic
├── worker/                 # Celery Workers
│   └── tasks/              # Celery tasks
├── modules/                # ML модули
│   └── yolo_detector/      # YOLO + SAHI детектор
├── ui/                     # PySide6 Desktop App
├── storage/                # Файловое хранилище (bind mount)
│   └── diagrams/           # Загруженные диаграммы
├── models/                 # ML веса (bind mount)
│   └── yolo/best.pt        # YOLO веса
├── configs/                # Конфигурации проектов
│   └── projects/           # YAML конфиги
├── alembic/                # Миграции БД
│   └── versions/           # Файлы миграций
├── docker-compose.yml      # Unified: P&ID + CVAT
└── .env                    # Конфигурация
```

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```powershell
git clone <repository-url>
cd pid_pipeline

# Создать .env из примера
copy .env.example .env
```

### 2. Подготовить ML веса

```powershell
# Скопировать YOLO веса в папку models
copy C:\path\to\best.pt models\yolo\best.pt
```

### 3. Запуск всех сервисов

```powershell
docker-compose up -d
```

Это запустит:
- P&ID API (порт 8000)
- P&ID Worker (Celery + GPU)
- CVAT (порт 8080)
- PostgreSQL (порт 5433 для P&ID)
- Redis

### 4. Применить миграции БД

```powershell
docker exec -it pid_api alembic upgrade head
```

### 5. Создать суперпользователя CVAT

```powershell
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

Ввести:
- Username: `admin`
- Email: (можно пустой)
- Password: `admin123`

### 6. Проверить работу

| Сервис | URL |
|--------|-----|
| P&ID API Docs | http://localhost:8000/docs |
| CVAT UI | http://localhost:8080 |
| Health Check | http://localhost:8000/health |

## 📊 Использование API

### Загрузка диаграммы

```bash
curl -X POST "http://localhost:8000/api/diagrams/upload" \
  -F "file=@diagram.png" \
  -F "project_code=thermohydraulics"
```

### Запуск детекции

```bash
curl -X POST "http://localhost:8000/api/detection/{uid}/detect"
```

### Получение статуса

```bash
curl "http://localhost:8000/api/diagrams/{uid}/status"
```

## 🔧 Разработка

### Локальный запуск API (без Docker)

```powershell
# Активировать venv
.venv\Scripts\activate

# Установить зависимости
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements/api.txt

# Запустить только инфраструктуру в Docker
docker-compose up -d postgres redis cvat_server cvat_ui traefik

# Запустить API локально
uvicorn app.main:app --reload --port 8000
```

### Создание новой миграции

```powershell
# После изменения моделей
docker exec -it pid_api alembic revision --autogenerate -m "Description"

# Применить
docker exec -it pid_api alembic upgrade head
```

### Просмотр логов

```powershell
# API
docker logs -f pid_api

# Worker
docker logs -f pid_worker

# CVAT
docker logs -f cvat_server
```

## 🐳 Docker команды

```powershell
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Перезапуск одного сервиса
docker-compose restart api

# Пересборка после изменений
docker-compose up -d --build api worker

# Полная очистка (удаляет данные!)
docker-compose down -v
```

## 📋 Статусы обработки диаграммы

```
uploaded → detecting → detected → validating_bbox → validated_bbox
→ segmenting → segmented → skeletonizing → skeletonized
→ classifying_junctions → classified → validating_masks → validated_masks
→ building_graph → built → validating_graph → validated_graph
→ generating_fxml → completed
```

## 📚 Документация

- [Обзор системы](docs/01-overview.md)
- [Архитектура](docs/02-architecture.md)
- [Установка](docs/03-installation.md)
- [Структура проекта](docs/04-project-structure.md)
- [База данных](docs/05-database.md)
- [API Reference](docs/06-api-reference.md)
- [Celery Workers](docs/07-celery-workers.md)
- [Конфигурация](docs/08-configuration.md)
- [Разработка](docs/09-development.md)
- [Troubleshooting](docs/10-troubleshooting.md)

## 🔑 Переменные окружения

Основные переменные в `.env`:

| Переменная | Описание | Default |
|------------|----------|---------|
| `DB_USER` | Пользователь PostgreSQL | `pid_user` |
| `DB_PASSWORD` | Пароль PostgreSQL | `changeme` |
| `CVAT_SUPERUSER` | Логин CVAT | `admin` |
| `CVAT_SUPERUSER_PASSWORD` | Пароль CVAT | `admin123` |
| `YOLO_DEVICE` | Устройство для YOLO | `cuda` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

## ⚠️ Важно

1. **YOLO веса** должны лежать в `models/yolo/best.pt`
2. **Миграции** применяются один раз при первом запуске
3. **CVAT суперпользователь** создаётся вручную после первого запуска
4. **Storage** использует bind mount — файлы видны в `storage/diagrams/`
