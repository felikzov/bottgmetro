"""
Менеджер состояний пользователей
"""
import logging
from typing import Optional, Dict, Any

from database import Database
from config import States

logger = logging.getLogger(__name__)


class StateManager:
    """Управление состояниями пользователей"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_state(self, user_id: int) -> int:
        """Получить текущее состояние"""
        state_data = self.db.get_user_state(user_id)
        return state_data.get('state', States.IDLE) if state_data else States.IDLE
    
    def set_state(self, user_id: int, state: int):
        """Установить состояние"""
        current_data = self.db.get_user_state(user_id) or {}
        current_data['state'] = state
        self.db.set_user_state(user_id, current_data)
    
    def get_data(self, user_id: int) -> Dict[str, Any]:
        """Получить данные пользователя"""
        state_data = self.db.get_user_state(user_id)
        return state_data.get('data', {}) if state_data else {}
    
    def set_data(self, user_id: int, key: str, value: Any):
        """Установить одно значение"""
        state_data = self.db.get_user_state(user_id) or {'state': States.IDLE, 'data': {}}
        if 'data' not in state_data:
            state_data['data'] = {}
        state_data['data'][key] = value
        self.db.set_user_state(user_id, state_data)
    
    def update_data(self, user_id: int, updates: Dict[str, Any]):
        """Обновить несколько значений"""
        state_data = self.db.get_user_state(user_id) or {'state': States.IDLE, 'data': {}}
        if 'data' not in state_data:
            state_data['data'] = {}
        state_data['data'].update(updates)
        self.db.set_user_state(user_id, state_data)
    
    def clear_state(self, user_id: int):
        """Полностью очистить состояние"""
        self.db.clear_user_state(user_id)
    
    def reset_state(self, user_id: int):
        """Сбросить к IDLE"""
        self.set_state(user_id, States.IDLE)
