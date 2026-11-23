import asyncio
import os
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, 
    LabeledPrice, PreCheckoutQuery, InlineQuery, InlineQueryResultGame
)
from aiogram.exceptions import TelegramBadRequest

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GAME_SHORT_NAME = "guesswho"  # То самое имя из BotFather!
GAME_URL = "https://tg-game-bot.pages.dev/" # Ссылка на твою HTML страницу с игрой
# ============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. ИГРА (Кнопка в чате) ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Нажми на кнопку ниже, чтобы сыграть в 'Угадай кто'.")
    try:
        await bot.send_game(chat_id=message.chat.id, game_short_name=GAME_SHORT_NAME)
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка игры: {e}. Проверь, создана ли игра в BotFather.")

@dp.callback_query(F.data.startswith("game_"))
async def process_game_callback(call: CallbackQuery):
    await bot.answer_game(
        game_short_name=GAME_SHORT_NAME,
        url=GAME_URL,
        score=0 
    )
    await call.answer()

# --- 2. ИНЛАЙН РЕЖИМ (Вызов через @бот) ---
@dp.inline_query()
async def inline_game_handler(inline_query: InlineQuery):
    result = InlineQueryResultGame(
        id="1", 
        game_short_name=GAME_SHORT_NAME
    )
    await inline_query.answer(
        results=[result],
        cache_time=1
    )

# --- 3. ПОДДЕРЖКА АВТОРА (Telegram Stars) ---
@dp.message(Command("donate"))
async def cmd_donate(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 звезда ⭐", callback_data="donate_1")],
        [InlineKeyboardButton(text="5 звезд ⭐", callback_data="donate_5")],
        [InlineKeyboardButton(text="10 звезд ⭐", callback_data="donate_10")]
    ])
    await message.answer("Поддержи автора проекта! Выбери количество звезд:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("donate_"))
async def process_donate(call: CallbackQuery):
    amount = int(call.data.split("_")[1])
    
    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Поддержка автора",
        description=f"Спасибо за поддержку на {amount} звезд!",
        payload=f"donate_{amount}",
        provider_token="", # Для звезд всегда пустая строка
        currency="XTR", # Валюта Telegram Stars
        prices=[LabeledPrice(label="Поддержка", amount=amount)],
        start_parameter="donate"
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    await message.answer(f"Спасибо огромное за поддержку! Ты оплатил {message.successful_payment.total_amount} звезд. ❤️")

# --- 4. FLASK ДЛЯ RENDER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()
# ------------------------------

async def main():
    print("Бот Угадай кто запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())