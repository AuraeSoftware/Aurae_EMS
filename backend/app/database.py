from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os


def _build_url() -> str:
    """Build DATABASE_URL. Supports Railway's DATABASE_URL and PG* individual vars."""
    raw = os.environ.get("APP_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "").strip()
    
    if not raw and os.environ.get("PGHOST"):
        raw = "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
            user=os.environ.get("PGUSER", "postgres"),
            pw=os.environ.get("PGPASSWORD", ""),
            host=os.environ.get("PGHOST", "localhost"),
            port=os.environ.get("PGPORT", "5432"),
            db=os.environ.get("PGDATABASE", "railway"),
        )
    
    if not raw:
        raw = "postgresql+asyncpg://aurae_admin:aurae_secret@localhost:5432/aurae_ems"
    
    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://") and "+asyncpg" not in raw:
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
    
    return raw


_DATABASE_URL = _build_url()
_is_local = any(h in _DATABASE_URL for h in ["localhost", "127.0.0.1", "railway.internal"])
_connect_args = {} if _is_local else {"ssl": "require"}

engine = create_async_engine(
    _DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()