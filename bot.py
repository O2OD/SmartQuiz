import asyncio
import logging
import contextlib
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

from core.config import settings
from database.engine import init_models
from handlers.admin import admin_router
from handlers.solo_quiz import solo_router

async def set_bot_commands(bot: Bot):
    user_commands = [
        BotCommand(command="start", description="🏠 Asosiy menyu"),
        BotCommand(command="clear", description="🧹 Botni tozalash")
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = [
        BotCommand(command="start", description="🏠 Asosiy menyu"),
        BotCommand(command="stats", description="📊 Statistika"),
        BotCommand(command="export", description="💾 Natijalar (Excel)"),
        BotCommand(command="clear", description="🧹 Tozalash")
    ]
    
    with contextlib.suppress(Exception):
        await bot.set_my_commands(
            admin_commands, 
            scope=BotCommandScopeChat(chat_id=settings.ADMIN_ID)
        )

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    
    await init_models()
    
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(admin_router)
    dp.include_router(solo_router)
    
    await set_bot_commands(bot)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")