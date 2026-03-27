import asyncio
import aiosqlite
import os
import aiohttp
import urllib.parse
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

# --- КЛАВИАТУРА ---
def main_kb(user_id):
    buttons = [
        [KeyboardButton(text="👤 OSINT ВКонтакте"), KeyboardButton(text="🎮 OSINT Discord")],
        [KeyboardButton(text="🌐 Проверка IP адрес")],
        [KeyboardButton(text="🔎 Гугл Дорк"), KeyboardButton(text="📜 Телелог")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🔐 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ОБРАБОТЧИКИ (START) ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = (
        "🚀 Приветствую в @searchHams_bot\n\n"
        "Выбери нужный модуль поиска ниже.\n\n"
        "📢 Канал: @owhig"
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id))

# --- [1] ВКОНТАКТЕ ---
@dp.message(F.text == "👤 OSINT ВКонтакте")
async def s_vk(message: Message, state: FSMContext):
    await message.answer("🔗 Введите ID или никнейм ВК:")
    await state.set_state(SearchStates.vk)

@dp.message(SearchStates.vk)
async def p_vk(message: Message, state: FSMContext):
    url = f"https://api.vk.com/method/users.get?user_ids={message.text}&fields=photo_max,domain,bdate,city,status,followers_count,relation,occupation,site,verified&access_token={VK_API_TOKEN}&v=5.131"
    async with session.get(url) as resp:
        res = await resp.json()
        if 'response' in res and res['response']:
            u = res['response'][0]
            rel = {1:"Одинокий", 2:"Есть друг", 3:"Помолвлен", 4:"В браке", 5:"Сложно", 6:"В поиске", 7:"Влюблен", 8:"Гражд. брак"}.get(u.get('relation'), "Скрыто")
            info = (
                f"👤 {u['first_name']} {u['last_name']} {'✅' if u.get('verified') else ''}\n"
                f"🆔 ID: {u['id']} | @{u.get('domain')}\n"
                f"🎂 ДР: {u.get('bdate', 'Скрыто')}\n"
                f"🏙 Город: {u.get('city', {}).get('title', 'N/A')}\n"
                f"💍 Отношения: {rel}\n"
                f"👥 Подписчиков: {u.get('followers_count', 0)}\n"
                f"🌐 Сайт: {u.get('site', 'Нет')}"
            )
            await save_log(message.from_user.id, "VK", message.text, info)
            if u.get('photo_max'): await message.answer_photo(u['photo_max'], caption=info)
            else: await message.answer(info)
        else: await message.answer("❌ Ошибка поиска ВК.")
    await state.clear()

# --- [2] DISCORD ---
@dp.message(F.text == "🎮 OSINT Discord")
async def s_discord(message: Message, state: FSMContext):
    await message.answer("🆔 Введите ID пользователя Discord:")
    await state.set_state(SearchStates.discord)

@dp.message(SearchStates.discord)
async def p_discord(message: Message, state: FSMContext):
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    async with session.get(f"https://discord.com/api/v10/users/{message.text}", headers=headers) as resp:
        if resp.status == 200:
            d = await resp.json()
            reg_date = datetime.fromtimestamp(((int(d['id']) >> 22) + 1420070400000) / 1000).strftime('%d.%m.%Y')
            report = f"🎮 DISCORD OSINT\n━━━━━━━━━━━━━━\n👤 Имя: {d['username']}\n🆔 ID: {d['id']}\n📅 Регистрация: {reg_date}\n━━━━━━━━━━━━━━"
            await save_log(message.from_user.id, "DISCORD", message.text, report)
            await message.answer(report)
        else: await message.answer("❌ Discord ID не найден.")
    await state.clear()

# --- [3] IP ---
@dp.message(F.text == "🌐 Проверка IP адрес")
async def s_ip(message: Message, state: FSMContext):
    await message.answer("🌐 Введите IP адрес:")
    await state.set_state(SearchStates.ip)

@dp.message(SearchStates.ip)
async def p_ip(message: Message, state: FSMContext):
    async with session.get(f"http://ip-api.com/json/{message.text}?fields=66846719") as r:
        d = await r.json()
        if d.get('status') == 'success':
            res_text = f"🌐 IP: {d['query']}\n📍 Страна: {d['country']}\n🏙 Город: {d['city']}\n🏢 ISP: {d['isp']}\n🛡 VPN: {'Да' if d['proxy'] else 'Нет'}"
            await save_log(message.from_user.id, "IP", message.text, res_text)
            await message.answer(res_text)
        else: await message.answer("❌ IP не найден.")
    await state.clear()

# --- [4] ГУГЛ ДОРК (Google Dorks) ---
@dp.message(F.text == "🔎 Гугл Дорк")
async def s_dork(message: Message, state: FSMContext):
    await message.answer("🔎 Введите объект поиска (ФИО, Никнейм, Почта или Номер):")
    await state.set_state(SearchStates.dork)

@dp.message(SearchStates.dork)
async def p_dork(message: Message, state: FSMContext):
    query = message.text
    encoded_query = urllib.parse.quote(f'"{query}"')
    
    dorks = (
        f"🔎 **Результаты Google Dorks для: {query}**\n\n"
        f"🔗 [Поиск по соцсетям](https://www.google.com/search?q={encoded_query}+site:linkedin.com+OR+site:instagram.com+OR+site:facebook.com+OR+site:twitter.com)\n"
        f"📂 [Поиск документов (PDF, Doc)](https://www.google.com/search?q={encoded_query}+filetype:pdf+OR+filetype:doc+OR+filetype:xlsx)\n"
        f"💬 [Упоминания в Telegram/Vkontakte](https://www.google.com/search?q={encoded_query}+site:t.me+OR+site:vk.com)\n"
        f"📧 [Поиск паролей/утечек](https://www.google.com/search?q={encoded_query}+\"password\"+OR+\"leak\"+OR+\"database\")\n"
        f"💻 [Поиск на GitHub/Pastebin](https://www.google.com/search?q={encoded_query}+site:github.com+OR+site:pastebin.com)\n"
    )
    await save_log(message.from_user.id, "DORK", query, "Generated links")
    await message.answer(dorks, parse_mode="Markdown", disable_web_page_preview=True)
    await state.clear()

# --- [5] ТЕЛЕЛОГ (История ников Telegram) ---
@dp.message(F.text == "📜 Телелог")
async def s_telelog(message: Message, state: FSMContext):
    await message.answer("📜 Введите @username или ID пользователя Telegram:")
    await state.set_state(SearchStates.telelog)

@dp.message(SearchStates.telelog)
async def p_telelog(message: Message, state: FSMContext):
    target = message.text.replace("@", "")
    
    # Ссылки на внешние сервисы логирования истории
    tele_report = (
        f"📜 **Отчет Telelog для: @{target}**\n\n"
        f"1️⃣ [История в TGStat](https://tgstat.ru/user/@{target})\n"
        f"2️⃣ [Анализ в Telemetr](https://telemetr.io/ru/user/@{target})\n"
        f"3️⃣ [Поиск в базах (Google)](https://www.google.com/search?q=site:t.me+\"{target}\")\n\n"
        f"ℹ️ *Примечание: Если пользователь менял ник недавно, данные появятся в течение 24-48 часов.*"
    )
    await save_log(message.from_user.id, "TELELOG", target, "Generated report links")
    await message.answer(tele_report, parse_mode="Markdown", disable_web_page_preview=True)
    await state.clear()

# --- АДМИНКА ---
@dp.message(F.text == "🔐 Админ-панель")
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📥 Скачать базу")], [KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Добро пожаловать в админ-панель.", reply_markup=kb)

@dp.message(F.text == "📥 Скачать базу")
async def download_logs(message: Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect("history.db") as db:
        async with db.execute("SELECT * FROM search_logs") as cursor:
            rows = await cursor.fetchall()
    log_text = "\n".join([str(r) for r in rows])
    file = BufferedInputFile(log_text.encode(), filename="history.txt")
    await message.answer_document(file, caption="✅ База запросов")

@dp.message(F.text == "⬅️ Назад")
async def back_to_main(message: Message):
    await message.answer("Главное меню:", reply_markup=main_kb(message.from_user.id))

# --- ЗАПУСК ---
async def main():
    global session
    await init_db()
    session = aiohttp.ClientSession()
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot Active"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8080))).start()
    try:
        await dp.start_polling(bot)
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())
