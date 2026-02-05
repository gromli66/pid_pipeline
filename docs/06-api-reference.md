# 6. API Reference

## 6.1 Обзор

**Base URL:** `http://localhost:8000`

**Документация:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

**Формат:** JSON

---

## 6.2 Health Endpoints

### GET /health

```json
{"status": "healthy", "service": "pid-pipeline-api"}
```

---

## 6.3 Projects API

### GET /api/projects/

Получить список всех проектов.

**Response:**
```json
{
    "items": [
        {
            "code": "thermohydraulics",
            "name": "Термогидравлика",
            "cvat_project_id": null,
            "cvat_project_name": "P&ID Термогидравлика",
            "config_path": "configs/projects/thermohydraulics.yaml",
            "created_at": "2025-02-04T12:00:00",
            "updated_at": "2025-02-04T12:00:00"
        }
    ],
    "total": 1
}
```

---

### GET /api/projects/summary

Краткий список для выбора в UI.

**Response:**
```json
[
    {
        "code": "thermohydraulics",
        "name": "Термогидравлика",
        "has_cvat_project": false,
        "diagram_count": 5
    }
]
```

---

### GET /api/projects/{project_code}

Получить проект по коду.

**Response:** `200 OK`
```json
{
    "code": "thermohydraulics",
    "name": "Термогидравлика",
    "cvat_project_id": 1,
    "cvat_project_name": "P&ID Термогидравлика",
    "config_path": "configs/projects/thermohydraulics.yaml",
    "created_at": "2025-02-04T12:00:00",
    "updated_at": "2025-02-04T12:00:00"
}
```

---

### GET /api/projects/{project_code}/config

Получить конфигурацию из YAML.

**Response:**
```json
{
    "code": "thermohydraulics",
    "name": "Термогидравлика",
    "cvat_project_name": "P&ID Термогидравлика",
    "num_classes": 40,
    "yolo_num_classes": 36,
    "yolo_weights": "models/thermohydraulics/yolo/best.pt"
}
```

---

### GET /api/projects/{project_code}/classes

Получить список классов проекта.

**Response:**
```json
{
    "project_code": "thermohydraulics",
    "num_classes": 40,
    "classes": [
        {"id": 1, "name": "armatura_ruchn"},
        {"id": 2, "name": "klapan_obratn"},
        ...
    ]
}
```

---

## 6.4 Diagrams API

### POST /api/diagrams/upload

Загрузить новую диаграмму.

**Request:**
- Content-Type: `multipart/form-data`
- Body:
  - `file` — изображение (PNG, JPEG, TIFF)
  - `project_code` — код проекта (обязательно)

**Response:** `200 OK`
```json
{
    "uid": "550e8400-e29b-41d4-a716-446655440000",
    "number": 1,
    "project_code": "thermohydraulics",
    "status": "uploaded",
    "filename": "scheme_001.png"
}
```

**Пример (curl):**
```bash
curl -X POST "http://localhost:8000/api/diagrams/upload" \
  -F "file=@scheme_001.png" \
  -F "project_code=thermohydraulics"
```

**Пример (Python):**
```python
import httpx

with open("scheme.png", "rb") as f:
    response = httpx.post(
        "http://localhost:8000/api/diagrams/upload",
        files={"file": f},
        data={"project_code": "thermohydraulics"}
    )
    data = response.json()
    print(f"Uploaded: {data['uid']}")
```

---

### GET /api/diagrams/

Получить список диаграмм.

**Query Parameters:**
| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| skip | int | 0 | Пропустить N записей |
| limit | int | 50 | Максимум записей (1-100) |
| project_code | string | - | Фильтр по проекту |
| status | string | - | Фильтр по статусу |

**Response:**
```json
{
    "items": [
        {
            "uid": "550e8400-e29b-41d4-a716-446655440000",
            "number": 1,
            "project_code": "thermohydraulics",
            "original_filename": "scheme_001.png",
            "status": "uploaded",
            "image_width": 4900,
            "image_height": 3500,
            ...
        }
    ],
    "total": 1,
    "skip": 0,
    "limit": 50
}
```

---

### GET /api/diagrams/{uid}

Получить информацию о диаграмме.

---

### GET /api/diagrams/{uid}/status

Получить статус (для polling).

**Response:**
```json
{
    "status": "detecting",
    "error_message": null,
    "cvat_task_id": null,
    "detection_count": null,
    "updated_at": "2025-02-03T12:05:00"
}
```

---

### DELETE /api/diagrams/{uid}

Удалить диаграмму и все файлы.

---

## 6.5 Detection API

### POST /api/detection/{uid}/detect

Запустить YOLO детекцию.

**Precondition:** `status == "uploaded"`

**Response:**
```json
{
    "status": "detecting",
    "task_id": "abc123-celery-task-id",
    "uid": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 6.6 CVAT API

### POST /api/cvat/{uid}/open-validation

Открыть валидацию в CVAT.

**Response:**
```json
{
    "status": "validating_bbox",
    "cvat_url": "http://localhost:8080/tasks/123/jobs/456"
}
```

---

### POST /api/cvat/{uid}/fetch-annotations

Получить аннотации из CVAT.

---

## 6.7 Остальные API

| Endpoint | Статус |
|----------|--------|
| POST /api/segmentation/{uid}/segment |  Phase 3 |
| POST /api/skeleton/{uid}/skeletonize |  Phase 3 |
| POST /api/junction/{uid}/classify |  Phase 4 |
| POST /api/graph/{uid}/build |  Phase 5 |
| POST /api/graph/{uid}/generate-fxml |  Phase 5 |

---

## 6.8 Коды ошибок

| Код | Описание |
|-----|----------|
| 200 | Успешно |
| 400 | Некорректный запрос / Неизвестный проект |
| 404 | Диаграмма или проект не найден |
| 422 | Ошибка валидации данных |
| 500 | Внутренняя ошибка сервера |
