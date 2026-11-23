import asyncio
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, 
    LabeledPrice, PreCheckoutQuery, WebAppInfo
)

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GAME_URL = "https://tg-game-bot.pages.dev/" # Ссылка на твою HTML страницу
# ============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. КНОПКА ИГРЫ (Открывает Web App) ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Создаем кнопку Web App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", web_app=WebAppInfo(url=GAME_URL))]
    ])
    await message.answer("Привет! Нажми на кнопку ниже, чтобы сыграть в 'Угадай кто'.", reply_markup=keyboard)

# --- 2. ПРИЕМ ДАННЫХ ИЗ ИГРЫ ---
@dp.message(F.web_app_data)
async def web_app_data_handler(message: Message):
    data = message.web_app_data.data
    await message.answer(f"✅ Игра завершена! Данные получены: {data}")

# --- 3. ПОДДЕРЖКА АВТОРА (Звезды) ---
@dp.message(Command("donate"))
async def cmd_donate(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 звезда ⭐", callback_data="donate_1")],
        [InlineKeyboardButton(text="5 звезд ⭐", callback_data="donate_5")],
        [InlineKeyboardButton(text="10 звезд ⭐", callback_data="donate_10")]
    ])
    await message.answer("Поддержи автора! Выбери количество звезд:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("donate_"))
async def process_donate(call: CallbackQuery):
    amount = int(call.data.split("_")[1])
    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Поддержка автора",
        description=f"Спасибо за поддержку на {amount} звезд!",
        payload=f"donate_{amount}",
        provider_token="", 
        currency="XTR", 
        prices=[LabeledPrice(label="Поддержка", amount=amount)],
        start_parameter="donate"
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    await message.answer(f"Спасибо огромное! Ты оплатил {message.successful_payment.total_amount} звезд. ❤️")

# --- 4. СЕРВЕР ДЛЯ RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())