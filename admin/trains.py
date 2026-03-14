"""
Модуль управления списком составов — команда /trains
Кнопки: добавить поезд, удалить конкретный, удалить все
"""
import logging
from telebot import TeleBot, types
from database import Database
from config import ADMINS

logger = logging.getLogger(__name__)


class TrainsManager:

    def __init__(self, bot: TeleBot, db: Database):
        self.bot = bot
        self.db  = db
        # user_id -> ждём ввод названия нового поезда
        self._waiting_add: set = set()

    def register_handlers(self):
        @self.bot.message_handler(commands=['trains'])
        def cmd_trains(message):
            self._show_trains(message)

        @self.bot.message_handler(func=lambda m: m.from_user.id in self._waiting_add)
        def add_train_text(message):
            self._handle_add_text(message)

        logger.info("Trains handlers registered")

    def register_callbacks(self):
        # Главное меню управления
        @self.bot.callback_query_handler(func=lambda c: c.data == "trains_menu")
        def cb_menu(call):
            self._edit_menu(call)

        # Запрос добавления
        @self.bot.callback_query_handler(func=lambda c: c.data == "trains_add")
        def cb_add(call):
            self._ask_add(call)

        # Показать список для удаления
        @self.bot.callback_query_handler(func=lambda c: c.data == "trains_delete_list")
        def cb_delete_list(call):
            self._show_delete_list(call)

        # Удалить конкретный поезд
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("trains_del_"))
        def cb_delete_one(call):
            self._delete_one(call)

        # Удалить все поезда — запрос подтверждения
        @self.bot.callback_query_handler(func=lambda c: c.data == "trains_clear_confirm")
        def cb_clear_confirm(call):
            self._clear_confirm(call)

        # Удалить все — подтверждено
        @self.bot.callback_query_handler(func=lambda c: c.data == "trains_clear_yes")
        def cb_clear_yes(call):
            self._clear_all(call)

        logger.info("Trains callbacks registered")

    # ---------- /trains ----------

    def _show_trains(self, message):
        try:
            if message.from_user.id not in ADMINS:
                return
            trains = self.db.get_trains()
            text   = self._trains_text(trains)
            markup = self._main_markup()
            self.bot.send_message(message.chat.id, text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Error in /trains: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка")

    # ---------- вспомогательные ----------

    def _trains_text(self, trains):
        if not trains:
            return "🚆 Список составов пуст"
        lines = "\n".join(f"{i+1}. {t}" for i, t in enumerate(trains))
        return f"🚆 Составы ({len(trains)} шт.):\n\n{lines}"

    def _main_markup(self):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("➕ Добавить поезд",      callback_data="trains_add"),
            types.InlineKeyboardButton("🗑 Удалить поезд",       callback_data="trains_delete_list"),
            types.InlineKeyboardButton("❌ Удалить все составы", callback_data="trains_clear_confirm"),
        )
        return markup

    # ---------- добавление ----------

    def _ask_add(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            self._waiting_add.add(call.from_user.id)
            self.bot.answer_callback_query(call.id)
            self.bot.send_message(call.message.chat.id, "✍️ Введите название нового состава:")
        except Exception as e:
            logger.error(f"Error ask_add: {e}", exc_info=True)

    def _handle_add_text(self, message):
        try:
            user_id = message.from_user.id
            if user_id not in ADMINS:
                return
            self._waiting_add.discard(user_id)

            name = message.text.strip()
            if not name:
                self.bot.reply_to(message, "❗️ Название не может быть пустым")
                return
            if len(name) > 100:
                self.bot.reply_to(message, "❗️ Слишком длинное название (макс. 100 символов)")
                return

            trains = self.db.get_trains()
            if name in trains:
                self.bot.reply_to(message, f"⚠️ Состав «{name}» уже есть в списке")
                return

            trains.append(name)
            self.db.set_trains(trains)

            markup = self._main_markup()
            self.bot.send_message(
                message.chat.id,
                f"✅ Состав «{name}» добавлен!\n\n{self._trains_text(trains)}",
                reply_markup=markup
            )
            logger.info(f"Admin {user_id} added train: {name}")
        except Exception as e:
            logger.error(f"Error handle_add_text: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка при добавлении")

    # ---------- удаление одного ----------

    def _show_delete_list(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            trains = self.db.get_trains()
            if not trains:
                self.bot.answer_callback_query(call.id, "Список уже пуст")
                return

            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, t in enumerate(trains):
                markup.add(types.InlineKeyboardButton(f"🗑 {t}", callback_data=f"trains_del_{i}"))
            markup.add(types.InlineKeyboardButton("« Назад", callback_data="trains_menu"))

            self.bot.answer_callback_query(call.id)
            self.bot.edit_message_text(
                "Выберите состав для удаления:",
                call.message.chat.id, call.message.message_id,
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error show_delete_list: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    def _delete_one(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            idx    = int(call.data.split("_", 2)[2])
            trains = self.db.get_trains()
            if idx < 0 or idx >= len(trains):
                self.bot.answer_callback_query(call.id, "❌ Состав не найден")
                return
            removed = trains.pop(idx)
            self.db.set_trains(trains)

            markup = self._main_markup()
            self.bot.answer_callback_query(call.id, f"✅ «{removed}» удалён")
            self.bot.edit_message_text(
                f"✅ Состав «{removed}» удалён\n\n{self._trains_text(trains)}",
                call.message.chat.id, call.message.message_id,
                reply_markup=markup
            )
            logger.info(f"Admin {call.from_user.id} deleted train: {removed}")
        except Exception as e:
            logger.error(f"Error delete_one: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    # ---------- удалить все ----------

    def _clear_confirm(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ Да, удалить все", callback_data="trains_clear_yes"),
                types.InlineKeyboardButton("« Отмена",           callback_data="trains_menu"),
            )
            self.bot.answer_callback_query(call.id)
            self.bot.edit_message_text(
                "⚠️ Вы уверены, что хотите удалить ВСЕ составы из списка?",
                call.message.chat.id, call.message.message_id,
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error clear_confirm: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    def _clear_all(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            self.db.set_trains([])
            markup = self._main_markup()
            self.bot.answer_callback_query(call.id, "✅ Все составы удалены")
            self.bot.edit_message_text(
                "✅ Все составы удалены.\n\n🚆 Список составов пуст",
                call.message.chat.id, call.message.message_id,
                reply_markup=markup
            )
            logger.info(f"Admin {call.from_user.id} cleared all trains")
        except Exception as e:
            logger.error(f"Error clear_all: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    # ---------- возврат в меню ----------

    def _edit_menu(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            trains = self.db.get_trains()
            markup = self._main_markup()
            self.bot.answer_callback_query(call.id)
            self.bot.edit_message_text(
                self._trains_text(trains),
                call.message.chat.id, call.message.message_id,
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error edit_menu: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
