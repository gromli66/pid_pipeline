# 5. База данных

## 5.1 Обзор

**СУБД:** PostgreSQL 15

**Подключение:**
- Host: `localhost` (dev) / `postgres` (Docker)
- Port: `5433`
- Database: `pid_pipeline`

**ORM:** SQLAlchemy 2.0 с async поддержкой

---

## 5.2 Схема базы данных

### ER-диаграмма

```
┌─────────────────────────────────────────────────────────────┐
│                        projects                              │
├─────────────────────────────────────────────────────────────┤
│ PK │ code: VARCHAR(50)                                       │
│    │ name: VARCHAR(200)                                      │
│    │ cvat_project_id: INTEGER (nullable)                     │
│    │ cvat_project_name: VARCHAR(200)                         │
│    │ config_path: VARCHAR(500)                               │
│    │ created_at, updated_at: TIMESTAMP                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ 1:N
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        diagrams                              │
├─────────────────────────────────────────────────────────────┤
│ PK │ uid: UUID                                               │
│ FK │ project_code: VARCHAR(50)                               │
│    │ number: INTEGER (unique)                                │
│    │ original_filename: VARCHAR(255)                         │
│    │ status: ENUM(DiagramStatus)                             │
│    │ error_message, error_stage                              │
│    │ cvat_task_id, cvat_job_id                               │
│    │ image_width, image_height                               │
│    │ detection_count, validated_detection_count              │
│    │ segmentation_pixels, junction_count, bridge_count       │
│    │ node_count, edge_count                                  │
│    │ created_at, updated_at: TIMESTAMP                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │ 1:N            │ 1:N            │
          ▼                ▼                
┌─────────────────┐  ┌─────────────────┐
│    artifacts    │  │processing_stages│
├─────────────────┤  ├─────────────────┤
│ PK │ id: SERIAL │  │ PK │ id: SERIAL │
│ FK │ diagram_uid│  │ FK │ diagram_uid│
│    │ type: ENUM │  │    │ stage_type │
│    │ file_path  │  │    │ status     │
│    │ file_size  │  │    │ attempt    │
│    │ mime_type  │  │    │ task_id    │
│    │ for_training│ │    │ started_at │
│    │ created_at │  │    │ completed  │
└─────────────────┘  │    │ duration   │
                     │    │ error_msg  │
                     │    │ metrics    │
                     └─────────────────┘
```

---

## 5.3 Таблицы

### 5.3.1 `projects`

Проекты P&ID (термогидравлика, электрика и т.д.)

```sql
CREATE TABLE projects (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    
    -- CVAT интеграция
    cvat_project_id INTEGER,           -- NULL если не создан в CVAT
    cvat_project_name VARCHAR(200),
    
    -- Конфигурация
    config_path VARCHAR(500),          -- Путь к YAML конфигу
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Связь с YAML конфигами:**

Каждый проект имеет YAML конфиг в `configs/projects/{code}.yaml`, который содержит:
- Список классов для CVAT
- Путь к весам YOLO модели
- Маппинг классов YOLO → CVAT

### 5.3.2 `diagrams`

Основная таблица с метаданными диаграмм.

```sql
CREATE TABLE diagrams (
    uid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Project reference
    project_code VARCHAR(50) NOT NULL REFERENCES projects(code),
    
    number INTEGER NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'uploaded',
    error_message TEXT,
    error_stage VARCHAR(50),
    
    -- CVAT
    cvat_task_id INTEGER,
    cvat_job_id INTEGER,
    
    -- Image metadata
    image_width INTEGER,
    image_height INTEGER,
    
    -- Statistics
    detection_count INTEGER,
    validated_detection_count INTEGER,
    segmentation_pixels INTEGER,
    junction_count INTEGER,
    bridge_count INTEGER,
    node_count INTEGER,
    edge_count INTEGER,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_diagrams_status ON diagrams(status);
CREATE INDEX ix_diagrams_project_code ON diagrams(project_code);
```

### 5.3.3 `artifacts`

Файлы, создаваемые в процессе обработки.

```sql
CREATE TABLE artifacts (
    id SERIAL PRIMARY KEY,
    diagram_uid UUID NOT NULL REFERENCES diagrams(uid) ON DELETE CASCADE,
    
    artifact_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),
    
    for_training BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_artifacts_diagram_uid ON artifacts(diagram_uid);
CREATE INDEX ix_artifacts_type ON artifacts(artifact_type);
```

### 5.3.4 `processing_stages`

История выполнения этапов обработки.

```sql
CREATE TABLE processing_stages (
    id SERIAL PRIMARY KEY,
    diagram_uid UUID NOT NULL REFERENCES diagrams(uid) ON DELETE CASCADE,
    
    stage_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt INTEGER DEFAULT 1,
    
    celery_task_id VARCHAR(255),
    
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds FLOAT,
    
    error_message TEXT,
    error_traceback TEXT,
    
    metrics_json TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_processing_stages_diagram_uid ON processing_stages(diagram_uid);
CREATE INDEX ix_processing_stages_type ON processing_stages(stage_type);
```

---

## 5.4 Enum типы

### DiagramStatus

```python
class DiagramStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    DETECTING = "detecting"
    DETECTED = "detected"
    VALIDATING_BBOX = "validating_bbox"
    VALIDATED_BBOX = "validated_bbox"
    SEGMENTING = "segmenting"
    SEGMENTED = "segmented"
    SKELETONIZING = "skeletonizing"
    SKELETONIZED = "skeletonized"
    CLASSIFYING_JUNCTIONS = "classifying_junctions"
    CLASSIFIED = "classified"
    VALIDATING_MASKS = "validating_masks"
    VALIDATED_MASKS = "validated_masks"
    BUILDING_GRAPH = "building_graph"
    BUILT = "built"
    VALIDATING_GRAPH = "validating_graph"
    VALIDATED_GRAPH = "validated_graph"
    GENERATING_FXML = "generating_fxml"
    COMPLETED = "completed"
    ERROR = "error"
```

### ArtifactType

```python
class ArtifactType(str, enum.Enum):
    ORIGINAL_IMAGE = "original_image"
    YOLO_PREDICTED = "yolo_predicted"
    YOLO_VALIDATED = "yolo_validated"
    COCO_PREDICTED = "coco_predicted"
    COCO_VALIDATED = "coco_validated"
    NODE_MASK = "node_mask"
    PIPE_MASK = "pipe_mask"
    PIPE_MASK_VALIDATED = "pipe_mask_validated"
    SKELETON = "skeleton"
    SKELETON_FINAL = "skeleton_final"
    JUNCTION_MASK = "junction_mask"
    BRIDGE_MASK = "bridge_mask"
    JUNCTION_MASK_VALIDATED = "junction_mask_validated"
    BRIDGE_MASK_VALIDATED = "bridge_mask_validated"
    GRAPH_JSON = "graph_json"
    GRAPH_VALIDATED = "graph_validated"
    FXML = "fxml"
```

---

## 5.5 Примеры запросов

### Получить диаграммы проекта

```python
from sqlalchemy import select
from app.models import Diagram

result = await session.execute(
    select(Diagram)
    .where(Diagram.project_code == "thermohydraulics")
    .order_by(Diagram.number.desc())
)
diagrams = result.scalars().all()
```

### Загрузить конфиг проекта

```python
from app.services.project_loader import get_project_loader

loader = get_project_loader()
config = loader.load("thermohydraulics")
print(f"Classes: {config.num_classes}")
print(f"YOLO mapping: {config.yolo.class_mapping}")
```

---

## 5.6 Миграции / Бэкапы

```bash
# Создание миграции
alembic revision --autogenerate -m "Add new field"

# Применение
alembic upgrade head

# Бэкап
docker-compose exec postgres pg_dump -U pid_user pid_pipeline > backup.sql

# Восстановление
docker-compose exec -T postgres psql -U pid_user pid_pipeline < backup.sql
```
