"""
FastAPI application entry point.

Run locally:
    uvicorn server.main:app --reload --port 8000

Deploy (Railway / Render):
    uvicorn server.main:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.database import Database
from src.face_auth import FaceAuth
from server.routes import auth as auth_routes
from server.routes import game as game_routes
from server.ws import game_ws, multiplayer_ws

# ---------------------------------------------------------------------------
# Init shared singletons
# ---------------------------------------------------------------------------
db = Database()
face_auth = FaceAuth(db)

auth_routes.init(db, face_auth)
game_routes.init(db)
game_ws.init(db)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Red Light Green Light", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# REST routes
app.include_router(auth_routes.router)
app.include_router(game_routes.router)

# WebSocket routes
app.include_router(game_ws.router)
app.include_router(multiplayer_ws.router)

# Base project root
BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
IMAGES_DIR = BASE_DIR / "images"
MUSIC_DIR = BASE_DIR / "squid-music"

if IMAGES_DIR.exists():
    app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

if MUSIC_DIR.exists():
    app.mount("/squid-music", StaticFiles(directory=str(MUSIC_DIR)), name="squid-music")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        """Return requested file from frontend/images/squid-music or fallback to index.html for SPA routing."""
        # 1. Check frontend directory
        f_file = FRONTEND_DIR / full_path
        if f_file.exists() and f_file.is_file():
            return FileResponse(str(f_file))

        # 2. Check root directory (for images/..., squid-music/...)
        r_file = BASE_DIR / full_path
        if r_file.exists() and r_file.is_file():
            return FileResponse(str(r_file))

        return FileResponse(str(FRONTEND_DIR / "index.html"))

