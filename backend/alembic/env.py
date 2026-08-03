import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models import *  # noqa

config = context.config


def _build_url() -> str:
    """Build DATABASE_URL from env vars. Supports Railway's DATABASE_URL and PG* vars."""
    # Try DATABASE_URL first
    raw = os.environ.get("APP_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "").strip()
    
    # Fallback: build from Railway PG* individual vars
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
    
    # Normalize to asyncpg
    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://") and "+asyncpg" not in raw:
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
    
    return raw


DB_URL = _build_url()
config.set_main_option("sqlalchemy.url", DB_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    is_local = any(h in DB_URL for h in ["localhost", "127.0.0.1", "railway.internal"])
    connect_args = {} if is_local else {"ssl": "require"}
    
    host_part = DB_URL.split("@")[-1] if "@" in DB_URL else DB_URL
    print(f"[Alembic] Host: {host_part} | SSL: {not is_local}", flush=True)

    connectable = create_async_engine(
        DB_URL,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()