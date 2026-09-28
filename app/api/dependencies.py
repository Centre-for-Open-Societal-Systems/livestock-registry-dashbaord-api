import asyncpg
from fastapi import Request


async def get_db_pool(request: Request) -> asyncpg.Pool:
    """Dependency to retrieve the asyncpg connection pool from the app state."""
    return request.app.state.pool
