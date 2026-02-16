import logging
import sqlite3
import asyncio
import urllib.parse
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8269048955:AAEcETD-iCNu5x5qHOj2VCw2gXlu4kTFHs8"  # ВСТАВЬТЕ СВОЙ ТОКЕН
MAIN_ADMIN_ID = 6225083329  # ВСТАВЬТЕ СВОЙ ID
DB_PATH = Path(__file__).parent / "bot_database.db"

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.add_main_admin()
    
    def create_tables(self):
        # Таблица администраторов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица каналов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                channel_url TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP
            )
        ''')
        
        # Таблица прокси
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy_string TEXT UNIQUE,
                server TEXT,
                port INTEGER,
                secret TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Таблица выданных прокси
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS given_proxies (
                user_id INTEGER,
                proxy_id INTEGER,
                given_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, proxy_id)
            )
        ''')
        
        self.conn.commit()
    
    def add_main_admin(self):
        self.cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (MAIN_ADMIN_ID,))
        self.conn.commit()
    
    # ----- АДМИНЫ -----
    def is_admin(self, user_id):
        self.cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone() is not None
    
    def add_admin(self, user_id, username=None):
        self.cursor.execute('INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)',
                          (user_id, username))
        self.conn.commit()
        return True
    
    def remove_admin(self, user_id):
        if user_id == MAIN_ADMIN_ID:
            return False
        self.cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        self.conn.commit()
        return True
    
    def get_admins(self):
        self.cursor.execute('SELECT user_id, username FROM admins ORDER BY added_at')
        return self.cursor.fetchall()
    
    # ----- КАНАЛЫ -----
    def add_channel(self, channel_id, channel_name):
        channel_id = channel_id.strip()
        channel_name = channel_name.strip()
        
        # Правильное формирование ссылки на канал
        if str(channel_id).startswith('-100'):
            # Для каналов с числовым ID
            channel_url = f"https://t.me/c/{str(channel_id)[4:]}"
        else:
            # Для публичных каналов - используем channel_name как username
            # Убираем @ если есть
            clean_name = channel_name.replace('@', '')
            channel_url = f"https://t.me/{clean_name}"
        
        self.cursor.execute('''
            INSERT OR IGNORE INTO channels (channel_id, channel_name, channel_url) 
            VALUES (?, ?, ?)
        ''', (channel_id, channel_name, channel_url))
        self.conn.commit()
        return True
    
    def remove_channel(self, channel_id):
        self.cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
        self.conn.commit()
        return True
    
    def get_channels(self):
        self.cursor.execute('SELECT channel_id, channel_name, channel_url FROM channels ORDER BY added_at')
        return self.cursor.fetchall()
    
    # ----- ПРОКСИ -----
    def add_proxy(self, server, port, secret):
        secret = secret.strip().strip('"').strip("'").strip('`')
        proxy_string = f"tg://proxy?server={server}&port={port}&secret={secret}"
        try:
            self.cursor.execute('''
                INSERT INTO proxies (proxy_string, server, port, secret) 
                VALUES (?, ?, ?, ?)
            ''', (proxy_string, server, port, secret))
            self.conn.commit()
            return True
        except:
            return False
    
    def remove_proxy(self, proxy_id):
        self.cursor.execute('DELETE FROM proxies WHERE id = ?', (proxy_id,))
        self.conn.commit()
        return True
    
    def get_proxies(self, limit=50):
        self.cursor.execute('''
            SELECT id, proxy_string, server, port, secret, added_at 
            FROM proxies WHERE is_active = 1 
            ORDER BY added_at DESC LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()
    
    def get_proxy_count(self):
        self.cursor.execute('SELECT COUNT(*) FROM proxies WHERE is_active = 1')
        return self.cursor.fetchone()[0]
    
    def get_random_proxy(self, user_id):
        self.cursor.execute('''
            SELECT proxy_id FROM given_proxies WHERE user_id = ?
        ''', (user_id,))
        used = [row[0] for row in self.cursor.fetchall()]
        
        if used:
            placeholders = ','.join(['?'] * len(used))
            self.cursor.execute(f'''
                SELECT id, proxy_string, server, port, secret FROM proxies 
                WHERE is_active = 1 AND id NOT IN ({placeholders})
                ORDER BY RANDOM() LIMIT 1
            ''', used)
        else:
            self.cursor.execute('''
                SELECT id, proxy_string, server, port, secret FROM proxies 
                WHERE is_active = 1 ORDER BY RANDOM() LIMIT 1
            ''')
        
        proxy = self.cursor.fetchone()
        if proxy:
            self.cursor.execute('INSERT INTO given_proxies (user_id, proxy_id) VALUES (?, ?)',
                              (user_id, proxy[0]))
            self.conn.commit()
            return {
                'id': proxy[0],
                'string': proxy[1],
                'server': proxy[2],
                'port': proxy[3],
                'secret': proxy[4]
            }
        return None
    
    # ----- ПОЛЬЗОВАТЕЛИ -----
    def add_user(self, user_id, username, first_name):
        self.cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_active) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, first_name))
        self.conn.commit()
    
    def get_stats(self):
        self.cursor.execute('SELECT COUNT(*) FROM users')
        users = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM proxies')
        proxies = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM given_proxies')
        given = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM channels')
        channels = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM admins')
        admins = self.cursor.fetchone()[0]
        return users, proxies, given, channels, admins

db = Database()

# ========== ПРОВЕРКА ПОДПИСКИ ==========
async def check_subscription(user_id, channel_id):
    """Проверка подписки пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        is_subscribed = member.status in [
            ChatMemberStatus.MEMBER, 
            ChatMemberStatus.ADMINISTRATOR, 
            ChatMemberStatus.CREATOR
        ]
        logging.info(f"Проверка подписки {user_id} на канал {channel_id}: {is_subscribed}")
        return is_subscribed
    except Exception as e:
        logging.error(f"Ошибка при проверке подписки: {e}")
        return False

# ========== ФУНКЦИЯ ВЫДАЧИ ПРОКСИ ==========
async def give_proxy(message: types.Message, user_id: int):
    """Выдача прокси пользователю"""
    proxy_data = db.get_random_proxy(user_id)
    if proxy_data:
        encoded_secret = urllib.parse.quote(proxy_data['secret'], safe='')
        tg_link = f"tg://proxy?server={proxy_data['server']}&port={proxy_data['port']}&secret={encoded_secret}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Добавить прокси в один клик", url=tg_link)]
        ])
        
        await message.answer(
            f"✅ **Ваш прокси для Telegram:**\n\n"
            f"```\n{proxy_data['string']}\n```\n\n"
            f"📌 **Нажмите кнопку ниже** - Telegram автоматически добавит прокси",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(
            "😔 **К сожалению, все прокси временно закончились.**\n\n"
            "Новые появятся в ближайшее время. Попробуйте позже!",
            parse_mode=ParseMode.MARKDOWN
        )

# ========== ФУНКЦИЯ ПОКАЗА КАНАЛОВ ==========
async def show_channels(message: types.Message, channels: list):
    """Показать кнопки с каналами для подписки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for channel in channels:
        channel_url = channel[2]  # channel[2] - channel_url
        keyboard.inline_keyboard.append([InlineKeyboardButton(
            text=f"📢 Подписаться на {channel[1]}",
            url=channel_url
        )])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(
        text="✅ Я подписался",
        callback_data="check_subscription"
    )])
    
    await message.answer(
        "🔒 **Для получения прокси подпишитесь на каналы:**\n\n"
        "После подписки нажмите кнопку 'Я подписался'",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ========== КОМАНДА START ==========
@dp.message(Command('start'))
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Сохраняем пользователя
    db.add_user(user_id, username, first_name)
    
    # Получаем список каналов
    channels = db.get_channels()
    
    if not channels:
        await message.answer(
            "👋 **Добро пожаловать!**\n\n"
            "Бот временно не работает. Попробуйте позже.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Проверяем подписку на все каналы
    all_subscribed = True
    for channel in channels:
        if not await check_subscription(user_id, channel[0]):  # channel[0] - channel_id
            all_subscribed = False
            break
    
    if all_subscribed:
        # Пользователь подписан на все каналы - выдаем прокси
        await give_proxy(message, user_id)
    else:
        # Пользователь не подписан - показываем кнопки с каналами
        await show_channels(message, channels)

# ========== ПРОВЕРКА ПОДПИСКИ ПО КНОПКЕ ==========
@dp.callback_query(lambda c: c.data == 'check_subscription')
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Получаем список каналов
    channels = db.get_channels()
    
    if not channels:
        await callback.message.answer("❌ **Каналы не найдены**", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    # Проверяем подписку на все каналы
    all_subscribed = True
    for channel in channels:
        if not await check_subscription(user_id, channel[0]):
            all_subscribed = False
            break
    
    if all_subscribed:
        # Удаляем старое сообщение с кнопками
        await callback.message.delete()
        # Выдаем прокси
        await give_proxy(callback.message, user_id)
    else:
        # Показываем сообщение, что не все каналы подписаны
        await callback.answer("❌ Вы не подписались на все каналы!", show_alert=True)
        # Показываем актуальный список каналов
        await show_channels(callback.message, channels)
    
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(Command('admin'))
async def admin(message: types.Message):
    if not db.is_admin(message.from_user.id):
        await message.answer("⛔ **У вас нет прав администратора.**", parse_mode=ParseMode.MARKDOWN)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [
            InlineKeyboardButton(text="👑 Админы", callback_data="list_admins"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="add_admin")
        ],
        [
            InlineKeyboardButton(text="📢 Каналы", callback_data="list_channels"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="add_channel")
        ],
        [
            InlineKeyboardButton(text="🔢 Прокси", callback_data="list_proxies"),
            InlineKeyboardButton(text="➕ Добавить", callback_data="add_proxy")
        ]
    ])
    
    await message.answer(
        "🔧 **Панель администратора**\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

# ========== ПОКАЗ СПИСКОВ ==========
@dp.callback_query(lambda c: c.data == "list_admins")
async def list_admins(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    admins = db.get_admins()
    if not admins:
        await callback.message.answer("👑 **Администраторы не найдены**", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    text = "👑 **Список администраторов:**\n\n"
    for a in admins:
        text += f"• `{a[0]}`"
        if a[0] == MAIN_ADMIN_ID:
            text += " 👑 (главный)"
        if a[1]:
            text += f" (@{a[1]})"
        text += "\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for a in admins:
        if a[0] != MAIN_ADMIN_ID:
            btn_text = f"❌ Удалить {a[0]}"
            if a[1]:
                btn_text += f" (@{a[1]})"
            keyboard.inline_keyboard.append([InlineKeyboardButton(
                text=btn_text,
                callback_data=f"deladmin_{a[0]}"
            )])
    
    if keyboard.inline_keyboard:
        await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "list_channels")
async def list_channels(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    channels = db.get_channels()
    if not channels:
        await callback.message.answer("📢 **Каналы не добавлены**", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    text = "📢 **Список каналов:**\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for i, ch in enumerate(channels, 1):
        text += f"{i}. **{ch[1]}**\n   ID: `{ch[0]}`\n   [Ссылка]({ch[2]})\n\n"
        keyboard.inline_keyboard.append([InlineKeyboardButton(
            text=f"❌ Удалить {ch[1]}",
            callback_data=f"delchannel_{ch[0]}"
        )])
    
    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "list_proxies")
async def list_proxies(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    proxies = db.get_proxies(20)
    if not proxies:
        await callback.message.answer("🔢 **Прокси не добавлены**", parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    text = "🔢 **Список прокси:**\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for i, p in enumerate(proxies, 1):
        short_proxy = p[1][:50] + "..." if len(p[1]) > 50 else p[1]
        text += f"{i}. `{short_proxy}`\n   Сервер: {p[2]}:{p[3]}\n\n"
        keyboard.inline_keyboard.append([InlineKeyboardButton(
            text=f"❌ Удалить прокси #{i}",
            callback_data=f"delproxy_{p[0]}"
        )])
    
    text += f"\n📊 **Всего прокси:** {len(proxies)}"
    await callback.message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

# ========== ДОБАВЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data == "add_admin")
async def add_admin_prompt(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    await callback.message.answer(
        "👑 **Добавление администратора**\n\n"
        "Отправьте ID пользователя (только цифры):\n"
        "`123456789`",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_channel")
async def add_channel_prompt(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    await callback.message.answer(
        "📢 **Добавление канала**\n\n"
        "Отправьте сообщение в формате:\n"
        "`ID_канала Название_канала`\n\n"
        "**Пример:**\n"
        "`-100123456789 МойКанал`\n\n"
        "ID можно получить у @getidsbot",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_proxy")
async def add_proxy_prompt(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    await callback.message.answer(
        "🔢 **Добавление прокси**\n\n"
        "Отправьте сообщение в формате:\n"
        "`сервер порт секрет`\n\n"
        "**Пример:**\n"
        "`www.humaontop.space 443 3XnnAQIAAQAH8AMDhuJMOt0`",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

# ========== СТАТИСТИКА ==========
@dp.callback_query(lambda c: c.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    users, proxies, given, channels, admins = db.get_stats()
    await callback.message.answer(
        f"📊 **Статистика бота**\n\n"
        f"👤 **Пользователей:** {users}\n"
        f"🔢 **Прокси в базе:** {proxies}\n"
        f"✅ **Выдано прокси:** {given}\n"
        f"📢 **Каналов:** {channels}\n"
        f"👑 **Администраторов:** {admins}",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

# ========== УДАЛЕНИЕ ==========
@dp.callback_query(lambda c: c.data.startswith('deladmin_'))
async def delete_admin(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    admin_id = int(callback.data.split('_')[1])
    
    if admin_id == MAIN_ADMIN_ID:
        await callback.message.answer("❌ **Нельзя удалить главного администратора**", parse_mode=ParseMode.MARKDOWN)
    else:
        if db.remove_admin(admin_id):
            await callback.message.answer(f"✅ **Администратор {admin_id} удален**", parse_mode=ParseMode.MARKDOWN)
        else:
            await callback.message.answer("❌ **Ошибка при удалении**", parse_mode=ParseMode.MARKDOWN)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('delchannel_'))
async def delete_channel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    channel_id = callback.data.split('_')[1]
    
    if db.remove_channel(channel_id):
        await callback.message.answer(f"✅ **Канал удален**", parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.message.answer("❌ **Ошибка при удалении**", parse_mode=ParseMode.MARKDOWN)
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('delproxy_'))
async def delete_proxy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not db.is_admin(user_id):
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    
    proxy_id = int(callback.data.split('_')[1])
    
    if db.remove_proxy(proxy_id):
        await callback.message.answer(f"✅ **Прокси #{proxy_id} удален**", parse_mode=ParseMode.MARKDOWN)
    else:
        await callback.message.answer("❌ **Ошибка при удалении**", parse_mode=ParseMode.MARKDOWN)
    
    await callback.answer()

# ========== ОБРАБОТКА ТЕКСТА ==========
@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if not db.is_admin(user_id):
        return
    
    # ПРОВЕРЯЕМ ID АДМИНА (только цифры)
    if text.isdigit():
        new_admin_id = int(text)
        if db.add_admin(new_admin_id, message.from_user.username):
            await message.answer(f"✅ **Администратор {new_admin_id} добавлен**", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.answer("❌ **Ошибка при добавлении**", parse_mode=ParseMode.MARKDOWN)
        return
    
    # ПРОВЕРЯЕМ ФОРМАТ КАНАЛА (ID и название)
    parts = text.split()
    if len(parts) == 2:
        channel_id = parts[0].strip()
        channel_name = parts[1].strip()
        
        try:
            # Проверяем доступ к каналу
            chat = await bot.get_chat(channel_id)
            if db.add_channel(channel_id, channel_name):
                await message.answer(
                    f"✅ **Канал добавлен!**\n\n"
                    f"**Название:** {chat.title}\n"
                    f"**ID:** `{channel_id}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.answer("❌ **Канал уже существует**", parse_mode=ParseMode.MARKDOWN)
            return
        except Exception as e:
            await message.answer(
                f"❌ **Ошибка:** {str(e)}\n\n"
                f"Убедитесь, что бот добавлен в канал как администратор",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    # ПРОВЕРЯЕМ ФОРМАТ ПРОКСИ (сервер порт секрет)
    if len(parts) == 3:
        server = parts[0].strip()
        port_str = parts[1].strip()
        secret = parts[2].strip().strip('"').strip("'").strip('`')
        
        try:
            port = int(port_str)
            if db.add_proxy(server, port, secret):
                proxy_string = f"tg://proxy?server={server}&port={port}&secret={secret}"
                
                encoded_secret = urllib.parse.quote(secret, safe='')
                tg_link = f"tg://proxy?server={server}&port={port}&secret={encoded_secret}"
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Проверить прокси", url=tg_link)]
                ])
                
                await message.answer(
                    f"✅ **Прокси добавлен!**\n\n"
                    f"`{proxy_string}`\n\n"
                    f"Нажмите кнопку для проверки:",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.answer("❌ **Прокси уже существует**", parse_mode=ParseMode.MARKDOWN)
            return
        except ValueError:
            await message.answer("❌ **Порт должен быть числом**", parse_mode=ParseMode.MARKDOWN)
            return
    
    await message.answer(
        "❌ **Неизвестный формат команды**\n\n"
        "Используйте кнопки в админ-панели",
        parse_mode=ParseMode.MARKDOWN
    )

# ========== ЗАПУСК ==========
async def main():
    logging.info("="*50)
    logging.info("БОТ ЗАПУЩЕН")
    logging.info(f"Главный администратор: {MAIN_ADMIN_ID}")
    logging.info("="*50)
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())