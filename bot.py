import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault
from core.config import settings
from database.engine import init_models
from handlers.creator import creator_router
from handlers.play import play_router
from handlers.admin import admin_router

async def set_main_menu(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 Bosh menyu"),
        BotCommand(command="mytests", description="📂 Mening testlarim"),
        BotCommand(command="help", description="❓ Qo'llanma va namuna"),
        BotCommand(command="clear", description="🧹 Tozalash"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_models()
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    # Routerlarni ulash
    dp.include_router(admin_router)
    dp.include_router(creator_router)
    dp.include_router(play_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await set_main_menu(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())