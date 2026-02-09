# 3. Установка и настройка

## 3.1 Требования

### Системные требования

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| ОС | Windows 10 / Ubuntu 20.04 | Windows 11 / Ubuntu 22.04 |
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| GPU | NVIDIA 6GB VRAM | NVIDIA 8GB+ VRAM |
| Диск | 50 GB | 100+ GB SSD |

### Программное обеспечение

- **Python** 3.11+
- **Docker Desktop** 4.20+ (с Docker Compose v2)
- **NVIDIA Driver** 525+ (для GPU)
- **CUDA** 12.x (для GPU)
- **Git**

---

## 3.2 Проверка требований

### Windows (PowerShell)

```powershell
# Python
python --version
# Python 3.11.x

# Docker
docker --version
# Docker version 24.x.x

docker compose version
# Docker Compose version v2.x.x

# NVIDIA Driver
nvidia-smi
# NVIDIA-SMI 525.xx.xx

# CUDA (через PyTorch, если установлен)
python -c "import torch; print(f'CUDA: {torch.version.cuda}')"
# CUDA: 12.4
```

---

## 3.3 Установка (Unified Docker)

### Шаг 1: Клонирование

```powershell
git clone <repository-url>
cd pid_pipeline
```

### Шаг 2: Настройка .env

```powershell
copy .env.example .env
notepad .env
```

Основные параметры (можно оставить по умолчанию):

```env
# Database
DB_USER=pid_user
DB_PASSWORD=changeme
DB_NAME=pid_pipeline

# CVAT
CVAT_SUPERUSER=admin
CVAT_SUPERUSER_PASSWORD=admin123

# GPU
YOLO_DEVICE=cuda
```

### Шаг 3: Подготовить ML веса

```powershell
# Создать папку если нет
mkdir models\yolo -Force

# Скопировать веса YOLO
copy C:\path\to\best.pt models\yolo\best.pt
```

### Шаг 4: Запустить все сервисы

```powershell
docker-compose up -d
```

Первый запуск займёт 5-10 минут (скачивание образов).

**Что запускается:**

| Сервис | Контейнер | Порт |
|--------|-----------|------|
| P&ID API | pid_api | 8000 |
| P&ID Worker | pid_worker | - |
| P&ID PostgreSQL | pid_postgres | 5433 |
| P&ID Redis | pid_redis | 6380 |
| CVAT Server | cvat_server | - |
| CVAT UI | cvat_ui | - |
| CVAT PostgreSQL | cvat_db | - |
| CVAT Redis | cvat_redis_inmem | - |
| Traefik (CVAT proxy) | traefik | 8080 |

### Шаг 5: Применить миграции БД

```powershell
docker exec -it pid_api alembic upgrade head
```

Ожидаемый вывод:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 6d4b720721f2, Initial tables
```

### Шаг 6: Создать суперпользователя CVAT

```powershell
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```

Ввести:
- **Username:** `admin`
- **Email:** (нажать Enter, пропустить)
- **Password:** `admin123`
- **Password (again):** `admin123`

### Шаг 7: Проверить работу

```powershell
# Проверить что контейнеры работают
docker ps

# Проверить API
curl http://localhost:8000/health

# Или открыть в браузере
start http://localhost:8000/docs
start http://localhost:8080
```

| Сервис | URL | Логин |
|--------|-----|-------|
| P&ID API Docs | http://localhost:8000/docs | - |
| CVAT UI | http://localhost:8080 | admin / admin123 |

---

## 3.4 Структура Docker Compose

```yaml
# Unified docker-compose.yml включает:

# P&ID Pipeline Services
- postgres       # БД для P&ID (порт 5433)
- redis          # Celery broker (порт 6380)
- api            # FastAPI (порт 8000)
- worker         # Celery + GPU

# CVAT Services
- cvat_db        # БД для CVAT
- cvat_redis_inmem
- cvat_redis_ondisk
- cvat_server
- cvat_worker_*  # Несколько воркеров
- cvat_ui
- cvat_opa       # Open Policy Agent
- traefik        # Reverse proxy (порт 8080)
```

### Bind Mounts (локальные папки)

| Хост | Контейнер | Описание |
|------|-----------|----------|
| `./storage` | `/storage` | Загруженные диаграммы |
| `./models` | `/models:ro` | ML веса (read-only) |
| `./configs` | `/app/configs` | Конфигурации проектов |
| `./alembic` | `/app/alembic` | Миграции БД |
| `./app` | `/app/app` | Код API (hot reload) |
| `./worker` | `/app/worker` | Код worker (hot reload) |

### Named Volumes (внутри Docker)

| Volume | Описание |
|--------|----------|
| `postgres_data` | Данные P&ID PostgreSQL |
| `redis_data` | Данные P&ID Redis |
| `cvat_db` | Данные CVAT PostgreSQL |
| `cvat_data` | Данные CVAT (изображения) |

---

## 3.5 Установка для локальной разработки

Если нужно запускать API или Worker локально (без Docker):

### Шаг 1: Создать виртуальное окружение

```powershell
python -m venv .venv
.venv\Scripts\activate
```

<<<<<<< HEAD
### Шаг 2: Установить PyTorch с CUDA
=======
### Шаг 5: Установить PyTorch с CUDA

** ВАЖНО: PyTorch устанавливается ОТДЕЛЬНО, до остальных зависимостей!**

```powershell
# PyTorch 2.6.0 + CUDA 12.4
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

Проверить:
```powershell
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"
```

Ожидаемый вывод:
```
PyTorch: 2.6.0+cu124
CUDA available: True
```

### Шаг 6: Установить остальные зависимости

```powershell
# Для API разработки
pip install -r requirements/api.txt

# Для Worker (ML задачи) — если запускаете локально
pip install -r requirements/worker.txt

# Для UI (PySide6)
pip install -r requirements/ui.txt
```

### Шаг 7: Запустить инфраструктуру

```powershell
docker-compose up -d postgres redis
```

### Шаг 8: Инициализировать БД

```powershell
python scripts/init_db.py
```

### Шаг 9: Проверить запуск API

```powershell
uvicorn app.main:app --reload --port 8000
```

Открыть: http://localhost:8000/docs

---

## 3.4 Установка на Linux (Ubuntu)

### Шаг 1: Клонирование

```bash
git clone <repository-url>
cd pid_pipeline
```

### Шаг 2: Настройка .env

```bash
cp .env.example .env
nano .env
```

Изменить:
```env
DB_PASSWORD=your_secure_password
CVAT_TOKEN=your_cvat_token
```

### Шаг 3: Создать виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Шаг 4: Установить PyTorch с CUDA
>>>>>>> 90fdd883de8a8d9391f08e933a05b42a252eed65

** ВАЖНО: PyTorch устанавливается ОТДЕЛЬНО!**

```powershell
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

Проверить:
```powershell
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
# CUDA available: True
```

### Шаг 3: Установить зависимости

```powershell
# Для API
pip install -r requirements/api.txt

# Для Worker (если запускаете локально)
pip install -r requirements/worker.txt

# Для UI
pip install -r requirements/ui.txt
```

### Шаг 4: Запустить только инфраструктуру

```powershell
# Запустить БД, Redis и CVAT в Docker
docker-compose up -d postgres redis cvat_db cvat_redis_inmem cvat_redis_ondisk cvat_server cvat_opa cvat_ui traefik
```

### Шаг 5: Запустить API локально

```powershell
uvicorn app.main:app --reload --port 8000
```

---

## 3.6 Команды после установки

### Ежедневная работа

```powershell
# Запустить всё
docker-compose up -d

# Остановить всё
docker-compose down

# Посмотреть логи
docker logs -f pid_api
docker logs -f pid_worker
docker logs -f cvat_server
```

### После изменения моделей БД

```powershell
# Создать миграцию
docker exec -it pid_api alembic revision --autogenerate -m "Description"

# Применить
docker exec -it pid_api alembic upgrade head
```

### После изменения docker-compose.yml

```powershell
# Пересоздать контейнеры
docker-compose up -d
```

### После изменения Dockerfile

```powershell
# Пересобрать образы
docker-compose up -d --build api worker
```

---

## 3.7 Типичные проблемы

### Контейнер не запускается

```powershell
# Посмотреть логи
docker logs pid_api
docker logs cvat_server

# Проверить статус
docker ps -a
```

### Порт занят

```powershell
# Найти процесс на порту 8000
netstat -ano | findstr :8000

# Изменить порт в .env
API_PORT=8001
```

### CVAT показывает "Connecting..."

```powershell
# Проверить что cvat_server работает
docker logs cvat_server --tail 50

# Перезапустить CVAT
docker-compose restart cvat_server
```

### GPU не доступен в worker

```powershell
# Проверить NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi

# Проверить логи worker
docker logs pid_worker
```

### Миграции не применяются

```powershell
# Проверить что alembic примонтирован
docker exec -it pid_api ls -la /app/alembic

# Проверить статус миграций
docker exec -it pid_api alembic current
```

---

## 3.8 Обновление

### Обновление кода

```powershell
git pull
docker-compose up -d --build api worker
docker exec -it pid_api alembic upgrade head
```

### Полная переустановка

```powershell
# Остановить и удалить контейнеры
docker-compose down

# Удалить volumes (ОСТОРОЖНО - удалит данные!)
docker-compose down -v

# Запустить заново
docker-compose up -d
docker exec -it pid_api alembic upgrade head
docker exec -it cvat_server bash -ic 'python3 ~/manage.py createsuperuser'
```
