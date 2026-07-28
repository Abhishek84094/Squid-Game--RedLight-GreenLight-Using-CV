"""
Game REST endpoints:
  GET /api/leaderboard      – top players by wins
  GET /api/profile/{game_id}– player stats + match history
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from src.database import Database

router = APIRouter(prefix="/api")

_db: Database | None = None


def init(db: Database) -> None:
    global _db
    _db = db


def _get_db() -> Database:
    if _db is None:
        raise HTTPException(500, "DB not initialised")
    return _db


@router.get("/leaderboard")
async def leaderboard():
    db = _get_db()
    return db.leaderboard(order_by="wins", limit=20)


@router.get("/profile/{game_id}")
async def profile(game_id: str):
    db = _get_db()
    player = db.get_player_by_game_id(game_id)
    if not player:
        raise HTTPException(404, "Player not found")
    stats = db.get_stats(player["id"])
    history = db.match_history_for(player["id"], limit=10)
    return {"player": player, "stats": stats, "history": history}
