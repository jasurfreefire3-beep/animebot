import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import Database
from handlers import admin_router, user_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        logger.error("❌ BOT_TOKEN belgilanmagan! Iltimos, .env faylida bot tokeningizni kiriting.")
        sys.exit(1)

    # Bazani ishga tushirish
    db = Database()
    logger.info("Ma'lumotlar bazasi tayyorlandi.")

    # Bot va Dispatcher yaratish
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Routerlarni ulash
    dp.include_router(admin_router)
    dp.include_router(user_router)

    bot_info = await bot.get_me()
    logger.info(f"🚀 Bot muvaffaqiyatli ishga tushdi: @{bot_info.username}")
    print(f"\n=======================================================")
    print(f"  🎬 Animem Uz Telegram Bot ishga tushdi!")
    print(f"  🤖 Bot username: @{bot_info.username}")
    print(f"  👑 Admin panel: /admin")
    print(f"=======================================================\n")

    # Polling boshlash
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")

