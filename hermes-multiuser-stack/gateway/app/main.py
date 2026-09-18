import asyncio
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db, hermes_manager
from .config import settings
from .routes import auth as auth_routes
from .routes import sessions as session_routes
from .routes import vtuber as vtuber_routes
from .routes import device as device_routes

_reaper_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _reaper_task
    await db.init_pool()
    _reaper_task = asyncio.create_task(hermes_manager.idle_reaper_loop())
    yield
    if _reaper_task:
        _reaper_task.cancel()
    await db.close_pool()


app = FastAPI(title="Hermes Multiuser Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(session_routes.router)
app.include_router(vtuber_routes.router)
app.include_router(device_routes.router)


@app.get("/health")
async def health():
    return {"ok": True}


_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
