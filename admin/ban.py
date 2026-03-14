"""
Модуль управления банами — команды /ban /unban /banlist /recent
"""
import logging
from telebot import TeleBot, types
from database import Database
from config import ADMINS

logger = logging.getLogger(__name__)


class BanManager:

    def __init__(self, bot: TeleBot, db: Database):
        self.bot = bot
        self.db  = db

    def register_handlers(self):
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
        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("ban_user_"))
        def callback_ban_user(call):
            self._callback_ban_user(call)

        @self.bot.callback_query_handler(func=lambda c: c.data.startswith("unban_user_"))
        def callback_unban_user(call):
            self._callback_unban_user(call)

    # ---------- команды ----------

    def _handle_ban(self, message):
        try:
            if message.from_user.id not in ADMINS:
                return
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                self.bot.reply_to(message, "❗️ Использование:\n• /ban <user_id> [причина]\n• /ban @username [причина]")
                return
            identifier = args[1]
            reason     = args[2] if len(args) > 2 else "-"
            user_id = self._resolve_user(message, identifier)
            if user_id is None:
                return
            self.db.ban_user(user_id, reason)
            self.bot.reply_to(message, f"✅ Пользователь {identifier} (ID: {user_id}) забанен\nПричина: {reason}")
            logger.info(f"Admin {message.from_user.id} banned {user_id}: {reason}")
        except Exception as e:
            logger.error(f"Error in /ban: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка при бане")

    def _handle_unban(self, message):
        try:
            if message.from_user.id not in ADMINS:
                return
            args = message.text.split()
            if len(args) < 2:
                self.bot.reply_to(message, "❗️ Использование: /unban <user_id> или /unban @username")
                return
            user_id = self._resolve_user(message, args[1])
            if user_id is None:
                return
            self.db.unban_user(user_id)
            self.bot.reply_to(message, f"✅ Пользователь {args[1]} (ID: {user_id}) разбанен")
            logger.info(f"Admin {message.from_user.id} unbanned {user_id}")
        except Exception as e:
            logger.error(f"Error in /unban: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка при разбане")

    def _handle_banlist(self, message):
        try:
            if message.from_user.id not in ADMINS:
                return
            banned = self.db.get_banned_users_detailed()
            if not banned:
                self.bot.reply_to(message, "📋 Список банов пуст")
                return
            text = f"📋 Забаненные ({len(banned)}):\n\n"
            for u in banned:
                uname = f"@{u['username']}" if u.get("username") else "нет username"
                text += f"• ID: {u['user_id']}\n  {uname} — {u.get('first_name','')}\n  Причина: {u.get('reason','-')}\n\n"
            # разбить если длинно
            for i in range(0, len(text), 4000):
                self.bot.send_message(message.chat.id, text[i:i+4000])
            logger.info(f"Admin {message.from_user.id} viewed banlist")
        except Exception as e:
            logger.error(f"Error in /banlist: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка получения списка")

    def _handle_recent(self, message):
        try:
            if message.from_user.id not in ADMINS:
                return
            recent = self.db.get_recent_users(limit=10)
            if not recent:
                self.bot.reply_to(message, "📋 Нет пользователей в базе")
                return
            text   = "📋 Последние 10 пользователей:\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            for i, u in enumerate(recent, 1):
                uid       = u["user_id"]
                uname     = f"@{u['username']}" if u.get("username") else "нет username"
                fname     = u.get("first_name", "Без имени")
                is_banned = u.get("is_banned", False)
                status    = "🚫 ЗАБАНЕН" if is_banned else "✅"
                text += f"{i}. {status} {fname}\n   ID: {uid}\n   {uname}\n\n"
                if is_banned:
                    markup.add(types.InlineKeyboardButton(f"✅ Разбанить {fname}", callback_data=f"unban_user_{uid}"))
                else:
                    markup.add(types.InlineKeyboardButton(f"🚫 Забанить {fname}", callback_data=f"ban_user_{uid}"))
            self.bot.reply_to(message, text, reply_markup=markup)
            logger.info(f"Admin {message.from_user.id} viewed recent users")
        except Exception as e:
            logger.error(f"Error in /recent: {e}", exc_info=True)
            self.bot.reply_to(message, "❌ Ошибка получения списка")

    # ---------- callbacks ----------

    def _callback_ban_user(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            user_id   = int(call.data.split("_")[2])
            self.db.ban_user(user_id, "Забанен через кнопку")
            info  = self.db.get_user_info(user_id) or {}
            fname = info.get("first_name", "Пользователь")
            uname = f"@{info['username']}" if info.get("username") else ""
            self.bot.answer_callback_query(call.id, f"✅ {fname} забанен")
            self.bot.edit_message_text(
                f"✅ {fname} {uname} (ID: {user_id}) забанен\n\nИспользуйте /recent для обновления.",
                call.message.chat.id, call.message.message_id
            )
        except Exception as e:
            logger.error(f"Error callback ban: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    def _callback_unban_user(self, call):
        try:
            if call.from_user.id not in ADMINS:
                self.bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            user_id = int(call.data.split("_")[2])
            self.db.unban_user(user_id)
            info  = self.db.get_user_info(user_id) or {}
            fname = info.get("first_name", "Пользователь")
            uname = f"@{info['username']}" if info.get("username") else ""
            self.bot.answer_callback_query(call.id, f"✅ {fname} разбанен")
            self.bot.edit_message_text(
                f"✅ {fname} {uname} (ID: {user_id}) разбанен\n\nИспользуйте /recent для обновления.",
                call.message.chat.id, call.message.message_id
            )
        except Exception as e:
            logger.error(f"Error callback unban: {e}", exc_info=True)
            self.bot.answer_callback_query(call.id, "❌ Ошибка")

    # ---------- helpers ----------

    def _resolve_user(self, message, identifier: str):
        if identifier.startswith("@"):
            uid = self.db.get_user_id_by_username(identifier[1:])
            if uid is None:
                self.bot.reply_to(message, f"❌ Пользователь {identifier} не найден в базе")
            return uid
        try:
            return int(identifier)
        except ValueError:
            self.bot.reply_to(message, "❌ Неверный формат. Используйте ID или @username")
            return None

    def is_banned(self, user_id: int) -> bool:
        return self.db.is_banned(user_id)
