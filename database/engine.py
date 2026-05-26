from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from database.models import Base
from core.config import settings

# Ma'lumotlar bazasi URL manzilini settings.py dan oladi.
# Agar u yerda yozilmagan bo'lsa, standart SQLite bazasidan foydalanadi.
DB_URL = getattr(settings, "DB_URL", "sqlite+aiosqlite:///database/smartquiz.db")

# Async dvigatelni yaratish
engine = create_async_engine(DB_URL, echo=False)

# Sessiya yaratuvchi (Boshqa fayllarda chaqiriladigan async_session_maker shu yerda)
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# bot.py qidirayotgan jadvallarni ishga tushiruvchi funksiya
async def init_models():
    async with engine.begin() as conn:
        # Modellarni (jadvallarni) bazada yaratish
        await conn.run_sync(Base.metadata.create_all)