import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GAME_SHORT_NAME = "guess_game_bot"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await bot.send_game(chat_id=message.chat.id, game_short_name=GAME_SHORT_NAME)

@dp.callback_query(F.data.startswith("game_"))
async def process_game_callback(call: CallbackQuery):
    game_url = "https://example.com" 
    
    await bot.answer_game(
        game_short_name=GAME_SHORT_NAME,
        url=game_url,
        score=0
    )
    await call.answer()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())