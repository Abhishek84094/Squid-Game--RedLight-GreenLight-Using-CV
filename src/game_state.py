"""
The game's rules, independent of any rendering or input tech.

Kept deliberately free of pygame/opencv imports so the state machine can be
unit tested with plain numbers (see tests/test_game_state.py) and so it
would be re-usable as-is behind a server-authoritative multiplayer loop
later (see README).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto

from src import config


class Phase(Enum):
    WAITING = auto()
    COUNTDOWN = auto()
    GREEN_LIGHT = auto()
    RED_LIGHT = auto()
    ELIMINATED = auto()
    VICTORY = auto()
    TIMEOUT = auto()


@dataclass
class MatchResult:
    outcome: str            # "victory" | "eliminated" | "timeout"
    distance: float
    time_taken_sec: float
    score: int
    longest_freeze_sec: float


@dataclass
class GameState:
    practice_mode: bool = False

    phase: Phase = Phase.WAITING
    elapsed_sec: float = 0.0
    phase_timer: float = 0.0
    phase_duration: float = 0.0

    distance: float = 0.0
    score: int = 0

    over_threshold_frames: int = 0
    time_since_light_change: float = 0.0
    longest_freeze_sec: float = 0.0
    _freeze_clock: float = field(default=0.0, repr=False)

    result: MatchResult | None = None
    flash_warning: bool = False   # true for a brief moment when movement is flagged

    tempo: float = 1.0

    # -- lifecycle ------------------------------------------------------
    def start_countdown(self):
        self.phase = Phase.COUNTDOWN
        self.phase_timer = 0.0
        self.phase_duration = config.COUNTDOWN_SEC

    def _enter_green(self):
        self.phase = Phase.GREEN_LIGHT
        self.phase_timer = 0.0
        # Dynamic pace: Randomly select tempo mode (fast/slow/normal)
        # In Squid Game, doll randomly chants fast or slow to catch players off-guard!
        modes = [
            (1.0, 4.5),   # Normal chant
            (1.5, 3.0),   # Fast chant!
            (1.9, 2.2),   # Super fast quick-turn!
            (0.8, 5.5),   # Slow chant
        ]
        self.tempo, base_dur = random.choice(modes)
        # Add slight randomness
        self.phase_duration = base_dur * random.uniform(0.9, 1.1)
        self.time_since_light_change = 0.0
        self.over_threshold_frames = 0

    def _enter_red(self):
        self.phase = Phase.RED_LIGHT
        self.phase_timer = 0.0
        self.tempo = 1.0
        self.phase_duration = random.uniform(
            config.RED_LIGHT_MIN_SEC, config.RED_LIGHT_MAX_SEC
        )
        self.time_since_light_change = 0.0
        self.over_threshold_frames = 0
        self._freeze_clock = 0.0

    # -- main tick --------------------------------------------------------
    def update(self, dt: float, movement_score: float) -> None:
        """Advance the state machine by `dt` seconds given the latest
        movement_score from MovementScorer. No-op once match has ended."""
        self.flash_warning = False

        if self.phase in (Phase.ELIMINATED, Phase.VICTORY, Phase.TIMEOUT):
            return

        self.elapsed_sec += dt
        self.phase_timer += dt
        self.time_since_light_change += dt

        if self.phase == Phase.WAITING:
            return

        if self.phase == Phase.COUNTDOWN:
            if self.phase_timer >= self.phase_duration:
                self._enter_green()
            return

        if self.elapsed_sec >= config.MATCH_TIME_LIMIT_SEC:
            self._end_match("timeout")
            return

        if self.phase == Phase.GREEN_LIGHT:
            self._tick_green(dt, movement_score)
        elif self.phase == Phase.RED_LIGHT:
            self._tick_red(dt, movement_score)

    def _tick_green(self, dt: float, movement_score: float) -> None:
        if movement_score >= config.GREEN_LIGHT_MIN_SCORE_TO_MOVE:
            self.distance += movement_score * config.MOVEMENT_TO_DISTANCE_SCALE * dt

        if self.distance >= config.DISTANCE_TO_WIN:
            self.distance = config.DISTANCE_TO_WIN
            self._end_match("victory")
            return

        if self.phase_timer >= self.phase_duration:
            self._enter_red()

    def _tick_red(self, dt: float, movement_score: float) -> None:
        self._freeze_clock += dt
        self.longest_freeze_sec = max(self.longest_freeze_sec, self._freeze_clock)

        in_grace = self.time_since_light_change <= config.RED_LIGHT_GRACE_PERIOD_SEC
        if movement_score > config.RED_LIGHT_MOVEMENT_THRESHOLD and not in_grace:
            self.over_threshold_frames += 1
            self.flash_warning = True
        else:
            self.over_threshold_frames = 0

        if self.over_threshold_frames >= config.RED_LIGHT_CONSECUTIVE_FRAMES:
            if self.practice_mode:
                # Practice mode never eliminates - just resets the streak
                # so the player gets instant feedback and keeps playing.
                self.over_threshold_frames = 0
            else:
                self._end_match("eliminated")
                return

        if self.phase_timer >= self.phase_duration:
            self._enter_green()

    def _end_match(self, outcome: str) -> None:
        base_score = int(self.distance * 10)
        time_bonus = int(max(0, config.MATCH_TIME_LIMIT_SEC - self.elapsed_sec) * 5)
        self.score = base_score + (time_bonus if outcome == "victory" else 0)
        self.phase = {
            "victory": Phase.VICTORY,
            "eliminated": Phase.ELIMINATED,
            "timeout": Phase.TIMEOUT,
        }[outcome]
        self.result = MatchResult(
            outcome=outcome,
            distance=round(self.distance, 1),
            time_taken_sec=round(self.elapsed_sec, 1),
            score=self.score,
            longest_freeze_sec=round(self.longest_freeze_sec, 1),
        )

    # -- convenience ------------------------------------------------------
    @property
    def progress_fraction(self) -> float:
        return min(1.0, self.distance / config.DISTANCE_TO_WIN)

    @property
    def is_over(self) -> bool:
        return self.phase in (Phase.ELIMINATED, Phase.VICTORY, Phase.TIMEOUT)

    @property
    def is_red(self) -> bool:
        return self.phase == Phase.RED_LIGHT
