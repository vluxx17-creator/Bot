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

# --- КОНФИГУРАЦИЯ ---
TOKEN = '8782789238:AAENc2VrGUNUKQnUbI2SKt79dpJfJKF6UZo'
VK_API_TOKEN = 'vk1.a.gg0A2uqhaeJR4Q0rQroAOrKxLtlld-zpDhUuNRsLph2tyJZzoyIioGN8vNs_AzCfepKFqTdigONU-ydz1VZnL68Ns7qZ0HcgUhmEOE_F1ZI26awIwunbGfzTpn-xmEEXAueaaBR5lb-ew_z478YoxYuNlAEHHfGBddR9u10-MJae6l1UUC4C3eKWD28ugFy7hhguP-Ihcxsb42Fbq_SPsw'
DISCORD_TOKEN = 'f847835bad2fd33ef6f4450d2cb38bf6c6f591d7a3e905468f310c8a83e86e3c'
ADMIN_ID = 7572936594 

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
session = None 

class SearchStates(StatesGroup):
    vk = State()
    discord = State()
    ip = State()
    dork = State()
    telelog = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("history.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            query TEXT,
            result TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.commit()

async def save_log(user_id, s_type, query, result):
    async with aiosqlite.connect("history.db") as db:
        await db.execute("INSERT INTO search_logs (user_id, type, query, result) VALUES (?, ?, ?, ?)",
                         (user_id, s_type, query, result))
        await db.commit()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def fetch_osint_data(query, source_type="general"):
    """Универсальный парсер для Dork и Telelog"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    if source_type == "telelog":
        search_query = f"site:t.me OR site:tgstat.ru OR site:telemetr.io \"{query}\""
    else:
        search_query = query

    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
    
    try:
        async with session.get(url, headers=headers) as response:
            if response.status != 200: return "❌ Ошибка доступа к данным."
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            results = []
            blocks = soup.find_all('div', class_='result', limit=5)
            
            for block in blocks:
                title = block.find('a', class_='result__a').get_text(strip=True)
                snippet = block.find('a', class_='result__snippet').get_text(strip=True)
                results.append(f"🔹 **{title}**\n📝 {snippet}\n")
            
            return "\n".join(results) if results else "🔍 Данных в открытых архивах не найдено."
    except Exception:
        return "⚠️ Ошибка при сканировании архивов."

# --- КЛАВИАТУРА ---
def main_kb(user_id):
    buttons = [
        [KeyboardButton(text="👤 OSINT ВКонтакте"), KeyboardButton(text="🎮 OSINT Discord")],
        [KeyboardButton(text="🌐 Проверка IP адрес")],
        [KeyboardButton(text="🔎 Гугл Дорк"), KeyboardButton(text="📜 Телелог")]
    ]
    if user_id == ADMIN_ID: buttons.append([KeyboardButton(text="🔐 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("🚀 OSINT Бот активен.\nВыбери модуль ниже.", reply_markup=main_kb(message.from_user.id))

# [1] Гугл Дорк
@dp.message(F.text == "🔎 Гугл Дорк")
async def s_dork(message: Message, state: FSMContext):
    await message.answer("🔎 Введите объект поиска (ФИО, почта, ник):")
    await state.set_state(SearchStates.dork)

@dp.message(SearchStates.dork)
async def p_dork(message: Message, state: FSMContext):
    msg = await message.answer("🔄 Глубокое сканирование интернета...")
    res = await fetch_osint_data(message.text)
    await message.answer(f"📊 **ОТЧЕТ ПО ЗАПРОСУ: {message.text}**\n\n{res}", parse_mode="Markdown", disable_web_page_preview=True)
    await msg.delete()
    await state.clear()

# [2] Телелог (ОБНОВЛЕННЫЙ)
@dp.message(F.text == "📜 Телелог")
async def s_telelog(message: Message, state: FSMContext):
    await message.answer("📜 Введите @username пользователя Telegram:")
    await state.set_state(SearchStates.telelog)

@dp.message(SearchStates.telelog)
async def p_telelog(message: Message, state: FSMContext):
    target = message.text.replace("@", "")
    msg = await message.answer(f"⏳ Собираю историю активности для @{target}...")
    
    # Получаем отчет по упоминаниям в истории групп и каналов
    report = await fetch_osint_data(target, source_type="telelog")
    
    final_report = (
        f"📜 **ОТЧЕТ ПО ИСТОРИИ: @{target}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔍 **Найденные упоминания и старые имена:**\n\n{report}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💡 *Если данных мало, значит пользователь скрыт настройками приватности или редко пишет в публичных чатах.*"
    )
    
    await save_log(message.from_user.id, "TELELOG", target, "Text Report Generated")
    await message.answer(final_report, parse_mode="Markdown", disable_web_page_preview=True)
    await msg.delete()
    await state.clear()

# [Остальные функции ВК, Discord, IP, Админка...]

@dp.message(F.text == "👤 OSINT ВКонтакте")
async def s_vk(message: Message, state: FSMContext):
    await message.answer("🔗 Введите ID или ник ВК:")
    await state.set_state(SearchStates.vk)

@dp.message(SearchStates.vk)
async def p_vk(message: Message, state: FSMContext):
    url = f"https://api.vk.com/method/users.get?user_ids={message.text}&fields=photo_max,domain,city&access_token={VK_API_TOKEN}&v=5.131"
    async with session.get(url) as resp:
        res = await resp.json()
        if 'response' in res and res['response']:
            u = res['response'][0]
            info = f"👤 {u['first_name']} {u['last_name']}\n🆔 ID: {u['id']} | @{u.get('domain')}"
            if u.get('photo_max'): await message.answer_photo(u['photo_max'], caption=info)
            else: await message.answer(info)
        else: await message.answer("❌ Ошибка.")
    await state.clear()

@dp.message(F.text == "🎮 OSINT Discord")
async def s_discord(message: Message, state: FSMContext):
    await message.answer("🆔 Введите ID Discord:")
    await state.set_state(SearchStates.discord)

@dp.message(SearchStates.discord)
async def p_discord(message: Message, state: FSMContext):
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with session.get(f"https://discord.com/api/v10/users/{message.text}", headers=headers) as resp:
        if resp.status == 200:
            d = await resp.json()
            await message.answer(f"🎮 Discord: {d['username']}")
        else: await message.answer("❌ Ошибка.")
    await state.clear()

@dp.message(F.text == "🌐 Проверка IP адрес")
async def s_ip(message: Message, state: FSMContext):
    await message.answer("🌐 Введите IP:")
    await state.set_state(SearchStates.ip)

@dp.message(SearchStates.ip)
async def p_ip(message: Message, state: FSMContext):
    async with session.get(f"http://ip-api.com/json/{message.text}") as r:
        d = await r.json()
        if d.get('status') == 'success': await message.answer(f"🌐 IP: {d['query']}\n📍 Страна: {d['country']}")
        else: await message.answer("❌ Ошибка.")
    await state.clear()

@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📥 Скачать базу")], [KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Админка.", reply_markup=kb)

@dp.message(F.text == "📥 Скачать базу")
async def download_logs(message: Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("history.db") as db:
        async with db.execute("SELECT * FROM search_logs") as cursor:
            rows = await cursor.fetchall()
    file = BufferedInputFile("\n".join([str(r) for r in rows]).encode(), filename="history.txt")
    await message.answer_document(file)

@dp.message(F.text == "⬅️ Назад")
async def back_to_main(message: Message):
    await message.answer("Главное меню:", reply_markup=main_kb(message.from_user.id))

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
