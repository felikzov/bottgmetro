"""
Вспомогательные утилиты
"""
import logging
import html
import time
from functools import wraps
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)


def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """Декоратор для повторных попыток при ошибках"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts", exc_info=True)
            raise last_exception
        return wrapper
    return decorator


def safe_html(text: str) -> str:
    """Экранировать HTML"""
    return html.escape(str(text)) if text else ""


def format_user_link(user_id: int, username: Optional[str] = None, 
                     first_name: Optional[str] = None) -> str:
    """Создать ссылку на пользователя"""
    if username:
        return f"@{username}"
    name = safe_html(first_name) if first_name else "Пользователь"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


def validate_text_length(text: str, max_length: int, field_name: str = "Текст") -> Tuple[bool, Optional[str]]:
    """Проверить длину текста"""
    if not text or not text.strip():
        return False, f"❗️ {field_name} не может быть пустым"
    if len(text) > max_length:
        return False, f"❗️ {field_name} слишком длинный (макс. {max_length} символов)"
    return True, None


def validate_route_number(route: str) -> Tuple[bool, Optional[str]]:
    """Проверить номер маршрута"""
    if not route.isdigit():
        return False, "❗️ Маршрут должен содержать только цифры"
    if len(route) != 3:
        return False, "❗️ Маршрут должен быть трёхзначным"
    return True, None


def parse_time_ago(time_str: str) -> int:
    """Парсить время в минуты"""
    if time_str == "Сейчас":
        return 0
    try:
        return int(time_str.split()[0])
    except (ValueError, IndexError):
        return 0


class RateLimiter:
    """Контроль частоты отправки"""
    
    def __init__(self, messages_per_period: int, period_seconds: float):
        self.messages_per_period = messages_per_period
        self.period_seconds = period_seconds
        self.message_count = 0
        self.period_start = time.time()
    
    def wait_if_needed(self):
        """Подождать при достижении лимита"""
        self.message_count += 1
        if self.message_count >= self.messages_per_period:
            elapsed = time.time() - self.period_start
            if elapsed < self.period_seconds:
                time.sleep(self.period_seconds - elapsed)
            self.message_count = 0
            self.period_start = time.time()


def setup_logging(log_file: str, log_level: str = "INFO"):
    """Настроить логирование"""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('telebot').setLevel(logging.INFO)
