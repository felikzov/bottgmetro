"""
Главный модуль запуска бота
"""
import logging
import time
import signal
import sys
from telebot import TeleBot

from config import (
    BOT_TOKEN, DATABASE_PATH, LOG_FILE, LOG_LEVEL,
    POLLING_TIMEOUT, LONG_POLLING_TIMEOUT, STATE_TIMEOUT, KEEPALIVE_INTERVAL
)
from database import Database
from state_manager import StateManager
from bot import ReportBot
from admin.ban import BanManager
from admin.gong import GongManager
from admin.trains import TrainsManager
from utils import setup_logging

logger = logging.getLogger(__name__)


class MetroBot:
    """Главный класс бота"""
    
    def __init__(self):
        # Настройка логирования
        setup_logging(LOG_FILE, LOG_LEVEL)
        logger.info("="*50)
        logger.info("Metro Bot Starting...")
        
        # Инициализация компонентов
        self.bot = TeleBot(BOT_TOKEN, threaded=True, num_threads=4)
        self.db = Database(DATABASE_PATH)
        self.state_mgr = StateManager(self.db)
        
        # Инициализация модулей
        self.ban_mgr = BanManager(self.bot, self.db)
        self.report_bot = ReportBot(self.bot, self.db, self.state_mgr, self.ban_mgr)
        self.gong_mgr = GongManager(self.bot, self.db)
        self.trains_mgr = TrainsManager(self.bot, self.db)
        
        # Флаг для остановки
        self.running = True
        
        # Настройка обработчика сигналов
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов остановки"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.bot.stop_polling()
        sys.exit(0)
    
    def _register_all_handlers(self):
        """Зарегистрировать все обработчики"""
        logger.info("Registering handlers...")
        
        # Регистрация модулей
        self.report_bot.register_handlers()
        self.ban_mgr.register_handlers()
        self.ban_mgr.register_callbacks()  # Добавлено
        self.gong_mgr.register_handlers()
        self.gong_mgr.register_callbacks()
        self.trains_mgr.register_handlers()
        
        # Команда помощи для админов
        @self.bot.message_handler(commands=['help', 'admin'])
        def cmd_help(message):
            from config import ADMINS
            if message.from_user.id not in ADMINS:
                return
            
            help_text = (
                "🔧 Админские команды:\n\n"
                "👤 Управление пользователями:\n"
                "• /ban <user_id|@username> [причина] — забанить\n"
                "• /unban <user_id|@username> — разбанить\n"
                "• /banlist — список банов\n"
                "• /recent — последние 10 пользователей (с кнопками)\n\n"
                "📢 Рассылка:\n"
                "• /gong — начать рассылку\n\n"
                "🚆 Управление составами:\n"
                "• /trains — показать список\n"
                "• /edittrains — редактировать список (с кнопкой отмены)\n\n"
                "ℹ️ Другое:\n"
                "• /help — эта справка\n"
                "• /stats — статистика бота"
            )
            
            self.bot.reply_to(message, help_text)
        
        # Статистика
        @self.bot.message_handler(commands=['stats'])
        def cmd_stats(message):
            from config import ADMINS
            if message.from_user.id not in ADMINS:
                return
            
            try:
                total_users = len(self.db.get_all_user_ids())
                banned_users = len(self.db.get_banned_users())
                total_trains = len(self.db.get_trains())
                
                stats_text = (
                    f"📊 Статистика бота:\n\n"
                    f"👥 Всего пользователей: {total_users}\n"
                    f"🚫 Забанено: {banned_users}\n"
                    f"🚆 Составов в базе: {total_trains}"
                )
                
                self.bot.reply_to(message, stats_text)
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                self.bot.reply_to(message, "❌ Ошибка получения статистики")
        
        logger.info("All handlers registered successfully")
    
    def _cleanup_task(self):
        """Периодическая очистка старых состояний"""
        last_cleanup = time.time()
        cleanup_interval = 300  # 5 минут
        
        while self.running:
            try:
                current_time = time.time()
                if current_time - last_cleanup >= cleanup_interval:
                    self.db.cleanup_old_states(STATE_TIMEOUT)
                    last_cleanup = current_time
                time.sleep(60)  # Проверка каждую минуту
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    def run(self):
        """Запустить бота"""
        try:
            self._register_all_handlers()
            
            # Запустить фоновую задачу keepalive
            import threading
            keepalive_thread = threading.Thread(target=self._keepalive_task, daemon=True)
            keepalive_thread.start()
            logger.info("Keepalive task started")
            
            logger.info("Bot is starting polling...")
            logger.info(f"Timeout: {POLLING_TIMEOUT}s, Long polling: {LONG_POLLING_TIMEOUT}s")
            
            # Запуск в бесконечном цикле с обработкой ошибок
            retry_count = 0
            max_retries = 10
            
            while self.running and retry_count < max_retries:
                try:
                    self.bot.infinity_polling(
                        timeout=POLLING_TIMEOUT,
                        long_polling_timeout=LONG_POLLING_TIMEOUT,
                        none_stop=True,
                        interval=0,  # Без задержки между запросами
                        allowed_updates=["message", "callback_query"]  # Только нужные типы
                    )
                    
                except Exception as e:
                    retry_count += 1
                    wait_time = min(5 * (2 ** (retry_count - 1)), 60)
                    
                    logger.error(
                        f"Polling error (attempt {retry_count}/{max_retries}): {e}",
                        exc_info=True
                    )
                    
                    if retry_count < max_retries:
                        logger.info(f"Restarting in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        logger.critical("Max retries reached, shutting down")
                        break
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.critical(f"Critical error in main loop: {e}", exc_info=True)
        finally:
            logger.info("Bot stopped")
    
    def _keepalive_task(self):
        """Фоновая задача для поддержания активности бота"""
        import time
        
        # Подождать 30 секунд после старта
        time.sleep(30)
        
        while self.running:
            try:
                # Получить информацию о боте (лёгкий API запрос)
                self.bot.get_me()
                logger.debug("Keepalive ping sent")
                
                # Очистить старые состояния
                self.db.cleanup_old_states(STATE_TIMEOUT)
                
                # Подождать до следующего пинга
                time.sleep(KEEPALIVE_INTERVAL)
                
            except Exception as e:
                logger.warning(f"Keepalive ping failed: {e}")
                time.sleep(KEEPALIVE_INTERVAL * 1.5)  # При ошибке подождать дольше


def main():
    """Точка входа"""
    bot = MetroBot()
    bot.run()


if __name__ == "__main__":
    main()
