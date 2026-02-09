"""
Logging configuration - централизованное логирование.

Использование:
    from app.core.logging import get_logger
    
    logger = get_logger(__name__)
    logger.info("Сообщение")
    logger.error("Ошибка", exc_info=True)
"""

import logging
import sys
from typing import Optional


# Формат логов
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Цвета для консоли (ANSI)
COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",      # Reset
}


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветным выводом для консоли."""
    
    def __init__(self, fmt: str, datefmt: str, use_colors: bool = True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors
    
    def format(self, record: logging.LogRecord) -> str:
        # Сохраняем оригинальный levelname
        orig_levelname = record.levelname
        
        if self.use_colors and sys.stdout.isatty():
            color = COLORS.get(record.levelname, COLORS["RESET"])
            record.levelname = f"{color}{record.levelname}{COLORS['RESET']}"
        
        result = super().format(record)
        
        # Восстанавливаем
        record.levelname = orig_levelname
        
        return result


def setup_logging(
    level: str = "DEBUG",
    log_format: Optional[str] = None,
    date_format: Optional[str] = None,
) -> None:
    """
    Настроить логирование для всего приложения.
    
    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_format: Формат сообщений (опционально)
        date_format: Формат даты (опционально)
    
    Вызывать один раз при старте приложения:
        from app.core.logging import setup_logging
        setup_logging(level="DEBUG")
    """
    log_format = log_format or LOG_FORMAT
    date_format = date_format or DATE_FORMAT
    
    # Преобразуем строку в уровень
    numeric_level = getattr(logging, level.upper(), logging.DEBUG)
    
    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Удаляем существующие handlers (избегаем дубликатов)
    root_logger.handlers.clear()
    
    # Console handler с цветами
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(ColoredFormatter(log_format, date_format))
    root_logger.addHandler(console_handler)
    
    # Уменьшаем шум от сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    
    # Логируем что настройка завершена
    logger = logging.getLogger("app.core.logging")
    logger.info(f"Logging configured: level={level}")


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер для модуля.
    
    Args:
        name: Имя модуля (обычно __name__)
    
    Returns:
        logging.Logger
    
    Использование:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        
        logger.debug("Детальная информация")
        logger.info("Важное событие")
        logger.warning("Предупреждение")
        logger.error("Ошибка")
        logger.exception("Ошибка с traceback")  # В except блоке
    """
    return logging.getLogger(name)


# Shortcuts для быстрого доступа
def debug(msg: str, *args, **kwargs) -> None:
    """Быстрый debug лог."""
    logging.getLogger("app").debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs) -> None:
    """Быстрый info лог."""
    logging.getLogger("app").info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    """Быстрый warning лог."""
    logging.getLogger("app").warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    """Быстрый error лог."""
    logging.getLogger("app").error(msg, *args, **kwargs)
