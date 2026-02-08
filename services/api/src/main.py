"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, is_write_enabled
from .database import init_db
from .routers import drives, roots, files, scan, items, hash


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Milestone API",
    description="File scanner backend with media grouping and hashing",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS for Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(drives.router)
app.include_router(roots.router)
app.include_router(files.router)
app.include_router(scan.router)
app.include_router(items.router)
app.include_router(hash.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Milestone API", "status": "running"}


@app.get("/health")
async def health() -> dict[str, str | bool]:
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "healthy",
        "write_mode": settings.write_mode,
    }


@app.get("/mode")
async def get_mode() -> dict[str, str]:
    """Get current operation mode."""
    mode = "write" if is_write_enabled() else "read-only"
    return {"mode": mode}
