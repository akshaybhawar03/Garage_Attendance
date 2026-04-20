import os
import asyncpg
from pgvector.asyncpg import register_vector
from dotenv import load_dotenv

load_dotenv()

_raw_url = os.getenv("DATABASE_URL", "")

# asyncpg expects plain postgresql:// — strip SQLAlchemy dialect prefix
DATABASE_URL = _raw_url.replace("postgresql+asyncpg://", "postgresql://", 1)

pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection):
    """Register pgvector codec on every new connection."""
    await register_vector(conn)


async def connect_db():
    """Create the connection pool (called once at startup)."""
    global pool
    pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=2,
        max_size=10,
        init=_init_connection,
        ssl="require",
    )


async def close_db():
    """Drain the pool (called once at shutdown)."""
    global pool
    if pool:
        await pool.close()
        pool = None


async def get_db():
    """FastAPI dependency — yields a connection back to the pool."""
    async with pool.acquire() as conn:
        yield conn
