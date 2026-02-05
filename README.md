# P&ID Pipeline

Приложение для автоматической обработки P&ID диаграмм.

## 🏗️ Архитектура

- **FastAPI** - Backend API
- **Celery** - Фоновые задачи (ML inference)
- **PostgreSQL** - База данных
- **Redis** - Message broker
- **PySide6** - Desktop UI
- **CVAT** - Валидация аннотаций

## 📁 Структура проекта
```
pid_pipeline/
├── app/                # FastAPI Backend
├── worker/             # Celery Workers
├── modules/            # ML модули
├── ui/                 # PySide6 Desktop App
├── storage/            # Файловое хранилище
├── alembic/            # Миграции БД
└── docker-compose.yml
```

## 🚀 Запуск

### 1. Настройка окружения
```bash
copy .env.example .env
# Отредактировать .env
```

### 2. Запуск через Docker
```bash
docker-compose up -d
```

### 3. Инициализация БД
```bash
python scripts/init_db.py
```

### 4. Запуск UI (локально)
```bash
pip install -r requirements/ui.txt
python -m ui.main
```

## 📊 API Документация

После запуска: http://localhost:8000/docs

## 🔧 Разработка

### Локальный запуск API
```bash
pip install -r requirements/api.txt
uvicorn app.main:app --reload --port 8000
```

### Локальный запуск Worker
```bash
pip install -r requirements/worker.txt
celery -A worker.celery_app worker --loglevel=info
```