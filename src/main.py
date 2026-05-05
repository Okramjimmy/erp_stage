"""
Main FastAPI application for ERP Stage Builder.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add parent directory to path for imports when running from src/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.app.api import ui as ui_router
from src.app.api.v1 import form_records, form_types, metadata, permissions, stages, storage
import src.app.models  # noqa: F401 — ensures all models are registered with Base
from src.app.cache import cache
from src.app.database import close_db, init_db
from src.app.storage import init_storage
from src.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up ERP Stage Builder...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Connect to Redis
    await cache.connect()
    logger.info("Cache connected")

    # Initialize MinIO storage
    storage_initialized = init_storage()
    logger.info(f"Storage initialized: {'success' if storage_initialized else 'failed'}")

    yield

    # Shutdown
    logger.info("Shutting down ERP Stage Builder...")
    await close_db()
    await cache.disconnect()
    logger.info("Cleanup complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Hierarchical Stage & Form Builder ERP Module with lineage-based permissions",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="/app/src/static"), name="static")

# Jinja2 Templates
templates = Jinja2Templates(directory="/app/src/templates")

# Include UI routes (before API to avoid catch-all conflicts)
app.include_router(ui_router.router)

# Include API routers
app.include_router(stages.router, prefix="/api/v1")
app.include_router(form_types.router, prefix="/api/v1")
app.include_router(form_records.router, prefix="/api/v1")
app.include_router(permissions.router, prefix="/api/v1")
app.include_router(metadata.router, prefix="/api/v1")
app.include_router(storage.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "ERP Stage Builder API",
        "version": settings.app_version,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "database": "connected",
        "cache": "connected" if cache.redis_client else "disconnected",
        "storage": "connected" if init_storage() else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
