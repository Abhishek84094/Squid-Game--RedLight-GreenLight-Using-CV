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
    for _ in range(300):
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


def test_five_players_cap_and_rejection():
    m = MultiplayerMatch()
    for i in range(1, 6):
        added = m.add_player(f"P{i}", f"Player {i}", "#ffffff")
        assert added is True
    assert len(m.players) == 5
    assert m.can_add_player() is False
    # 6th player attempt must return False
    sixth_added = m.add_player("P6", "Player 6", "#ffffff")
    assert sixth_added is False
    assert len(m.players) == 5


def test_five_players_eliminations_and_rankings():
    m = MultiplayerMatch()
    for i in range(1, 6):
        m.add_player(f"P{i}", f"Player {i}", "#ffffff")

    m.phase = LightPhase.GREEN
    m.phase_duration = 1000.0
    # Simulate movement: P1 runs fast, P2 moderate, P3 slow, P4 and P5 stand still
    for _ in range(50):
        m.update(0.1, {"P1": 10.0, "P2": 6.0, "P3": 3.0, "P4": 0.0, "P5": 0.0})

    # Switch to RED light
    m.phase = LightPhase.RED
    m.phase_duration = 10.0
    m.time_since_light_change = 5.0
    # P4 moves during red and gets eliminated
    for _ in range(config.RED_LIGHT_CONSECUTIVE_FRAMES + 1):
        m.update(0.05, {"P1": 0.0, "P2": 0.0, "P3": 0.0, "P4": 5.0, "P5": 0.0})

    assert not m.players["P4"].alive
    assert any(p.game_id == "P4" for p in m.new_eliminations)

    # Continue race on GREEN until P1 finishes
    m.phase = LightPhase.GREEN
    m.phase_duration = 1000.0
    for _ in range(250):
        m.update(0.1, {"P1": 20.0, "P2": 5.0, "P3": 2.0, "P5": 1.0})
        if m.over:
            break

    assert m.over
    assert m.winner_game_id == "P1"
    assert len(m.rankings) == 5
    # Rank 1 must be Winner (P1)
    assert m.rankings[0]["game_id"] == "P1"
    assert m.rankings[0]["status"] == "Winner"
    # P4 must be marked Eliminated
    p4_rank = next(r for r in m.rankings if r["game_id"] == "P4")
    assert p4_rank["status"] == "Eliminated"


def test_to_dict_serializes_cleanly():
    m = MultiplayerMatch()
    m.add_player("P1", "Alice", "#ff0000")
    d = m.to_dict()
    assert d["players"]["P1"]["name"] == "Alice"
    assert d["phase"] == "WAITING"
    assert "rankings" in d
    assert "distance_to_win" in d
