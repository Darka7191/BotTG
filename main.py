import os
import json
import asyncio
import tempfile
import logging
import sys
import locale
from telethon import functions
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from cryptography.fernet import Fernet
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramBadRequest
from telethon.errors import SessionPasswordNeededError
from aiogram.types import Message
from typing import Union
from telethon.tl.types import User, Chat, Channel, ChatForbidden, DialogFilterDefault, MessageEntityCustomEmoji, \
    MessageEntityBlockquote
from telethon.tl.types import (
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
    MessageEntityStrike, MessageEntityCode, MessageEntityPre,
    MessageEntityTextUrl, MessageEntityCustomEmoji
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Конфигурация
BOT_TOKEN = "7756390652:AAHdh2BzueaaNW_YzZKFTjFtok2SRnXRWVI" #ТОКЕН НЕ ЗАБУДЬ ИЗМЕНИТЬ ДОЛБЕНЬ)))
ADMIN_IDS = [8041841804] #И СВОЙ АЙДИ ВПИШИ ДОЛБЕНЬ)))
# Конфигурация Telethon
API_ID = 20650580  # Ваш API ID из my.telegram.org
API_HASH = 'd567be9ad0d5c77f012568a55db87cec'  # Ваш API HASH
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')

# Пути к файлам
USERS_DB = "users.json"
SUBS_DB = "subscriptions.json"
SESSIONS_DB = "sessions.json"
SPAM_SETTINGS_DB = "spam_settings.json"
KEY_FILE = "secret.key"
WELCOME_IMG = "welcome_photo.jpg"
PAYMENT_IMG = "payments.jpg"
SPAMMER_IMG = "spammer.jpg"
GLEINT_IMG = "welcome_photo.jpg"
photo = FSInputFile("images/welcome_photo.jpg")
photo2 = FSInputFile("images/payments.jpg")
photo3 = FSInputFile("images/spammer.jpg")
photo4 = FSInputFile("images/welcome_photo.jpg")
SUBSCRIPTION_LOGS = "subscription_logs.json"
favorites_db = "favorites.json"
user_spam_states = {}
spam_tasks = {}
auth_clients = {}
active_spam_tasks = {}

if not os.path.exists(SUBSCRIPTION_LOGS):
    with open(SUBSCRIPTION_LOGS, 'w', encoding='utf-8') as f:
        json.dump([], f)

if not os.path.exists(KEY_FILE):
    with open(KEY_FILE, 'wb') as f:
        f.write(Fernet.generate_key())

with open(KEY_FILE, 'rb') as f:
    cipher = Fernet(f.read())


async def on_startup():
    if not os.path.exists(SPAM_SETTINGS_DB):
        save_db(SPAM_SETTINGS_DB, {})

    if not os.path.exists(WELCOME_IMG):
        logger.warning(f"Файл {WELCOME_IMG} не найден!")

# Инициализация
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubManageStates1(StatesGroup):
    WAITING_USER_ID = State()

class AdminStates(StatesGroup):
    WAITING_USER_ID = State()
    WAITING_DAYS = State()
    WAITING_PLUS_USER_ID = State()
    WAITING_PLUS_DAYS = State()
    WAITING_REMOVE_USER_ID = State()
    WAITING_REMOVE_PLUS_USER_ID = State()
    WAITING_REJECT_REASON = State()

class AuthStates(StatesGroup):
    WAITING_PHONE = State()
    WAITING_CODE = State()
    WAITING_PASSWORD = State()

class BuySub(StatesGroup):
    waiting_for_duration = State()
    waiting_for_receipt = State()

class SubManageStates(StatesGroup):
    WAITING_USER_ID = State()
    WAITING_DAYS = State()
    WAITING_CONTEXT = State()
    WAITING_PLUS_DATA = State()
    WAITING_REVOKE_USER_ID = State()
    WAITING_REMOVE_USER_ID = State()

class SpamStates(StatesGroup):
    WAITING_USERNAME = State()
    WAITING_SELECTED_CHAT = State()
    WAITING_FOLDER = State()
    WAITING_DELAY = State()
    WAITING_MESSAGE = State()
    WAITING_MEDIA = State()

class BroadcastStates(StatesGroup):
    WAITING_TEXT = State()
    WAITING_MEDIA = State()
    WAITING_FILTER = State()
    WAITING_CONFIRM = State()

def encrypt_sessions(data):
    return cipher.encrypt(json.dumps(data).encode()).decode()

def save_encrypted_sessions(data):
    with open(SESSIONS_DB, 'w', encoding='utf-8') as f:
        f.write(encrypt_sessions(data))

def load_db(file_path):
    if not os.path.exists(file_path):
        return {}

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def message_entity_to_dict(entity):
    entity_dict = {
        'type': entity.type,
        'offset': entity.offset,
        'length': entity.length,
    }

    if hasattr(entity, 'url'):
        entity_dict['url'] = entity.url
    if hasattr(entity, 'language'):
        entity_dict['language'] = entity.language
    if hasattr(entity, 'custom_emoji_id'):
        entity_dict['custom_emoji_id'] = entity.custom_emoji_id

    return entity_dict

def save_db(file_path: str, data: dict):
    try:
        dirname = os.path.dirname(file_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения файла {file_path}: {e}")
        raise

def load_spam_settings(user_id: str):
    settings = load_db(SPAM_SETTINGS_DB)
    if user_id in settings:
        user_spam_states[user_id] = settings[user_id]
        if user_spam_states[user_id].get('send_to_all'):
            user_spam_states[user_id]['send_mode'] = 'Во все чаты'
        elif user_spam_states[user_id].get('folder'):
            user_spam_states[user_id]['send_mode'] = f'Папка: {user_spam_states[user_id]["folder"]}'
        elif user_spam_states[user_id].get('username'):
            user_spam_states[user_id]['send_mode'] = f'Чат: @{user_spam_states[user_id]["username"]}'
        else:
            user_spam_states[user_id]['send_mode'] = 'Не выбран'


class UserManager:
    def __init__(self):
        self.users = load_db(USERS_DB)
        self.subs = load_db(SUBS_DB)

    def is_premium(self, user_id: str) -> bool:
        user_id = str(user_id)
        return self.users.get(user_id, {}).get("premium", False)

    def set_premium(self, user_id: str, status: bool):
        user_id = str(user_id)
        if user_id in self.users:
            self.users[user_id]["premium"] = status
            save_db(USERS_DB, self.users)
            return True
        return False

    def get_stats(self):
        total_users = len(self.users)
        active_subs = sum(1 for u in self.users.values() if u.get("subscription"))
        return {
            "total_users": total_users,
            "active_subs": active_subs,
            "inactive_subs": total_users - active_subs
        }

    def add_user(self, user: types.User):
        user_id = str(user.id)
        if user_id not in self.users:
            self.users[user_id] = {
                "username": user.username,
                "full_name": user.full_name,
                "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "subscription": False,
                "sub_end": None
            }
            save_db(USERS_DB, self.users)
            return True
        return False

    def give_sub(self, user_id: str, days: int, is_premium: bool = False) -> Union[str, bool]:
        """Выдает подписку и возвращает дату окончания (или False при ошибке)"""
        user_id = str(user_id)
        if user_id in self.users:
            end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            self.users[user_id].update({
                "subscription": True,
                "sub_end": end_date,
                "premium": is_premium
            })
            save_db(USERS_DB, self.users)
            return end_date
        return False

user_manager = UserManager()
sessions = load_db(SESSIONS_DB)

assert 'ADMIN_IDS' in globals(), "ADMIN_IDS не определены"
assert 'user_manager' in globals(), "user_manager не определен"
assert 'logger' in globals(), "logger не определен"

def main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="spam_menu"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Купить подписку", callback_data="buy_standard"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="profile")
    )
    builder.row(
        InlineKeyboardButton(text="🛟 Поддержка", url="https://t.me/gleintvein")
    )
    return builder.as_markup()


def log_subscription(user_id: int, action: str, days: int = None, reason: str = None):
    """Логирование действий с подпиской"""
    log_entry = {
        "user_id": user_id,
        "action": action,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days": days,
        "reason": reason
    }

    logs = load_db(SUBSCRIPTION_LOGS)
    logs.append(log_entry)
    save_db(SUBSCRIPTION_LOGS, logs)

class AdminPanel(StatesGroup):
    waiting_for_broadcast_text = State()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа.")
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Выдать Подписку", callback_data="give_sub"),
        InlineKeyboardButton(text="🔧 Забрать подписку", callback_data="remove_sub"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")
    )

    if os.path.exists(WELCOME_IMG):
        await message.answer_photo(
            photo=FSInputFile(WELCOME_IMG),
            caption="👋 Добро пожаловать в админ-панель. Выберите действие:",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(
            "👋 Добро пожаловать в админ-панель. Выберите действие:",
            reply_markup=builder.as_markup()
        )


@dp.callback_query(F.data == "broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для администраторов!", show_alert=True)
        return
    await callback.message.answer("✏️ Введите текст рассылки или 'отмена':")
    await state.set_state(BroadcastStates.WAITING_TEXT)
    await callback.answer()

@dp.message(BroadcastStates.WAITING_TEXT)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена':
        await state.clear()
        return await message.answer("❌ Рассылка отменена", reply_markup=main_kb())

    await state.update_data(text=message.html_text)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить медиа", callback_data="add_media")],
        [InlineKeyboardButton(text="➡️ Продолжить без медиа", callback_data="skip_media")]
    ])
    await message.answer("📎 Хотите добавить медиа-вложение?", reply_markup=markup)
    await state.set_state(BroadcastStates.WAITING_MEDIA)

@dp.callback_query(F.data == "skip_media", BroadcastStates.WAITING_MEDIA)
async def skip_media(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(media_type=None, media_file_id=None)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Все пользователи", callback_data="filter:all")],
        [InlineKeyboardButton(text="✅ Активные подписки", callback_data="filter:active")],
        [InlineKeyboardButton(text="🚫 Неактивные", callback_data="filter:inactive")]
    ])
    await callback.message.answer("👥 Выберите аудиторию:", reply_markup=markup)
    await state.set_state(BroadcastStates.WAITING_FILTER)
    await callback.answer()

@dp.callback_query(F.data == "add_media", BroadcastStates.WAITING_MEDIA)
async def ask_for_media(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📤 Отправьте фото/видео/GIF для рассылки:")
    await state.set_state(BroadcastStates.WAITING_MEDIA)
    await callback.answer()


@dp.message(BroadcastStates.WAITING_MEDIA)
async def process_media(message: types.Message, state: FSMContext):
    if message.content_type not in {'photo', 'video', 'animation'}:
        await message.answer("❌ Поддерживаются только фото/видео/GIF!")
        return

    media_type = message.content_type
    file_id = message.photo[-1].file_id if media_type == 'photo' else \
        message.video.file_id if media_type == 'video' else \
            message.animation.file_id

    await state.update_data(
        media_type=media_type,
        media_file_id=file_id,
        has_media=True
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Все пользователи", callback_data="filter:all")],
        [InlineKeyboardButton(text="✅ Активные подписки", callback_data="filter:active")],
        [InlineKeyboardButton(text="🚫 Неактивные", callback_data="filter:inactive")]
    ])
    await message.answer("👥 Выберите целевую аудиторию:", reply_markup=markup)
    await state.set_state(BroadcastStates.WAITING_FILTER)


@dp.callback_query(F.data.startswith("filter:"), BroadcastStates.WAITING_FILTER)
async def select_filter(callback: types.CallbackQuery, state: FSMContext):
    filter_type = callback.data.split(":")[1]
    await state.update_data(filter=filter_type)

    data = await state.get_data()
    text = data.get('text', '')
    media = data.get('media_file_id')

    preview = f"📬 Предпросмотр рассылки:\n\n{text}"
    if media:
        preview += f"\n\n📎 Прикреплено медиа ({data['media_type']})"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать рассылку", callback_data="confirm_broadcast")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_broadcast")]
    ])

    if media:
        await callback.message.answer_photo(
            photo=data['media_file_id'],
            caption=preview,
            reply_markup=markup
        )
    else:
        await callback.message.answer(preview, reply_markup=markup)


@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.clear()

    if os.path.exists(WELCOME_IMG):
        await callback.message.answer_photo(
            photo=FSInputFile(WELCOME_IMG),
            caption="Главное меню:",
            reply_markup=main_kb()
        )
    else:
        await callback.message.answer(
            "Главное меню:",
            reply_markup=main_kb()
        )
    await callback.answer("❌ Рассылка отменена")

@dp.callback_query(F.data == "confirm_broadcast")
async def send_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    users = user_manager.users

    if data['filter'] == 'active':
        users = {uid: u for uid, u in users.items() if u.get('subscription')}
    elif data['filter'] == 'inactive':
        users = {uid: u for uid, u in users.items() if not u.get('subscription')}

    success = 0
    errors = 0
    start_time = datetime.now()

    progress_message = await callback.message.answer(
        f"⏳ Начало рассылки...\n"
        f"Всего получателей: {len(users)}\n"
        f"Успешно: 0\n"
        f"Ошибок: 0"
    )

    for user_id in users:
        try:
            if data.get('media_file_id'):
                if data['media_type'] == 'photo':
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=data['media_file_id'],
                        caption=data['text'],
                        parse_mode='HTML'
                    )
                else:
                    await bot.send_video(
                        chat_id=user_id,
                        video=data['media_file_id'],
                        caption=data['text'],
                        parse_mode='HTML'
                    )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=data['text'],
                    parse_mode='HTML'
                )
            success += 1
        except Exception as e:
            errors += 1

        if (datetime.now() - start_time).seconds % 5 == 0:
            await progress_message.edit_text(
                f"⏳ Рассылка в процессе...\n"
                f"Всего получателей: {len(users)}\n"
                f"Успешно: {success}\n"
                f"Ошибок: {errors}\n"
                f"Прогресс: {round((success + errors)/len(users)*100, 1)}%"
            )

    await progress_message.delete()
    total_time = (datetime.now() - start_time).seconds
    await callback.message.answer(
        f"✅ Рассылка завершена!\n"
        f"• Успешно: {success}\n"
        f"• Ошибок: {errors}\n"
        f"• Время: {total_time} сек\n"
        f"• Скорость: {round(success/total_time, 1) if total_time > 0 else 0} сообщ/сек"
    )
    await state.clear()

@dp.callback_query(F.data == "cancel_broadcast", BroadcastStates.WAITING_CONFIRM)
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await state.clear()
    await callback.answer("❌ Рассылка отменена")

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    try:
        stats = user_manager.get_stats()
        text = (
            "📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
            f"✅ Активных подписок: <b>{stats['active_subs']}</b>\n"
            f"❌ Неактивных подписок: <b>{stats['inactive_subs']}</b>"
        )

        try:
            await callback.message.edit_text(
                text=text
            )
        except Exception as e:
            await callback.message.answer(
                text=text
            )

        await callback.answer()

    except Exception as e:
        logger.error(f"Error in show_stats: {e}")
        await callback.answer("⚠️ Произошла ошибка при получении статистики", show_alert=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    is_new = user_manager.add_user(message.from_user)

    if os.path.exists(WELCOME_IMG):
        photo = FSInputFile(WELCOME_IMG)
        await message.answer_photo(
            photo=photo,
            caption=f"<b>👋 Добро пожаловать, {message.from_user.full_name}!</b>\n\n"
                    "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
                    "🛠 <i>Используйте кнопки ниже для навигации:</i>",
            reply_markup=main_kb()
        )
    else:
        await message.answer(
            f"<b>👋 Добро пожаловать, {message.from_user.full_name}!</b>\n\n"
            "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
            "🛠 <i>Используйте кнопки ниже для навигации:</i>",
            reply_markup=main_kb()
        )

    if is_new and message.from_user.id not in ADMIN_IDS:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"🆕 Новый пользователь:\n"
                         f"ID: <code>{message.from_user.id}</code>\n"
                         f"Имя: {message.from_user.full_name}\n"
                         f"Юзернейм: @{message.from_user.username}"
                )
            except TelegramBadRequest as e:
                print(f"Failed to send message to admin {admin_id}: {e}")
                continue

@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: types.CallbackQuery):
    try:
        if os.path.exists(WELCOME_IMG):
            photo = FSInputFile(WELCOME_IMG)
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=photo,
                caption=f"<b>👋 Добро пожаловать, {callback.from_user.full_name}!</b>\n\n"
                        "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
                        "🛠 <i>Используйте кнопки ниже для навигации:</i>",
                reply_markup=main_kb()
            )
        else:
            await callback.message.edit_text(
                f"<b>👋 Добро пожаловать, {callback.from_user.full_name}!</b>\n\n"
                "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
                "🛠 <i>Используйте кнопки ниже для навигации:</i>",
                reply_markup=main_kb()
            )
    except TelegramBadRequest:
        if os.path.exists(WELCOME_IMG):
            photo = FSInputFile(WELCOME_IMG)
            await callback.message.answer_photo(
                photo=photo,
                caption=f"<b>👋 Добро пожаловать, {callback.from_user.full_name}!</b>\n\n"
                        "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
                        "🛠 <i>Используйте кнопки ниже для навигации:</i>",
                reply_markup=main_kb()
            )
        else:
            await callback.message.answer(
                f"<b>👋 Добро пожаловать, {callback.from_user.full_name}!</b>\n\n"
                "Я - бот для автоматической рассылки сообщений в Telegram.\n\n"
                "🛠 <i>Используйте кнопки ниже для навигации:</i>",
                reply_markup=main_kb()
            )
    await callback.answer()

@dp.callback_query(F.data == "spam_menu")
async def spam_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    user_data = user_manager.users.get(user_id, {})

    if not user_data.get("subscription"):
        await callback.answer("❌ Требуется активная подписка!", show_alert=True)
        return

    if not sessions.get(user_id):
        await state.set_state(AuthStates.WAITING_PHONE)
        await callback.message.answer(
            "<b>🔒 Авторизация</b>\n\n"
            "Для доступа к рассылке необходимо авторизоваться через Telegram API.\n"
            "Пожалуйста, отправьте свой <b>номер телефона</b> в формате +380123456789:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        await callback.message.delete()
    else:
        await show_spam_menu(callback.message)


@dp.message(AuthStates.WAITING_PHONE, F.contact | F.text)
async def handle_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text

    try:
        client = TelegramClient(
            StringSession(),
            API_ID,
            API_HASH,
            device_model="Iphone",
            system_version="1.0",
            app_version="1.0"
        )
        await client.connect()
        sent_code = await client.send_code_request(phone)

        auth_clients[message.from_user.id] = client

        await state.update_data({
            'phone': phone,
            'phone_code_hash': sent_code.phone_code_hash
        })
        await state.set_state(AuthStates.WAITING_CODE)

        await message.answer(
            "📲 Введите код подтверждения из Telegram (формат: 1 2 3 4 5):",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", parse_mode="HTML")
        await state.clear()


@dp.message(AuthStates.WAITING_CODE)
async def handle_code(message: types.Message, state: FSMContext):
    code = message.text.replace(" ", "")
    user_id = message.from_user.id

    client = auth_clients.get(user_id)
    if not client:
        await message.answer("❌ Сессия истекла. Попробуйте заново.")
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)

        string_session = client.session.save()

        session_path = os.path.join("sessions", f"{user_id}.session")
        os.makedirs("sessions", exist_ok=True)
        with open(session_path, "w") as f:
            f.write(string_session)

        sessions[str(user_id)] = string_session
        save_db(SESSIONS_DB, sessions)

        await message.answer("✅ Авторизация прошла успешно!")
        await state.clear()
        await show_spam_menu(message)

    except SessionPasswordNeededError:
        await state.update_data({'client': client})
        await message.answer("🔐 Ваш аккаунт защищен двухэтапной аутентификацией. Пожалуйста, введите пароль:")
        await state.set_state(AuthStates.WAITING_PASSWORD)

    except Exception as e:
        await message.answer(f"❌ Ошибка при авторизации: {e}")
        await state.clear()


@dp.message(AuthStates.WAITING_PASSWORD, F.text)
async def handle_2fa_password(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    client = user_data['client']
    password = message.text

    try:
        await client.sign_in(password=password)

        session_data = client.session.save()
        sessions[str(message.from_user.id)] = session_data
        save_db(SESSIONS_DB, sessions)

        await message.answer(
            "✅ Авторизация успешно завершена!\n\n",
            reply_markup=ReplyKeyboardRemove()
        )

        await show_spam_menu(message)

        await state.clear()

    except Exception as e:
        error_message = f"❌ Ошибка при вводе пароля: {str(e)}"

        explanation = (
            "\n\nℹ️ Возможные причины:\n"
            "1. Неправильный пароль\n"
            "2. Слишком много попыток\n"
            "3. Проблемы с подключением"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="retry_password")]
        ])

        await message.answer(
            "🔐 Двухэтапная аутентификация - это дополнительная защита вашего аккаунта, "
            "которая требует ввода пароля после кода подтверждения.\n\n"
            f"{error_message}{explanation}",
            reply_markup=keyboard
        )

@dp.callback_query(F.data == "retry_password")
async def retry_password_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Пожалуйста, введите ваш пароль еще раз:")
    await state.set_state(AuthStates.WAITING_PASSWORD)
    await callback.answer()


async def show_spam_menu(message_or_callback: Union[types.Message, types.CallbackQuery]):
    user_id = str(message_or_callback.from_user.id)
    state = user_spam_states.get(user_id, {})
    user_data = user_manager.users.get(user_id, {})

    delay = state.get("delay", 3)
    message_text = state.get("message", "❌ Нету текста")
    media = state.get("media")
    username = state.get("username")
    folder = state.get("folder")
    send_to_all = state.get("send_to_all", False)

    if send_to_all:
        target = "🌍 Все чаты"
    elif folder:
        target = f"📂 Папка: {folder}"
    elif username:
        target = f"👤 @{username}"
    else:
        target = "❌ Не выбрано"

    media_status = "🖼️ Есть" if media else "❌ Нету медии"

    text = (
        "📬 <b>Меню настройки рассылки</b>\n\n"
        f"🎯 <b>Цель:</b> {target}\n"
        f"💬 <b>Текст:</b> {message_text[:50] + '…' if len(message_text) > 50 else message_text}\n"
        f"🖼 <b>Медиа:</b> {media_status}\n"
        f"⏱ <b>Интервал:</b> {delay} сек\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Во все чаты", callback_data="send_to_all"),
            InlineKeyboardButton(text="📂 Папка", callback_data="folder_mode"),
            InlineKeyboardButton(text="👤 Username", callback_data="send_to_selected")
        ],
        [
            InlineKeyboardButton(text="✏️ Ввести текст", callback_data="write_personal"),
            InlineKeyboardButton(text="🖼 Добавить медиа", callback_data="set_photo"),
            InlineKeyboardButton(text="⚙️ Изменить интервал", callback_data="set_delay")
        ],
        [
            InlineKeyboardButton(text="🚀 Начать рассылку", callback_data="start_spam"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])

    try:
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.delete()
            except:
                pass
            return await message_or_callback.message.answer_photo(
                photo=photo3,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            return await message_or_callback.answer_photo(
                photo=photo3,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except Exception as e:
        logging.exception(f"Ошибка при отправке меню пользователю {user_id}: {e}")
        return None

@dp.callback_query(F.data == "set_photo")
async def set_media_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    current_text = user_spam_states.get(user_id, {}).get("message", "")

    await state.update_data(message_text=current_text)

    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        "📤 Пришлите фото или видео для сообщения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Удалить медиа", callback_data="remove_media")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_photo_input")]
        ])
    )
    await state.set_state(SpamStates.WAITING_MEDIA)
    await callback.answer()

@dp.callback_query(F.data == "remove_photo")
async def remove_photo_handler(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id in user_spam_states and "photo" in user_spam_states[user_id]:
        del user_spam_states[user_id]["photo"]
    await callback.message.edit_text("✅ Фото удалено из сообщения.")
    await show_spam_menu(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "cancel_photo_input")
async def cancel_photo_input(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Добавление фото отменено.")
    await show_spam_menu(callback.message)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "send_to_selected")
async def ask_chat_username(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите юзернейм чата (без @):")
    await state.set_state(SpamStates.WAITING_SELECTED_CHAT)
    await callback.answer()


@dp.callback_query(F.data == "send_to_all")
async def set_send_to_all(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id]["send_to_all"] = True
    user_spam_states[user_id]["folder"] = None
    user_spam_states[user_id]["username"] = None

    await callback.answer("✅ Цель установлена: все чаты!")
    await show_spam_menu(callback)

@dp.callback_query(F.data == "folder_mode")
async def folder_mode(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id]["send_to_all"] = False
    user_spam_states[user_id]["username"] = None

    await state.set_state(SpamStates.WAITING_FOLDER)
    await callback.message.answer("📂 Введите название папки:")

@dp.callback_query(F.data == "send_to_folder")
async def ask_folder_name(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    user_spam_states.setdefault(user_id, {})["send_to_all"] = False
    await callback.message.answer("📂 Введите название папки:")
    await state.set_state(SpamStates.WAITING_FOLDER)
    await callback.answer()

@dp.callback_query(F.data == "cancel_username_input")
async def cancel_username_input(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Ввод username отменен")
    await show_spam_menu(callback.message)
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "set_delay")
async def set_delay_handler(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        pass

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_delay_input")]
        ]
    )

    await callback.message.answer(
        "Введите задержку в секундах:",
        reply_markup=keyboard
    )
    await state.set_state(SpamStates.WAITING_DELAY)
    await callback.answer()

@dp.callback_query(F.data == "cancel_delay_input")
async def cancel_delay_input(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Ввод интервала отменен")
    await show_spam_menu(callback.message)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "continue_spam")
async def continue_spam(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id in active_spam_tasks and not active_spam_tasks[user_id]['task'].done():
        await callback.answer("ℹ️ Рассылка уже активна!")
    else:
        await start_spam(callback)


@dp.message(F.text, SpamStates.WAITING_DELAY)
async def process_delay(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    text = message.text.strip()

    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Введите корректное положительное число секунд.")
        return

    delay = int(text)

    user_spam_states.setdefault(user_id, {})["delay"] = delay

    if user_id in active_spam_tasks:
        active_spam_tasks[user_id]['delay'] = delay

    settings = load_db(SPAM_SETTINGS_DB)
    if user_id not in settings or not isinstance(settings[user_id], dict):
        settings[user_id] = {}

    settings[user_id]["last_delay"] = delay
    save_db(SPAM_SETTINGS_DB, settings)

    await message.answer(f"✅ Задержка установлена: {delay} секунд.")

    if user_id in user_spam_states and "stats_message_id" in user_spam_states[user_id]:
        stats = {
            "sent": active_spam_tasks[user_id].get("sent", 0),
            "failed": active_spam_tasks[user_id].get("failed", 0),
            "start_time": active_spam_tasks[user_id].get("start_time", datetime.now()),
            "last_update": datetime.now()
        }
        await update_stats(message.from_user.id, stats)
    else:
        await show_spam_menu(message)

    await state.clear()

@dp.callback_query(F.data == "write_personal")
async def ask_personal_text(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите текст сообщения:")
    await state.set_state(SpamStates.WAITING_MESSAGE)
    await callback.answer()


@dp.callback_query(F.data == "revoke_subscription")
async def revoke_subscription_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только администратор может отзывать подписки!", show_alert=True)
        return

    await callback.message.answer("Введите ID пользователя, у которого нужно отозвать подписку:")
    await state.set_state(SubManageStates.WAITING_REVOKE_USER_ID)
    await callback.answer()


@dp.message(SubManageStates.WAITING_REVOKE_USER_ID)
async def process_revoke_subscription(message: types.Message, state: FSMContext):
    try:
        user_id = str(message.text)

        if user_id in user_manager.users:
            user_manager.users[user_id]["subscription"] = False
            user_manager.users[user_id]["premium"] = False
            user_manager.users[user_id]["sub_end"] = None
            save_db(USERS_DB, user_manager.users)

            await message.answer(f"✅ Подписка пользователя {user_id} успешно отозвана")

            try:
                await bot.send_message(
                    chat_id=int(user_id),
                    text="❌ Ваша подписка была отозвана администратором"
                )
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()


@dp.message(Command("revoke_sub"))
async def revoke_sub_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только для админа!")

    parts = message.text.split()
    if len(parts) != 2:
        return await message.answer("Используйте: /revoke_sub user_id")

    user_id = parts[1]

    if user_id in user_manager.users:
        user_manager.users[user_id]["subscription"] = False
        user_manager.users[user_id]["premium"] = False
        user_manager.users[user_id]["sub_end"] = None
        save_db(USERS_DB, user_manager.users)

        await message.answer(f"✅ Подписка пользователя {user_id} отозвана")

        try:
            await bot.send_message(int(user_id), "❌ Ваша подписка была отозвана администратором")
        except:
            pass
    else:
        await message.answer("❌ Пользователь не найден")


@dp.message(SpamStates.WAITING_MESSAGE, F.text)
async def process_message_input(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id]["message"] = message.text
    user_spam_states[user_id]["entities"] = [message_entity_to_dict(e) for e in message.entities] if message.entities else []

    custom_emojis = []
    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                custom_emojis.append(message_entity_to_dict(entity))

    user_spam_states[user_id]["custom_emojis"] = custom_emojis
    await message.answer("✅ Текст сообщения сохранен с форматированием!")
    await show_spam_menu(message)
    await state.clear()

@dp.callback_query(F.data == "cancel_message_input")
async def cancel_message_input(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Ввод текста отменен")
    await show_spam_menu(callback.message)
    await state.clear()
    await callback.answer()


@dp.message(SpamStates.WAITING_MEDIA, F.content_type.in_({'photo', 'video'}))
async def process_media_input(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data = await state.get_data()

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id]["message"] = data.get("message_text", "")

    if message.photo:
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_file_id = message.video.file_id
    else:
        await message.answer("⚠️ Только фото или видео!")
        return

    user_spam_states[user_id]["media"] = media_file_id

    await message.answer("✅ Медиа добавлено к сообщению!")
    await show_spam_menu(message)
    await state.clear()


@dp.callback_query(F.data == "remove_media")
async def remove_media_handler(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_id in user_spam_states:
        user_spam_states[user_id].pop("photo", None)
        user_spam_states[user_id].pop("video", None)
    await callback.message.edit_text("✅ Медиа удалено из сообщения.")
    await show_spam_menu(callback.message)
    await callback.answer()


@dp.message(SpamStates.WAITING_FOLDER, F.text)
async def process_folder_name(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    folder_name = message.text.strip()

    if not folder_name:
        await message.answer("❌ Название папки не может быть пустым!")
        return

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id]["folder"] = folder_name
    user_spam_states[user_id]["send_to_all"] = False
    user_spam_states[user_id]["username"] = None

    await state.clear()
    await message.answer(f"✅ Папка выбрана: {folder_name}")
    await show_spam_menu(message)

@dp.message(SpamStates.WAITING_SELECTED_CHAT, F.text)
async def process_selected_chat(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    username = message.text.strip().lstrip('@')

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    user_spam_states[user_id].update({
        "username": username,
        "send_mode": f"Чат: @{username}",
        "send_to_all": False,
        "folder": None
    })

    settings = load_db(SPAM_SETTINGS_DB)
    settings[user_id] = user_spam_states[user_id]
    save_db(SPAM_SETTINGS_DB, settings)

    await message.answer(f"✅ Установлен чат: @{username}")
    await show_spam_menu(message)
    await state.clear()


async def download_and_send_media(client, username, file_id, caption=None):
    try:
        file = await bot.get_file(file_id)
        file_path = file.file_path
        mime_type = getattr(file, 'mime_type', 'application/octet-stream')

        if 'image' in mime_type:
            file_type = 'photo'
        elif 'video' in mime_type:
            file_type = 'video'
        else:
            file_type = 'document'

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            await bot.download_file(file_path, tmp_file.name)

            if file_type == 'photo':
                await client.send_file(username, tmp_file.name, caption=caption, parse_mode='html')
            elif file_type == 'video':
                await client.send_file(username, tmp_file.name, caption=caption,
                                       supports_streaming=True, parse_mode='html')
            else:
                await client.send_file(username, tmp_file.name, caption=caption,
                                       force_document=True, parse_mode='html')

        os.remove(tmp_file.name)
        return True
    except Exception as e:
        print(f"Ошибка отправки медиа: {e}")
        return False

def dict_to_message_entity(entity_dict):
    entity_type = entity_dict['type']
    offset = entity_dict['offset']
    length = entity_dict['length']

    if entity_type == "bold":
        return MessageEntityBold(offset, length)
    elif entity_type == "italic":
        return MessageEntityItalic(offset, length)
    elif entity_type == "underline":
        return MessageEntityUnderline(offset, length)
    elif entity_type == "strikethrough":
        return MessageEntityStrike(offset, length)
    elif entity_type == "code":
        return MessageEntityCode(offset, length)
    elif entity_type == "pre":
        return MessageEntityPre(offset, length, language=entity_dict.get('language', ''))
    elif entity_type == "text_link":
        return MessageEntityTextUrl(offset, length, url=entity_dict['url'])
    elif entity_type == "custom_emoji":
        return MessageEntityCustomEmoji(offset, length, document_id=int(entity_dict['custom_emoji_id']))
    elif entity_type == "blockquote":
        return MessageEntityBlockquote(offset, length)
    else:
        return None

def normalize(text):
    if not isinstance(text, str):
        text = str(text)
    return ''.join(text.casefold().split())

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass

    user_id = str(callback.from_user.id)

    if user_id not in user_spam_states:
        user_spam_states[user_id] = {}

    state = user_spam_states.get(user_id, {})
    media = state.get("media")
    username = state.get("username")
    message = state.get("message")
    send_to_all = state.get("send_to_all", False)
    folder_name = state.get("folder")

    if not username and not send_to_all and not folder_name:
        await callback.answer("⚠️ Сначала выберите цель (username / папка / все чаты)!", show_alert=True)
        await show_spam_menu(callback.message)
        return

    if not message or not message.strip():
        await callback.answer("⚠️ Сначала введите текст сообщения!", show_alert=True)
        await callback.message.answer("✏️ Пожалуйста, введите текст.")
        await show_spam_menu(callback.message)
        return

    if user_id in active_spam_tasks:
        task_info = active_spam_tasks[user_id]
        if not task_info['task'].done():
            await callback.answer("⚠️ Рассылка уже запущена!", show_alert=True)
            return
        else:
            del active_spam_tasks[user_id]

    session_string = sessions.get(user_id)
    if not session_string:
        await callback.answer("❌ Сначала авторизуйтесь!", show_alert=True)
        return

    async def send_to_target(client, target, stats, user_id):
        state = user_spam_states.get(user_id, {})
        message_text = state.get("message", "")
        media = state.get("media")
        entities_dicts = state.get("entities", [])
        custom_emojis_dicts = state.get("custom_emojis", [])

        try:
            telethon_entities = []
            for entity_dict in entities_dicts + custom_emojis_dicts:
                entity = dict_to_message_entity(entity_dict)
                if entity:
                    telethon_entities.append(entity)

            if media:
                file = await bot.get_file(media)
                file_path = file.file_path
                ext = file_path.split('.')[-1].lower() if '.' in file_path else ''

                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp_file:
                    await bot.download_file(file_path, tmp_file.name)
                    tmp_path = tmp_file.name

                send_kwargs = {
                    'entity': target,
                    'file': tmp_path,
                    'caption': message_text,
                    'formatting_entities': telethon_entities if telethon_entities else None
                }

                if ext in ['jpg', 'jpeg', 'png', 'webp']:
                    send_kwargs['force_document'] = False
                elif ext in ['mp4', 'mov', 'avi']:
                    send_kwargs['supports_streaming'] = True
                    send_kwargs['force_document'] = False
                else:
                    send_kwargs['force_document'] = True

                await client.send_file(**send_kwargs)
                os.unlink(tmp_path)
            else:
                await client.send_message(
                    entity=target,
                    message=message_text,
                    formatting_entities=telethon_entities if telethon_entities else None
                )

            stats["sent"] += 1
            active_spam_tasks[user_id]['sent'] = stats["sent"]

        except Exception as e:
            stats["failed"] += 1
            print(f"Ошибка отправки в {target}: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def spam_loop(callback: types.CallbackQuery):
        user_id = str(callback.from_user.id)
        client = None
        try:
            client = TelegramClient(
                StringSession(sessions.get(user_id)),
                API_ID,
                API_HASH
            )
            await client.connect()

            state = user_spam_states.get(user_id, {})
            delay = state.get("delay", 3)
            send_to_all = state.get("send_to_all", False)
            folder_name = state.get("folder")
            username = state.get("username")

            stats = {
                "sent": 0,
                "failed": 0,
                "start_time": datetime.now(),
                "last_update": datetime.now(),
                "delay": delay
            }

            targets = []

            if send_to_all:
                async for dialog in client.iter_dialogs():
                    entity = dialog.entity
                    try:
                        if isinstance(entity, (User, Chat, ChatForbidden)):
                            continue

                        if isinstance(entity, (User, Chat)) or (isinstance(entity, Channel) and not entity.broadcast):
                            if hasattr(entity, "default_banned_rights") and getattr(entity.default_banned_rights,
                                                                                    "send_messages", False):
                                continue
                            targets.append(entity)
                    except Exception as e:
                        stats["failed"] += 1
                        print(f"Ошибка получения чата: {e}")

            elif folder_name:
                try:
                    filters = await client(functions.messages.GetDialogFiltersRequest())
                    target_folder = None
                    for f in filters.filters:
                        if isinstance(f, DialogFilterDefault):
                            continue
                        if normalize(folder_name) in normalize(f.title):
                            target_folder = f
                            break

                    if target_folder and hasattr(target_folder, 'include_peers'):
                        for peer in target_folder.include_peers:
                            try:
                                entity = await client.get_entity(peer)
                                if isinstance(entity, types.User) or getattr(entity, "broadcast", False) is False:
                                    if hasattr(entity, "default_banned_rights") and getattr(
                                            entity.default_banned_rights, "send_messages", False):
                                        continue
                                    targets.append(entity)
                            except Exception as e:
                                stats["failed"] += 1
                                print(f"Ошибка получения {peer}: {e}")
                    else:
                        await callback.message.answer(f"❌ Папка '{folder_name}' не найдена или пуста!")
                        return
                except Exception as e:
                    await callback.message.answer(f"❌ Ошибка получения папок: {e}")
                    return

            elif username:
                try:
                    entity = await client.get_entity(username)
                    targets.append(entity)
                except Exception as e:
                    await callback.message.answer(f"❌ Не удалось найти @{username}: {e}")
                    return

            if not targets:
                await callback.message.answer("❌ Не найдено ни одной цели для рассылки!")
                return

            while True:
                if user_id not in active_spam_tasks:
                    break

                current_delay = active_spam_tasks[user_id].get('delay', delay)

                await asyncio.gather(*[send_to_target(client, t, stats, user_id) for t in targets])

                if (datetime.now() - stats["last_update"]).total_seconds() >= 5:
                    try:
                        await update_stats(callback.from_user.id, stats)
                    except Exception as e:
                        print(f"Ошибка обновления статистики: {e}")
                    stats["last_update"] = datetime.now()

                for _ in range(current_delay * 10):
                    if user_id not in active_spam_tasks:
                        return
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Критическая ошибка в spam_loop: {e}")
            await callback.message.answer(f"❌ Критическая ошибка: {str(e)}")
        finally:
            if client:
                await client.disconnect()
            if user_id in active_spam_tasks:
                del active_spam_tasks[user_id]

    task = asyncio.create_task(spam_loop(callback))
    active_spam_tasks[user_id] = {
        'task': task,
        'delay': state.get("delay", 3),
        'sent': 0,
        'failed': 0,
        'start_time': datetime.now()
    }

    stats_message = await callback.message.answer(
        "📊 Статистика рассылки:\n"
        f"• Отправлено: 0\n"
        f"• Ошибок: 0\n"
        f"• Время работы: 0 сек\n"
        f"• Интервал: {state.get('delay', 3)} сек",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⏹ Остановить полностью", callback_data="stop_spam_completely"),
            InlineKeyboardButton(text="⚙️ Изменить интервал", callback_data="change_delay")
        ]])
    )

    user_spam_states[user_id]["stats_message_id"] = stats_message.message_id
    await callback.answer("✅ Рассылка началась!")

async def update_stats(user_id: int, stats: dict):
    user_id = str(user_id)
    if user_id not in user_spam_states:
        return

    state = user_spam_states[user_id]
    if "stats_message_id" not in state:
        return

    duration = (datetime.now() - stats["start_time"]).total_seconds()
    current_delay = active_spam_tasks[user_id].get('delay', 3) if user_id in active_spam_tasks else 3

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=state["stats_message_id"],
            text="📊 Статистика рассылки:\n"
                 f"• Отправлено: {stats['sent']}\n"
                 f"• Ошибок: {stats['failed']}\n"
                 f"• Время работы: {int(duration)} сек\n"
                 f"• Интервал: {current_delay} сек",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⏹ Остановить полностью", callback_data="stop_spam_completely"),
                InlineKeyboardButton(text="⚙️ Изменить интервал", callback_data="change_delay")
            ]]))
    except Exception as e:
        print(f"Ошибка обновления статистики: {e}")


@dp.callback_query(F.data == "stop_spam_completely")
async def stop_spam_completely(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)

    task_info = active_spam_tasks.get(user_id)
    if task_info:
        task = task_info.get('task')
        if task and not task.done():
            task.cancel()
            try:
                await task
            except:
                pass

    user_spam_states.pop(user_id, None)
    active_spam_tasks.pop(user_id, None)

    await callback.answer("✅ Рассылка полностью остановлена и сброшена!")
    await show_spam_menu(callback.message)

@dp.callback_query(F.data == "change_delay")
async def change_delay_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новый интервал в секундах:")
    await state.set_state(SpamStates.WAITING_DELAY)
    await callback.answer()


@dp.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    user_data = user_manager.users.get(user_id, {})

    sub_status = "✅ Активна" if user_data.get("subscription") else "❌ Не активна"
    sub_end = user_data.get("sub_end")
    remaining = ""

    if sub_end:
        end_date = datetime.strptime(sub_end, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        if end_date > now:
            delta = end_date - now
            days = delta.days
            hours = delta.seconds // 3600
            remaining = f"\n🔹 Осталось: {days} дн. {hours} ч."
        else:
            sub_status = "🔹 Истекла подписка / Или нету у вас подписки"

    text = (
        f"<b>👤 Профиль пользователя</b>\n\n"
        f"🔹 <b>Имя:</b> {callback.from_user.full_name}\n"
        f"🔹 <b>Юзернейм:</b> @{callback.from_user.username}\n"
        f"🔹 <b>ID:</b> <code>{callback.from_user.id}</code>\n"
        f"🔹 <b>Подписка:</b> {sub_status}{remaining}\n"
        f"🔹 <b>До:</b> {sub_end or 'не указано'}\n"
    )

    await callback.message.edit_caption(
        caption=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
        ])
    )

@dp.callback_query(F.data == "buy_standard")
async def show_subscription_plans(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuySub.waiting_for_duration)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3 дня - 60₴ / 1.5$", callback_data="sub_duration:3"),
            InlineKeyboardButton(text="7 дней - 102₴ / 5$", callback_data="sub_duration:7")
        ],
        [
            InlineKeyboardButton(text="30 дней - 420₴ / 10$", callback_data="sub_duration:30"),
            InlineKeyboardButton(text="Навсегда - 1000₴ / 22$", callback_data="sub_duration:999")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_caption(
        caption="<b>💰 Выберите срок подписки:</b>",
        reply_markup=markup
    )

@dp.callback_query(F.data.startswith("sub_duration:"), StateFilter("*"))
async def select_payment_method(callback: types.CallbackQuery, state: FSMContext):
    days = int(callback.data.split(":")[1])
    await state.update_data(days=days)
    await state.set_state(BuySub.waiting_for_duration)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Банковская карта", callback_data="payment_method:card"),
            InlineKeyboardButton(text="₿ Криптовалюта", callback_data="payment_method:crypto")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_standard")]
    ])
    duration_text = f"{days} дней" if days > 0 else "Навсегда"
    await callback.message.edit_caption(
        caption=f"<b>💳 Выберите способ оплаты для подписки ({duration_text}):</b>",
        reply_markup=markup
    )


@dp.callback_query(F.data.startswith("payment_method:"), BuySub.waiting_for_duration)
async def handle_payment_selection(callback: types.CallbackQuery, state: FSMContext):
    payment_method = callback.data.split(":")[1]
    await state.update_data(payment_method=payment_method)
    data = await state.get_data()

    payment_info = ""
    if payment_method == "card":
        payment_info = (
            "💳 <b>Реквизиты карты:</b>\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "Номер карты: <code>4441 1144 0855 4812</code>\n"
            "Получатель: Никита Н.\n"
            "Сумма: "
        )
    else:
        payment_info = (
            "₿ <b>Крипто-реквизиты:</b>\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "@send: https://t.me/send?start=IVTZvwkcmLWd\n"
            "USDT (TRC20): <code>UQDgfvqrpkcUaMXi8kIq1k4QXeNPrevQdlIrCgAjBxqQDM34</code>\n"
            "TON: <code>UQDgfvqrpkcUaMXi8kIq1k4QXeNPrevQdlIrCgAjBxqQDM34</code>\n"
            "Сумма: "
        )

    days = data['days']
    amount = {
        3: 60,
        7: 102,
        30: 420,
        999: 1000
    }.get(days, 0)

    payment_info += f"{amount}₴\n\nОтправьте скриншот чека или хеш транзакции:"

    await callback.message.edit_caption(
        caption=payment_info,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"sub_duration:{days}")]
        ])
    )
    await state.set_state(BuySub.waiting_for_receipt)


@dp.message(F.photo, BuySub.waiting_for_receipt)
async def handle_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    days = data.get('days', 0)
    payment_method = data.get('payment_method', 'card')

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"confirm_sub:{user_id}:{days}:std"
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_sub:{user_id}"
            )
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=(
                    f"🧾 Новый платёж!\n"
                    f"👤 Пользователь: @{message.from_user.username}\n"
                    f"🆔 ID: {user_id}\n"
                    f"📅 Срок: {days if days > 0 else 'Навсегда'} дней\n"
                    f"💳 Метод: {'Карта' if payment_method == 'card' else 'Крипта'}\n\n"
                    f"Подтвердить или отклонить:"
                ),
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

    await message.answer(
        "✅ Чек отправлен на проверку. Ожидайте подтверждения.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()


@dp.callback_query(F.data.startswith("confirm_sub:"))
async def confirm_subscription(callback: types.CallbackQuery):
    try:
        _, user_id_str, days_str, sub_type = callback.data.split(':')
        user_id = int(user_id_str)
        days = int(days_str)

        user_manager.give_sub(user_id_str, days, sub_type == 'plus')

        await bot.send_message(
            user_id,
            f"✅ Ваша подписка успешно активирована на {days} дней!",
        )

        await callback.message.delete()
        await callback.answer("Подписка активирована", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка подтверждения: {e}")
        await callback.answer("❌ Ошибка активации", show_alert=True)

@dp.callback_query(F.data.startswith("reject_sub:"))
async def reject_subscription(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(':')
    user_id = parts[1]
    await state.update_data(reject_user_id=user_id)
    await callback.message.answer("✏️ Введите причину отклонения для пользователя:")
    await state.set_state(AdminStates.WAITING_REJECT_REASON)
    await callback.answer()


@dp.message(AdminStates.WAITING_REJECT_REASON)
async def process_reject_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['reject_user_id']

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"❌ Ваша заявка на подписку отклонена. Причина:\n{message.text}"
        )
        await message.answer(f"✅ Пользователю {user_id} отправлено уведомление")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {str(e)}")

    await state.clear()

@dp.callback_query(F.data == "give_sub")
async def ask_user_id_for_sub(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя:")
    await state.set_state(SubManageStates.WAITING_USER_ID)
    await callback.answer()

@dp.message(SubManageStates.WAITING_USER_ID)
async def ask_days_for_sub(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer("Введите количество дней:")
        await state.set_state(SubManageStates.WAITING_DAYS)
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число.")


@dp.message(SubManageStates.WAITING_DAYS)
async def give_sub_to_user(message: types.Message, state: FSMContext):
    try:
        days = int(message.text)
        data = await state.get_data()
        user_id = data['user_id']

        end_date = user_manager.give_sub(user_id, days)
        if end_date:
            await message.answer(f"✅ Подписка выдана пользователю {user_id} до {end_date}")
            await bot.send_message(user_id, f"🎉 Вам выдана подписка до {end_date}!")
        else:
            await message.answer("❌ Пользователь не найден")
    except ValueError:
        await message.answer("❌ Введите число дней")
    finally:
        await state.clear()


@dp.callback_query(F.data == "ungive_sub")
async def ask_user_id_for_unsub(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя, у которого нужно забрать подписку:")
    await state.set_state(SubManageStates1.WAITING_USER_ID)
    await callback.answer()


@dp.message(SubManageStates1.WAITING_USER_ID)
async def ungive_sub_to_user(message: types.Message, state: FSMContext):
    try:
        user_id = str(message.text)
        users = load_db(USERS_DB)

        if user_id in users:
            users[user_id]["subscription"] = False
            users[user_id]["sub_end"] = None
            save_db(USERS_DB, users)
            user_manager.users = users

            await message.answer(f"✅ Подписка у пользователя {user_id} отменена")
            try:
                await bot.send_message(int(user_id), "❌ Ваша подписка была отменена администратором")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()


@dp.message(Command("give_sub"))
async def give_sub_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только для админа!")

    try:
        parts = message.text.split()
        if len(parts) != 3:
            return await message.answer(
                "⚠️ Используйте: <code>/give_sub user_id дней</code>\n"
                "Пример: <code>/give_sub 1234567 30</code>",
                parse_mode=ParseMode.HTML
            )

        user_id = parts[1]
        days = int(parts[2])

        end_date = user_manager.give_sub(user_id, days)
        if not end_date:
            return await message.answer("❌ Пользователь не найден")

        await message.answer(
            f"✅ Подписка выдана пользователю <code>{user_id}</code>\n"
            f"Срок: {days} дней (до {end_date})",
            parse_mode=ParseMode.HTML
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 Вам выдана подписка на {days} дней (до {end_date})!"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

    except ValueError:
        await message.answer(
            "❌ Неверный формат. Используйте:\n"
            "<code>/give_sub user_id дней</code>\n"
            "Пример: <code>/give_sub 1234567 30</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка в give_sub: {e}")
        await message.answer("❌ Произошла ошибка при выдаче подписки")

@dp.message(Command("give_plus"))
async def give_plus_command(message: types.Message):
    """Выдача подписки Плюс администратором"""
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только для админа!")

    try:
        parts = message.text.split()
        if len(parts) != 3:
            return await message.answer(
                "⚠️ Используйте: <code>/give_plus user_id дней</code>\n"
                "Пример: <code>/give_plus 1234567 30</code>",
                parse_mode=ParseMode.HTML
            )

        user_id = parts[1]
        days = int(parts[2])

        success = user_manager.give_sub(user_id, days, is_premium=True)
        if not success:
            return await message.answer("❌ Пользователь не найден")

        await message.answer(
            f"✅ Премиум подписка выдана пользователю <code>{user_id}</code>\n"
            f"Срок: {days} дней",
            parse_mode=ParseMode.HTML
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 Вам выдана ПРЕМИУМ подписка на {days} дней! Теперь доступны все функции."
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

    except ValueError:
        await message.answer(
            "❌ Неверный формат. Используйте:\n"
            "<code>/give_plus user_id дней</code>\n"
            "Пример: <code>/give_plus 1234567 30</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Ошибка в give_plus: {e}")
        await message.answer("❌ Произошла ошибка при выдаче подписки")

@dp.callback_query(F.data == "give_plus")
async def ask_plus_user_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя для выдачи Плюс:")
    await state.set_state(AdminStates.WAITING_PLUS_USER_ID)
    await callback.answer()

@dp.message(AdminStates.WAITING_PLUS_USER_ID)
async def ask_plus_days(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer("Введите количество дней для подписки Плюс:")
        await state.set_state(AdminStates.WAITING_PLUS_DAYS)
    except ValueError:
        await message.answer("❌ Неверный ID. Введите число.")

@dp.message(AdminStates.WAITING_PLUS_DAYS)
async def give_plus_sub(message: types.Message, state: FSMContext):
    try:
        days = int(message.text)
        data = await state.get_data()
        user_id = data['user_id']

        if user_manager.give_sub(str(user_id), days, is_premium=True):
            await message.answer(f"✅ Подписка Плюс выдана пользователю {user_id} на {days} дней")
            try:
                await bot.send_message(user_id, f"🎉 Вам выдана ПРЕМИУМ подписка на {days} дней!")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден")
    except ValueError:
        await message.answer("❌ Введите число дней")
    finally:
        await state.clear()

@dp.callback_query(F.data == "remove_plus")
async def ask_remove_plus_user_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя для отмены Плюс:")
    await state.set_state(AdminStates.WAITING_REMOVE_PLUS_USER_ID)
    await callback.answer()

@dp.message(AdminStates.WAITING_REMOVE_PLUS_USER_ID)
async def remove_plus_sub(message: types.Message, state: FSMContext):
    try:
        user_id = str(message.text)
        users = load_db(USERS_DB)

        if user_id in users:
            users[user_id]["premium"] = False
            save_db(USERS_DB, users)
            user_manager.users = users

            await message.answer(f"✅ Подписка Плюс у пользователя {user_id} отменена")
            try:
                await bot.send_message(int(user_id), "❌ Ваша подписка Плюс была отменена администратором")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()

@dp.callback_query(F.data == "remove_sub")
async def ask_remove_sub_user_id(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID пользователя для отмены подписки:")
    await state.set_state(SubManageStates.WAITING_REMOVE_USER_ID)
    await callback.answer()

@dp.message(SubManageStates.WAITING_REMOVE_USER_ID)
async def remove_sub_from_user(message: types.Message, state: FSMContext):
    try:
        user_id = str(message.text)
        users = load_db(USERS_DB)

        if user_id in users:
            users[user_id]["subscription"] = False
            users[user_id]["sub_end"] = None
            save_db(USERS_DB, users)
            user_manager.users = users

            await message.answer(f"✅ Подписка у пользователя {user_id} отменена")
            try:
                await bot.send_message(int(user_id), "❌ Ваша подписка была отменена администратором")
            except:
                pass
        else:
            await message.answer("❌ Пользователь не найден")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        await state.clear()

@dp.message(Command("give_plus_sub"))
async def give_plus_sub_command(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только для админа!")

    await message.answer("Введите ID пользователя для выдачи Плюс:")
    await state.set_state(AdminStates.WAITING_PLUS_USER_ID)


@dp.message(Command("remove_plus_sub"))
async def remove_plus_sub_command(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Только для админа!")

    await message.answer("Введите ID пользователя для отмены Плюс:")
    await state.set_state(AdminStates.WAITING_REMOVE_PLUS_USER_ID)

async def main():
    global sessions
    sessions = load_db(SESSIONS_DB)

    await dp.start_polling(bot)

if __name__ == "__main__":
    dp.startup.register(on_startup)
    if not os.path.exists(USERS_DB):
        save_db(USERS_DB, {})
    if not os.path.exists(SUBS_DB):
        save_db(SUBS_DB, {})
    if not os.path.exists(SESSIONS_DB):
        save_db(SESSIONS_DB, {})

    asyncio.run(main())
