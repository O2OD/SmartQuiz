import asyncio
import logging
from aiogram import Bot, Dispatcher
from core.config import settings
from database.engine import init_models
from handlers.creator import creator_router
from handlers.play import play_router

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_models()
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(creator_router)
    dp.include_router(play_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())