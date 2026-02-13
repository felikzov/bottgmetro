"""
Модуль массовой рассылки (гонг)
"""
import logging
from telebot import TeleBot, types
from database import Database
from config import ADMINS, MAX_GONG_TEXT_LENGTH, GONG_RATE_LIMIT, GONG_DELAY
from utils import validate_text_length, RateLimiter

logger = logging.getLogger(__name__)


class GongManager:
    """Управление массовой рассылкой"""
    
    def __init__(self, bot: TeleBot, db: Database):
        self.bot = bot
        self.db = db
        self.waiting_for_text = set()
    
    def register_handlers(self):
        """Зарегистрировать обработчики"""
        
        @self.bot.message_handler(commands=['gong'])
        def cmd_gong(message):
            self._start_gong(message)
        
        @self.bot.message_handler(func=lambda m: m.from_user.id in self.waiting_for_text)
        def gong_text(message):
            self._handle_gong_text(message)
        
        logger.info("Gong handlers registered")
    
    def _start_gong(self, message):
        """Начать процесс рассылки"""
        try:
            if message.from_user.id not in ADMINS:
                return
            
            self.waiting_for_text.add(message.from_user.id)
            self.bot.reply_to(message, "📢 Отправьте текст для рассылки:")
            logger.info(f"Admin {message.from_user.id} started gong")
            
        except Exception as e:
            logger.error(f"Error starting gong: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка запуска рассылки")
    
    def _handle_gong_text(self, message):
        """Обработать текст и выполнить рассылку"""
        try:
            user_id = message.from_user.id
            
            if user_id not in ADMINS:
                return
            
            self.waiting_for_text.discard(user_id)
            text = message.text.strip()
            
            # Валидация
            valid, error = validate_text_length(text, MAX_GONG_TEXT_LENGTH, "Текст рассылки")
            if not valid:
                self.bot.reply_to(message, error)
                return
            
            # Получить всех пользователей
            all_users = self.db.get_all_user_ids()
            
            if not all_users:
                self.bot.reply_to(message, "❗️ Нет пользователей для рассылки")
                return
            
            # Подтверждение
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Да", callback_data=f"gong_confirm_{message.message_id}"),
                types.InlineKeyboardButton("❌ Нет", callback_data="gong_cancel")
            )
            
            confirm_text = f"📢 Рассылка для {len(all_users)} пользователей:\n\n{text}\n\n❓ Подтвердите рассылку:"
            self.bot.reply_to(message, confirm_text, reply_markup=markup)
            
            # Сохранить текст временно
            self.bot.send_message(user_id, f"_gong_text_{message.message_id}_{text}", parse_mode=None)
            
        except Exception as e:
            logger.error(f"Error handling gong text: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка обработки текста")
    
    def register_callbacks(self):
        """Зарегистрировать callback обработчики"""
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("gong_confirm_"))
        def confirm_gong(call):
            self._execute_gong(call)
        
        @self.bot.callback_query_handler(func=lambda c: c.data == "gong_cancel")
        def cancel_gong(call):
            self._cancel_gong(call)
    
    def _execute_gong(self, call):
        """Выполнить рассылку"""
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            # Извлечь ID сообщения с текстом
            msg_id = int(call.data.split("_")[2])
            
            # Найти текст в истории сообщений
            text = None
            try:
                # Попытка найти сохраненное сообщение
                for i in range(1, 20):
                    try:
                        msg = self.bot.forward_message(call.from_user.id, call.from_user.id, call.message.message_id - i)
                        if msg.text and msg.text.startswith(f"_gong_text_{msg_id}_"):
                            text = msg.text.replace(f"_gong_text_{msg_id}_", "")
                            self.bot.delete_message(call.from_user.id, msg.message_id)
                            break
                    except:
                        continue
            except:
                pass
            
            if not text:
                # Резервный вариант - извлечь из сообщения с подтверждением
                lines = call.message.text.split("\n")
                if len(lines) >= 3:
                    text = "\n".join(lines[1:-2])
            
            if not text:
                self.bot.answer_callback_query(call.id, "❌ Текст не найден")
                return
            
            all_users = self.db.get_all_user_ids()
            
            self.bot.answer_callback_query(call.id, "🔄 Рассылка началась...")
            self.bot.edit_message_text(
                "🔄 Рассылка в процессе...",
                call.message.chat.id,
                call.message.message_id
            )
            
            # Выполнить рассылку с rate limiting
            rate_limiter = RateLimiter(GONG_RATE_LIMIT, GONG_DELAY)
            success_count = 0
            fail_count = 0
            
            for i, user_id in enumerate(all_users, 1):
                try:
                    rate_limiter.wait_if_needed()
                    self.bot.send_message(user_id, text)
                    success_count += 1
                    
                    # Обновлять прогресс каждые 50 сообщений
                    if i % 50 == 0:
                        try:
                            self.bot.edit_message_text(
                                f"🔄 Прогресс: {i}/{len(all_users)} ({success_count} успешно, {fail_count} ошибок)",
                                call.message.chat.id,
                                call.message.message_id
                            )
                        except:
                            pass
                    
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Failed to send gong to {user_id}: {e}")
            
            # Итоговый отчет
            result_text = (
                f"✅ Рассылка завершена!\n\n"
                f"📊 Статистика:\n"
                f"• Всего пользователей: {len(all_users)}\n"
                f"• Успешно: {success_count}\n"
                f"• Ошибок: {fail_count}"
            )
            
            self.bot.edit_message_text(result_text, call.message.chat.id, call.message.message_id)
            logger.info(f"Gong completed: {success_count}/{len(all_users)} successful")
            
        except Exception as e:
            logger.error(f"Error executing gong: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка рассылки")
    
    def _cancel_gong(self, call):
        """Отменить рассылку"""
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            self.bot.edit_message_text("❌ Рассылка отменена", call.message.chat.id, call.message.message_id)
            self.bot.answer_callback_query(call.id, "Отменено")
            logger.info(f"Admin {call.from_user.id} cancelled gong")
            
        except Exception as e:
            logger.error(f"Error cancelling gong: {e}", exc_info=True)
