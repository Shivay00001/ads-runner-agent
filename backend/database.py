import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# Override with e.g. postgresql+asyncpg://user:pass@host/db for production.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./ads_runner.db")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
