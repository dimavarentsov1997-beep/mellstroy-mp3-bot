import asyncio
import sqlite3
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.types import (
    InlineQueryResultCachedAudio, InlineQueryResultCachedVoice,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

# ===== НАСТРОЙКИ =====
TOKEN = "8838743887:AAGwl6r4X_ZlTgRcD4a0ezlky9Mawc_cGXE"
OWNER_ID = 5209929082
CHANNEL_USERNAME = "@MellstroySounds"
CHANNEL_URL = "https://t.me/MellstroySounds"
DB_PATH = "sounds.db"

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_id TEXT NOT NULL,
            file_type TEXT DEFAULT 'audio',
            added_by INTEGER,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for col in ['added_by', 'usage_count', 'created_at', 'file_type']:
        try:
            cursor.execute(f'ALTER TABLE sounds ADD COLUMN {col} INTEGER DEFAULT 0')
        except:
            pass
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            level INTEGER DEFAULT 1,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            subscribed BOOLEAN DEFAULT FALSE,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute("DELETE FROM sounds WHERE name IS NULL OR name = '' OR TRIM(name) = ''")
    
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, username, level) VALUES (?, ?, ?)',
                   (OWNER_ID, 'OWNER', 4))
    
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def add_sound(name, file_id, file_type, added_by):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sounds (name, file_id, file_type, added_by) VALUES (?, ?, ?, ?)',
                   (name, file_id, file_type, added_by))
    conn.commit()
    conn.close()

def search_sounds(query):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, file_id, file_type FROM sounds WHERE name IS NOT NULL AND name != '' AND LOWER(name) LIKE LOWER(?) ORDER BY usage_count DESC LIMIT 50",
        (f'%{query}%',)
    )
    results = cursor.fetchall()
    conn.close()
    return results

def get_all_sounds():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, file_id, file_type FROM sounds WHERE name IS NOT NULL AND name != '' ORDER BY usage_count DESC")
    results = cursor.fetchall()
    conn.close()
    return results

def delete_sound(sound_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM sounds WHERE id = ?', (sound_id,))
    conn.commit()
    conn.close()

def increment_usage(sound_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE sounds SET usage_count = usage_count + 1 WHERE id = ?', (sound_id,))
    conn.commit()
    conn.close()

def add_admin(user_id, username, level, added_by):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO admins (user_id, username, level, added_by) VALUES (?, ?, ?, ?)',
                   (user_id, username, level, added_by))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id = ? AND user_id != ?', (user_id, OWNER_ID))
    conn.commit()
    conn.close()

def get_admin_level(user_id):
    if user_id == OWNER_ID:
        return 4
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT level FROM admins WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, level FROM admins ORDER BY level DESC')
    results = cursor.fetchall()
    conn.close()
    return results

def add_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO users (user_id, username, first_name, last_activity, subscribed) VALUES (?, ?, ?, ?, ?)',
                   (user_id, username, first_name, datetime.now(), False))
    conn.commit()
    conn.close()

def get_users_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name FROM users')
    results = cursor.fetchall()
    conn.close()
    return results

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sounds')
    sounds_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users')
    users_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM admins')
    admins_count = cursor.fetchone()[0]
    conn.close()
    return sounds_count, users_count, admins_count

# ===== СОСТОЯНИЯ =====
class AddSound(StatesGroup):
    waiting_for_name = State()
    waiting_for_file = State()

class AddAdmin(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_level = State()

class Broadcast(StatesGroup):
    waiting_for_post = State()

# ===== РОУТЕР =====
router = Router()

# ===== КЛАВИАТУРЫ =====
def admin_keyboard(level):
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить звук", callback_data="add_sound")],
        [InlineKeyboardButton(text="📋 Все звуки", callback_data="list_sounds")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]
    ]
    if level >= 2:
        buttons.append([InlineKeyboardButton(text="🗑 Удалить звук", callback_data="delete_menu")])
    if level >= 3:
        buttons.append([InlineKeyboardButton(text="👥 Управление админами", callback_data="admin_menu")])
    if level >= 4:
        buttons.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="list_users")])
        buttons.append([InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def channel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ])

def admin_list_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")],
        [InlineKeyboardButton(text="🗑 Удалить админа", callback_data="remove_admin")],
        [InlineKeyboardButton(text="📋 Список админов", callback_data="list_admins")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")]
    ])

# ===== КОМАНДА /start =====
@router.message(Command('start'))
async def cmd_start(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    admin_level = get_admin_level(user_id)
    add_user(user_id, message.from_user.username, message.from_user.first_name)

    if admin_level > 0:
        level_names = {1: "Базовый", 2: "Продвинутый", 3: "Админ", 4: "Владелец"}
        await message.answer(
            f"👑 Админ-панель Mellstroy Sounds\n\n"
            f"Уровень: {level_names.get(admin_level, 'Админ')}\n"
            f"Управление звуками Mellstroy\n\n"
            f"Выбери действие:",
            reply_markup=admin_keyboard(admin_level)
        )
        return

    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_subscribed = member.status not in ['left', 'kicked']
    except:
        is_subscribed = False

    if not is_subscribed:
        await message.answer(
            f"🎵 Mellstroy Sounds Bot\n\n"
            f"Привет! Я бот для поиска звуков Mellstroy.\n\n"
            f"⚠️ Для использования подпишись на канал: {CHANNEL_USERNAME}\n\n"
            f"После подписки нажми кнопку проверки!",
            reply_markup=channel_keyboard()
        )
    else:
        await message.answer(
            "🎵 Mellstroy Sounds Bot\n\n"
            "✅ Спасибо за подписку!\n\n"
            "🎯 Как использовать:\n"
            "• Напиши @MellstroyMP3_bot в любом чате\n"
            "• Введи название звука\n"
            "• Выбери и отправь в чат!\n\n"
            "💡 Звуки отправляются как аудиофайлы."
        )

# ===== ПРОВЕРКА ПОДПИСКИ =====
@router.callback_query(lambda c: c.data == "check_sub")
async def check_subscription_btn(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    add_user(user_id, callback.from_user.username, callback.from_user.first_name)

    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_subscribed = member.status not in ['left', 'kicked']
    except Exception as e:
        await callback.answer(f"Ошибка проверки: {e}", show_alert=True)
        return

    if is_subscribed:
        await callback.message.edit_text(
            "🎵 Mellstroy Sounds Bot\n\n"
            "✅ Спасибо за подписку!\n\n"
            "🎯 Как использовать:\n"
            "• Напиши @MellstroyMP3_bot в любом чате\n"
            "• Введи название звука\n"
            "• Выбери и отправь в чат!\n\n"
            "💡 Звуки отправляются как аудиофайлы."
        )
    else:
        await callback.answer("❌ Ты ещё не подписался! Проверь @MellstroySounds", show_alert=True)

# ===== АДМИН-МЕНЮ =====
@router.callback_query(lambda c: c.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    level = get_admin_level(callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=admin_keyboard(level))
    await callback.answer()

@router.callback_query(lambda c: c.data == "add_sound")
async def btn_add_sound(callback: types.CallbackQuery, state: FSMContext):
    if get_admin_level(callback.from_user.id) < 1:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    await callback.message.answer("✏️ Напиши название звука:")
    await state.set_state(AddSound.waiting_for_name)
    await callback.answer()

@router.callback_query(lambda c: c.data == "list_sounds")
async def btn_list_sounds(callback: types.CallbackQuery):
    sounds = get_all_sounds()
    if not sounds:
        await callback.message.answer("❌ Нет звуков в базе")
    else:
        text = "📋 Все звуки:\n\n"
        for sound_id, name, _, _ in sounds[:50]:
            text += f"• {name} (ID: {sound_id})\n"
        if len(sounds) > 50:
            text += f"\n... и ещё {len(sounds) - 50} звуков"
        await callback.message.answer(text)
    await callback.answer()

@router.callback_query(lambda c: c.data == "stats")
async def btn_stats(callback: types.CallbackQuery):
    sounds_count, users_count, admins_count = get_stats()
    stats_text = f"""
📊 Статистика бота:

👥 Пользователей: {users_count}
🎵 Звуков: {sounds_count}
👑 Админов: {admins_count}
📅 Дата: {datetime.now().strftime('%d.%m.%Y')}
"""
    await callback.message.answer(stats_text)
    await callback.answer()

@router.callback_query(lambda c: c.data == "delete_menu")
async def btn_delete_menu(callback: types.CallbackQuery):
    if get_admin_level(callback.from_user.id) < 2:
        await callback.answer("❌ Нужен 2 уровень!", show_alert=True)
        return
    sounds = get_all_sounds()
    if not sounds:
        await callback.message.answer("❌ Нет звуков для удаления")
        await callback.answer()
        return
    text = "🗑 Выбери ID для удаления:\n\n"
    for sound_id, name, _, _ in sounds[:30]:
        text += f"• ID: {sound_id} | {name}\n"
    text += "\nИспользуй команду: /delete ID"
    await callback.message.answer(text)
    await callback.answer()

@router.message(Command('delete'))
async def cmd_delete(message: types.Message):
    if get_admin_level(message.from_user.id) < 2:
        await message.answer("❌ Нет прав!")
        return
    try:
        sound_id = int(message.text.split()[1])
        delete_sound(sound_id)
        await message.answer(f"✅ Звук с ID {sound_id} удалён!")
    except:
        await message.answer("❌ Используй: /delete ID")

# ===== УПРАВЛЕНИЕ АДМИНАМИ =====
@router.callback_query(lambda c: c.data == "admin_menu")
async def btn_admin_menu(callback: types.CallbackQuery):
    if get_admin_level(callback.from_user.id) < 3:
        await callback.answer("❌ Нужен 3 уровень!", show_alert=True)
        return
    await callback.message.answer("👥 Управление админами", reply_markup=admin_list_keyboard())
    await callback.answer()

@router.callback_query(lambda c: c.data == "add_admin")
async def btn_add_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("👤 Отправь ID пользователя (число):")
    await state.set_state(AddAdmin.waiting_for_user_id)
    await callback.answer()

@router.callback_query(lambda c: c.data == "remove_admin")
async def btn_remove_admin(callback: types.CallbackQuery):
    admins = get_all_admins()
    text = "🗑 Удалить админа:\n\n"
    for user_id, username, level in admins:
        if user_id != OWNER_ID:
            text += f"• {username or 'ID:'+str(user_id)} (Уровень {level})\n"
    text += "\nКоманда: /removeadmin ID"
    await callback.message.answer(text)
    await callback.answer()

@router.callback_query(lambda c: c.data == "list_admins")
async def btn_list_admins(callback: types.CallbackQuery):
    admins = get_all_admins()
    text = "👥 Список админов:\n\n"
    for user_id, username, level in admins:
        crown = "👑" if user_id == OWNER_ID else "⭐" if level >= 3 else "👤"
        text += f"{crown} {username or 'Без username'} - Уровень {level}\n"
    await callback.message.answer(text)
    await callback.answer()

@router.message(Command('removeadmin'))
async def cmd_remove_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Только владелец может удалять админов!")
        return
    try:
        user_id = int(message.text.split()[1])
        remove_admin(user_id)
        await message.answer(f"✅ Админ {user_id} удалён!")
    except:
        await message.answer("❌ /removeadmin ID")

# ===== РАССЫЛКА =====
@router.callback_query(lambda c: c.data == "broadcast")
async def btn_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if get_admin_level(callback.from_user.id) < 4:
        await callback.answer("❌ Только владелец!", show_alert=True)
        return
    await callback.message.answer(
        "📢 Рассылка сообщений\n\n"
        "Отправь сообщение (текст, фото, видео, голосовое)\n"
        "и я разошлю его всем пользователям бота!\n\n"
        "Для отмены: /cancel"
    )
    await state.set_state(Broadcast.waiting_for_post)
    await callback.answer()

@router.message(Command('cancel'))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Рассылка отменена")

@router.message(Broadcast.waiting_for_post)
async def broadcast_post(message: types.Message, state: FSMContext, bot: Bot):
    users = get_all_users()
    success = 0
    failed = 0
    await message.answer(f"📤 Начинаю рассылку на {len(users)} пользователей...")
    for user_id, username, first_name in users:
        try:
            if message.text:
                await bot.send_message(user_id, message.text)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption or "")
            elif message.voice:
                await bot.send_voice(user_id, message.voice.file_id)
            elif message.audio:
                await bot.send_audio(user_id, message.audio.file_id)
            elif message.document:
                await bot.send_document(user_id, message.document.file_id)
            else:
                await bot.forward_message(user_id, message.chat.id, message.message_id)
            success += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📊 Успешно: {success}\n"
        f"❌ Не доставлено: {failed}"
    )
    await state.clear()

# ===== ДОБАВЛЕНИЕ ЗВУКА =====
@router.message(AddSound.waiting_for_name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("📁 Отправь звук (MP3, аудиофайл или голосовое)")
    await state.set_state(AddSound.waiting_for_file)

@router.message(AddSound.waiting_for_file)
async def get_file(message: types.Message, state: FSMContext, bot: Bot):
    file_id = None
    file_type = 'audio'

    data = await state.get_data()
    name = data['name']

    if message.voice:
        # Переотправляем голосовое с названием, чтобы Telegram запомнил title
        sent = await bot.send_voice(
            chat_id=message.chat.id,
            voice=message.voice.file_id,
            caption=name
        )
        file_id = sent.voice.file_id
        file_type = 'voice'
        await sent.delete()
    elif message.audio:
        file_id = message.audio.file_id
        file_type = 'audio'
    elif message.document and message.document.mime_type and 'audio' in message.document.mime_type:
        file_id = message.document.file_id
        file_type = 'audio'
    else:
        await message.answer("❌ Отправь аудиофайл (MP3) или голосовое!")
        return

    if not file_id:
        await message.answer("❌ Не удалось получить файл.")
        return

    add_sound(name, file_id, file_type, message.from_user.id)
    await message.answer(f"✅ Звук «{name}» добавлен!\nПроверь: @MellstroyMP3_bot {name}")
    await state.clear()
    
# ===== ДОБАВЛЕНИЕ АДМИНА =====
@router.message(AddAdmin.waiting_for_user_id)
async def get_admin_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(user_id=user_id)
        await message.answer(
            "📊 Выбери уровень доступа:\n\n"
            "1 — Базовый (добавление звуков)\n"
            "2 — Продвинутый (удаление звуков)\n"
            "3 — Админ (управление админами)"
        )
        await state.set_state(AddAdmin.waiting_for_level)
    except:
        await message.answer("❌ Отправь ID числом!")

@router.message(AddAdmin.waiting_for_level)
async def get_admin_level_state(message: types.Message, state: FSMContext):
    try:
        level = int(message.text.strip())
        if level not in [1, 2, 3]:
            await message.answer("❌ Уровень должен быть 1, 2 или 3!")
            return
        if message.from_user.id != OWNER_ID and level >= get_admin_level(message.from_user.id):
            await message.answer("❌ Нельзя назначить уровень выше своего!")
            return
        data = await state.get_data()
        user_id = data['user_id']
        add_admin(user_id, None, level, message.from_user.id)
        await message.answer(f"✅ Админ {user_id} добавлен с уровнем {level}!")
        await state.clear()
    except:
        await message.answer("❌ Отправь число 1, 2 или 3!")

# ===== КНОПКА ПОЛЬЗОВАТЕЛИ =====
@router.callback_query(lambda c: c.data == "list_users")
async def btn_list_users(callback: types.CallbackQuery):
    if get_admin_level(callback.from_user.id) < 4:
        await callback.answer("❌ Только владелец!", show_alert=True)
        return
    
    users = get_all_users()
    text = f"👥 Все пользователи бота: {len(users)}\n\n"
    
    for i, (user_id, username, first_name) in enumerate(users[:50]):
        name = username or first_name or "Без имени"
        text += f"{i+1}. {name} (`{user_id}`)\n"
    
    if len(users) > 50:
        text += f"\n... и ещё {len(users) - 50} пользователей"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# ===== ИНЛАЙН-ПОИСК =====
@router.inline_query()
async def inline_search(inline_query: types.InlineQuery, bot: Bot):
    user_id = inline_query.from_user.id
    add_user(user_id, inline_query.from_user.username, inline_query.from_user.first_name)

    query = inline_query.query.strip()
    sounds = search_sounds(query) if query else get_all_sounds()

    results = []
    for sound_id, name, file_id, file_type in sounds:
        if not name or not name.strip():
            continue

        if file_id.startswith('CQ'):
            results.append(
                InlineQueryResultCachedVoice(
                    id=str(sound_id),
                    voice_file_id=file_id
                )
            )
        else:
            results.append(
                InlineQueryResultCachedAudio(
                    id=str(sound_id),
                    audio_file_id=file_id,
                    title=name.strip()
                )
            )

    await inline_query.answer(results, cache_time=1)
    
@router.chosen_inline_result()
async def on_sound_chosen(chosen_result: types.ChosenInlineResult):
    increment_usage(int(chosen_result.result_id))

# ===== ЗАПУСК =====
async def main():
    print("🚀 Запуск Mellstroy Sounds Bot...")
    init_db()

    sounds = get_all_sounds()
    users = get_users_count()
    print(f"📊 Звуков: {len(sounds)} | Пользователей: {users}")

    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
