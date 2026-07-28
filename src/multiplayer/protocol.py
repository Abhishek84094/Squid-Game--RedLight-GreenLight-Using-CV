"""
Low-level networking helpers for private room multiplayer.

Design: there is NO matchmaking server and NO central lobby of strangers.
"Create Room" starts a small TCP server directly on the host's own
machine. The "room code" is nothing more than the host's IP address and
port, packed into a short alphanumeric string. Sharing that code (out of
band - text, Discord, voice call, whatever) is what lets a friend's game
client connect *directly* to the host. This is exactly what the user
asked for: room creation + join-by-code, with zero automatic pairing
with strangers.

Practical note: this works immediately over the same LAN/Wi-Fi. Playing
over the open internet needs the host to port-forward (or use a VPN like
Tailscale/Hamachi) since there's no relay server doing NAT traversal -
see README for details.
"""

from __future__ import annotations

import base64
import json
import socket
import struct


def get_lan_ip() -> str:
    """Best-effort local network IP (not 127.0.0.1) without sending any traffic."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def encode_room_code(ip: str, port: int) -> str:
    """Packs an IPv4 address + port into a short, typeable base32 code."""
    octets = [int(x) for x in ip.split(".")]
    if len(octets) != 4:
        raise ValueError(f"Not a valid IPv4 address: {ip}")
    packed = struct.pack("!BBBBH", *octets, port)
    return base64.b32encode(packed).decode("ascii").rstrip("=")


def decode_room_code(code: str) -> tuple[str, int]:
    code = code.strip().upper().replace(" ", "").replace("-", "")
    padded = code + "=" * (-len(code) % 8)
    try:
        packed = base64.b32decode(padded)
        o1, o2, o3, o4, port = struct.unpack("!BBBBH", packed)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"'{code}' doesn't look like a valid room code") from exc
    return f"{o1}.{o2}.{o3}.{o4}", port


def send_json(sock: socket.socket, obj: dict) -> None:
    data = (json.dumps(obj) + "\n").encode("utf-8")
    sock.sendall(data)


class LineReader:
    """Buffers raw TCP bytes into complete newline-delimited JSON messages."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buffer = b""

    def read_messages(self) -> list[dict] | None:
        """Blocks on one recv() call. Returns a list of parsed messages
        (possibly empty), or None to signal the connection closed."""
        try:
            chunk = self.sock.recv(65536)
        except OSError:
            return None
        if not chunk:
            return None

        self.buffer += chunk
        messages = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if line.strip():
                try:
                    messages.append(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError:
                    pass
        return messages
