"""
Session management: maps session tokens → player dicts.
Simple in-memory store; suitable for single-process deployment.
"""
from __future__ import annotations

import uuid
from typing import Optional

# {session_id: player_dict}
_sessions: dict[str, dict] = {}

# Partial registrations: {name: {angle: count_saved}}
_pending_registrations: dict[str, dict] = {}


def create_session(player: dict) -> str:
    sid = str(uuid.uuid4())
    _sessions[sid] = player
    return sid


def get_player(session_id: str) -> Optional[dict]:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


# -- Partial registration helpers ------------------------------------------

def init_registration(name: str) -> None:
    _pending_registrations[name] = {"front": 0, "left": 0, "right": 0}


def increment_sample(name: str, angle: str) -> int:
    reg = _pending_registrations.get(name, {})
    reg[angle] = reg.get(angle, 0) + 1
    _pending_registrations[name] = reg
    return reg[angle]


def registration_progress(name: str) -> dict:
    return _pending_registrations.get(name, {})


def clear_registration(name: str) -> None:
    _pending_registrations.pop(name, None)
