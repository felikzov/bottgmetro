"""
Модуль управления списком составов
"""
import logging
from telebot import TeleBot, types
from database import Database
from config import ADMINS

logger = logging.getLogger(__name__)


class TrainsManager:
    """Управление списком составов"""
    
    def __init__(self, bot: TeleBot, db: Database):
        self.bot = bot
        self.db = db
        self.editing_users = set()
    
    def register_handlers(self):
        """Зарегистрировать обработчики"""
        
        @self.bot.message_handler(commands=['trains'])
        def cmd_trains(message):
            self._show_trains(message)
        
        @self.bot.message_handler(commands=['edittrains'])
        def cmd_edit_trains(message):
            self._start_edit(message)
        
        @self.bot.message_handler(func=lambda m: m.from_user.id in self.editing_users and m.text == "❌ Отменить")
        def cancel_edit(message):
            self._cancel_edit(message)
        
        @self.bot.message_handler(func=lambda m: m.from_user.id in self.editing_users)
        def edit_trains_text(message):
            self._handle_edit(message)
        
        logger.info("Trains handlers registered")
    
    def _show_trains(self, message):
        """Показать текущий список составов"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            trains = self.db.get_trains()
            
            if not trains:
                self.bot.reply_to(message, "📋 Список составов пуст")
                return
            
            text = f"📋 Список составов ({len(trains)} шт.):\n\n"
            for i, train in enumerate(trains, 1):
                text += f"{i}. {train}\n"
            
            self.bot.reply_to(message, text)
            logger.info(f"Admin {message.from_user.id} viewed trains list")
            
        except Exception as e:
            logger.error(f"Error showing trains: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка получения списка")
    
    def _start_edit(self, message):
        """Начать редактирование списка"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            current_trains = self.db.get_trains()
            current_text = "\n".join(current_trains) if current_trains else ""
            
            self.editing_users.add(message.from_user.id)
            
            # Создать клавиатуру с кнопкой отмены
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(types.KeyboardButton("❌ Отменить"))
            
            instructions = (
                "✏️ Редактирование списка составов\n\n"
                "Отправьте новый список (каждый состав с новой строки).\n"
                "Пустые строки будут удалены.\n\n"
                "📋 Текущий список:\n"
                f"{current_text if current_text else '(пусто)'}\n\n"
                "Или нажмите «❌ Отменить» для отмены редактирования."
            )
            
            self.bot.reply_to(message, instructions, reply_markup=markup)
            logger.info(f"Admin {message.from_user.id} started editing trains")
            
        except Exception as e:
            logger.error(f"Error starting edit: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка запуска редактирования")
    
    def _cancel_edit(self, message):
        """Отменить редактирование"""
        try:
            user_id = message.from_user.id
            
            if user_id not in ADMINS:
                return
            
            self.editing_users.discard(user_id)
            
            # Убрать клавиатуру
            markup = types.ReplyKeyboardRemove()
            
            self.bot.reply_to(message, "❌ Редактирование отменено", reply_markup=markup)
            logger.info(f"Admin {user_id} cancelled trains editing")
            
        except Exception as e:
            logger.error(f"Error cancelling edit: {e}", exc_info=True)
    
    def _handle_edit(self, message):
        """Обработать новый список составов"""
        try:
            user_id = message.from_user.id
            
            if user_id not in ADMINS:
                return
            
            self.editing_users.discard(user_id)
            
            # Парсинг списка
            lines = message.text.strip().split("\n")
            trains = []
            
            for line in lines:
                line = line.strip()
                # Пропустить пустые строки и команды
                if line and not line.startswith("/"):
                    trains.append(line)
            
            if not trains:
                markup = types.ReplyKeyboardRemove()
                self.bot.reply_to(
                    message, 
                    "❗️ Список не может быть пустым. Попробуйте /edittrains снова.",
                    reply_markup=markup
                )
                return
            
            # Удалить дубликаты, сохраняя порядок
            seen = set()
            unique_trains = []
            for train in trains:
                if train not in seen:
                    seen.add(train)
                    unique_trains.append(train)
            
            # Сохранить в БД
            self.db.set_trains(unique_trains)
            
            # Убрать клавиатуру
            markup = types.ReplyKeyboardRemove()
            
            result_text = (
                f"✅ Список составов обновлен!\n\n"
                f"📊 Добавлено: {len(unique_trains)} составов\n"
                f"🔁 Удалено дубликатов: {len(trains) - len(unique_trains)}\n\n"
                f"Используйте /trains для просмотра."
            )
            
            self.bot.reply_to(message, result_text, reply_markup=markup)
            logger.info(f"Admin {user_id} updated trains list: {len(unique_trains)} items")
            
        except Exception as e:
            logger.error(f"Error handling edit: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка сохранения списка")
