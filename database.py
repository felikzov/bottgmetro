"""
Хранение данных в JSON-файлах (вместо SQLite)
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from threading import Lock

logger = logging.getLogger(__name__)

DEFAULT_TRAINS = [
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


class Database:
    """Хранение данных через JSON-файлы"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.lock = Lock()
        os.makedirs(data_dir, exist_ok=True)

        self.users_file  = os.path.join(data_dir, "users.json")
        self.banned_file = os.path.join(data_dir, "banned.json")
        self.states_file = os.path.join(data_dir, "states.json")
        self.trains_file = os.path.join(data_dir, "trains.json")

        self._init_files()

    def _read(self, path: str, default):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
        return default

    def _write(self, path: str, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing {path}: {e}")
            raise

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_files(self):
        for path, default in [
            (self.users_file,  {}),
            (self.banned_file, {}),
            (self.states_file, {}),
            (self.trains_file, DEFAULT_TRAINS),
        ]:
            if not os.path.exists(path):
                self._write(path, default)
        logger.info("Data files initialized")

    # ===== ПОЛЬЗОВАТЕЛИ =====

    def add_user(self, user_id: int,
                 username: Optional[str] = None,
                 first_name: Optional[str] = None):
        with self.lock:
            users = self._read(self.users_file, {})
            key = str(user_id)
            existing_ts = users.get(key, {}).get("created_at", self._now_iso())
            users[key] = {
                "username":   username,
                "first_name": first_name,
                "created_at": existing_ts,
            }
            self._write(self.users_file, users)

    def get_all_user_ids(self) -> List[int]:
        with self.lock:
            return [int(k) for k in self._read(self.users_file, {})]

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            users = self._read(self.users_file, {})
            info = users.get(str(user_id))
            return {"user_id": user_id, **info} if info else None

    def get_user_id_by_username(self, username: str) -> Optional[int]:
        with self.lock:
            users = self._read(self.users_file, {})
            for uid_str, info in users.items():
                if (info.get("username") or "").lower() == username.lower():
                    return int(uid_str)
            return None

    def get_recent_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.lock:
            users  = self._read(self.users_file,  {})
            banned = self._read(self.banned_file, {})
            sorted_users = sorted(
                users.items(),
                key=lambda x: x[1].get("created_at", ""),
                reverse=True
            )[:limit]
            return [
                {
                    "user_id":    int(uid),
                    "username":   info.get("username"),
                    "first_name": info.get("first_name", "Без имени"),
                    "is_banned":  uid in banned,
                }
                for uid, info in sorted_users
            ]

    # ===== БАНЫ =====

    def ban_user(self, user_id: int, reason: str = "-"):
        with self.lock:
            banned = self._read(self.banned_file, {})
            banned[str(user_id)] = {"reason": reason, "banned_at": self._now_iso()}
            self._write(self.banned_file, banned)
            logger.info(f"User {user_id} banned: {reason}")

    def unban_user(self, user_id: int):
        with self.lock:
            banned = self._read(self.banned_file, {})
            banned.pop(str(user_id), None)
            self._write(self.banned_file, banned)
            logger.info(f"User {user_id} unbanned")

    def is_banned(self, user_id: int) -> bool:
        with self.lock:
            return str(user_id) in self._read(self.banned_file, {})

    def get_banned_users(self) -> Dict[int, str]:
        with self.lock:
            banned = self._read(self.banned_file, {})
            return {int(uid): v.get("reason", "-") for uid, v in banned.items()}

    def get_banned_users_detailed(self) -> List[Dict[str, Any]]:
        with self.lock:
            banned = self._read(self.banned_file, {})
            users  = self._read(self.users_file,  {})
            result = []
            for uid_str, ban_info in banned.items():
                u = users.get(uid_str, {})
                result.append({
                    "user_id":    int(uid_str),
                    "username":   u.get("username"),
                    "first_name": u.get("first_name"),
                    "reason":     ban_info.get("reason", "-"),
                })
            return result

    # ===== СОСТОЯНИЯ =====

    def set_user_state(self, user_id: int, state_data: Dict[str, Any]):
        with self.lock:
            states = self._read(self.states_file, {})
            states[str(user_id)] = {
                "state_data": state_data,
                "updated_at": self._now_iso(),
            }
            self._write(self.states_file, states)

    def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            entry = self._read(self.states_file, {}).get(str(user_id))
            return entry["state_data"] if entry else None

    def clear_user_state(self, user_id: int):
        with self.lock:
            states = self._read(self.states_file, {})
            states.pop(str(user_id), None)
            self._write(self.states_file, states)

    def cleanup_old_states(self, minutes: int = 30):
        with self.lock:
            states = self._read(self.states_file, {})
            now    = datetime.now(timezone.utc)
            to_del = [
                uid for uid, entry in states.items()
                if (now - datetime.fromisoformat(entry["updated_at"])).total_seconds()
                   > minutes * 60
            ]
            for uid in to_del:
                del states[uid]
            if to_del:
                self._write(self.states_file, states)
                logger.info(f"Cleaned {len(to_del)} old states")

    # ===== СОСТАВЫ =====

    def get_trains(self) -> List[str]:
        with self.lock:
            return self._read(self.trains_file, DEFAULT_TRAINS)

    def set_trains(self, trains: List[str]):
        with self.lock:
            self._write(self.trains_file, trains)
            logger.info(f"Updated trains: {len(trains)} items")
