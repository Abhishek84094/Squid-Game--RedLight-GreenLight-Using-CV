"""
SQLite persistence layer.

Handles player profiles, lifetime statistics, and match history. Kept as
plain sqlite3 (stdlib) so the project has zero extra dependency for storage
and SQLite file can be swapped for PostgreSQL later without touching game
logic (see README -> "Growing this project").
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from src import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    avatar_color TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stats (
    player_id        INTEGER PRIMARY KEY REFERENCES players(id),
    games_played     INTEGER NOT NULL DEFAULT 0,
    wins             INTEGER NOT NULL DEFAULT 0,
    losses           INTEGER NOT NULL DEFAULT 0,
    eliminations     INTEGER NOT NULL DEFAULT 0,
    fastest_time_sec REAL,
    best_distance    REAL NOT NULL DEFAULT 0,
    longest_freeze_sec REAL NOT NULL DEFAULT 0,
    total_distance   REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS match_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER REFERENCES players(id),
    mode        TEXT NOT NULL,
    result      TEXT NOT NULL,
    distance    REAL NOT NULL,
    time_taken_sec REAL NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,
    played_at   TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin wrapper around sqlite3 exposing the game's data operations."""

    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ #
    # Players
    # ------------------------------------------------------------------ #
    def create_player(self, name: str, avatar_color: str = "#ff2d82") -> dict:
        game_id = f"P-{uuid.uuid4().hex[:6].upper()}"
        cur = self.conn.execute(
            "INSERT INTO players (game_id, name, avatar_color, created_at) "
            "VALUES (?, ?, ?, ?)",
            (game_id, name, avatar_color, _now()),
        )
        player_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO stats (player_id) VALUES (?)", (player_id,)
        )
        self.conn.commit()
        return self.get_player_by_id(player_id)

    def get_player_by_id(self, player_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_player_by_game_id(self, game_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM players WHERE game_id = ?", (game_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_players(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM players ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Stats
    # ------------------------------------------------------------------ #
    def get_stats(self, player_id: int) -> dict:
        row = self.conn.execute(
            "SELECT * FROM stats WHERE player_id = ?", (player_id,)
        ).fetchone()
        return dict(row) if row else {}

    def record_match(
        self,
        player_id: int,
        mode: str,
        result: str,          # "victory" | "eliminated" | "timeout"
        distance: float,
        time_taken_sec: float,
        score: int,
        freeze_duration_sec: float = 0.0,
    ) -> None:
        self.conn.execute(
            "INSERT INTO match_history "
            "(player_id, mode, result, distance, time_taken_sec, score, played_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (player_id, mode, result, distance, time_taken_sec, score, _now()),
        )

        stats = self.get_stats(player_id)
        games_played = stats.get("games_played", 0) + 1
        wins = stats.get("wins", 0) + (1 if result == "victory" else 0)
        losses = stats.get("losses", 0) + (1 if result != "victory" else 0)
        eliminations = stats.get("eliminations", 0) + (1 if result == "eliminated" else 0)
        best_distance = max(stats.get("best_distance", 0) or 0, distance)
        total_distance = (stats.get("total_distance", 0) or 0) + distance
        longest_freeze = max(stats.get("longest_freeze_sec", 0) or 0, freeze_duration_sec)

        fastest = stats.get("fastest_time_sec")
        if result == "victory":
            fastest = time_taken_sec if fastest is None else min(fastest, time_taken_sec)

        self.conn.execute(
            "UPDATE stats SET games_played=?, wins=?, losses=?, eliminations=?, "
            "fastest_time_sec=?, best_distance=?, longest_freeze_sec=?, total_distance=? "
            "WHERE player_id=?",
            (
                games_played, wins, losses, eliminations,
                fastest, best_distance, longest_freeze, total_distance,
                player_id,
            ),
        )
        self.conn.commit()

    def match_history_for(self, player_id: int, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM match_history WHERE player_id = ? "
            "ORDER BY played_at DESC LIMIT ?",
            (player_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Leaderboard
    # ------------------------------------------------------------------ #
    def leaderboard(self, order_by: str = "wins", limit: int = 10) -> list[dict]:
        assert order_by in {"wins", "best_distance", "total_distance", "fastest_time_sec"}
        direction = "ASC" if order_by == "fastest_time_sec" else "DESC"
        rows = self.conn.execute(
            f"""
            SELECT p.name, p.game_id, s.*
            FROM stats s JOIN players p ON p.id = s.player_id
            WHERE s.games_played > 0
            ORDER BY s.{order_by} {direction}
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Face label <-> player_id mapping (used by face_auth.py alongside the LBPH
# model, since LBPH only knows integer labels, not our string game_ids).
# ---------------------------------------------------------------------------
def load_face_labels() -> dict:
    try:
        with open(config.FACE_LABELS_PATH, "r") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except FileNotFoundError:
        return {}


def save_face_labels(labels: dict) -> None:
    with open(config.FACE_LABELS_PATH, "w") as f:
        json.dump({str(k): v for k, v in labels.items()}, f, indent=2)
