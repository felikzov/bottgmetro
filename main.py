"""
Главный модуль запуска бота
"""
import logging
import time
import signal
import sys
from telebot import TeleBot

from config import (
    BOT_TOKEN, DATA_DIR, LOG_FILE, LOG_LEVEL,
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

    def __init__(self):
        setup_logging(LOG_FILE, LOG_LEVEL)
        logger.info("=" * 50)
        logger.info("Metro Bot Starting...")

        self.bot       = TeleBot(BOT_TOKEN, threaded=True, num_threads=4)
        self.db        = Database(DATA_DIR)
        self.state_mgr = StateManager(self.db)

        self.ban_mgr    = BanManager(self.bot, self.db)
        self.report_bot = ReportBot(self.bot, self.db, self.state_mgr, self.ban_mgr)
        self.gong_mgr   = GongManager(self.bot, self.db)
        self.trains_mgr = TrainsManager(self.bot, self.db)

        self.running = True
        signal.signal(signal.SIGINT,  self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.bot.stop_polling()
        sys.exit(0)

    def _register_all_handlers(self):
        logger.info("Registering handlers...")
        self.report_bot.register_handlers()
        self.ban_mgr.register_handlers()
        self.ban_mgr.register_callbacks()
        self.gong_mgr.register_handlers()
        self.gong_mgr.register_callbacks()
        self.trains_mgr.register_handlers()
        self.trains_mgr.register_callbacks()
        logger.info("All handlers registered")

    def run(self):
        try:
            self._register_all_handlers()

            import threading
            threading.Thread(target=self._keepalive_task, daemon=True).start()

            logger.info("Bot is starting polling...")
            retry_count = 0
            max_retries = 10

            while self.running and retry_count < max_retries:
                try:
                    self.bot.infinity_polling(
                        timeout=POLLING_TIMEOUT,
                        long_polling_timeout=LONG_POLLING_TIMEOUT,
                        none_stop=True,
                        interval=0,
                        allowed_updates=["message", "callback_query"]
                    )
                except Exception as e:
                    retry_count += 1
                    wait_time = min(5 * (2 ** (retry_count - 1)), 60)
                    logger.error(f"Polling error ({retry_count}/{max_retries}): {e}", exc_info=True)
                    if retry_count < max_retries:
                        time.sleep(wait_time)
                    else:
                        logger.critical("Max retries reached")
                        break

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt")
        except Exception as e:
            logger.critical(f"Critical error: {e}", exc_info=True)
        finally:
            logger.info("Bot stopped")

    def _keepalive_task(self):
        time.sleep(30)
        while self.running:
            try:
                self.bot.get_me()
                self.db.cleanup_old_states(STATE_TIMEOUT)
                time.sleep(KEEPALIVE_INTERVAL)
            except Exception as e:
                logger.warning(f"Keepalive failed: {e}")
                time.sleep(KEEPALIVE_INTERVAL * 1.5)


def main():
    MetroBot().run()


if __name__ == "__main__":
    main()
