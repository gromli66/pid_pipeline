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
- **Docker** 20.10+ и Docker Compose v2
- **NVIDIA Driver** 525+ (для GPU)
- **CUDA** 12.4 (для GPU)
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

# NVIDIA Driver
nvidia-smi
# NVIDIA-SMI 525.xx.xx

# CUDA (через PyTorch, если установлен)
python -c "import torch; print(f'CUDA: {torch.version.cuda}')"
# CUDA: 12.4
```

### Linux (Bash)

```bash
# Python
python3 --version
# Python 3.11.x

# Docker
docker --version
docker compose version

# NVIDIA
nvidia-smi

# CUDA
python3 -c "import torch; print(f'CUDA: {torch.version.cuda}')"
```

---

## 3.3 Установка на Windows

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

Изменить:
```env
DB_PASSWORD=your_secure_password
CVAT_TOKEN=your_cvat_token
```

### Шаг 3: Разрешить выполнение скриптов (один раз)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Шаг 4: Создать виртуальное окружение

```powershell
python -m venv .venv
.venv\Scripts\activate
```

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

** ВАЖНО: PyTorch устанавливается ОТДЕЛЬНО!**

```bash
# PyTorch 2.6.0 + CUDA 12.4
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

Проверить:
```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"
```

### Шаг 5: Установить остальные зависимости

```bash
# Для API
pip install -r requirements/api.txt

# Для Worker
pip install -r requirements/worker.txt

# Для UI — на Linux нужен WebEngine отдельно!
pip install -r requirements/ui.txt
pip install PySide6-WebEngine
```

### Шаг 6: Запустить инфраструктуру

```bash
docker compose up -d postgres redis
```

### Шаг 7: Инициализировать БД

```bash
python scripts/init_db.py
```

### Шаг 8: Проверить запуск API

```bash
uvicorn app.main:app --reload --port 8000
```

---

## 3.5 Различия Windows и Linux

| Аспект | Windows | Linux |
|--------|---------|-------|
| Активация venv | `.venv\Scripts\activate` | `source .venv/bin/activate` |
| Копирование файлов | `copy` | `cp` |
| Редактор | `notepad` | `nano` / `vim` |
| Docker Compose | `docker-compose` | `docker compose` (v2) |
| PySide6-WebEngine | Включён в PySide6 | Нужен отдельно |
| Путь к Python | `python` | `python3` |
| Разделитель путей | `\` | `/` |

---

## 3.6 Установка PyTorch (подробно)

### Почему отдельно?

PyTorch с CUDA требует специальный index URL. Если ставить через обычный `pip install torch`, установится CPU-версия.

### Варианты установки

**CUDA 12.4 (рекомендуется):**
```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
```

**CUDA 12.1:**
```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu121
```

**CUDA 11.8:**
```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu118
```

**CPU only (без GPU):**
```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
```

### Проверка версии CUDA

```bash
# Через nvidia-smi
nvidia-smi
# Смотреть "CUDA Version" в правом верхнем углу

# Через PyTorch (если установлен)
python -c "import torch; print(torch.version.cuda)"
```

### Официальный селектор

https://pytorch.org/get-started/locally/ — выбрать ОС, версию CUDA, получить команду.

---

## 3.7 Настройка CVAT

### Шаг 1: Запуск CVAT

```bash
# Клонировать CVAT (если ещё нет)
git clone https://github.com/opencv/cvat.git
cd cvat

# Запустить
docker compose up -d
```

### Шаг 2: Создание пользователя

1. Открыть http://localhost:8080
2. Зарегистрировать пользователя
3. Создать проект "P&ID Diagrams"

### Шаг 3: Получение API токена

1. Войти в CVAT
2. Имя пользователя → Settings
3. Скопировать API Token
4. Вставить в `.env`:

```env
CVAT_TOKEN=your_token_here
CVAT_PROJECT_ID=1
```

---

## 3.8 Настройка ML моделей

### Структура папки

```
models/
├── yolo/
│   └── best.pt          # YOLO веса (~50MB)
├── u2net/
│   └── best.pth         # U2-Net++ веса (~150MB)
└── junction/
    └── best.pth         # Junction CNN веса (~50MB)
```

### Копирование весов

**Windows:**
```powershell
mkdir models\yolo
mkdir models\u2net
mkdir models\junction

copy C:\path\to\yolo\best.pt models\yolo\
copy C:\path\to\u2net\best.pth models\u2net\
copy C:\path\to\junction\best.pth models\junction\
```

**Linux:**
```bash
mkdir -p models/{yolo,u2net,junction}

cp /path/to/yolo/best.pt models/yolo/
cp /path/to/u2net/best.pth models/u2net/
cp /path/to/junction/best.pth models/junction/
```

### Обновить .env

```env
YOLO_WEIGHTS=./models/yolo/best.pt
U2NET_WEIGHTS=./models/u2net/best.pth
JUNCTION_WEIGHTS=./models/junction/best.pth
```

---

## 3.9 Запуск в Docker (Production)

### Полный запуск

```bash
# Собрать и запустить
docker compose up -d --build

# Проверить статус
docker compose ps

# Логи
docker compose logs -f api
docker compose logs -f worker
```

### Инициализация БД в Docker

```bash
docker compose exec api python scripts/init_db.py
```

### Остановка

```bash
docker compose down

# С удалением данных (осторожно!)
docker compose down -v
```

---

## 3.10 Типичные проблемы

### PyTorch: CUDA not available

**Проблема:** `torch.cuda.is_available()` возвращает `False`

**Решения:**
1. Проверить что установлена CUDA версия PyTorch (не CPU)
2. Проверить NVIDIA драйвер: `nvidia-smi`
3. Переустановить PyTorch с правильным индексом

### Windows: PowerShell не выполняет скрипты

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Linux: PySide6 не запускается

```bash
# Установить системные зависимости
sudo apt install libxcb-xinerama0 libxkbcommon-x11-0

# Установить WebEngine
pip install PySide6-WebEngine
```

### Docker: GPU не доступен

```bash
# Проверить NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### Порт занят

```bash
# Найти процесс
# Windows
netstat -ano | findstr :8000

# Linux
lsof -i :8000

# Убить или изменить порт в .env
```
