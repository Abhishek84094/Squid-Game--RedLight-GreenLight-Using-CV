import random

from src import config
from src.game_state import GameState, Phase


def run_countdown(state: GameState):
    while state.phase == Phase.COUNTDOWN:
        state.update(0.1, 0.0)


def test_countdown_transitions_to_green_light():
    state = GameState()
    state.start_countdown()
    run_countdown(state)
    assert state.phase == Phase.GREEN_LIGHT


def test_moving_during_green_light_increases_distance():
    random.seed(1)
    state = GameState()
    state.start_countdown()
    run_countdown(state)
    before = state.distance
    for _ in range(10):
        state.update(0.1, movement_score=10.0)
        if state.phase != Phase.GREEN_LIGHT:
            break
    assert state.distance > before


def test_freezing_during_red_light_survives():
    random.seed(2)
    state = GameState()
    state.phase = Phase.RED_LIGHT
    state.phase_duration = 5.0
    for _ in range(20):
        state.update(0.05, movement_score=0.0)
    assert state.phase == Phase.RED_LIGHT
    assert not state.is_over


def test_moving_during_red_light_eliminates():
    random.seed(3)
    state = GameState(practice_mode=False)
    state.phase = Phase.RED_LIGHT
    state.phase_duration = 5.0
    state.time_since_light_change = 10.0  # well past the grace period
    for _ in range(config.RED_LIGHT_CONSECUTIVE_FRAMES + 1):
        state.update(0.05, movement_score=config.RED_LIGHT_MOVEMENT_THRESHOLD + 5.0)
    assert state.phase == Phase.ELIMINATED
    assert state.result.outcome == "eliminated"


def test_practice_mode_never_eliminates():
    random.seed(4)
    state = GameState(practice_mode=True)
    state.phase = Phase.RED_LIGHT
    state.phase_duration = 5.0
    state.time_since_light_change = 10.0
    for _ in range(config.RED_LIGHT_CONSECUTIVE_FRAMES + 5):
        state.update(0.05, movement_score=config.RED_LIGHT_MOVEMENT_THRESHOLD + 5.0)
    assert state.phase == Phase.RED_LIGHT
    assert not state.is_over


def test_reaching_distance_wins():
    state = GameState()
    state.phase = Phase.GREEN_LIGHT
    state.phase_duration = 1000.0
    state.distance = config.DISTANCE_TO_WIN - 1
    state.update(1.0, movement_score=50.0)
    assert state.phase == Phase.VICTORY
    assert state.result.outcome == "victory"


def test_match_time_limit_ends_in_timeout():
    state = GameState()
    state.phase = Phase.GREEN_LIGHT
    state.phase_duration = 1000.0
    state.elapsed_sec = config.MATCH_TIME_LIMIT_SEC - 0.05
    state.update(0.1, movement_score=0.0)
    assert state.phase == Phase.TIMEOUT
