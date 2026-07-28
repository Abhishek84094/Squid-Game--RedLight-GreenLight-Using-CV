"""
RoomClient: the network connection every player (host included - the host
connects to its own RoomServer on localhost, so both roles share one code
path) uses to join a room, ready up, and exchange gameplay state.
"""

from __future__ import annotations

import socket
import threading

from src.multiplayer.protocol import LineReader, send_json


class RoomClient:
    def __init__(self, ip: str, port: int, connect_timeout: float = 4.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(connect_timeout)
        self.sock.connect((ip, port))
        self.sock.settimeout(None)

        self.reader = LineReader(self.sock)
        self.lock = threading.Lock()
        self.latest_lobby: dict | None = None
        self.latest_state: dict | None = None
        self.match_starting = False
        self.start_rejected_reason: str | None = None
        self.connected = True

        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self):
        while self.connected:
            messages = self.reader.read_messages()
            if messages is None:
                self.connected = False
                break
            for msg in messages:
                mtype = msg.get("type")
                with self.lock:
                    if mtype == "lobby_update":
                        self.latest_lobby = msg
                    elif mtype == "state_update":
                        self.latest_state = msg
                    elif mtype == "match_starting":
                        self.match_starting = True
                    elif mtype == "start_rejected":
                        self.start_rejected_reason = msg.get("reason")

    def send(self, obj: dict):
        if not self.connected:
            return
        try:
            send_json(self.sock, obj)
        except OSError:
            self.connected = False

    def join(self, game_id: str, name: str, avatar_color: str):
        self.send({"type": "join", "game_id": game_id, "name": name, "avatar_color": avatar_color})

    def set_ready(self, ready: bool):
        self.send({"type": "ready", "ready": ready})

    def request_start(self):
        self.start_rejected_reason = None
        self.send({"type": "start_match"})

    def send_movement(self, score: float):
        self.send({"type": "movement", "score": score})

    def close(self):
        self.connected = False
        try:
            self.sock.close()
        except OSError:
            pass
