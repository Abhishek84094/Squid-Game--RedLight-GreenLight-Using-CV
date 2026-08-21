"""
Multiplayer WebSocket handler.

Flow:
  Host:   ws://<host>/ws/multi/{session_id}?action=create
          ← receives {"type": "room_created", "room_code": "ABCD1234"}
  Guest:  ws://<host>/ws/multi/{session_id}?action=join&room_code=ABCD1234
  Both:   send {"type": "ready"} → host sends {"type": "start"} to begin
          send {"type": "movement", "score": <float>} during play
          receive {"type": "match_state", ...} every tick
"""
from __future__ import annotations

import asyncio
import random
import string
import time
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.multiplayer.match_state import MultiplayerMatch
from server import session as sess

router = APIRouter()

# {room_code: MultiplayerMatch}
_rooms: dict[str, MultiplayerMatch] = {}
# {room_code: {game_id: WebSocket}}
_room_sockets: dict[str, dict[str, WebSocket]] = defaultdict(dict)
# {room_code: asyncio.Task}
_room_loops: dict[str, asyncio.Task] = {}
# {room_code: host_game_id}
_room_hosts: dict[str, str] = {}

TICK_RATE = 20


def _gen_room_code() -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(chars, k=8))
        if code not in _rooms:
            return code


async def _broadcast(room_code: str, msg: dict):
    sockets = list(_room_sockets[room_code].values())
    dead = []
    for ws in sockets:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    # clean up dead sockets
    if dead:
        for gid, ws in list(_room_sockets[room_code].items()):
            if ws in dead:
                _room_sockets[room_code].pop(gid, None)


async def _match_loop(room_code: str, match: MultiplayerMatch):
    last = time.monotonic()

    while not match.over:
        now = time.monotonic()
        dt = now - last
        last = now
        latest_scores = getattr(match, "_latest_scores", {})
        match.update(dt, latest_scores)

        state = match.to_dict()
        state["type"] = "match_state"
        await _broadcast(room_code, state)

        if match.over:
            break

        await asyncio.sleep(1 / TICK_RATE)

    # Final state
    final = match.to_dict()
    final["type"] = "match_over"
    await _broadcast(room_code, final)

    # Cleanup loop task only — keep room and sockets intact so players can replay in the same room
    _room_loops.pop(room_code, None)


@router.websocket("/ws/multi/{session_id}")
async def multi_ws(
    websocket: WebSocket,
    session_id: str,
    action: str = "create",
    room_code: str = "",
):
    player = sess.get_player(session_id)
    if not player:
        # Fallback for guest sessions
        from src import database
        db = database.Database()
        player = db.create_player("Guest Player")

    await websocket.accept()
    game_id = player["game_id"]
    name = player["name"]
    avatar_color = player.get("avatar_color", "#ff2d82")

    try:
        if action == "create":
            code = _gen_room_code()
            match = MultiplayerMatch()
            _rooms[code] = match
            _room_hosts[code] = game_id
            match.add_player(game_id, name, avatar_color)
            _room_sockets[code][game_id] = websocket
            await websocket.send_json({
                "type": "room_created",
                "room_code": code,
                "game_id": game_id,
            })
            await _broadcast(code, {"type": "lobby", "players": [
                {"game_id": gid, "name": p.name, "ready": p.ready}
                for gid, p in match.players.items()
            ]})

        elif action == "join":
            code = room_code.upper().strip()
            match = _rooms.get(code)
            if match is None:
                await websocket.send_json({"type": "error", "reason": "room_not_found"})
                await websocket.close()
                return
            if match.over:
                match.reset()
            match.add_player(game_id, name, avatar_color)
            _room_sockets[code][game_id] = websocket
            await websocket.send_json({
                "type": "joined",
                "room_code": code,
                "game_id": game_id,
            })
            # Notify everyone about the new player roster
            await _broadcast(code, {"type": "lobby", "players": [
                {"game_id": gid, "name": p.name, "ready": p.ready}
                for gid, p in match.players.items()
            ]})
        else:
            await websocket.close(code=4000, reason="Unknown action")
            return

        # Main message loop
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ready":
                match.players[game_id].ready = True
                await _broadcast(code, {"type": "lobby", "players": [
                    {"game_id": gid, "name": p.name, "ready": p.ready}
                    for gid, p in match.players.items()
                ]})

            elif msg_type == "start":
                # Only host can start
                if game_id == _room_hosts.get(code):
                    if match.over:
                        match.reset()
                    # Auto-ready all players when host clicks start match
                    for p in match.players.values():
                        p.ready = True
                    match.start_countdown()
                    loop = asyncio.create_task(_match_loop(code, match))
                    _room_loops[code] = loop
                    await _broadcast(code, {"type": "match_starting"})

            elif msg_type == "movement":
                score = float(data.get("score", 0.0))
                # Store score for match loop to use
                if code in _rooms:
                    # latest_scores is local to _match_loop; inject via player state proxy
                    # We use a dict attached to match as a side channel
                    if not hasattr(match, "_latest_scores"):
                        match._latest_scores = {}
                    match._latest_scores[game_id] = score

    except WebSocketDisconnect:
        # Mark disconnected player as eliminated
        if code in _rooms:
            room_match = _rooms[code]
            room_match.mark_disconnected(game_id)
            if hasattr(room_match, "_latest_scores"):
                room_match._latest_scores.pop(game_id, None)
            _room_sockets[code].pop(game_id, None)
            await _broadcast(code, {
                "type": "player_disconnected",
                "game_id": game_id,
            })
