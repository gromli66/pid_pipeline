# P&ID Pipeline — Документация

## Содержание

1. [Обзор проекта](./01-overview.md)
2. [Архитектура](./02-architecture.md)
3. [Установка и настройка](./03-installation.md)
4. [Структура проекта](./04-project-structure.md)
5. [База данных](./05-database.md)
6. [API Reference](./06-api-reference.md)
7. [Celery Workers](./07-celery-workers.md)
8. [Конфигурация](./08-configuration.md)
9. [Разработка](./09-development.md)
10. [Troubleshooting](./10-troubleshooting.md)

---

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone <repository-url>
cd pid_pipeline

# 2. Настроить окружение
copy .env.example .env
# Отредактировать .env

# 3. Запустить инфраструктуру
docker-compose up -d postgres redis

# 4. Инициализировать БД
python scripts/init_db.py

# 5. Запустить API
uvicorn app.main:app --reload --port 8000

# 6. Открыть документацию API
# http://localhost:8000/docs
```

---

## Статус разработки

| Phase | Описание | Статус |
|-------|----------|--------|
| Phase 1 | Инфраструктура + Projects |  Завершено |
| Phase 2 | YOLO + CVAT |  В процессе |
| Phase 3 | Сегментация + Скелет |  В планах |
| Phase 4 | Junction + Валидация масок |  В планах |
| Phase 5 | Граф + FXML |  В планах |
| Phase 6 | UI + Интеграция |  В планах |

---

## Проекты

Система поддерживает несколько проектов (термогидравлика, электрика и т.д.)

Конфигурация проектов в `configs/projects/`:
- `thermohydraulics.yaml` — Термогидравлика (40 классов, YOLO 36 классов)

---

