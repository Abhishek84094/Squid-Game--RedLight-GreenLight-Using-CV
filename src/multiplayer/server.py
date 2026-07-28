"""
RoomServer: what "Create Room" starts.

Binds a TCP socket on an OS-assigned free port, listens for direct
connections, and runs one server-authoritative MultiplayerMatch. No
matchmaking, no discovery, no directory of open rooms anywhere - the only
way to find this room is to be given its code directly by the host.
"""

from __future__ import annotations

import socket
import threading
import time

from src.multiplayer.match_state import MultiplayerMatch
from src.multiplayer.protocol import LineReader, encode_room_code, get_lan_ip, send_json

TICK_RATE_HZ = 20


class RoomServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.lan_ip = get_lan_ip()
        self.room_code = encode_room_code(self.lan_ip, self.port)

        self.match = MultiplayerMatch()
        self.clients: dict[str, socket.socket] = {}
        self.movement_scores: dict[str, float] = {}
        self.host_game_id: str | None = None
        self.match_started = False
        self.running = True
        self.last_error: str | None = None

        self.lock = threading.Lock()
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)

    def start(self):
        self._accept_thread.start()
        self._tick_thread.start()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass
        with self.lock:
            for s in self.clients.values():
                try:
                    s.close()
                except OSError:
                    pass

    # -- accepting connections -------------------------------------------
    def _accept_loop(self):
        while self.running:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn: socket.socket):
        reader = LineReader(conn)
        game_id: str | None = None
        try:
            while self.running:
                messages = reader.read_messages()
                if messages is None:
                    break
                for msg in messages:
                    game_id = self._handle_message(conn, msg, game_id) or game_id
        finally:
            self._on_client_gone(game_id)
            try:
                conn.close()
            except OSError:
                pass

    def _on_client_gone(self, game_id: str | None):
        if not game_id:
            return
        with self.lock:
            self.clients.pop(game_id, None)
            self.movement_scores.pop(game_id, None)
            if self.match_started:
                self.match.mark_disconnected(game_id)
            else:
                self.match.remove_player(game_id)
        self._broadcast_lobby()

    # -- message handling ---------------------------------------------------
    def _handle_message(self, conn: socket.socket, msg: dict, game_id: str | None) -> str | None:
        mtype = msg.get("type")

        if mtype == "join":
            game_id = msg["game_id"]
            with self.lock:
                is_first = len(self.clients) == 0
                self.clients[game_id] = conn
                self.match.add_player(game_id, msg["name"], msg.get("avatar_color", "#ff2d82"))
                if is_first:
                    self.host_game_id = game_id
            self._broadcast_lobby()
            return game_id

        if mtype == "ready":
            with self.lock:
                if game_id in self.match.players:
                    self.match.players[game_id].ready = bool(msg.get("ready", False))
            self._broadcast_lobby()
            return game_id

        if mtype == "start_match" and game_id == self.host_game_id and not self.match_started:
            with self.lock:
                can_start = self.match.all_ready()
            if can_start:
                with self.lock:
                    self.match_started = True
                    self.match.start_countdown()
                self._broadcast({"type": "match_starting"})
            else:
                send_json(conn, {"type": "start_rejected", "reason": "Not everyone is ready yet"})
            return game_id

        if mtype == "movement":
            with self.lock:
                self.movement_scores[game_id] = float(msg.get("score", 0.0))
            return game_id

        return game_id

    # -- broadcasting -------------------------------------------------------
    def _broadcast(self, obj: dict):
        with self.lock:
            dead = []
            for gid, s in self.clients.items():
                try:
                    send_json(s, obj)
                except OSError:
                    dead.append(gid)
            for gid in dead:
                self.clients.pop(gid, None)

    def _broadcast_lobby(self):
        with self.lock:
            players = [
                {
                    "game_id": gid,
                    "name": p.name,
                    "avatar_color": p.avatar_color,
                    "ready": p.ready,
                    "is_host": gid == self.host_game_id,
                }
                for gid, p in self.match.players.items()
            ]
        self._broadcast({"type": "lobby_update", "players": players, "room_code": self.room_code})

    # -- tick loop ------------------------------------------------------
    def _tick_loop(self):
        last = time.monotonic()
        while self.running:
            time.sleep(1.0 / TICK_RATE_HZ)
            now = time.monotonic()
            dt = now - last
            last = now
            if not self.match_started:
                continue
            with self.lock:
                scores = dict(self.movement_scores)
                self.match.update(dt, scores)
                state = self.match.to_dict()
            self._broadcast({"type": "state_update", **state})
