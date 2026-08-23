import os
import sqlite3
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiohttp import web

# ---------- НАСТРОЙКИ (из переменных окружения) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8610780281:AAFZxc5KSd4wEtUNZ4U47Poltu0jMVR-mbg")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://sevelevd86-lgtm.github.io/musor_drop/")
WEBAPP_PORT = int(os.getenv("PORT", 8080))

# ---------- ЛОГГИНГ ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- БАЗА ДАННЫХ ----------
DB_FILE = "casino_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 1000,
            referrer_id INTEGER DEFAULT NULL,
            wallet_address TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, referrer_id, wallet_address FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1], "balance": row[2], "referrer_id": row[3], "wallet_address": row[4]}
    return None

def create_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if referrer_id:
        cursor.execute("INSERT INTO users (user_id, username, referrer_id, balance) VALUES (?, ?, ?, ?)", (user_id, username, referrer_id, 1500))
        cursor.execute("UPDATE users SET balance = balance + 500 WHERE user_id=?", (referrer_id,))
        bonus = 1500
    else:
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, 1000))
        bonus = 1000
    conn.commit()
    conn.close()
    logger.info(f"Создан пользователь {user_id} с балансом {bonus}")
    return bonus

def update_balance(user_id, new_balance):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = ? WHERE user_id=?", (new_balance, user_id))
    conn.commit()
    conn.close()

def update_wallet(user_id, wallet):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET wallet_address = ? WHERE user_id=?", (wallet, user_id))
    conn.commit()
    conn.close()

# ---------- БОТ ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1].replace("ref", ""))
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass

    user = get_user(user_id)
    if not user:
        create_user(user_id, username, referrer_id)
        bonus_text = " + 500 бонусных монет!" if referrer_id else ""
        await message.answer(f"🎰 Добро пожаловать в казино, {username}!\nТвой стартовый баланс: 1000 монет{bonus_text}\nНажми 'Играть', чтобы открыть казино!")
    else:
        await message.answer(f"🎰 С возвращением, {username}!\nТвой баланс: {user['balance']} монет.\nНажми 'Играть', чтобы открыть казино!")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎰 Играть", web_app=WebAppInfo(url=f"{WEBAPP_URL}"))]
        ]
    )
    await message.answer("Нажми на кнопку, чтобы открыть приложение:", reply_markup=keyboard)

# ---------- WEBAPP API ----------
async def handle_webapp(request):
    try:
        data = await request.json()
        action = data.get("action")
        user_id = data.get("user_id")
        logger.info(f"Получен запрос: {action} от {user_id}")

        if action == "get_profile":
            user = get_user(user_id)
            if user:
                return web.json_response({
                    "status": "ok",
                    "username": user["username"],
                    "user_id": user["user_id"],
                    "balance": user["balance"],
                    "wallet": user["wallet_address"]
                })
            return web.json_response({"status": "error", "message": "User not found"})

        elif action == "update_wallet":
            wallet = data.get("wallet")
            if wallet and len(wallet) > 10:
                update_wallet(user_id, wallet)
                return web.json_response({"status": "ok", "message": "Кошелек привязан!"})
            return web.json_response({"status": "error", "message": "Неверный адрес"})

        elif action == "update_balance":
            new_balance = data.get("balance")
            if new_balance is not None:
                update_balance(user_id, new_balance)
                return web.json_response({"status": "ok", "balance": new_balance})
            return web.json_response({"status": "error", "message": "Invalid balance"})

        elif action == "withdraw":
            user = get_user(user_id)
            if not user:
                return web.json_response({"status": "error", "message": "User not found"})
            if user["balance"] < 100:
                return web.json_response({"status": "error", "message": "Минимальная сумма вывода 100 монет"})
            if not user["wallet_address"]:
                return web.json_response({"status": "error", "message": "Сначала привяжите кошелек!"})
            update_balance(user_id, user["balance"] - 100)
            return web.json_response({"status": "ok", "message": f"Заявка на вывод 100 монет на {user['wallet_address']} отправлена!"})

        return web.json_response({"status": "error", "message": "Неизвестное действие"})

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return web.json_response({"status": "error", "message": str(e)})

# ---------- ОБРАБОТЧИК КОРНЯ ----------
async def handle_root(request):
    try:
        return web.FileResponse("index.html")
    except FileNotFoundError:
        return web.Response(text="index.html not found", status=404)

# ---------- ЗАПУСК ВЕБ-СЕРВЕРА ----------
async def start_webapp():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_post("/webapp", handle_webapp)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", WEBAPP_PORT)
    await site.start()
    logger.info(f"WebApp сервер запущен на порту {WEBAPP_PORT}")

# ---------- ОСНОВНОЙ ЗАПУСК ----------
async def main():
    init_db()
    await start_webapp()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    