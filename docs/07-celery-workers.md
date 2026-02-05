# 7. Celery Workers

## 7.1 Обзор

**Celery** используется для выполнения ресурсоёмких ML задач в фоновом режиме.

**Broker:** Redis

**Очереди:**
- `default` — обычные задачи (скелетизация, граф)
- `gpu` — задачи требующие GPU (YOLO, U2-Net++, Junction CNN)

---

## 7.2 Конфигурация

### Файл `worker/celery_app.py`

```python
from celery import Celery

celery_app = Celery(
    "pid_pipeline",
    broker="redis://localhost:6380/0",
    backend="redis://localhost:6380/0",
    include=[
        "worker.tasks.detection",
        "worker.tasks.segmentation",
        "worker.tasks.skeleton",
        "worker.tasks.junction",
        "worker.tasks.graph",
    ]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_time_limit=3600,        # 1 час максимум
    task_soft_time_limit=3300,   # Мягкий лимит 55 минут
    task_acks_late=True,         # Подтверждение после выполнения
    worker_prefetch_multiplier=1, # Для GPU задач
)
```

### Роутинг задач

```python
celery_app.conf.task_routes = {
    "worker.tasks.detection.*": {"queue": "gpu"},
    "worker.tasks.segmentation.*": {"queue": "gpu"},
    "worker.tasks.skeleton.*": {"queue": "default"},
    "worker.tasks.junction.*": {"queue": "gpu"},
    "worker.tasks.graph.*": {"queue": "default"},
}
```

---

## 7.3 Задачи

### 7.3.1 task_detect_yolo

**Файл:** `worker/tasks/detection.py`

**Назначение:** YOLO детекция объектов на схеме

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить изображение из storage
2. Выполнить YOLO inference с SAHI
3. Сохранить `yolo_predicted.txt`
4. Создать CVAT task
5. Импортировать аннотации в CVAT
6. Обновить статус → `detected`

**Retry:** 2 попытки с интервалом 60 сек

**Timeout:** 30 минут

```python
@celery_app.task(
    bind=True,
    name="worker.tasks.detection.task_detect_yolo",
    max_retries=2,
    default_retry_delay=60,
    time_limit=1800,
)
def task_detect_yolo(self, diagram_uid: str):
    ...
```

---

### 7.3.2 task_segment_pipes

**Файл:** `worker/tasks/segmentation.py`

**Назначение:** U2-Net++ сегментация труб

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить изображение
2. Создать node_mask из COCO
3. Выполнить U2-Net++ inference
4. Сохранить `pipe_mask.png`
5. Обновить статус → `segmented`

**Status:**  Phase 3

---

### 7.3.3 task_skeletonize

**Файл:** `worker/tasks/skeleton.py`

**Назначение:** Полная скелетизация маски труб

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить pipe_mask, node_mask
2. Выполнить скелетизацию
3. Сохранить `skeleton.png`
4. Обновить статус → `skeletonized`

**Status:**  Phase 3

---

### 7.3.4 task_skeletonize_simple

**Файл:** `worker/tasks/skeleton.py`

**Назначение:** Простая скелетизация валидированной маски

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Вызывается:** После валидации масок (Phase 4)

**Status:**  Phase 4

---

### 7.3.5 task_classify_junctions

**Файл:** `worker/tasks/junction.py`

**Назначение:** CNN классификация перекрёстков

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить skeleton, original image
2. Найти critical points
3. Классифицировать через CNN
4. Сохранить `junction_mask.png`, `bridge_mask.png`
5. Обновить статус → `classified`

**Status:**  Phase 4

---

### 7.3.6 task_build_graph

**Файл:** `worker/tasks/graph.py`

**Назначение:** Построение топологического графа

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить все маски
2. Выполнить GraphBuilder.build()
3. Сохранить `graph.json`
4. Обновить статус → `built`

**Status:**  Phase 5

---

### 7.3.7 task_generate_fxml

**Файл:** `worker/tasks/graph.py`

**Назначение:** Генерация FXML

**Параметры:**
- `diagram_uid: str` — UUID диаграммы

**Этапы выполнения:**
1. Загрузить validated_graph.json
2. Конвертировать в FXML
3. Сохранить `output.fxml`
4. Обновить статус → `completed`

**Status:** 🔄 Phase 5

---

## 7.4 Запуск Worker

### Локально (разработка)

```bash
# Активировать окружение
.venv\Scripts\activate

# Запустить worker
celery -A worker.celery_app worker --loglevel=info --concurrency=2

# С указанием очередей
celery -A worker.celery_app worker -Q default,gpu --loglevel=info
```

### В Docker

```bash
docker-compose up -d worker

# Логи
docker-compose logs -f worker
```

### Несколько workers

```bash
# Worker для GPU задач
celery -A worker.celery_app worker -Q gpu --concurrency=1 -n gpu@%h

# Worker для обычных задач
celery -A worker.celery_app worker -Q default --concurrency=4 -n default@%h
```

---

## 7.5 Мониторинг

### Flower (веб-интерфейс)

```bash
pip install flower
celery -A worker.celery_app flower --port=5555
```

Открыть: http://localhost:5555

### Командная строка

```bash
# Статус workers
celery -A worker.celery_app status

# Активные задачи
celery -A worker.celery_app inspect active

# Зарезервированные задачи
celery -A worker.celery_app inspect reserved

# Статистика
celery -A worker.celery_app inspect stats
```

---

## 7.6 Обработка ошибок

### Структура task с error handling

```python
@celery_app.task(bind=True, max_retries=2)
def task_example(self, diagram_uid: str):
    db = SessionLocal()
    
    try:
        # Основная логика
        ...
        
    except Exception as exc:
        # Обновить статус в БД
        diagram = db.query(Diagram).filter(Diagram.uid == diagram_uid).first()
        if diagram:
            diagram.status = DiagramStatus.ERROR
            diagram.error_message = str(exc)
            diagram.error_stage = "example_stage"
            db.commit()
        
        # Retry или fail
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
        
    finally:
        db.close()
```

### Типичные ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| CUDA out of memory | Большое изображение | Уменьшить batch size или tile size |
| Connection refused (Redis) | Redis не запущен | `docker-compose up -d redis` |
| Task timeout | Долгая обработка | Увеличить `time_limit` |
| FileNotFoundError | Файл не найден | Проверить storage path |

---

## 7.7 Best Practices

### 1. Всегда закрывать сессию БД

```python
finally:
    db.close()
```

### 2. Использовать bind=True для доступа к self

```python
@celery_app.task(bind=True)
def task_example(self, diagram_uid):
    print(f"Task ID: {self.request.id}")
    print(f"Retries: {self.request.retries}")
```

### 3. Логировать важные этапы

```python
print(f" Starting detection for {diagram_uid}")
print(f" Detected {count} objects")
print(f" Detection failed: {error}")
```

### 4. Сохранять промежуточные результаты

Если задача долгая, сохранять промежуточные файлы чтобы при retry не начинать сначала.

### 5. Использовать soft_time_limit для graceful shutdown

```python
from celery.exceptions import SoftTimeLimitExceeded

try:
    # Долгая операция
    ...
except SoftTimeLimitExceeded:
    # Сохранить состояние
    save_checkpoint()
    raise
```
