from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fair_assessment_proxy.config import load_db_config

db = load_db_config()
engine = create_async_engine(
    f"postgresql+psycopg://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}",
    echo=False,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
