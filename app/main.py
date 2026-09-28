from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import get_db_pool
from app.api.routes.router import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool
    app.state.pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        # Unset or empty lets asyncpg use the password in the DSN, if any.
        password=settings.PGPASSWORD or None,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
    )
    yield
    # Clean up the pool on shutdown
    await app.state.pool.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health(pool: asyncpg.Pool = Depends(get_db_pool)):
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"status": "ok"}


# Include the main API router
app.include_router(api_router, prefix=settings.API_V1_STR)
