from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import settings
from database.models import Base

engine = create_async_engine(settings.DB_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)