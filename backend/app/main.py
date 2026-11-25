"""
FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router as api_router
from app.database.connection import init_db
from app.services.cache_service import initialize_cache
from app.utils.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes database schema and response caching on startup.
    """
    # 1. Initialize SQLite database schema
    init_db()

    # 2. Initialize LiteLLM response caching
    initialize_cache()

    yield

    # Shutdown tasks if needed


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title="Lyftr AI LLM Chatbot",
        description="Production-ready LLM Chatbot with Key Failover, Response Caching, and Multi-turn Memory.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register standardized exception handlers
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Include API routes
    app.include_router(api_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
