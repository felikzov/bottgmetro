"""
Главный модуль бота с обработчиками отчетов
"""
import logging
from datetime import datetime, timedelta
from telebot import TeleBot, types

from config import (
    LINES, LINE_EMOJI, STATIONS, TIMES, States,
    MAX_COMMENT_LENGTH, MAX_TRAIN_NAME_LENGTH, CHANNEL_ID
)
from database import Database
from state_manager import StateManager
from utils import (
    safe_html, format_user_link, validate_text_length,
    validate_route_number, parse_time_ago, retry_on_error
)

logger = logging.getLogger(__name__)


class ReportBot:
    """Основной класс бота для создания отчетов"""
    
    def __init__(self, bot: TeleBot, db: Database, state_mgr: StateManager, ban_mgr):
        self.bot = bot
        self.db = db
        self.state_mgr = state_mgr
        self.ban_mgr = ban_mgr
    
    def register_handlers(self):
        """Зарегистрировать все обработчики"""
        
        @self.bot.message_handler(commands=['start'])
        def cmd_start(message):
            self._handle_start(message)
        
        @self.bot.message_handler(func=lambda m: m.text == "📨 Сообщить о вагоне")
        def start_report(message):
            self._start_report(message)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("line_"))
        def select_line(call):
            self._select_line(call)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("train_"))
        def select_train(call):
            self._select_train(call)
        
        @self.bot.message_handler(func=lambda m: self.state_mgr.get_state(m.from_user.id) == States.TRAIN_MANUAL)
        def manual_train(message):
            self._manual_train(message)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("station_"))
        def select_station(call):
            self._select_station(call)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("direction_"))
        def select_direction(call):
            self._select_direction(call)
        
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("time_"))
        def select_time(call):
            self._select_time(call)
        
        @self.bot.message_handler(func=lambda m: self.state_mgr.get_state(m.from_user.id) == States.ROUTE_CHOICE)
        def route_choice(message):
            self._route_choice(message)
        
        @self.bot.message_handler(func=lambda m: self.state_mgr.get_state(m.from_user.id) == States.ROUTE_MANUAL)
        def manual_route(message):
            self._manual_route(message)
        
        @self.bot.message_handler(func=lambda m: self.state_mgr.get_state(m.from_user.id) == States.COMMENT)
        def comment_input(message):
            self._comment_input(message)
        
        @self.bot.callback_query_handler(func=lambda c: c.data in ["confirm_publish", "confirm_cancel"])
        def confirm_action(call):
            self._confirm_action(call)
        
        logger.info("Report handlers registered")
    
    def _handle_start(self, message):
        """Команда /start"""
        try:
            user = message.from_user
            
            # Проверка бана
            if self.ban_mgr.is_banned(user.id):
                self.bot.send_message(
                    message.chat.id,
                    "❌ Вы заблокированы и не можете использовать бота."
                )
                return
            
            self.db.add_user(user.id, user.username, user.first_name)
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("📨 Сообщить о вагоне")
            
            self.bot.send_message(
                message.chat.id,
                "👋🏻 Здравствуйте! Здесь вы можете сообщить о необычном вагоне/составе.",
                reply_markup=markup
            )
            logger.info(f"User {user.id} started bot")
        except Exception as e:
            logger.error(f"Error in /start: {e}", exc_info=True)
    
    def _start_report(self, message):
        """Начать создание отчета"""
        try:
            user_id = message.from_user.id
            
            # Проверка бана
            if self.ban_mgr.is_banned(user_id):
                self.bot.send_message(
                    message.chat.id,
                    "❌ Вы заблокированы и не можете использовать бота."
                )
                return
            
            self.state_mgr.clear_state(user_id)
            self.state_mgr.set_state(user_id, States.LINE)
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            for line_id, line_name in LINES.items():
                emoji = LINE_EMOJI[line_id]
                markup.add(types.InlineKeyboardButton(
                    f"{emoji} {line_name} ({line_id}) {emoji}",
                    callback_data=f"line_{line_id}"
                ))
            
            msg = self.bot.send_message(message.chat.id, "1️⃣ Выберите линию:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
            logger.info(f"User {user_id} started report")
        except Exception as e:
            logger.error(f"Error starting report: {e}", exc_info=True)
            self._error_msg(message.chat.id)
    
    def _select_line(self, call):
        """Выбор линии"""
        try:
            if not self._check_state(call, States.LINE):
                return
            
            user_id = call.from_user.id
            line_id = call.data.split("_")[1]
            
            if line_id not in LINES:
                self.bot.answer_callback_query(call.id, "❌ Неверная линия")
                return
            
            self.state_mgr.update_data(user_id, {'line': line_id})
            self.state_mgr.set_state(user_id, States.TRAIN)
            self._delete_msg(user_id, call.message.chat.id)
            
            # Полный список составов по умолчанию
            trains = self.db.get_trains()
            if not trains:
                trains = [
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
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            for train in trains:
                markup.add(types.InlineKeyboardButton(train, callback_data=f"train_{train}"))
            markup.add(types.InlineKeyboardButton("✍️ Ввести вручную", callback_data="train_manual"))
            
            msg = self.bot.send_message(call.message.chat.id, "2️⃣ Выберите состав:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error selecting line: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _select_train(self, call):
        """Выбор состава"""
        try:
            if not self._check_state(call, States.TRAIN):
                return
            
            user_id = call.from_user.id
            data = call.data.split("_", 1)[1]
            
            if data == "manual":
                self.state_mgr.set_state(user_id, States.TRAIN_MANUAL)
                self._delete_msg(user_id, call.message.chat.id)
                msg = self.bot.send_message(call.message.chat.id, "✍️ Введите название состава:")
                self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
            else:
                self.state_mgr.set_data(user_id, 'train', data)
                self.state_mgr.set_state(user_id, States.STATION)
                self._delete_msg(user_id, call.message.chat.id)
                self._ask_station(user_id, call.message.chat.id)
            
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error selecting train: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _manual_train(self, message):
        """Ручной ввод состава"""
        try:
            user_id = message.from_user.id
            train = message.text.strip()
            
            valid, error = validate_text_length(train, MAX_TRAIN_NAME_LENGTH, "Название")
            if not valid:
                self._delete_msg(user_id, message.chat.id)
                msg = self.bot.send_message(message.chat.id, error)
                self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
                return
            
            self.state_mgr.set_data(user_id, 'train', train)
            self.state_mgr.set_state(user_id, States.STATION)
            self._delete_msg(user_id, message.chat.id)
            self._ask_station(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Error in manual train: {e}", exc_info=True)
            self._error_msg(message.chat.id)
    
    def _ask_station(self, user_id: int, chat_id: int):
        """Запросить станцию"""
        try:
            data = self.state_mgr.get_data(user_id)
            line_id = data.get('line')
            
            if not line_id or line_id not in STATIONS:
                self._error_msg(chat_id)
                return
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            for station in STATIONS[line_id]:
                markup.add(types.InlineKeyboardButton(station, callback_data=f"station_{station}"))
            
            msg = self.bot.send_message(chat_id, "3️⃣ Станция обнаружения:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error asking station: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _select_station(self, call):
        """Выбор станции"""
        try:
            if not self._check_state(call, States.STATION):
                return
            
            user_id = call.from_user.id
            station = call.data.split("_", 1)[1]
            
            self.state_mgr.set_data(user_id, 'station', station)
            self.state_mgr.set_state(user_id, States.DIRECTION)
            self._delete_msg(user_id, call.message.chat.id)
            self._ask_direction(user_id, call.message.chat.id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error selecting station: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _ask_direction(self, user_id: int, chat_id: int):
        """Запросить направление"""
        try:
            data = self.state_mgr.get_data(user_id)
            line_id = data.get('line')
            
            if not line_id or line_id not in STATIONS:
                self._error_msg(chat_id)
                return
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            for station in STATIONS[line_id]:
                markup.add(types.InlineKeyboardButton(station, callback_data=f"direction_{station}"))
            
            msg = self.bot.send_message(chat_id, "4️⃣ Направление/конечная:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error asking direction: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _select_direction(self, call):
        """Выбор направления"""
        try:
            if not self._check_state(call, States.DIRECTION):
                return
            
            user_id = call.from_user.id
            direction = call.data.split("_", 1)[1]
            
            self.state_mgr.set_data(user_id, 'direction', direction)
            self.state_mgr.set_state(user_id, States.TIME)
            self._delete_msg(user_id, call.message.chat.id)
            self._ask_time(user_id, call.message.chat.id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error selecting direction: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _ask_time(self, user_id: int, chat_id: int):
        """Запросить время"""
        try:
            markup = types.InlineKeyboardMarkup(row_width=3)
            for time_opt in TIMES:
                markup.add(types.InlineKeyboardButton(time_opt, callback_data=f"time_{time_opt}"))
            
            msg = self.bot.send_message(chat_id, "5️⃣ Время обнаружения:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error asking time: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _select_time(self, call):
        """Выбор времени"""
        try:
            if not self._check_state(call, States.TIME):
                return
            
            user_id = call.from_user.id
            time_str = call.data.split("_", 1)[1]
            minutes_ago = parse_time_ago(time_str)
            real_time = (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%H:%M")
            
            self.state_mgr.set_data(user_id, 'time', real_time)
            self.state_mgr.set_state(user_id, States.ROUTE_CHOICE)
            self._delete_msg(user_id, call.message.chat.id)
            self._ask_route(user_id, call.message.chat.id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error selecting time: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    def _ask_route(self, user_id: int, chat_id: int):
        """Запросить маршрут"""
        try:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("Указать маршрут", "Пропустить")
            
            msg = self.bot.send_message(chat_id, "6️⃣ Маршрут (трёхзначное число) или пропустить:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error asking route: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _route_choice(self, message):
        """Выбор маршрута"""
        try:
            user_id = message.from_user.id
            choice = message.text.strip()
            
            if choice == "Пропустить":
                self.state_mgr.set_data(user_id, 'route', "-")
                self.state_mgr.set_state(user_id, States.COMMENT)
                self._ask_comment(user_id, message.chat.id)
            elif choice == "Указать маршрут":
                self.state_mgr.set_state(user_id, States.ROUTE_MANUAL)
                msg = self.bot.send_message(message.chat.id, "✍️ Введите маршрут (трёхзначное число):")
                self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
            else:
                msg = self.bot.send_message(message.chat.id, "❗️ Выберите кнопку")
                self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error in route choice: {e}", exc_info=True)
            self._error_msg(message.chat.id)
    
    def _manual_route(self, message):
        """Ручной ввод маршрута"""
        try:
            user_id = message.from_user.id
            route = message.text.strip()
            
            valid, error = validate_route_number(route)
            if not valid:
                msg = self.bot.send_message(message.chat.id, error)
                self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
                return
            
            self.state_mgr.set_data(user_id, 'route', route)
            self.state_mgr.set_state(user_id, States.COMMENT)
            self._ask_comment(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Error in manual route: {e}", exc_info=True)
            self._error_msg(message.chat.id)
    
    def _ask_comment(self, user_id: int, chat_id: int):
        """Запросить комментарий"""
        try:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add("Без комментария")
            
            msg = self.bot.send_message(chat_id, "7️⃣ Комментарий или «Без комментария»:", reply_markup=markup)
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error asking comment: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _comment_input(self, message):
        """Ввод комментария"""
        try:
            user_id = message.from_user.id
            comment = message.text.strip()
            
            if comment.lower() == "без комментария":
                comment = "-"
            else:
                valid, error = validate_text_length(comment, MAX_COMMENT_LENGTH, "Комментарий")
                if not valid:
                    msg = self.bot.send_message(message.chat.id, error)
                    self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
                    return
            
            self.state_mgr.set_data(user_id, 'comment', comment)
            self.state_mgr.set_state(user_id, States.CONFIRM)
            self._show_confirm(user_id, message.chat.id, message.from_user)
        except Exception as e:
            logger.error(f"Error in comment: {e}", exc_info=True)
            self._error_msg(message.chat.id)
    
    def _show_confirm(self, user_id: int, chat_id: int, user):
        """Показать подтверждение"""
        try:
            data = self.state_mgr.get_data(user_id)
            required = ['line', 'train', 'station', 'direction', 'time', 'route', 'comment']
            
            if not all(k in data for k in required):
                self._error_msg(chat_id)
                self.state_mgr.clear_state(user_id)
                return
            
            user_link = format_user_link(user.id, user.username, user.first_name)
            emoji = LINE_EMOJI.get(data['line'], "")
            
            text = (
                f"8️⃣ Проверьте перед публикацией:\n\n"
                f"🚇 Линия: {emoji} {data['line']} {emoji}\n"
                f"🚆 Состав: {safe_html(data['train'])}\n"
                f"📍 Станция: {safe_html(data['station'])}\n"
                f"⬆️ Направление: {safe_html(data['direction'])}\n"
                f"🕐 Время: {data['time']}\n"
                f"💬 Комментарий: {safe_html(data['comment'])}\n"
                f"🔁 Маршрут: {data['route']}\n"
                f"📫 Прислал: {user_link}\n"
                f"\nПредложка: @vagon_pred_bot"
            )
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ Опубликовать", callback_data="confirm_publish"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="confirm_cancel")
            )
            
            msg = self.bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            self.state_mgr.set_data(user_id, 'last_msg', msg.message_id)
        except Exception as e:
            logger.error(f"Error showing confirm: {e}", exc_info=True)
            self._error_msg(chat_id)
    
    def _confirm_action(self, call):
        """Подтверждение/отмена"""
        try:
            if not self._check_state(call, States.CONFIRM):
                return
            
            user_id = call.from_user.id
            
            if call.data == "confirm_publish":
                success = self._publish(user_id, call.message.chat.id, call.from_user)
                
                if success:
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    markup.add("📨 Сообщить о вагоне")
                    self.bot.send_message(call.message.chat.id, "✅ Опубликовано!", reply_markup=markup)
                else:
                    self.bot.send_message(call.message.chat.id, "❌ Ошибка публикации")
            else:
                self.bot.send_message(call.message.chat.id, "❌ Отменено. Используйте /start для новой попытки.")
            
            try:
                self.bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            self.state_mgr.clear_state(user_id)
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Error in confirm: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")
    
    @retry_on_error(max_retries=3, delay=1.0)
    def _publish(self, user_id: int, chat_id: int, user) -> bool:
        """Опубликовать в канал"""
        try:
            data = self.state_mgr.get_data(user_id)
            user_link = format_user_link(user.id, user.username, user.first_name)
            emoji = LINE_EMOJI.get(data['line'], "")
            
            text = (
                f"🚇 Линия: {emoji} {data['line']} {emoji}\n"
                f"🚆 Состав: {safe_html(data['train'])}\n"
                f"📍 Станция: {safe_html(data['station'])}\n"
                f"⬆️ Направление: {safe_html(data['direction'])}\n"
                f"🕐 Время: {data['time']}\n"
                f"💬 Комментарий: {safe_html(data['comment'])}\n"
                f"🔁 Маршрут: {data['route']}\n"
                f"📫 Прислал: {user_link}\n"
                f"\nПредложка: @vagon_pred_bot"
            )
            
            self.bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
            logger.info(f"Published report from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish: {e}", exc_info=True)
            return False
    
    def _check_state(self, call, expected: int) -> bool:
        """Проверить состояние"""
        if not call.message:
            self.bot.answer_callback_query(call.id, "❌ Устарело")
            return False
        
        if self.state_mgr.get_state(call.from_user.id) != expected:
            self.bot.answer_callback_query(call.id, "❌ Начните с /start")
            return False
        
        return True
    
    def _delete_msg(self, user_id: int, chat_id: int):
        """Удалить последнее сообщение"""
        try:
            msg_id = self.state_mgr.get_data(user_id).get('last_msg')
            if msg_id:
                self.bot.delete_message(chat_id, msg_id)
        except:
            pass
    
    def _error_msg(self, chat_id: int):
        """Сообщение об ошибке"""
        try:
            self.bot.send_message(chat_id, "❗️ Ошибка. Попробуйте /start")
        except Exception as e:
            logger.error(f"Could not send error: {e}")
