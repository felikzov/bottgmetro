"""
Модуль управления банами
"""
import logging
from telebot import TeleBot, types
from database import Database
from config import ADMINS

logger = logging.getLogger(__name__)


class BanManager:
    """Управление банами пользователей"""
    
    def __init__(self, bot: TeleBot, db: Database):
        self.bot = bot
        self.db = db
    
    def register_handlers(self):
        """Зарегистрировать обработчики"""
        
        @self.bot.message_handler(commands=['ban'])
        def cmd_ban(message):
            self._handle_ban(message)
        
        @self.bot.message_handler(commands=['unban'])
        def cmd_unban(message):
            self._handle_unban(message)
        
        @self.bot.message_handler(commands=['banlist'])
        def cmd_banlist(message):
            self._handle_banlist(message)
        
        @self.bot.message_handler(commands=['recent'])
        def cmd_recent(message):
            self._handle_recent(message)
        
        logger.info("Ban handlers registered")
    
    def register_callbacks(self):
        """Зарегистрировать callback обработчики"""
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("ban_user_"))
        def callback_ban_user(call):
            self._callback_ban_user(call)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("unban_user_"))
        def callback_unban_user(call):
            self._callback_unban_user(call)
    
    def _handle_ban(self, message):
        """Забанить пользователя по ID или username"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                help_text = (
                    "❗️ Использование:\n\n"
                    "• /ban <user_id> [причина]\n"
                    "• /ban @username [причина]\n"
                    "• /recent — показать последних пользователей"
                )
                self.bot.reply_to(message, help_text)
                return
            
            user_identifier = args[1]
            reason = args[2] if len(args) > 2 else "-"
            
            # Проверка: ID или username
            if user_identifier.startswith("@"):
                # Бан по username
                username = user_identifier[1:]  # Убрать @
                user_id = self.db.get_user_id_by_username(username)
                
                if not user_id:
                    self.bot.reply_to(message, f"❌ Пользователь @{username} не найден в базе")
                    return
                
                self.db.ban_user(user_id, reason)
                self.bot.reply_to(message, f"✅ Пользователь @{username} (ID: {user_id}) забанен\nПричина: {reason}")
                logger.info(f"Admin {message.from_user.id} banned @{username} ({user_id}): {reason}")
                
            else:
                # Бан по ID
                try:
                    user_id = int(user_identifier)
                except ValueError:
                    self.bot.reply_to(message, "❌ Неверный формат. Используйте ID или @username")
                    return
                
                self.db.ban_user(user_id, reason)
                self.bot.reply_to(message, f"✅ Пользователь {user_id} забанен\nПричина: {reason}")
                logger.info(f"Admin {message.from_user.id} banned user {user_id}: {reason}")
            
        except Exception as e:
            logger.error(f"Error in /ban: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка при бане")
    
    def _handle_unban(self, message):
        """Разбанить пользователя по ID или username"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            args = message.text.split()
            if len(args) < 2:
                self.bot.reply_to(message, "❗️ Использование: /unban <user_id> или /unban @username")
                return
            
            user_identifier = args[1]
            
            # Проверка: ID или username
            if user_identifier.startswith("@"):
                # Разбан по username
                username = user_identifier[1:]
                user_id = self.db.get_user_id_by_username(username)
                
                if not user_id:
                    self.bot.reply_to(message, f"❌ Пользователь @{username} не найден в базе")
                    return
                
                self.db.unban_user(user_id)
                self.bot.reply_to(message, f"✅ Пользователь @{username} (ID: {user_id}) разбанен")
                logger.info(f"Admin {message.from_user.id} unbanned @{username} ({user_id})")
                
            else:
                # Разбан по ID
                try:
                    user_id = int(user_identifier)
                except ValueError:
                    self.bot.reply_to(message, "❌ Неверный формат. Используйте ID или @username")
                    return
                
                self.db.unban_user(user_id)
                self.bot.reply_to(message, f"✅ Пользователь {user_id} разбанен")
                logger.info(f"Admin {message.from_user.id} unbanned user {user_id}")
            
        except Exception as e:
            logger.error(f"Error in /unban: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка при разбане")
    
    def _handle_banlist(self, message):
        """Показать список забаненных"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            banned = self.db.get_banned_users_detailed()
            
            if not banned:
                self.bot.reply_to(message, "📋 Список банов пуст")
                return
            
            text = f"📋 Забаненные пользователи ({len(banned)}):\n\n"
            
            for user_info in banned:
                user_id = user_info['user_id']
                username = user_info.get('username', 'нет')
                first_name = user_info.get('first_name', 'нет')
                reason = user_info.get('reason', '-')
                
                username_str = f"@{username}" if username else "нет username"
                text += f"• ID: {user_id}\n"
                text += f"  Username: {username_str}\n"
                text += f"  Имя: {first_name}\n"
                text += f"  Причина: {reason}\n\n"
            
            # Разбить на части если слишком длинное
            if len(text) > 4000:
                parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for part in parts:
                    self.bot.send_message(message.chat.id, part)
            else:
                self.bot.reply_to(message, text)
            
            logger.info(f"Admin {message.from_user.id} viewed ban list")
            
        except Exception as e:
            logger.error(f"Error in /banlist: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка получения списка")
    
    def _handle_recent(self, message):
        """Показать последних 10 пользователей с кнопками бана"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            recent_users = self.db.get_recent_users(limit=10)
            
            if not recent_users:
                self.bot.reply_to(message, "📋 Нет пользователей в базе")
                return
            
            text = "📋 Последние 10 пользователей:\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for i, user_info in enumerate(recent_users, 1):
                user_id = user_info['user_id']
                username = user_info.get('username')
                first_name = user_info.get('first_name', 'Без имени')
                is_banned = user_info.get('is_banned', False)
                
                # Формирование строки
                username_str = f"@{username}" if username else "нет username"
                status = "🚫 ЗАБАНЕН" if is_banned else "✅"
                
                text += f"{i}. {status} {first_name}\n"
                text += f"   ID: {user_id}\n"
                text += f"   {username_str}\n\n"
                
                # Кнопка бана/разбана
                if is_banned:
                    btn_text = f"✅ Разбанить {first_name}"
                    callback_data = f"unban_user_{user_id}"
                else:
                    btn_text = f"🚫 Забанить {first_name}"
                    callback_data = f"ban_user_{user_id}"
                
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
            
            self.bot.reply_to(message, text, reply_markup=markup)
            logger.info(f"Admin {message.from_user.id} viewed recent users")
            
        except Exception as e:
            logger.error(f"Error in /recent: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка получения списка пользователей")
    
    def _callback_ban_user(self, call):
        """Обработка кнопки бана пользователя"""
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            user_id = int(call.data.split("_")[2])
            
            # Забанить
            self.db.ban_user(user_id, "Забанен через кнопку админом")
            
            # Получить инфо о пользователе
            user_info = self.db.get_user_info(user_id)
            username = user_info.get('username') if user_info else None
            first_name = user_info.get('first_name', 'Пользователь') if user_info else 'Пользователь'
            
            username_str = f"@{username}" if username else ""
            
            # Обновить сообщение
            self.bot.answer_callback_query(call.id, f"✅ {first_name} забанен")
            self.bot.edit_message_text(
                f"✅ Пользователь {first_name} {username_str} (ID: {user_id}) забанен\n\n"
                f"Используйте /recent для обновления списка",
                call.message.chat.id,
                call.message.message_id
            )
            
            logger.info(f"Admin {call.from_user.id} banned user {user_id} via button")
            
        except Exception as e:
            logger.error(f"Error in callback ban: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _callback_unban_user(self, call):
        """Обработка кнопки разбана пользователя"""
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            user_id = int(call.data.split("_")[2])
            
            # Разбанить
            self.db.unban_user(user_id)
            
            # Получить инфо о пользователе
            user_info = self.db.get_user_info(user_id)
            username = user_info.get('username') if user_info else None
            first_name = user_info.get('first_name', 'Пользователь') if user_info else 'Пользователь'
            
            username_str = f"@{username}" if username else ""
            
            # Обновить сообщение
            self.bot.answer_callback_query(call.id, f"✅ {first_name} разбанен")
            self.bot.edit_message_text(
                f"✅ Пользователь {first_name} {username_str} (ID: {user_id}) разбанен\n\n"
                f"Используйте /recent для обновления списка",
                call.message.chat.id,
                call.message.message_id
            )
            
            logger.info(f"Admin {call.from_user.id} unbanned user {user_id} via button")
            
        except Exception as e:
            logger.error(f"Error in callback unban: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def is_banned(self, user_id: int) -> bool:
        """Проверить, забанен ли пользователь"""
        return self.db.is_banned(user_id)
