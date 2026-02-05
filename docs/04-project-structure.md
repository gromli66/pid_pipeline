# 4. Структура проекта

## 4.1 Обзор

```
pid_pipeline/
│
├── app/                    # FastAPI Backend
├── worker/                 # Celery Workers
├── modules/                # ML модули (существующие)
├── ui/                     # PySide6 Desktop App
├── storage/                # Файловое хранилище
├── alembic/                # Миграции БД
├── scripts/                # Утилиты
├── tests/                  # Тесты
├── docs/                   # Документация
├── requirements/           # Python зависимости
│
├── docker-compose.yml      # Docker конфигурация
├── Dockerfile.api          # Образ для API
├── Dockerfile.worker       # Образ для Worker
├── alembic.ini             # Конфигурация Alembic
├── .env.example            # Пример переменных окружения
├── .env                    # Переменные окружения (не в git)
├── .gitignore              # Игнорируемые файлы
└── README.md               # Описание проекта
```

---

## 4.2 Детальная структура

### 4.2.1 `app/` — FastAPI Backend

```
app/
├── __init__.py             # Версия приложения
├── main.py                 # FastAPI app, роутеры, middleware
├── config.py               # Настройки из .env
│
├── api/                    # REST API endpoints
│   ├── __init__.py
│   ├── diagrams.py         # CRUD диаграмм (/api/diagrams)
│   ├── detection.py        # Детекция (/api/detection)
│   ├── cvat.py             # CVAT интеграция (/api/cvat)
│   ├── segmentation.py     # Сегментация (/api/segmentation)
│   ├── skeleton.py         # Скелетизация (/api/skeleton)
│   ├── junction.py         # Junction (/api/junction)
│   ├── graph.py            # Граф (/api/graph)
│   └── validation.py       # Валидация (/api/validation)
│
├── models/                 # SQLAlchemy ORM модели
│   ├── __init__.py         # Экспорт всех моделей
│   ├── diagram.py          # Diagram, DiagramStatus
│   ├── artifact.py         # Artifact, ArtifactType
│   └── stage.py            # ProcessingStage, StageType, StageStatus
│
├── schemas/                # Pydantic схемы (валидация запросов/ответов)
│   ├── __init__.py
│   └── diagram.py          # DiagramResponse, DiagramStatusResponse, etc.
│
├── services/               # Бизнес-логика
│   ├── __init__.py
│   └── storage.py          # StorageService — работа с файлами
│
└── db/                     # База данных
    ├── __init__.py
    ├── base.py             # Base класс для моделей
    └── session.py          # Подключение, сессии
```

### 4.2.2 `worker/` — Celery Workers

```
worker/
├── __init__.py
├── celery_app.py           # Конфигурация Celery
│
├── tasks/                  # Celery задачи
│   ├── __init__.py
│   ├── detection.py        # task_detect_yolo
│   ├── segmentation.py     # task_segment_pipes
│   ├── skeleton.py         # task_skeletonize, task_skeletonize_simple
│   ├── junction.py         # task_classify_junctions
│   └── graph.py            # task_build_graph, task_generate_fxml
│
└── utils/                  # Утилиты worker
    └── __init__.py
```

### 4.2.3 `modules/` — ML модули

```
modules/
├── yolo/                   # YOLO детекция (pid_node_detection)
│   ├── inference/
│   │   └── detector.py     # NodeDetector
│   ├── config/
│   └── ...
│
├── segmentation/           # U2-Net++ (pipe_segmentation)
│   ├── cli.py
│   ├── data/
│   └── ...
│
├── skeleton/               # Скелетизация (skeleton_extension)
│   ├── core.py
│   ├── processing.py
│   └── ...
│
├── junction/               # Junction CNN (junction_classifier)
│   └── src/
│       ├── inference.py
│       ├── model.py
│       └── ...
│
└── graph/                  # Построение графа (graph_builder)
    ├── core/
    │   ├── builder.py      # GraphBuilder
    │   ├── tracing.py
    │   └── ...
    └── graph_to_fxml.py    # FXML генератор
```

### 4.2.4 `ui/` — PySide6 Desktop App

```
ui/
├── __init__.py
├── main.py                 # Entry point
├── app.py                  # QApplication
│
├── windows/                # Главные окна
│   ├── __init__.py
│   ├── main_window.py      # Главное окно, список диаграмм
│   └── diagram_window.py   # Окно диаграммы, этапы обработки
│
├── widgets/                # Переиспользуемые виджеты
│   ├── __init__.py
│   ├── diagram_list.py     # Таблица диаграмм
│   ├── stage_progress.py   # Индикатор прогресса
│   ├── cvat_browser.py     # Встроенный CVAT
│   └── action_buttons.py   # Кнопки действий
│
├── editors/                # Редакторы валидации
│   ├── __init__.py
│   ├── base_editor.py      # Базовый класс
│   ├── mask_editor.py      # Редактор масок (квадраты)
│   ├── polyline_editor.py  # Редактор полилиний
│   └── graph_editor.py     # Редактор графа
│
├── services/               # Сервисы UI
│   ├── __init__.py
│   ├── api_client.py       # HTTP клиент к FastAPI
│   ├── status_provider.py  # Абстракция обновления статуса
│   ├── polling_provider.py # HTTP polling реализация
│   └── websocket_provider.py # WebSocket (будущее)
│
└── resources/              # Ресурсы
    ├── styles.qss          # Qt стили
    └── icons/              # Иконки
```

### 4.2.5 `storage/` — Файловое хранилище

```
storage/
└── diagrams/
    └── {uuid}/                     # Папка диаграммы
        ├── original/
        │   └── image.png           # Оригинал
        │
        ├── detection/
        │   ├── yolo_predicted.txt  # YOLO предсказания
        │   ├── yolo_validated.txt  # После CVAT
        │   ├── coco_predicted.json
        │   └── coco_validated.json
        │
        ├── segmentation/
        │   ├── node_mask.png       # Маска узлов из COCO
        │   ├── pipe_mask.png       # Предсказанная маска труб
        │   └── validated_pipe_mask.png
        │
        ├── skeleton/
        │   ├── skeleton.png        # Скелет
        │   └── final_skeleton.png  # После валидации масок
        │
        ├── junction/
        │   ├── junction_mask.png
        │   ├── bridge_mask.png
        │   ├── validated_junction_mask.png
        │   └── validated_bridge_mask.png
        │
        ├── graph/
        │   ├── graph.json
        │   └── validated_graph.json
        │
        └── output/
            └── output.fxml
```

### 4.2.6 `alembic/` — Миграции БД

```
alembic/
├── env.py                  # Настройка Alembic
├── script.py.mako          # Шаблон миграции
└── versions/               # Файлы миграций
    └── xxxx_initial.py     # Начальная миграция
```

### 4.2.7 `requirements/` — Зависимости

```
requirements/
├── base.txt                # Общие зависимости
├── api.txt                 # FastAPI + зависимости API
├── worker.txt              # Celery + ML зависимости
├── ui.txt                  # PySide6 + зависимости UI
└── dev.txt                 # Тестирование, линтинг
```

---

## 4.3 Ключевые файлы

### `app/main.py`

Точка входа FastAPI приложения:
- Создание FastAPI app
- Подключение middleware (CORS)
- Регистрация роутеров
- Health check endpoints

### `app/config.py`

Конфигурация через Pydantic Settings:
- Читает переменные из `.env`
- Предоставляет типизированный доступ к настройкам

### `worker/celery_app.py`

Конфигурация Celery:
- Подключение к Redis
- Настройка очередей
- Роутинг задач

### `docker-compose.yml`

Оркестрация контейнеров:
- PostgreSQL
- Redis
- API
- Worker

---

## 4.4 Соглашения по именованию

### Файлы

| Тип | Паттерн | Пример |
|-----|---------|--------|
| Модуль Python | snake_case | `diagram.py` |
| Класс | PascalCase | `class Diagram` |
| Функция | snake_case | `def get_diagram()` |
| Константа | UPPER_SNAKE | `CELERY_BROKER_URL` |
| API endpoint | kebab-case | `/api/diagrams/{uid}/status` |

### Статусы

- Глаголы в continuous для процессов: `detecting`, `segmenting`
- Past participle для завершённых: `detected`, `validated`
- Существительные для ожидания действия: `uploaded`, `error`

### UUID

- Диаграммы идентифицируются по UUID v4
- В URL используется строковое представление
- В БД хранится как `UUID` тип PostgreSQL
