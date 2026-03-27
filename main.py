import asyncio
import aiosqlite
import os
import aiohttp
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramForbiddenError

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8782789238:AAENc2VrGUNUKQnUbI2SKt79dpJfJKF6UZo'
VK_API_TOKEN = 'vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw'
DISCORD_TOKEN = 'f847835bad2fd33ef6f4450d2cb38bf6c6f591d7a3e905468f310c8a83e86e3c'
ADMIN_ID = 7572936594 

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

class States(StatesGroup):
    vk = State()
    discord = State()
    ip = State()
    dork = State()
    telelog = State()
    phone = State()
    photo_search = State()
    city_name = State()
    add_admin = State()
    broadcast = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("history.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS search_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, query TEXT, result TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.commit()

async def is_admin(user_id):
    if user_id == ADMIN_ID: return True
    async with aiosqlite.connect("history.db") as db:
        async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone() is not None

async def save_log(user_id, s_type, query, result):
    async with aiosqlite.connect("history.db") as db:
        await db.execute("INSERT INTO search_logs (user_id, type, query, result) VALUES (?, ?, ?, ?)", (user_id, s_type, query, result))
        await db.commit()

# --- ПАРСЕР KOMANDIROVKA.RU ---
async def fetch_city_data(city_query):
    h = {"User-Agent": "Mozilla/5.0"}
    search_url = f"https://www.komandirovka.ru/search/?q={urllib.parse.quote(city_query)}"
    try:
        async with session.get(search_url, headers=h) as r:
            soup = BeautifulSoup(await r.text(), 'html.parser')
            result_link = soup.find('a', class_='search-result__title')
            if not result_link: return "🔍 Город или область не найдены в базе Komandirovka.ru"
            
            city_url = "https://www.komandirovka.ru" + result_link['href']
            async with session.get(city_url, headers=h) as cr:
                csoup = BeautifulSoup(await cr.text(), 'html.parser')
                desc = csoup.find('div', class_='city-info__description')
                info_text = desc.get_text(strip=True)[:500] if desc else "Описание отсутствует."
                
                return (f"🏙 **Результат поиска: {result_link.text}**\n"
                        f"🔗 [Страница на Komandirovka.ru]({city_url})\n\n"
                        f"📝 **Информация:** {info_text}...")
    except: return "⚠️ Ошибка при подключении к сервису Komandirovka.ru"

async def fetch_advanced_osint(query, mode="general"):
    h = {"User-Agent": "Mozilla/5.0"}
    if mode == "phone": q = f"\"{query}\" site:avito.ru OR site:vk.com"
    elif mode == "telelog": q = f"site:t.me OR site:tgstat.ru \"{query}\""
    else: q = query
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
    try:
        async with session.get(url, headers=h) as r:
            soup = BeautifulSoup(await r.text(), 'html.parser')
            res = [f"🔹 **{b.find('a', class_='result__a').text}**\n🔗 {b.find('a', class_='result__a')['href']}\n" 
                   for b in soup.find_all('div', class_='result', limit=4)]
            return "\n".join(res) if res else "🔍 Данные не найдены."
    except: return "⚠️ Ошибка индексации."

# --- КЛАВИАТУРЫ ---
def main_kb(user_id, admin=False):
    buttons = [
        [KeyboardButton(text="👤 OSINT ВКонтакте"), KeyboardButton(text="🎮 OSINT Discord")],
        [KeyboardButton(text="🌐 Проверка IP адрес"), KeyboardButton(text="📱 Поиск по номеру")],
        [KeyboardButton(text="🔎 Гугл Дорк"), KeyboardButton(text="📜 Телелог")],
        [KeyboardButton(text="🖼 Поиск по фото/городу")]
    ]
    if admin: buttons.append([KeyboardButton(text="🔐 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    async with aiosqlite.connect("history.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    admin_status = await is_admin(message.from_user.id)
    await message.answer("🚀 OSINT Бот активен.\nВыберите модуль поиска.", reply_markup=main_kb(message.from_user.id, admin_status))

# [НОВОЕ] ПОИСК ПО ФОТО И ГОРОДУ
@dp.message(F.text == "🖼 Поиск по фото/городу")
async def s_photo_start(message: Message, state: FSMContext):
    await message.answer("📸 Отправьте фото объекта или местности, которую нужно найти.\n\n(Если фото нет, просто напишите название города или области)")
    await state.set_state(States.photo_search)

@dp.message(States.photo_search, F.photo)
async def p_photo_rec(message: Message, state: FSMContext):
    await message.answer("✅ Фото получено. Теперь введите **название города или области**, к которой оно может относиться (для поиска на Komandirovka.ru):")
    await state.set_state(States.city_name)

@dp.message(States.photo_search, F.text)
async def p_photo_text(message: Message, state: FSMContext):
    # Если пользователь сразу ввел текст вместо фото
    res = await fetch_city_data(message.text)
    await message.answer(res, parse_mode="Markdown")
    await state.clear()

@dp.message(States.city_name)
async def p_city_final(message: Message, state: FSMContext):
    msg = await message.answer(f"⏳ Ищу информацию по локации: {message.text}...")
    res = await fetch_city_data(message.text)
    
    # Добавляем ссылки на визуальный поиск для помощи пользователю
    visual_help = (
        f"\n\n🌍 **Дополнительный визуальный поиск:**\n"
        f"🔗 [Поиск в Google Images](https://www.google.com/searchbyimage?image_url=https://t.me/)\n"
        f"🔗 [Поиск в Yandex Images](https://yandex.ru/images/search?rpt=imageview)"
    )
    
    await msg.edit_text(res + visual_help, parse_mode="Markdown", disable_web_page_preview=True)
    await save_log(message.from_user.id, "CITY_PHOTO", message.text, "City Data Fetched")
    await state.clear()

# [ОСТАЛЬНЫЕ МОДУЛИ]
@dp.message(F.text == "📱 Поиск по номеру")
async def s_phone(message: Message, state: FSMContext):
    await message.answer("📱 Введите номер телефона:")
    await state.set_state(States.phone)

@dp.message(States.phone)
async def p_phone(message: Message, state: FSMContext):
    res = await fetch_advanced_osint(message.text, mode="phone")
    await message.answer(f"📱 **ОТЧЕТ:**\n\n{res}", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔎 Гугл Дорк")
async def s_dork(message: Message, state: FSMContext):
    await message.answer("🔎 Введите объект поиска:")
    await state.set_state(States.dork)

@dp.message(States.dork)
async def p_dork(message: Message, state: FSMContext):
    res = await fetch_advanced_osint(message.text)
    await message.answer(f"📊 **ОТЧЕТ:**\n\n{res}", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: Message):
    if not await is_admin(message.from_user.id): return
    btns = [[KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="📥 Скачать базу")], [KeyboardButton(text="➕ Добавить админа")], [KeyboardButton(text="⬅️ Назад")]]
    await message.answer("🛠 Админка:", reply_markup=ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True))

@dp.message(F.text == "⬅️ Назад")
async def back(message: Message):
    admin_status = await is_admin(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_kb(message.from_user.id, admin_status))

async def main():
    global session
    await init_db()
    session = aiohttp.ClientSession()
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot Active"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080))).start()
    try: await dp.start_polling(bot)
    finally: await session.close()

if __name__ == "__main__":
    asyncio.run(main())
