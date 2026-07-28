import random

from src import config
from src.multiplayer.match_state import LightPhase, MultiplayerMatch


def run_countdown(m: MultiplayerMatch):
    while m.phase == LightPhase.COUNTDOWN:
        m.update(0.1, {})


def test_two_players_join_and_ready_up():
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.add_player("P2", "Bob", "#00ff00")
    assert not m.all_ready()
    m.players["P1"].ready = True
    assert not m.all_ready()
    m.players["P2"].ready = True
    assert m.all_ready()


def test_countdown_leads_to_green():
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.start_countdown()
    run_countdown(m)
    assert m.phase == LightPhase.GREEN


def test_first_to_finish_wins():
    random.seed(10)
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.add_player("P2", "Bob", "#00ff00")
    m.phase = LightPhase.GREEN
    m.phase_duration = 1000.0
    for _ in range(200):
        m.update(0.1, {"P1": 20.0, "P2": 3.0})
        if m.over:
            break
    assert m.over
    assert m.winner_game_id == "P1"
    assert m.players["P1"].finished


def test_elimination_during_red_light():
    random.seed(11)
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.add_player("P2", "Bob", "#00ff00")
    m.phase = LightPhase.RED
    m.phase_duration = 5.0
    m.time_since_light_change = 10.0
    for _ in range(config.RED_LIGHT_CONSECUTIVE_FRAMES + 1):
        m.update(0.05, {"P1": config.RED_LIGHT_MOVEMENT_THRESHOLD + 5.0, "P2": 0.0})
    assert not m.players["P1"].alive
    assert m.players["P1"].elimination_reason == "Moved during Red Light"
    assert m.players["P2"].alive


def test_last_survivor_wins_when_others_eliminated():
    random.seed(12)
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.add_player("P2", "Bob", "#00ff00")
    m.phase = LightPhase.RED
    m.phase_duration = 5.0
    m.time_since_light_change = 10.0
    for _ in range(config.RED_LIGHT_CONSECUTIVE_FRAMES + 1):
        m.update(0.05, {"P1": config.RED_LIGHT_MOVEMENT_THRESHOLD + 5.0, "P2": 0.0})
    assert m.over
    assert m.winner_game_id == "P2"


def test_disconnect_mid_match_ends_match_with_remaining_player_winning():
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    m.add_player("P2", "Bob", "#00ff00")
    m.phase = LightPhase.GREEN
    m.phase_duration = 1000.0
    m.mark_disconnected("P1")
    assert not m.players["P1"].alive
    assert m.players["P1"].elimination_reason == "Disconnected"
    m.update(0.1, {"P2": 0.0})
    assert m.over
    assert m.winner_game_id == "P2"


def test_to_dict_serializes_cleanly():
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    d = m.to_dict()
    assert d["players"]["P1"]["name"] == "Alice"
    assert d["phase"] == "WAITING"
