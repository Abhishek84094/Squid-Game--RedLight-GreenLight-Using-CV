"""
Single-player WebSocket game handler.

Connect: ws://<host>/ws/game/<session_id>?mode=challenge|practice

Client → Server messages (JSON):
  {"type": "start"}                         – begin countdown
  {"type": "movement", "score": <float>}    – pose movement score from browser MediaPipe

Server → Client messages (JSON):
  {"type": "waiting"}
  {"type": "state", "phase": str, "distance": float, "progress": float,
   "flash": bool, "phase_timer": float, "phase_duration": float,
   "elapsed": float, "time_left": float, "score": int, "movement_score": float}
  {"type": "result", "outcome": str, "score": int, "distance": float,
   "time_taken_sec": float, "longest_freeze_sec": float}
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.game_state import GameState, Phase
from src import config
from server import session as sess
from src.database import Database

router = APIRouter()
_db: Database | None = None


def init(db: Database) -> None:
    global _db
    _db = db


TICK_RATE = 30  # fps


@router.websocket("/ws/game/{session_id}")
async def game_ws(websocket: WebSocket, session_id: str, mode: str = "challenge"):
    player = sess.get_player(session_id)
    if not player:
        await websocket.close(code=4001, reason="Invalid session")
        return

    await websocket.accept()

    game = GameState(practice_mode=(mode == "practice"))
    # Pose movement score from browser MediaPipe — drives both GREEN movement and RED detection
    latest_movement_score: float = 0.0
    running = True

    async def game_loop():
        nonlocal running
        last = time.monotonic()
        await websocket.send_json({"type": "waiting"})

        while running:
            now = time.monotonic()
            dt = now - last
            last = now

            game.update(dt, latest_movement_score)

            state_msg = {
                "type": "state",
                "phase": game.phase.name,
                "distance": round(game.distance, 2),
                "progress": round(game.progress_fraction, 4),
                "flash": game.flash_warning,
                "phase_timer": round(game.phase_timer, 2),
                "phase_duration": round(game.phase_duration, 2),
                "elapsed": round(game.elapsed_sec, 2),
                "time_left": round(max(0, config.MATCH_TIME_LIMIT_SEC - game.elapsed_sec), 1),
                "score": game.score,
                "movement_score": round(latest_movement_score, 2),
                "tempo": round(game.tempo, 2),
            }
            try:
                await websocket.send_json(state_msg)
            except Exception:
                running = False
                break

            if game.is_over:
                result = game.result
                try:
                    await websocket.send_json({
                        "type": "result",
                        "outcome": result.outcome,
                        "score": result.score,
                        "distance": result.distance,
                        "time_taken_sec": result.time_taken_sec,
                        "longest_freeze_sec": result.longest_freeze_sec,
                    })
                    if _db:
                        _db.record_match(
                            player_id=player["id"],
                            mode=mode,
                            result=result.outcome,
                            distance=result.distance,
                            time_taken_sec=result.time_taken_sec,
                            score=result.score,
                            freeze_duration_sec=result.longest_freeze_sec,
                        )
                except Exception:
                    pass
                running = False
                break

            await asyncio.sleep(1 / TICK_RATE)

    loop_task = asyncio.create_task(game_loop())

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "start":
                if game.phase == Phase.WAITING:
                    game.start_countdown()

            elif msg_type == "movement":
                # Body pose movement score from browser MediaPipe
                # Used to move character during GREEN and detect violations during RED
                latest_movement_score = float(data.get("score", 0.0))

    except WebSocketDisconnect:
        pass
    finally:
        running = False
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
