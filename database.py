"""
Модуль для работы с базой данных SQLite
"""
import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)


class Database:
    """Безопасная работа с базой данных"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        """Context manager для безопасной работы с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}", exc_info=True)
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Инициализация структуры БД"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица забаненных
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS banned_users (
                        user_id INTEGER PRIMARY KEY,
                        reason TEXT DEFAULT '-',
                        banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица состояний
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id INTEGER PRIMARY KEY,
                        state_data TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица составов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trains (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL
                    )
                """)
                
                # Индексы для производительности
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_banned ON banned_users(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_states_updated ON user_states(updated_at)")
                
                # Инициализация списка составов по умолчанию
                cursor.execute("SELECT COUNT(*) FROM trains")
                if cursor.fetchone()[0] == 0:
                    default_trains = [
                        "9050-9051 (Голубая смерть)",
                        "10222-10221 (Боинг)",
                        "🟣 Балтиец 🟣",
                        "🔴 Балтиец 🔴",
                        "🔵 Балтиец 🔵",
                        "🟤 Балтиец 🟤",
                        "Темат 320 лет",
                        "Темат 70 лет",
                        "Темат 25 состав",
                        "НВЛ (мойка)",
                        "7128-6973",
                        "7144-6977",
                        "Ретросостав",
                        "Перегонка",
                        "Обкатка",
                        "ЭКА",
                        "Лаборатория",
                        "Неизвестен"
                    ]
                    for train in default_trains:
                        cursor.execute("INSERT INTO trains (name) VALUES (?)", (train,))
                    logger.info(f"Initialized {len(default_trains)} default trains")
                
                logger.info("Database initialized successfully")
    
    # ===== ПОЛЬЗОВАТЕЛИ =====
    
    def add_user(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None):
        """Добавить/обновить пользователя"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO users (user_id, username, first_name)
                    VALUES (?, ?, ?)
                """, (user_id, username, first_name))
    
    def get_all_user_ids(self) -> List[int]:
        """Получить все ID пользователей"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users")
                return [row[0] for row in cursor.fetchall()]
    
    # ===== БАНЫ =====
    
    def ban_user(self, user_id: int, reason: str = "-"):
        """Забанить пользователя"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO banned_users (user_id, reason)
                    VALUES (?, ?)
                """, (user_id, reason))
                logger.info(f"User {user_id} banned: {reason}")
    
    def unban_user(self, user_id: int):
        """Разбанить пользователя"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
                logger.info(f"User {user_id} unbanned")
    
    def is_banned(self, user_id: int) -> bool:
        """Проверить бан"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,))
                return cursor.fetchone() is not None
    
    def get_banned_users(self) -> Dict[int, str]:
        """Получить всех забаненных"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, reason FROM banned_users")
                return {row[0]: row[1] for row in cursor.fetchall()}
    
    def get_banned_users_detailed(self) -> List[Dict[str, Any]]:
        """Получить детальную информацию о забаненных"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT u.user_id, u.username, u.first_name, b.reason
                    FROM banned_users b
                    JOIN users u ON b.user_id = u.user_id
                    ORDER BY b.banned_at DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
    
    def get_user_id_by_username(self, username: str) -> Optional[int]:
        """Получить ID пользователя по username"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_id FROM users WHERE username = ? COLLATE NOCASE",
                    (username,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT user_id, username, first_name FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
    
    def get_recent_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить последних пользователей"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        u.user_id, 
                        u.username, 
                        u.first_name,
                        CASE WHEN b.user_id IS NOT NULL THEN 1 ELSE 0 END as is_banned
                    FROM users u
                    LEFT JOIN banned_users b ON u.user_id = b.user_id
                    ORDER BY u.created_at DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
    
    # ===== СОСТОЯНИЯ =====
    
    def set_user_state(self, user_id: int, state_data: Dict[str, Any]):
        """Сохранить состояние"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO user_states (user_id, state_data, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user_id, json.dumps(state_data, ensure_ascii=False)))
    
    def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить состояние"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT state_data FROM user_states WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return json.loads(row[0]) if row else None
    
    def clear_user_state(self, user_id: int):
        """Очистить состояние"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
    
    def cleanup_old_states(self, minutes: int = 30):
        """Очистить старые состояния"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_states 
                    WHERE datetime(updated_at) < datetime('now', ?)
                """, (f'-{minutes} minutes',))
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info(f"Cleaned {deleted} old states")
    
    # ===== СОСТАВЫ =====
    
    def get_trains(self) -> List[str]:
        """Получить все составы"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM trains ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
    
    def set_trains(self, trains: List[str]):
        """Заменить все составы"""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM trains")
                for train in trains:
                    cursor.execute("INSERT OR IGNORE INTO trains (name) VALUES (?)", (train,))
                logger.info(f"Updated trains: {len(trains)} items")
