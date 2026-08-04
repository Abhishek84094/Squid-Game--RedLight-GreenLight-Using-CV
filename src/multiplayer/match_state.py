"""
Server-authoritative multiplayer match rules.

Same red-light/green-light rules as the single-player src/game_state.py,
generalized to N players sharing one light cycle. Deliberately has zero
socket/threading imports so it's unit-testable on its own (see
tests/test_multiplayer_match.py) - src/multiplayer/server.py is the only
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

    def reset(self):
        self.phase = LightPhase.WAITING
        self.phase_timer = 0.0
        self.phase_duration = 0.0
        self.elapsed_sec = 0.0
        self.time_since_light_change = 0.0
        self.winner_game_id = None
        self.over = False
        for p in self.players.values():
            p.ready = False
            p.alive = True
            p.finished = False
            p.distance = 0.0
            p.score = 0
            p.elimination_reason = None
            p.finish_time_sec = None
            p.longest_freeze_sec = 0.0
            p._freeze_clock = 0.0
            p._over_threshold_frames = 0

    # -- roster ---------------------------------------------------------
    def add_player(self, game_id: str, name: str, avatar_color: str):
        if game_id not in self.players:
            self.players[game_id] = PlayerState(game_id=game_id, name=name, avatar_color=avatar_color)

    def remove_player(self, game_id: str):
        self.players.pop(game_id, None)

    def mark_disconnected(self, game_id: str):
        """Used when a player drops mid-match: eliminate them rather than
        erasing them, so the remaining players' win condition stays correct."""
        p = self.players.get(game_id)
        if p and p.alive and not p.finished:
            p.alive = False
            p.elimination_reason = "Disconnected"

    def all_ready(self) -> bool:
        return len(self.players) > 0 and all(p.ready for p in self.players.values())

    # -- lifecycle --------------------------------------------------------
    def start_countdown(self):
        self.phase = LightPhase.COUNTDOWN
        self.phase_timer = 0.0
        self.phase_duration = config.COUNTDOWN_SEC

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

        active = [p for p in self.players.values() if p.alive and not p.finished]
        if not active:
            self._end_match()
            return
        if len(self.players) > 1 and len(active) == 1:
            # Everyone else has already finished or been eliminated - the
            # lone remaining player wins by survival, same as the show.
            self._end_match()
            return

        if self.phase == LightPhase.GREEN and self.phase_timer >= self.phase_duration:
            self._enter_red()
        elif self.phase == LightPhase.RED and self.phase_timer >= self.phase_duration:
            self._enter_green()

    def _tick_green_player(self, p: PlayerState, dt: float, score: float):
        if score >= config.GREEN_LIGHT_MIN_SCORE_TO_MOVE:
            p.distance += score * config.MOVEMENT_TO_DISTANCE_SCALE * dt
        if p.distance >= config.DISTANCE_TO_WIN:
            p.distance = config.DISTANCE_TO_WIN
            p.finished = True
            p.finish_time_sec = self.elapsed_sec

    def _tick_red_player(self, p: PlayerState, dt: float, score: float):
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

    def _end_match(self):
        self.phase = LightPhase.FINISHED
        self.over = True
        for p in self.players.values():
            p.score = int(p.distance * 10)

        finishers = sorted(
            (p for p in self.players.values() if p.finished),
            key=lambda p: p.finish_time_sec,
        )
        if finishers:
            self.winner_game_id = finishers[0].game_id
            return

        survivors = [p for p in self.players.values() if p.alive]
        if len(survivors) == 1:
            self.winner_game_id = survivors[0].game_id
        elif len(survivors) > 1:
            survivors.sort(key=lambda p: -p.distance)
            self.winner_game_id = survivors[0].game_id
        else:
            self.winner_game_id = None  # everyone eliminated, nobody wins

    # -- serialization for the network ------------------------------------
    def to_dict(self) -> dict:
        return {
            "phase": self.phase.name,
            "phase_timer": round(self.phase_timer, 2),
            "phase_duration": round(self.phase_duration, 2),
            "elapsed_sec": round(self.elapsed_sec, 2),
            "over": self.over,
            "winner_game_id": self.winner_game_id,
            "players": {
                gid: {
                    "name": p.name,
                    "avatar_color": p.avatar_color,
                    "alive": p.alive,
                    "finished": p.finished,
                    "distance": round(p.distance, 2),
                    "score": p.score,
                    "elimination_reason": p.elimination_reason,
                    "longest_freeze_sec": round(p.longest_freeze_sec, 1),
                }
                for gid, p in self.players.items()
            },
        }
