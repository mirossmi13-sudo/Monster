import asyncio
import sqlite3
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = "8693765655:AAGzkR4Pl1Mw3TWaoUZlLIJsKqrxwI1SWFc"
ADMIN_IDS = [7455548790, 8411096573]

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

conn = sqlite3.connect("monster.db")
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    checks INTEGER DEFAULT 0,
    ref_by INTEGER DEFAULT 0,
    joined_date TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    reward INTEGER,
    channel TEXT,
    is_active INTEGER DEFAULT 1
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS completed (
    user_id INTEGER,
    task_id INTEGER,
    PRIMARY KEY (user_id, task_id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS check_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT UNIQUE,
    is_used INTEGER DEFAULT 0
)
''')
conn.commit()

class AddTask(StatesGroup):
    title = State()
    reward = State()
    channel = State()

class AddLinks(StatesGroup):
    links = State()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_checks(user_id):
    cursor.execute("SELECT checks FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_checks(user_id, amount):
    cursor.execute("UPDATE users SET checks = checks + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def add_check_links(links_list):
    added = 0
    for link in links_list:
        link = link.strip()
        if link:
            try:
                cursor.execute("INSERT INTO check_links (link) VALUES (?)", (link,))
                added += 1
            except:
                pass
    conn.commit()
    return added

def get_random_check_link():
    cursor.execute("SELECT id, link FROM check_links WHERE is_used = 0 ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return None, None

def mark_link_as_used(link_id):
    cursor.execute("UPDATE check_links SET is_used = 1 WHERE id = ?", (link_id,))
    conn.commit()

@dp.message(Command("start"))
async def start(msg: types.Message):
    user_id = msg.from_user.id
    username = msg.from_user.username or msg.from_user.first_name
    args = msg.text.split()
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined_date) VALUES (?, ?, ?)",
                  (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            cursor.execute("UPDATE users SET ref_by = ? WHERE user_id = ?", (ref_id, user_id))
            cursor.execute("UPDATE users SET checks = checks + 1 WHERE user_id = ?", (ref_id,))
            conn.commit()
    
    checks = get_user_checks(user_id)
    
    await msg.answer(
        f"🔥 MONSTER TASK BOT 🔥\n\n"
        f"💰 Твои чеки: {checks}\n\n"
        f"📌 Выполняй задания и получай ссылки-чеки\n"
        f"👥 Приглашай друзей - получай +1 чек\n\n"
        f"🤖 Бот: @monstertaskbot",
        reply_markup=main_menu(user_id)
    )

def main_menu(user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 ЗАДАНИЯ", callback_data="tasks")],
        [InlineKeyboardButton(text="💰 МОИ ЧЕКИ", callback_data="checks")],
        [InlineKeyboardButton(text="👥 РЕФЕРАЛЫ", callback_data="refs")]
    ])
    
    if is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="👑 АДМИН ПАНЕЛЬ", callback_data="admin_panel")])
    
    return keyboard

def admin_panel_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ ЗАДАНИЕ", callback_data="admin_add_task")],
        [InlineKeyboardButton(text="📋 УПРАВЛЕНИЕ ЗАДАНИЯМИ", callback_data="admin_tasks")],
        [InlineKeyboardButton(text="🎁 ДОБАВИТЬ ССЫЛКИ-ЧЕКИ", callback_data="admin_add_links")],
        [InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_stats")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    return keyboard

@dp.callback_query(F.data == "tasks")
async def show_tasks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    cursor.execute("SELECT id, title, reward, channel FROM tasks WHERE is_active = 1")
    tasks = cursor.fetchall()
    
    if not tasks:
        await callback.answer("❌ Нет заданий!", show_alert=True)
        return
    
    text = "📋 ДОСТУПНЫЕ ЗАДАНИЯ:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for task_id, title, reward, channel in tasks:
        cursor.execute("SELECT 1 FROM completed WHERE user_id = ? AND task_id = ?", (user_id, task_id))
        completed = cursor.fetchone()
        
        if completed:
            text += f"✅ {title} | +{reward} чеков [ВЫПОЛНЕНО]\n\n"
        else:
            text += f"📢 {title}\n💰 Награда: +{reward} чеков\n📢 Канал: @{channel}\n\n"
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"📢 ПОДПИСАТЬСЯ", url=f"https://t.me/{channel}")])
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"✅ ВЫПОЛНИЛ", callback_data=f"complete_{task_id}_{channel}")])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    task_id = int(parts[1])
    channel = parts[2]
    
    cursor.execute("SELECT reward FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        await callback.answer("❌ Задание не найдено!", show_alert=True)
        return
    
    reward = row[0]
    
    cursor.execute("SELECT 1 FROM completed WHERE user_id = ? AND task_id = ?", (user_id, task_id))
    if cursor.fetchone():
        await callback.answer("❌ Ты уже получал награду!", show_alert=True)
        return
    
    link_id, link = get_random_check_link()
    
    if not link:
        await callback.answer("❌ Закончились ссылки-чеки! Обратитесь к админу", show_alert=True)
        return
    
    cursor.execute("INSERT INTO completed (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
    mark_link_as_used(link_id)
    add_checks(user_id, reward)
    conn.commit()
    
    new_checks = get_user_checks(user_id)
    
    await callback.answer(f"✅ Задание выполнено!", show_alert=True)
    
    await callback.message.edit_text(
        f"🎉 ЗАДАНИЕ ВЫПОЛНЕНО! 🎉\n\n"
        f"📢 Канал: @{channel}\n"
        f"💰 Начислено: +{reward} чеков\n"
        f"💰 Твои чеки: {new_checks}\n\n"
        f"🔗 ТВОЯ ССЫЛКА-ЧЕК:\n{link}\n\n"
        f"⚠️ Ссылка действительна только 1 раз!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В ГЛАВНОЕ МЕНЮ", callback_data="back_to_menu")]
        ])
    )

@dp.callback_query(F.data == "checks")
async def show_checks(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    checks = get_user_checks(user_id)
    await callback.answer(f"💰 Твои чеки: {checks}", show_alert=True)

@dp.callback_query(F.data == "refs")
async def show_refs(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,))
    ref_count = cursor.fetchone()[0]
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    text = f"👥 РЕФЕРАЛЬНАЯ ПРОГРАММА\n\n"
    text += f"📊 Приглашено: {ref_count}\n"
    text += f"🎁 Наград получено: {ref_count} чеков\n\n"
    text += f"🔗 Твоя ссылка:\n{ref_link}\n\n"
    text += f"💰 За каждого друга +1 чек!"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text("👑 АДМИН ПАНЕЛЬ", reply_markup=admin_panel_menu())
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    checks = get_user_checks(user_id)
    await callback.message.edit_text(
        f"💰 Твои чеки: {checks}\n\nГлавное меню:",
        reply_markup=main_menu(user_id)
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_add_task")
async def admin_add_task(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("📝 Введите название задания:")
    await state.set_state(AddTask.title)
    await callback.answer()

@dp.message(AddTask.title)
async def get_title(msg: types.Message, state: FSMContext):
    await state.update_data(title=msg.text)
    await msg.answer("💰 Введите количество чеков:")
    await state.set_state(AddTask.reward)

@dp.message(AddTask.reward)
async def get_reward(msg: types.Message, state: FSMContext):
    try:
        reward = int(msg.text)
        await state.update_data(reward=reward)
        await msg.answer("📢 Введите юзернейм канала (без @):")
        await state.set_state(AddTask.channel)
    except:
        await msg.answer("❌ Введите число!")

@dp.message(AddTask.channel)
async def get_channel(msg: types.Message, state: FSMContext):
    channel = msg.text.strip().lstrip('@')
    data = await state.get_data()
    
    cursor.execute("INSERT INTO tasks (title, reward, channel) VALUES (?, ?, ?)",
                  (data['title'], data['reward'], channel))
    conn.commit()
    
    await msg.answer(f"✅ Задание добавлено!\n\n📝 {data['title']}\n💰 {data['reward']} чеков\n📢 @{channel}")
    await state.clear()

@dp.callback_query(F.data == "admin_tasks")
async def admin_tasks(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    cursor.execute("SELECT id, title, reward, channel, is_active FROM tasks")
    tasks = cursor.fetchall()
    
    if not tasks:
        await callback.message.edit_text("📋 Нет заданий", reply_markup=admin_panel_menu())
        return
    
    text = "📋 УПРАВЛЕНИЕ ЗАДАНИЯМИ:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for task_id, title, reward, channel, active in tasks:
        status = "✅" if active else "❌"
        text += f"{status} ID:{task_id} | {title} (+{reward}) | @{channel}\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🔄", callback_data=f"toggle_{task_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delete_{task_id}")
        ])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_panel")])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_task(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    task_id = int(callback.data.split("_")[1])
    cursor.execute("UPDATE tasks SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (task_id,))
    conn.commit()
    await callback.answer("✅ Статус изменён!")
    await admin_tasks(callback)

@dp.callback_query(F.data.startswith("delete_"))
async def delete_task(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    task_id = int(callback.data.split("_")[1])
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    await callback.answer("🗑 Задание удалено!")
    await admin_tasks(callback)

@dp.callback_query(F.data == "admin_add_links")
async def admin_add_links(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    text = "🎁 ДОБАВЛЕНИЕ ССЫЛОК-ЧЕКОВ\n\nОтправь список ссылок (каждая с новой строки):\n\nПример:\nhttps://t.me/xxx?start=123\nhttps://t.me/xxx?start=456"
    
    await callback.message.edit_text(text)
    await state.set_state(AddLinks.links)
    await callback.answer()

@dp.message(AddLinks.links)
async def process_links(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    
    links = msg.text.split('\n')
    added = add_check_links(links)
    
    cursor.execute("SELECT COUNT(*) FROM check_links WHERE is_used = 0")
    total_available = cursor.fetchone()[0]
    
    await msg.answer(f"✅ ДОБАВЛЕНО {added} ССЫЛОК-ЧЕКОВ!\n\n📊 Всего доступно: {total_available}")
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(checks) FROM users")
    total_checks = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE is_active = 1")
    active_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM check_links WHERE is_used = 0")
    available_links = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM check_links WHERE is_used = 1")
    used_links = cursor.fetchone()[0]
    
    await callback.message.edit_text(
        f"📊 СТАТИСТИКА БОТА\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Всего чеков: {total_checks}\n"
        f"📋 Активных заданий: {active_tasks}\n\n"
        f"🎁 ССЫЛКИ-ЧЕКИ:\n"
        f"📦 Доступно: {available_links}\n"
        f"✅ Использовано: {used_links}\n"
        f"📊 Всего: {available_links + used_links}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

async def main():
    print("✅ БОТ @monstertaskbot ЗАПУЩЕН!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())