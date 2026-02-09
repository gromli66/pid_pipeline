# P&ID Pipeline

Приложение для автоматической обработки P&ID диаграмм с интегрированным CVAT.

## Архитектура

- **FastAPI** — Backend API
- **Celery** — Фоновые задачи (ML inference на GPU)
- **PostgreSQL** — База данных (отдельная для P&ID и CVAT)
- **Redis** — Message broker
- **CVAT** — Валидация аннотаций (встроен в docker-compose)
- **PySide6** — Desktop UI

## Структура проекта

```
pid_pipeline/
├── app/                    # FastAPI Backend
│   ├── api/                # API endpoints
│   ├── core/               # Logging, shared utilities
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic (CVATClient, Storage)
│   └── db/                 # Database session, engine
├── worker/                 # Celery Workers
│   └── tasks/              # Celery tasks
├── modules/                # ML модули
│   └── yolo_detector/      # YOLO + SAHI детектор
├── ui/                     # PySide6 Desktop App
│   ├── main.py             # Entry point
│   ├── windows/            # MainWindow, CVATWindow
│   ├── widgets/            # DiagramListWidget, UploadDialog
│   └── services/           # APIClient, StatusProvider
├── storage/                # Файловое хранилище (bind mount)
├── models/                 # ML веса (bind mount)
├── configs/                # Конфигурации проектов (YAML)
├── alembic/                # Миграции БД
├── docker-compose.yml      # Unified: P&ID + CVAT
├── .editorconfig           # Стиль кода
├── .gitattributes          # Нормализация line endings
└── .env                    # Конфигурация
```

## Быстрый старт

### 1. Клонирование и настройка

```powershell
git clone <repository-url>
cd pid_pipeline

# Создать .env из примера
copy .env.example .env
```

### 2. Подготовить ML веса

```powershell
copy C:\path\to\best.pt models\yolo\best.pt
```

### 3. Запуск всех сервисов

```powershell
docker-compose up -d
```

Это запустит: P&ID API (порт 8000), P&ID Worker (Celery + GPU), CVAT (порт 8080), PostgreSQL, Redis.

### 4. Применить миграции БД

```powershell
docker exec -it pid_api alembic upgrade head
```

### 5. Создать суперпользователя CVAT

```powershell
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

### 6. Проверить работу

```powershell
# Health check (должен показать healthy для api, database, redis)
Invoke-RestMethod http://localhost:8000/health
```

| Сервис | URL |
|--------|-----|
| P&ID API Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| CVAT UI | http://localhost:8080 |

## Desktop UI

Desktop-приложение на PySide6 для управления пайплайном.

### Запуск

```powershell
# Активировать venv
.venv311\Scripts\activate

# Запустить UI
python -m ui.main
```

### Возможности

- Загрузка P&ID диаграмм с выбором проекта
- Запуск YOLO детекции одной кнопкой
- Встроенный CVAT WebView для валидации аннотаций
- Автоматический polling статуса (обновление каждые 2 сек)
- Скачивание артефактов через API (оригинал, YOLO predicted/validated, COCO)
- Фильтры по проекту, статусу, поиск по имени файла
- Обработка ошибок: retry, перезагрузка оригинала

### Архитектура UI

```
MainWindow (координатор, 287 строк)
├── QTabWidget
│   └── DiagramListWidget (таблица + фильтры + действия, 611 строк)
├── StatusBar (🟢 API / 🔴 API недоступен)
└── ToolBar (Загрузить, Обновить)

CVATWindow (отдельное окно с QWebEngineView)

Services:
├── APIClient (persistent httpx.Client, retry с exponential backoff)
└── StatusProvider (HTTP polling, auto-unwatch на финальных статусах)
```

## API

### Основные endpoints

```bash
# Загрузка диаграммы
curl -X POST "http://localhost:8000/api/diagrams/upload" \
  -F "file=@diagram.png" \
  -F "project_code=thermohydraulics"

# Запуск детекции
curl -X POST "http://localhost:8000/api/detection/{uid}/detect"

# Статус
curl "http://localhost:8000/api/diagrams/{uid}/status"

# Скачивание артефакта
curl -O "http://localhost:8000/api/diagrams/{uid}/download/original_image"

# Health check
curl "http://localhost:8000/health"
```

### Типы артефактов для скачивания

| artifact_type | Описание |
|---------------|----------|
| `original_image` | Оригинальное изображение |
| `yolo_predicted` | YOLO предсказания (до валидации) |
| `yolo_validated` | YOLO после валидации в CVAT |
| `coco_validated` | COCO JSON после валидации |

Полный API Reference: [docs/06-api-reference.md](docs/06-api-reference.md)

## Разработка

### Перезапуск после изменений кода

```powershell
docker-compose restart api worker
docker logs --tail 15 pid_api
```

### Создание новой миграции

```powershell
docker exec -it pid_api alembic revision --autogenerate -m "Description"
docker exec -it pid_api alembic upgrade head
```

### Нормализация line endings (одноразово)

```bash
git add --renormalize .
git commit -m "Normalize line endings to LF"
```

### Просмотр логов

```powershell
docker logs -f pid_api      # API
docker logs -f pid_worker   # Worker
docker logs -f cvat_server  # CVAT
```

## Статусы обработки диаграммы

```
uploaded → detecting → detected → validating_bbox → validated_bbox
→ segmenting → segmented → skeletonizing → skeletonized
→ classifying_junctions → classified → validating_masks → validated_masks
→ building_graph → built → validating_graph → validated_graph
→ generating_fxml → completed
```

## Документация

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

## Переменные окружения

Основные переменные в `.env`:

| Переменная | Описание | Default |
|------------|----------|---------|
| `DB_USER` | Пользователь PostgreSQL | `pid_user` |
| `DB_PASSWORD` | Пароль PostgreSQL | `changeme` |
| `CVAT_SUPERUSER` | Логин CVAT | `admin` |
| `CVAT_SUPERUSER_PASSWORD` | Пароль CVAT | `admin123` |
| `YOLO_DEVICE` | Устройство для YOLO | `cuda` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
