# 10. Troubleshooting

## 10.1 Проблемы запуска

### API не запускается

**Ошибка:** `ModuleNotFoundError: No module named 'xxx'`

**Решение:**
```powershell
pip install -r requirements/api.txt
```

---

**Ошибка:** `Connection refused` (PostgreSQL)

**Решение:**
```powershell
# Проверить что PostgreSQL запущен
docker-compose ps

# Если не запущен
docker-compose up -d postgres

# Проверить логи
docker-compose logs postgres
```

---

**Ошибка:** `FATAL: password authentication failed`

**Решение:**
1. Проверить пароль в `.env`
2. Пересоздать контейнер:
```powershell
docker-compose down -v
docker-compose up -d postgres
```

---

### Worker не запускается

**Ошибка:** `Connection refused` (Redis)

**Решение:**
```powershell
docker-compose up -d redis
```

---

**Ошибка:** `No module named 'worker'`

**Решение:**
```powershell
# Запускать из корня проекта
cd C:\project\pid_pipeline
celery -A worker.celery_app worker --loglevel=info
```

---

### Docker проблемы

**Ошибка:** `port is already allocated`

**Решение:**
```powershell
# Найти процесс на порту
netstat -ano | findstr :5433

# Убить процесс
taskkill /PID <PID> /F

# Или изменить порт в docker-compose.yml
```

---

**Ошибка:** `GPU not available in Docker`

**Решение:**
1. Установить NVIDIA Container Toolkit
2. Перезапустить Docker Desktop
3. Проверить:
```powershell
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

---

## 10.2 Проблемы БД

### Таблицы не создаются

**Решение:**
```powershell
python scripts/init_db.py
```

---

### Ошибка миграции

**Ошибка:** `Target database is not up to date`

**Решение:**
```powershell
alembic upgrade head
```

---

### Конфликт миграций

**Решение:**
```powershell
# Посмотреть текущую версию
alembic current

# Откатить
alembic downgrade -1

# Применить заново
alembic upgrade head
```

---

## 10.3 Проблемы CVAT

### Не подключается к CVAT

**Проверить:**
1. CVAT запущен: `docker ps | grep cvat`
2. URL правильный в `.env`
3. Токен актуальный

**Тест подключения:**
```powershell
curl http://localhost:8080/api/server/about
```

---

### CVAT токен не работает

**Решение:**
1. Войти в CVAT
2. Settings → API Token → Regenerate
3. Обновить в `.env`

---

## 10.4 Проблемы ML

### CUDA out of memory

**Решение:**
1. Уменьшить batch size
2. Уменьшить размер изображения
3. Освободить GPU память:
```python
import torch
torch.cuda.empty_cache()
```

---

### Модель не загружается

**Проверить:**
1. Путь к весам в `.env`
2. Файл существует
3. Совместимость версий PyTorch

```powershell
# Проверить путь
dir models\yolo\best.pt

# Проверить загрузку
python -c "import torch; torch.load('models/yolo/best.pt')"
```

---

## 10.5 Проблемы Windows

### PowerShell: Execution Policy

**Ошибка:** `cannot be loaded because running scripts is disabled`

**Решение:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### Путь слишком длинный

**Ошибка:** `FileNotFoundError: [Errno 2] No such file or directory` (путь > 260 символов)

**Решение:**
1. Включить длинные пути в Windows:
   - Regedit → HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem
   - LongPathsEnabled = 1
2. Использовать короткий путь проекта: `C:\proj\pid`

---

### Проблемы с кодировкой

**Ошибка:** `UnicodeDecodeError`

**Решение:**
```python
# В коде
with open(file, encoding='utf-8') as f:
    ...

# В .env
# Сохранить файл в UTF-8
```

---

## 10.6 Логирование и диагностика

### Включить debug логи

```env
# .env
LOG_LEVEL=DEBUG
API_DEBUG=true
```

### Логи Docker

```powershell
# API
docker-compose logs -f api

# Worker
docker-compose logs -f worker

# Все
docker-compose logs -f
```

### Проверка состояния

```powershell
# Docker контейнеры
docker-compose ps

# Celery workers
celery -A worker.celery_app inspect active

# Redis
docker-compose exec redis redis-cli PING

# PostgreSQL
docker-compose exec postgres pg_isready
```

---

## 10.7 Сброс и очистка

### Полный сброс

```powershell
# Остановить всё
docker-compose down -v

# Удалить storage
Remove-Item -Recurse -Force storage\diagrams\*

# Запустить заново
docker-compose up -d postgres redis
python scripts/init_db.py
```

### Очистка Docker

```powershell
# Удалить неиспользуемые образы
docker image prune

# Удалить всё неиспользуемое
docker system prune -a
```

---

## 10.8 Получение помощи

### Информация для отчёта об ошибке

```powershell
# Версии
python --version
docker --version
pip freeze > requirements_current.txt

# Логи
docker-compose logs > docker_logs.txt

# Конфигурация (без секретов!)
cat .env | findstr /v PASSWORD | findstr /v TOKEN
```

### Контакты

- GitHub Issues: [URL]
- Email: [email]
