# 🏗️ P&ID Pipeline Application — План разработки

> **Версия:** 1.0  
> **Дата:** Февраль 2025  
> **Архитектура:** Monorepo, отдельная инфраструктура от CVAT

## 🎯 Ключевые решения

| Вопрос | Решение | Причина |
|--------|---------|---------|
| PostgreSQL | Отдельный контейнер | Изоляция от CVAT, независимые миграции |
| Celery/Redis | Отдельные | Независимые очереди, изоляция GPU задач |
| Docker Compose | Свой + CVAT external | Полный контроль, простое обновление CVAT |
| Status updates | HTTP Polling (MVP) | Проще, заменяемый на WebSocket потом |
| Batch processing | Нет (MVP) | Добавим позже если нужно |
| Кэширование моделей | Нет | Загружаем каждый раз (проще) |

## 📋 Содержание
1. [Обзор архитектуры](#обзор-архитектуры)
2. [Структура проекта](#структура-проекта)
3. [Phase 1: Инфраструктура](#phase-1-инфраструктура)
4. [Phase 2: YOLO + CVAT блок](#phase-2-yolo--cvat-блок)
5. [Phase 3: Сегментация + Скелетизация](#phase-3-сегментация--скелетизация)
6. [Phase 4: Junction + Валидация масок](#phase-4-junction--валидация-масок)
7. [Phase 5: Граф + FXML](#phase-5-граф--fxml)
8. [Phase 6: Интеграция и polish](#phase-6-интеграция-и-polish)

---

## 🎯 Обзор архитектуры

### Полный пайплайн обработки

```
ИЗОБРАЖЕНИЕ
    ↓
[1] YOLO детекция → CVAT валидация bbox/polygon 
    → yolo_validated.txt + coco_validated.json
    ↓
[2] U2-Net++ сегментация (image + node_mask) 
    → pipe_mask.png
    ↓
[3] Скелетизация (полная) 
    → skeleton.png
    ↓
[4] Junction CNN классификация 
    → junction_mask.png + bridge_mask.png
    ↓
[5] Валидация масок в PySide6 (полилинии + квадраты)
    → validated_pipe_mask.png + validated_junction_mask.png
    ↓
[5.1] Простая скелетизация валидированной маски
    → final_skeleton.png
    ↓
[6] Graph Builder 
    → graph.json
    ↓
[7] Валидация графа в PySide6 
    → validated_graph.json
    ↓
[8] FXML генерация 
    → output.fxml
```

### Статусы диаграммы

```
uploaded 
→ detecting → detected 
→ validating_bbox → validated_bbox 
→ segmenting → segmented 
→ skeletonizing → skeletonized 
→ classifying_junctions → classified 
→ validating_masks → validated_masks 
→ building_graph → built 
→ validating_graph → validated_graph 
→ generating_fxml → completed
```

**Дополнительные статусы:**
- `error` — ошибка на любом этапе (+ `error_stage` для retry)
- `retrying` — повторный запуск после ошибки

### Status Provider (заменяемый модуль)

UI получает обновления статуса через абстрактный `StatusProvider`:

```
ui/services/
├── status_provider.py      # Абстрактный интерфейс
├── polling_provider.py     # HTTP Polling (MVP) — каждые 2 сек
└── websocket_provider.py   # WebSocket (потом) — мгновенно
```

**MVP:** HTTP Polling — проще, надёжнее, достаточно для процессов 1-5 мин

**Потом:** WebSocket — замена в одном месте без изменения UI кода

```python
# Переключение через конфиг:
STATUS_PROVIDER = "polling"  # или "websocket"
```

### Сохраняемые артефакты (для дообучения)

| Этап | Артефакт | Назначение |
|------|----------|------------|
| После CVAT | `yolo_validated.txt`, `coco_validated.json` | Дообучение YOLO |
| После валидации масок | `validated_pipe_mask.png` | Дообучение U2-Net++ |
| После валидации масок | `validated_junction_mask.png`, `validated_bridge_mask.png` | Дообучение Junction CNN |
| После валидации графа | `validated_graph.json` | Тестирование графовых нейросетей |
| Всегда | `original.png` | Исходное изображение |

---

## 📁 Структура проекта

```
pid_pipeline/
├── docker-compose.yml              # Наш compose
├── docker-compose.override.yml     # Локальные настройки
├── .env                            # Конфигурация
├── .env.example
│
├── cvat/                           # Git submodule или скрипты запуска CVAT
│   └── docker-compose.cvat.yml     # Симлинк или копия официального
│
├── alembic/                        # Миграции БД
│   ├── alembic.ini
│   └── versions/
│
├── app/                            # FastAPI Backend
│   ├── __init__.py
│   ├── main.py                     # FastAPI app
│   ├── config.py                   # Settings из .env
│   │
│   ├── api/                        # API endpoints
│   │   ├── __init__.py
│   │   ├── diagrams.py             # CRUD диаграмм
│   │   ├── detection.py            # YOLO endpoints
│   │   ├── segmentation.py         # U2-Net++ endpoints
│   │   ├── skeleton.py             # Скелетизация endpoints
│   │   ├── junction.py             # Junction CNN endpoints
│   │   ├── graph.py                # Graph builder endpoints
│   │   ├── cvat.py                 # CVAT интеграция
│   │   └── validation.py           # Валидация endpoints
│   │
│   ├── models/                     # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── diagram.py              # Diagram, DiagramStatus
│   │   ├── stage.py                # ProcessingStage
│   │   ├── artifact.py             # Artifact (файлы)
│   │   └── cvat_job.py             # CVAT задачи
│   │
│   ├── schemas/                    # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── diagram.py
│   │   ├── stage.py
│   │   └── responses.py
│   │
│   ├── services/                   # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── cvat_client.py          # CVAT API client
│   │   ├── storage.py              # Файловое хранилище
│   │   └── status_machine.py       # Переходы статусов
│   │
│   └── db/                         # Database
│       ├── __init__.py
│       ├── session.py              # SessionLocal
│       └── base.py                 # Base model
│
├── worker/                         # Celery Workers
│   ├── __init__.py
│   ├── celery_app.py               # Celery конфигурация
│   │
│   ├── tasks/                      # Celery tasks
│   │   ├── __init__.py
│   │   ├── detection.py            # task_detect_yolo
│   │   ├── segmentation.py         # task_segment_pipes
│   │   ├── skeleton.py             # task_skeletonize, task_skeletonize_simple
│   │   ├── junction.py             # task_classify_junctions
│   │   ├── graph.py                # task_build_graph
│   │   └── fxml.py                 # task_generate_fxml
│   │
│   └── utils/                      # Worker utilities
│       ├── __init__.py
│       ├── gpu_lock.py             # GPU semaphore
│       └── error_handling.py       # Retry logic
│
├── modules/                        # ML модули (существующие)
│   ├── yolo/                       # pid_node_detection
│   │   ├── inference/
│   │   │   └── detector.py         # NodeDetector
│   │   └── ...
│   │
│   ├── segmentation/               # pipe_segmentation
│   │   ├── cli.py
│   │   └── ...
│   │
│   ├── skeleton/                   # skeleton_extension
│   │   ├── core.py
│   │   ├── processing.py
│   │   └── ...
│   │
│   ├── junction/                   # junction_classifier
│   │   └── src/
│   │       ├── inference.py
│   │       └── ...
│   │
│   └── graph/                      # graph_builder
│       ├── core/
│       │   └── builder.py
│       ├── graph_to_fxml.py
│       └── ...
│
├── ui/                             # PySide6 Desktop App
│   ├── __init__.py
│   ├── main.py                     # Entry point
│   ├── app.py                      # QApplication
│   │
│   ├── windows/                    # Окна
│   │   ├── __init__.py
│   │   ├── main_window.py          # Главное окно
│   │   └── diagram_window.py       # Окно диаграммы
│   │
│   ├── widgets/                    # Виджеты
│   │   ├── __init__.py
│   │   ├── diagram_list.py         # Список диаграмм
│   │   ├── stage_progress.py       # Прогресс этапов
│   │   ├── cvat_browser.py         # Встроенный CVAT
│   │   └── action_buttons.py       # Кнопки действий
│   │
│   ├── editors/                    # Редакторы валидации
│   │   ├── __init__.py
│   │   ├── base_editor.py          # Базовый класс
│   │   ├── mask_editor.py          # Редактор масок (квадраты)
│   │   ├── polyline_editor.py      # Редактор полилиний
│   │   └── graph_editor.py         # Редактор графа
│   │
│   ├── services/                   # UI services
│   │   ├── __init__.py
│   │   ├── api_client.py           # HTTP client к FastAPI
│   │   ├── status_provider.py      # Абстрактный интерфейс
│   │   ├── polling_provider.py     # HTTP Polling (MVP)
│   │   └── websocket_provider.py   # WebSocket (потом)
│   │
│   └── resources/                  # Ресурсы
│       ├── styles.qss
│       └── icons/
│
├── storage/                        # Файловое хранилище (volume)
│   └── diagrams/
│       └── {uid}/
│           ├── original/
│           │   └── image.png
│           ├── detection/
│           │   ├── yolo_predicted.txt
│           │   ├── yolo_validated.txt
│           │   └── coco_validated.json
│           ├── segmentation/
│           │   ├── node_mask.png
│           │   ├── pipe_mask.png
│           │   └── validated_pipe_mask.png
│           ├── skeleton/
│           │   ├── skeleton.png
│           │   └── final_skeleton.png
│           ├── junction/
│           │   ├── junction_mask.png
│           │   ├── bridge_mask.png
│           │   ├── validated_junction_mask.png
│           │   └── validated_bridge_mask.png
│           ├── graph/
│           │   ├── graph.json
│           │   └── validated_graph.json
│           └── output/
│               └── output.fxml
│
├── tests/                          # Тесты
│   ├── conftest.py
│   ├── test_api/
│   ├── test_worker/
│   └── test_ui/
│
├── scripts/                        # Утилиты
│   ├── init_db.py
│   ├── create_cvat_project.py
│   └── migrate.py
│
├── requirements/
│   ├── base.txt
│   ├── api.txt
│   ├── worker.txt
│   └── ui.txt
│
├── Dockerfile.api
├── Dockerfile.worker
└── README.md
```

---

## 🔧 Phase 1: Инфраструктура

**Цель:** Рабочая инфраструктура с PostgreSQL, Redis, Celery, интеграция с CVAT

### 1.1 Docker Compose Setup

**Файл:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  # === НАША ИНФРАСТРУКТУРА ===
  
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: pid_pipeline
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"  # Другой порт чтобы не конфликтовать с CVAT
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"  # Другой порт
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    environment:
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/pid_pipeline
      - REDIS_URL=redis://redis:6379/0
      - CVAT_URL=${CVAT_URL}
      - CVAT_TOKEN=${CVAT_TOKEN}
      - STORAGE_PATH=/storage
    volumes:
      - ./app:/app
      - storage_data:/storage
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - pid_network
      - cvat_network  # Для связи с CVAT

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/pid_pipeline
      - REDIS_URL=redis://redis:6379/0
      - CVAT_URL=${CVAT_URL}
      - CVAT_TOKEN=${CVAT_TOKEN}
      - STORAGE_PATH=/storage
    volumes:
      - ./worker:/worker
      - ./modules:/modules
      - storage_data:/storage
      - /dev/shm:/dev/shm  # Для PyTorch
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - pid_network
      - cvat_network

volumes:
  postgres_data:
  redis_data:
  storage_data:

networks:
  pid_network:
    driver: bridge
  cvat_network:
    external: true
    name: cvat_cvat  # Имя сети CVAT (проверить через docker network ls)
```

### 1.2 Файл `.env`

```env
# Database
DB_USER=pid_user
DB_PASSWORD=secure_password_here

# CVAT
CVAT_URL=http://cvat_server:8080
CVAT_TOKEN=your_cvat_api_token
CVAT_PROJECT_ID=1

# Celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CELERY_TASK_TIME_LIMIT=3600

# Storage
STORAGE_PATH=/storage/diagrams

# ML Models
YOLO_WEIGHTS=/models/yolo/best.pt
U2NET_WEIGHTS=/models/u2net/best.pth
JUNCTION_WEIGHTS=/models/junction/best.pth
```

### 1.3 Dockerfile.api

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements/base.txt requirements/api.txt ./
RUN pip install --no-cache-dir -r api.txt

# App
COPY app/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### 1.4 Dockerfile.worker

```dockerfile
FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /worker

# System deps
RUN apt-get update && apt-get install -y \
    libpq-dev gcc libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements/base.txt requirements/worker.txt ./
RUN pip install --no-cache-dir -r worker.txt

# ML modules
COPY modules/ /modules/
ENV PYTHONPATH=/modules:$PYTHONPATH

# Worker
COPY worker/ .

CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

### 1.5 Database Models

**Файл:** `app/models/diagram.py`

```python
from sqlalchemy import Column, String, Integer, DateTime, Enum, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import datetime

from app.db.base import Base


class DiagramStatus(str, enum.Enum):
    # Upload
    UPLOADED = "uploaded"
    
    # Detection
    DETECTING = "detecting"
    DETECTED = "detected"
    VALIDATING_BBOX = "validating_bbox"
    VALIDATED_BBOX = "validated_bbox"
    
    # Segmentation
    SEGMENTING = "segmenting"
    SEGMENTED = "segmented"
    
    # Skeleton
    SKELETONIZING = "skeletonizing"
    SKELETONIZED = "skeletonized"
    
    # Junction
    CLASSIFYING_JUNCTIONS = "classifying_junctions"
    CLASSIFIED = "classified"
    
    # Mask validation
    VALIDATING_MASKS = "validating_masks"
    VALIDATED_MASKS = "validated_masks"
    
    # Graph
    BUILDING_GRAPH = "building_graph"
    BUILT = "built"
    VALIDATING_GRAPH = "validating_graph"
    VALIDATED_GRAPH = "validated_graph"
    
    # Output
    GENERATING_FXML = "generating_fxml"
    COMPLETED = "completed"
    
    # Error
    ERROR = "error"


class Diagram(Base):
    __tablename__ = "diagrams"
    
    uid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = Column(Integer, nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    
    status = Column(Enum(DiagramStatus), default=DiagramStatus.UPLOADED)
    error_message = Column(Text, nullable=True)
    error_stage = Column(String(50), nullable=True)
    
    # CVAT
    cvat_task_id = Column(Integer, nullable=True)
    cvat_job_id = Column(Integer, nullable=True)
    
    # Metadata
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    
    # Statistics per stage
    detection_count = Column(Integer, nullable=True)
    segmentation_pixels = Column(Integer, nullable=True)
    junction_count = Column(Integer, nullable=True)
    node_count = Column(Integer, nullable=True)
    edge_count = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    stages = relationship("ProcessingStage", back_populates="diagram")
    artifacts = relationship("Artifact", back_populates="diagram")
```

**Файл:** `app/models/artifact.py`

```python
class ArtifactType(str, enum.Enum):
    # Original
    ORIGINAL_IMAGE = "original_image"
    
    # Detection
    YOLO_PREDICTED = "yolo_predicted"
    YOLO_VALIDATED = "yolo_validated"
    COCO_VALIDATED = "coco_validated"
    
    # Segmentation
    NODE_MASK = "node_mask"
    PIPE_MASK = "pipe_mask"
    PIPE_MASK_VALIDATED = "pipe_mask_validated"
    
    # Skeleton
    SKELETON = "skeleton"
    SKELETON_FINAL = "skeleton_final"
    
    # Junction
    JUNCTION_MASK = "junction_mask"
    BRIDGE_MASK = "bridge_mask"
    JUNCTION_MASK_VALIDATED = "junction_mask_validated"
    BRIDGE_MASK_VALIDATED = "bridge_mask_validated"
    
    # Graph
    GRAPH_JSON = "graph_json"
    GRAPH_VALIDATED = "graph_validated"
    
    # Output
    FXML = "fxml"


class Artifact(Base):
    __tablename__ = "artifacts"
    
    id = Column(Integer, primary_key=True)
    diagram_uid = Column(UUID(as_uuid=True), ForeignKey("diagrams.uid"))
    
    artifact_type = Column(Enum(ArtifactType), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    diagram = relationship("Diagram", back_populates="artifacts")
```

### 1.6 Задачи Phase 1

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 1.1 | Создать структуру проекта | Все папки | 30 мин |
| 1.2 | Docker Compose + Dockerfiles | `docker-compose.yml`, `Dockerfile.*` | 1 час |
| 1.3 | Настроить .env | `.env`, `.env.example` | 15 мин |
| 1.4 | SQLAlchemy models | `app/models/*.py` | 1.5 часа |
| 1.5 | Alembic миграции | `alembic/` | 30 мин |
| 1.6 | FastAPI base app | `app/main.py`, `app/config.py` | 1 час |
| 1.7 | Celery конфигурация | `worker/celery_app.py` | 30 мин |
| 1.8 | Проверить связь с CVAT network | Scripts | 30 мин |
| 1.9 | Health checks | API endpoints | 30 мин |

**Итого Phase 1:** ~6-7 часов

---

## 🔍 Phase 2: YOLO + CVAT блок

**Цель:** Полный цикл детекции с валидацией в CVAT

### 2.1 API Endpoints

```python
# app/api/diagrams.py

@router.post("/upload")
async def upload_diagram(file: UploadFile):
    """
    1. Генерируем uid
    2. Сохраняем файл в storage/{uid}/original/
    3. Создаём запись в БД (status=uploaded)
    4. Возвращаем {uid, number, status}
    """
    pass

@router.get("/{uid}/status")
async def get_status(uid: UUID):
    """
    Возвращает полный статус диаграммы:
    - status, error_message, error_stage
    - cvat_url (если есть)
    - statistics (counts)
    - artifacts (список файлов)
    """
    pass

@router.post("/{uid}/retry")
async def retry_stage(uid: UUID):
    """
    Повторить последний failed этап
    """
    pass


# app/api/detection.py

@router.post("/{uid}/detect")
async def start_detection(uid: UUID):
    """
    1. Проверяем status == uploaded
    2. Обновляем status = detecting
    3. Запускаем task_detect_yolo.delay(uid)
    4. Возвращаем {status: detecting}
    """
    pass


# app/api/cvat.py

@router.post("/{uid}/open-cvat")
async def open_cvat_validation(uid: UUID):
    """
    1. Проверяем status == detected
    2. Обновляем status = validating_bbox
    3. Возвращаем {cvat_url}
    """
    pass

@router.post("/{uid}/fetch-annotations")
async def fetch_cvat_annotations(uid: UUID):
    """
    1. Проверяем status == validating_bbox
    2. GET CVAT annotations
    3. Конвертируем COCO → YOLO
    4. Сохраняем yolo_validated.txt, coco_validated.json
    5. Обновляем status = validated_bbox
    6. Возвращаем {status, annotation_count}
    """
    pass
```

### 2.2 Celery Task: Detection

**Файл:** `worker/tasks/detection.py`

```python
@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=1800,
    acks_late=True
)
def task_detect_yolo(self, diagram_uid: str):
    """
    YOLO детекция с SAHI.
    
    Этапы:
    1. Загрузить изображение из storage
    2. NodeDetector.detect()
    3. Сохранить yolo_predicted.txt
    4. Создать CVAT task + job
    5. Импортировать аннотации в CVAT
    6. Обновить статус → detected
    """
    try:
        # 1. Load image
        image_path = get_artifact_path(diagram_uid, ArtifactType.ORIGINAL_IMAGE)
        
        # 2. Detect
        detector = NodeDetector(
            weights=settings.YOLO_WEIGHTS,
            confidence=0.8,
            device="cuda"
        )
        detections = detector.detect(image_path)
        
        # 3. Save predictions
        yolo_path = save_yolo_predictions(diagram_uid, detections)
        save_artifact(diagram_uid, ArtifactType.YOLO_PREDICTED, yolo_path)
        
        # 4. Create CVAT task
        cvat_client = CVATClient()
        task_id, job_id = cvat_client.create_task(
            name=f"PID_{diagram_uid[:8]}",
            project_id=settings.CVAT_PROJECT_ID,
            image_path=image_path
        )
        
        # 5. Import annotations to CVAT
        coco_data = convert_yolo_to_coco(detections, image_path)
        cvat_client.import_annotations(task_id, coco_data)
        
        # 6. Update status
        update_diagram(diagram_uid, 
            status=DiagramStatus.DETECTED,
            cvat_task_id=task_id,
            cvat_job_id=job_id,
            detection_count=len(detections)
        )
        
    except Exception as exc:
        handle_task_error(self, diagram_uid, "detecting", exc)
        raise
```

### 2.3 CVAT Client

**Файл:** `app/services/cvat_client.py`

```python
class CVATClient:
    """Клиент для работы с CVAT API."""
    
    def __init__(self):
        self.base_url = settings.CVAT_URL
        self.headers = {"Authorization": f"Token {settings.CVAT_TOKEN}"}
    
    def create_task(self, name: str, project_id: int, image_path: Path) -> Tuple[int, int]:
        """Создать task и вернуть (task_id, job_id)"""
        # POST /api/tasks
        # POST /api/tasks/{id}/data
        # GET /api/tasks/{id}/jobs
        pass
    
    def import_annotations(self, task_id: int, coco_data: dict):
        """Импортировать COCO аннотации в task"""
        # PUT /api/tasks/{id}/annotations
        pass
    
    def export_annotations(self, task_id: int) -> dict:
        """Экспортировать аннотации в COCO формате"""
        # GET /api/tasks/{id}/annotations?format=COCO
        pass
    
    def get_job_url(self, task_id: int, job_id: int) -> str:
        """Получить URL для открытия job в браузере"""
        return f"{self.base_url}/tasks/{task_id}/jobs/{job_id}"
```

### 2.4 PySide6 UI для YOLO блока

**Файл:** `ui/windows/main_window.py`

```python
class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    
    Layout:
    ┌─────────────────────────────────────────────────┐
    │  [📂 Загрузить]  [🔄 Обновить]                   │
    ├─────────────────────────────────────────────────┤
    │  # │ Файл          │ Статус        │ Дата  │ → │
    │  1 │ scheme_001.png│ ✅ completed  │ 01.02 │ → │
    │  2 │ scheme_002.png│ 🔄 detecting  │ 01.02 │ → │
    │  3 │ scheme_003.png│ ❌ error      │ 01.02 │ → │
    └─────────────────────────────────────────────────┘
    """
    pass
```

**Файл:** `ui/windows/diagram_window.py`

```python
class DiagramWindow(QMainWindow):
    """
    Окно конкретной диаграммы.
    
    Layout:
    ┌─────────────────────────────────────────────────┐
    │  #004 scheme_001.png           Этап 2 из 8     │
    ├─────────────────────────────────────────────────┤
    │                                                 │
    │  Статус: detected                              │
    │  ✅ YOLO нашёл 47 объектов                      │
    │                                                 │
    │  [🔍 Открыть в CVAT]  [✅ Подтвердить]          │
    │                                                 │
    ├─────────────────────────────────────────────────┤
    │  ┌─────────────────────────────────────────┐   │
    │  │                                         │   │
    │  │         CVAT WebView                    │   │
    │  │                                         │   │
    │  └─────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────┘
    """
    pass
```

### 2.5 Задачи Phase 2

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 2.1 | API endpoints upload/status | `app/api/diagrams.py` | 2 часа |
| 2.2 | API endpoints detection | `app/api/detection.py` | 1 час |
| 2.3 | CVAT Client | `app/services/cvat_client.py` | 3 часа |
| 2.4 | API endpoints CVAT | `app/api/cvat.py` | 2 часа |
| 2.5 | Celery task detection | `worker/tasks/detection.py` | 2 часа |
| 2.6 | Storage service | `app/services/storage.py` | 1.5 часа |
| 2.7 | YOLO → COCO конвертер | `worker/utils/converters.py` | 1 час |
| 2.8 | UI: MainWindow | `ui/windows/main_window.py` | 2 часа |
| 2.9 | UI: DiagramWindow + CVAT WebView | `ui/windows/diagram_window.py` | 3 часа |
| 2.10 | UI: API Client | `ui/services/api_client.py` | 1.5 часа |
| 2.11 | UI: StatusProvider (polling) | `ui/services/polling_provider.py` | 1 час |
| 2.12 | Интеграционные тесты | `tests/` | 2 часа |

**Итого Phase 2:** ~22 часа

---

## 🔬 Phase 3: Сегментация + Скелетизация

**Цель:** U2-Net++ сегментация труб и скелетизация

### 3.1 API Endpoints

```python
# app/api/segmentation.py

@router.post("/{uid}/segment")
async def start_segmentation(uid: UUID):
    """
    1. Проверяем status == validated_bbox
    2. Обновляем status = segmenting
    3. Запускаем task_segment_pipes.delay(uid)
    """
    pass


# app/api/skeleton.py

@router.post("/{uid}/skeletonize")
async def start_skeletonization(uid: UUID):
    """
    1. Проверяем status == segmented
    2. Обновляем status = skeletonizing
    3. Запускаем task_skeletonize.delay(uid)
    """
    pass
```

### 3.2 Celery Tasks

```python
# worker/tasks/segmentation.py

@celery_app.task(bind=True, max_retries=2, time_limit=3600)
def task_segment_pipes(self, diagram_uid: str):
    """
    U2-Net++ сегментация.
    
    Этапы:
    1. Загрузить изображение
    2. Создать node_mask из COCO (coco_validated.json)
    3. Запустить U2-Net++ inference
    4. Сохранить pipe_mask.png
    5. Обновить статус → segmented
    """
    pass


# worker/tasks/skeleton.py

@celery_app.task(bind=True, max_retries=2, time_limit=1800)
def task_skeletonize(self, diagram_uid: str):
    """
    Полная скелетизация.
    
    Этапы:
    1. Загрузить pipe_mask.png, node_mask.png
    2. Запустить skeleton_extension.core pipeline
    3. Сохранить skeleton.png
    4. Обновить статус → skeletonized
    """
    pass


@celery_app.task(bind=True, max_retries=1, time_limit=600)
def task_skeletonize_simple(self, diagram_uid: str):
    """
    Простая скелетизация валидированной маски.
    Вызывается после валидации масок (этап 5.1)
    """
    pass
```

### 3.3 Задачи Phase 3

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 3.1 | API endpoints segmentation | `app/api/segmentation.py` | 1 час |
| 3.2 | API endpoints skeleton | `app/api/skeleton.py` | 1 час |
| 3.3 | COCO → Node mask конвертер | `worker/utils/mask_converter.py` | 1.5 часа |
| 3.4 | Celery task segmentation | `worker/tasks/segmentation.py` | 2 часа |
| 3.5 | Celery task skeletonize | `worker/tasks/skeleton.py` | 2 часа |
| 3.6 | Celery task skeletonize_simple | `worker/tasks/skeleton.py` | 1 час |
| 3.7 | UI: Кнопки сегментации | `ui/windows/diagram_window.py` | 1 час |
| 3.8 | Тесты | `tests/` | 1.5 часа |

**Итого Phase 3:** ~11 часов

---

## 🔀 Phase 4: Junction + Валидация масок

**Цель:** Классификация перекрёстков и валидация в PySide6

### 4.1 API Endpoints

```python
# app/api/junction.py

@router.post("/{uid}/classify-junctions")
async def start_junction_classification(uid: UUID):
    """
    1. Проверяем status == skeletonized
    2. Обновляем status = classifying_junctions
    3. Запускаем task_classify_junctions.delay(uid)
    """
    pass


# app/api/validation.py

@router.post("/{uid}/start-mask-validation")
async def start_mask_validation(uid: UUID):
    """
    1. Проверяем status == classified
    2. Обновляем status = validating_masks
    3. Возвращаем пути к маскам для редактора
    """
    pass

@router.post("/{uid}/save-validated-masks")
async def save_validated_masks(uid: UUID, masks: ValidatedMasksRequest):
    """
    1. Сохраняем validated_pipe_mask.png
    2. Сохраняем validated_junction_mask.png
    3. Сохраняем validated_bridge_mask.png
    4. Запускаем task_skeletonize_simple.delay(uid)
    5. После завершения → status = validated_masks
    """
    pass
```

### 4.2 Celery Task

```python
# worker/tasks/junction.py

@celery_app.task(bind=True, max_retries=2, time_limit=1800)
def task_classify_junctions(self, diagram_uid: str):
    """
    Junction CNN классификация.
    
    Этапы:
    1. Загрузить skeleton.png, original.png
    2. Найти critical points
    3. Классифицировать через CNN
    4. Создать junction_mask.png, bridge_mask.png
    5. Обновить статус → classified
    """
    pass
```

### 4.3 UI: Редакторы валидации

```python
# ui/editors/mask_validation_window.py

class MaskValidationWindow(QMainWindow):
    """
    Окно валидации масок (труб + перекрёстков).
    
    Использует:
    - PolylineMaskEditor для труб
    - SquareMaskEditor для junction/bridge
    
    Layout:
    ┌─────────────────────────────────────────────────┐
    │  Валидация масок — scheme_001.png              │
    ├─────────────────────────────────────────────────┤
    │  [Трубы] [Перекрёстки] [Мосты]                 │ ← Tabs
    ├─────────────────────────────────────────────────┤
    │  ┌─────────────────────────────────────────┐   │
    │  │                                         │   │
    │  │    Editor (Polyline или Square)         │   │
    │  │                                         │   │
    │  └─────────────────────────────────────────┘   │
    ├─────────────────────────────────────────────────┤
    │  [↶ Undo]  [💾 Сохранить]  [✅ Подтвердить]    │
    └─────────────────────────────────────────────────┘
    """
    pass
```

### 4.4 Задачи Phase 4

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 4.1 | API endpoints junction | `app/api/junction.py` | 1 час |
| 4.2 | API endpoints validation | `app/api/validation.py` | 1.5 часа |
| 4.3 | Celery task junction | `worker/tasks/junction.py` | 2 часа |
| 4.4 | Адаптировать PolylineMaskEditor | `ui/editors/polyline_editor.py` | 2 часа |
| 4.5 | Адаптировать SquareMaskEditor | `ui/editors/mask_editor.py` | 1.5 часа |
| 4.6 | UI: MaskValidationWindow | `ui/editors/mask_validation_window.py` | 3 часа |
| 4.7 | Интеграция с API | `ui/services/` | 1.5 часа |
| 4.8 | Тесты | `tests/` | 1.5 часа |

**Итого Phase 4:** ~14 часов

---

## 📊 Phase 5: Граф + FXML

**Цель:** Построение графа, валидация, генерация FXML

### 5.1 API Endpoints

```python
# app/api/graph.py

@router.post("/{uid}/build-graph")
async def start_graph_building(uid: UUID):
    """
    1. Проверяем status == validated_masks
    2. Обновляем status = building_graph
    3. Запускаем task_build_graph.delay(uid)
    """
    pass

@router.post("/{uid}/start-graph-validation")
async def start_graph_validation(uid: UUID):
    """
    1. Проверяем status == built
    2. Обновляем status = validating_graph
    3. Возвращаем путь к graph.json
    """
    pass

@router.post("/{uid}/save-validated-graph")
async def save_validated_graph(uid: UUID, graph: dict):
    """
    1. Сохраняем validated_graph.json
    2. Обновляем status = validated_graph
    """
    pass

@router.post("/{uid}/generate-fxml")
async def start_fxml_generation(uid: UUID):
    """
    1. Проверяем status == validated_graph
    2. Обновляем status = generating_fxml
    3. Запускаем task_generate_fxml.delay(uid)
    """
    pass
```

### 5.2 Celery Tasks

```python
# worker/tasks/graph.py

@celery_app.task(bind=True, max_retries=2, time_limit=1800)
def task_build_graph(self, diagram_uid: str):
    """
    Построение графа.
    
    Этапы:
    1. Загрузить final_skeleton.png, node_mask, junction_mask, bridge_mask
    2. GraphBuilder.build()
    3. Сохранить graph.json
    4. Обновить статус → built
    """
    pass


# worker/tasks/fxml.py

@celery_app.task(bind=True, max_retries=1, time_limit=300)
def task_generate_fxml(self, diagram_uid: str):
    """
    Генерация FXML.
    
    Этапы:
    1. Загрузить validated_graph.json
    2. graph_to_fxml.convert()
    3. Сохранить output.fxml
    4. Обновить статус → completed
    """
    pass
```

### 5.3 UI: Редактор графа

```python
# ui/editors/graph_validation_window.py

class GraphValidationWindow(QMainWindow):
    """
    Окно валидации графа.
    
    Использует GraphValidatorEditor из pipeline_prototype.py
    
    Layout:
    ┌─────────────────────────────────────────────────┐
    │  Валидация графа — scheme_001.png              │
    ├─────────────────────────────────────────────────┤
    │  [➕ Ребро] [➖ Ребро] [⊕ Коннектор] [⊖ Узел]  │
    │  [📐 Оптимизировать] [✋ Двигать]              │
    ├─────────────────────────────────────────────────┤
    │  ┌─────────────────────────────────────────┐   │
    │  │                                         │   │
    │  │        GraphValidatorEditor             │   │
    │  │                                         │   │
    │  └─────────────────────────────────────────┘   │
    ├─────────────────────────────────────────────────┤
    │  Nodes: 52 | Edges: 48 | Connected: 50        │
    ├─────────────────────────────────────────────────┤
    │  [↶ Undo]  [💾 Сохранить]  [✅ Подтвердить]    │
    └─────────────────────────────────────────────────┘
    """
    pass
```

### 5.4 Задачи Phase 5

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 5.1 | API endpoints graph | `app/api/graph.py` | 2 часа |
| 5.2 | Celery task graph | `worker/tasks/graph.py` | 2 часа |
| 5.3 | Celery task fxml | `worker/tasks/fxml.py` | 1 час |
| 5.4 | Адаптировать GraphValidatorEditor | `ui/editors/graph_editor.py` | 2 часа |
| 5.5 | UI: GraphValidationWindow | `ui/editors/graph_validation_window.py` | 2 часа |
| 5.6 | Download FXML функция | `ui/windows/diagram_window.py` | 1 час |
| 5.7 | Тесты | `tests/` | 1.5 часа |

**Итого Phase 5:** ~11.5 часов

---

## 🎨 Phase 6: Интеграция и polish

**Цель:** Финальная интеграция, UI polish, документация

### 6.1 Задачи

| # | Задача | Файлы | Время |
|---|--------|-------|-------|
| 6.1 | Status machine (все переходы) | `app/services/status_machine.py` | 2 часа |
| 6.2 | Error handling во всех tasks | `worker/utils/error_handling.py` | 2 часа |
| 6.3 | Retry логика в UI | `ui/windows/diagram_window.py` | 1.5 часа |
| 6.4 | Progress indicators | `ui/widgets/stage_progress.py` | 2 часа |
| 6.5 | Стили и темы | `ui/resources/styles.qss` | 1.5 часа |
| 6.6 | Логирование | Везде | 2 часа |
| 6.7 | E2E тесты | `tests/e2e/` | 3 часа |
| 6.8 | README и документация | `README.md`, `docs/` | 2 часа |
| 6.9 | Docker production build | `Dockerfile.*` | 1 час |
| 6.10 | CI/CD (опционально) | `.github/workflows/` | 2 часа |

**Итого Phase 6:** ~19 часов

---

## 📅 Общая оценка времени

| Phase | Описание | Часы |
|-------|----------|------|
| 1 | Инфраструктура | 6-7 |
| 2 | YOLO + CVAT | 22 |
| 3 | Сегментация + Скелет | 11 |
| 4 | Junction + Валидация масок | 14 |
| 5 | Граф + FXML | 11.5 |
| 6 | Интеграция | 19 |
| **ИТОГО** | | **~84 часа** |

При работе 4-6 часов/день = **2-3 недели**

---

## 🚀 Quick Start (после завершения)

```bash
# 1. Запустить CVAT (отдельно)
cd ~/cvat && docker-compose up -d

# 2. Запустить наше приложение
cd ~/pid_pipeline
cp .env.example .env
# Отредактировать .env (CVAT_TOKEN и т.д.)

docker-compose up -d

# 3. Инициализировать БД
docker-compose exec api python scripts/init_db.py

# 4. Запустить UI
cd ui && python main.py
```

---

## 📝 Следующие шаги

1. **Подтверди план** — есть ли что-то что нужно изменить?
2. **Начинаем с Phase 1** — создаём структуру проекта и Docker
3. **Итеративно** — после каждой phase тестируем и фиксим

**Готов начинать?**
