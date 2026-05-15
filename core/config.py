import os
from dotenv import load_dotenv


load_dotenv()

class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", 0))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:1111@localhost:5432/smartquiz")

settings = Settings()