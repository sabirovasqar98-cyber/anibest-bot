import os
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🎌 ANIBEST BOT'ga xush kelibsiz!\n\n"
        "🆔 Anime kodini yuboring."
    )


@dp.message()
async def code_handler(message: Message):
    code = message.text.strip()

    if code == "187":
        await message.answer(
            "🎬 Iblisning xotini\n\n"
            "🎞 Qismni tanlang:\n"
            "1️⃣ 2️⃣ 3️⃣ 4️⃣"
        )
    else:
        await message.answer(
            "❌ Bunday anime kodi topilmadi.\n\n"
            "Kodini qayta yuboring."
        )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
