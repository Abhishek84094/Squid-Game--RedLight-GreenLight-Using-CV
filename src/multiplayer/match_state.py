"""
Server-authoritative multiplayer match rules.

Same red-light/green-light rules as the single-player src/game_state.py,
generalized to N players (up to 5 concurrent) sharing one light cycle.
Deliberately has zero socket/threading imports so it's unit-testable on its own
(see tests/test_multiplayer_match.py) - server/ws/multiplayer_ws.py is the only
place that wires it up to real networking.

Every player sends up their own movement_score each tick (computed
locally on their machine from their own webcam); the server is the single
source of truth for whose light is red/green and who's still alive.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto

from src import config


class LightPhase(Enum):
    WAITING = auto()
    COUNTDOWN = auto()
    GREEN = auto()
    RED = auto()
    FINISHED = auto()


@dataclass
class PlayerState:
    game_id: str
    name: str
    avatar_color: str
    ready: bool = False
    alive: bool = True
    finished: bool = False
    distance: float = 0.0
    score: int = 0
    is_moving: bool = False
    elimination_reason: str | None = None
    finish_time_sec: float | None = None
    longest_freeze_sec: float = 0.0
    _freeze_clock: float = field(default=0.0, repr=False)
    _over_threshold_frames: int = field(default=0, repr=False)


class MultiplayerMatch:
    def __init__(self):
        self.phase = LightPhase.WAITING
        self.phase_timer = 0.0
        self.phase_duration = 0.0
        self.elapsed_sec = 0.0
        self.time_since_light_change = 0.0
        self.players: dict[str, PlayerState] = {}
        self.winner_game_id: str | None = None
        self.over = False
        self._latest_scores: dict[str, float] = {}
        self.new_eliminations: list[PlayerState] = []
        self.rankings: list[dict] = []

    def reset(self):
        self.phase = LightPhase.WAITING
        self.phase_timer = 0.0
        self.phase_duration = 0.0
        self.elapsed_sec = 0.0
        self.time_since_light_change = 0.0
        self.winner_game_id = None
        self.over = False
        self._latest_scores.clear()
        self.new_eliminations.clear()
        self.rankings.clear()
        for p in self.players.values():
            p.ready = False
            p.alive = True
            p.finished = False
            p.distance = 0.0
            p.score = 0
            p.is_moving = False
            p.elimination_reason = None
            p.finish_time_sec = None
            p.longest_freeze_sec = 0.0
            p._freeze_clock = 0.0
            p._over_threshold_frames = 0

    # -- roster ---------------------------------------------------------
    def can_add_player(self) -> bool:
        return len(self.players) < config.MULTIPLAYER_MAX_PLAYERS

    def add_player(self, game_id: str, name: str, avatar_color: str) -> bool:
        if game_id in self.players:
            return True
        if len(self.players) >= config.MULTIPLAYER_MAX_PLAYERS:
            return False
        self.players[game_id] = PlayerState(game_id=game_id, name=name, avatar_color=avatar_color)
        return True

    def remove_player(self, game_id: str):
        self.players.pop(game_id, None)

    def mark_disconnected(self, game_id: str):
        """Used when a player drops mid-match: eliminate them rather than
        erasing them, so the remaining players' win condition stays correct."""
        p = self.players.get(game_id)
        if p and p.alive and not p.finished:
            p.alive = False
            p.elimination_reason = "Disconnected"
            self.new_eliminations.append(p)

    def all_ready(self) -> bool:
        return len(self.players) > 0 and all(p.ready for p in self.players.values())

    # -- lifecycle --------------------------------------------------------
    def start_countdown(self):
        self.phase = LightPhase.COUNTDOWN
        self.phase_timer = 0.0
        self.phase_duration = config.COUNTDOWN_SEC
        self.new_eliminations.clear()
        self.rankings.clear()

    def _enter_green(self):
        self.phase = LightPhase.GREEN
        self.phase_timer = 0.0
        self.phase_duration = random.uniform(config.GREEN_LIGHT_MIN_SEC, config.GREEN_LIGHT_MAX_SEC)
        self.time_since_light_change = 0.0
        for p in self.players.values():
            p._over_threshold_frames = 0

    def _enter_red(self):
        self.phase = LightPhase.RED
        self.phase_timer = 0.0
        self.phase_duration = random.uniform(config.RED_LIGHT_MIN_SEC, config.RED_LIGHT_MAX_SEC)
        self.time_since_light_change = 0.0
        for p in self.players.values():
            p._over_threshold_frames = 0
            p._freeze_clock = 0.0

    # -- main tick --------------------------------------------------------
    def update(self, dt: float, movement_scores: dict[str, float]) -> None:
        if self.over:
            return

        self.time_since_light_change += dt

        if self.phase == LightPhase.WAITING:
            return

        if self.phase == LightPhase.COUNTDOWN:
            self.phase_timer += dt
            if self.phase_timer >= self.phase_duration:
                self._enter_green()
            return

        self.elapsed_sec += dt
        self.phase_timer += dt

        if self.elapsed_sec >= config.MATCH_TIME_LIMIT_SEC:
            self._end_match()
            return

        active = [p for p in self.players.values() if p.alive and not p.finished]
        for p in active:
            score = movement_scores.get(p.game_id, 0.0)
            if self.phase == LightPhase.GREEN:
                self._tick_green_player(p, dt, score)
            elif self.phase == LightPhase.RED:
                self._tick_red_player(p, dt, score)

        # Check if anyone finished
        finishers = [p for p in self.players.values() if p.finished]
        if finishers:
            self._end_match()
            return

        active = [p for p in self.players.values() if p.alive and not p.finished]
        if not active:
            # Everyone eliminated
            self._end_match()
            return

        if len(self.players) > 1 and len(active) == 1:
            # Lone remaining player wins by survival
            self._end_match()
            return

        if self.phase == LightPhase.GREEN and self.phase_timer >= self.phase_duration:
            self._enter_red()
        elif self.phase == LightPhase.RED and self.phase_timer >= self.phase_duration:
            self._enter_green()

    def _tick_green_player(self, p: PlayerState, dt: float, score: float):
        p.is_moving = score >= config.GREEN_LIGHT_MIN_SCORE_TO_MOVE
        if p.is_moving:
            p.distance += score * config.MOVEMENT_TO_DISTANCE_SCALE * dt
        if p.distance >= config.DISTANCE_TO_WIN:
            p.distance = config.DISTANCE_TO_WIN
            p.finished = True
            p.finish_time_sec = self.elapsed_sec

    def _tick_red_player(self, p: PlayerState, dt: float, score: float):
        p.is_moving = score > config.RED_LIGHT_MOVEMENT_THRESHOLD
        p._freeze_clock += dt
        p.longest_freeze_sec = max(p.longest_freeze_sec, p._freeze_clock)
        in_grace = self.time_since_light_change <= config.RED_LIGHT_GRACE_PERIOD_SEC
        if score > config.RED_LIGHT_MOVEMENT_THRESHOLD and not in_grace:
            p._over_threshold_frames += 1
        else:
            p._over_threshold_frames = 0
        if p._over_threshold_frames >= config.RED_LIGHT_CONSECUTIVE_FRAMES:
            p.alive = False
            p.elimination_reason = "Moved during Red Light"
            self.new_eliminations.append(p)

    def _end_match(self):
        self.phase = LightPhase.FINISHED
        self.over = True
        for p in self.players.values():
            p.score = int(p.distance * 10)

        # 1. Determine Winner
        finishers = sorted(
            [p for p in self.players.values() if p.finished],
            key=lambda p: (p.finish_time_sec or 9999.0, -p.distance),
        )
        if finishers:
            self.winner_game_id = finishers[0].game_id
        else:
            survivors = [p for p in self.players.values() if p.alive]
            if survivors:
                survivors.sort(key=lambda p: (-p.distance, -p.longest_freeze_sec))
                self.winner_game_id = survivors[0].game_id
            else:
                self.winner_game_id = None  # everyone eliminated

        # 2. Build complete rankings list
        # Order: Finishers (by finish time) -> Survivors (by distance) -> Eliminated (by distance, then freeze)
        finishers = sorted(
            [p for p in self.players.values() if p.finished],
            key=lambda p: (p.finish_time_sec or 9999.0, -p.distance),
        )
        survivors = sorted(
            [p for p in self.players.values() if p.alive and not p.finished],
            key=lambda p: (-p.distance, -p.longest_freeze_sec),
        )
        eliminated = sorted(
            [p for p in self.players.values() if not p.alive],
            key=lambda p: (-p.distance, -p.longest_freeze_sec),
        )

        all_ordered = finishers + survivors + eliminated
        self.rankings = []
        for idx, p in enumerate(all_ordered, start=1):
            status = "Winner" if p.game_id == self.winner_game_id else ("Finished" if p.finished else ("Alive" if p.alive else "Eliminated"))
            self.rankings.append({
                "rank": idx,
                "game_id": p.game_id,
                "name": p.name,
                "avatar_color": p.avatar_color,
                "distance": round(p.distance, 2),
                "score": p.score,
                "status": status,
                "time_taken_sec": round(p.finish_time_sec or self.elapsed_sec, 1),
                "longest_freeze_sec": round(p.longest_freeze_sec, 1),
                "elimination_reason": p.elimination_reason,
            })

    # -- serialization for the network ------------------------------------
    def to_dict(self) -> dict:
        return {
            "phase": self.phase.name,
            "phase_timer": round(self.phase_timer, 2),
            "phase_duration": round(self.phase_duration, 2),
            "elapsed_sec": round(self.elapsed_sec, 2),
            "over": self.over,
            "winner_game_id": self.winner_game_id,
            "distance_to_win": config.DISTANCE_TO_WIN,
            "rankings": self.rankings,
            "players": {
                gid: {
                    "game_id": p.game_id,
                    "name": p.name,
                    "avatar_color": p.avatar_color,
                    "alive": p.alive,
                    "finished": p.finished,
                    "distance": round(p.distance, 2),
                    "score": p.score,
                    "is_moving": p.is_moving,
                    "elimination_reason": p.elimination_reason,
                    "longest_freeze_sec": round(p.longest_freeze_sec, 1),
                }
                for gid, p in self.players.items()
            },
        }
