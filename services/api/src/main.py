"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, is_write_enabled
from .database import init_db
from .routers import (
    drives, roots, files, scan, items, hash, ops, cleanup, exports,
    domains, simulation, plans, expert, advanced_copy, placement,
    reduction, evacuation, analytics, recovery, normalize, overrides,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    
    # Run v2.0.0 migration
    from .database import get_db
    from .migrations.v200 import run_migration
    async with get_db() as db:
        await run_migration(db)
    
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Milestone API",
    description="File scanner with expert mode, failure domains, bulk planning, simulations, and exports",
    version="2.0.0",
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

# Include routers — core
app.include_router(drives.router)
app.include_router(roots.router)
app.include_router(files.router)
app.include_router(scan.router)
app.include_router(items.router)
app.include_router(hash.router)
app.include_router(ops.router)
app.include_router(cleanup.router)
app.include_router(exports.router)
app.include_router(domains.router)
app.include_router(simulation.router)
app.include_router(plans.router)

# Include routers — v2.0.0 expert mode & advanced features
app.include_router(expert.router)
app.include_router(advanced_copy.router)
app.include_router(placement.router)
app.include_router(reduction.router)
app.include_router(evacuation.router)
app.include_router(analytics.router)
app.include_router(recovery.router)
app.include_router(normalize.router)
app.include_router(overrides.router)


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
