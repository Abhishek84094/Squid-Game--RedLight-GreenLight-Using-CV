import numpy as np

from src.pose_tracker import MovementScorer


def make_landmarks(offset=0.0, visibility=1.0):
    base = np.tile(np.array([0.5, 0.5, visibility]), (33, 1))
    base[:, 0] += offset
    return base


def test_no_movement_gives_low_score():
    scorer = MovementScorer()
    scorer.update(make_landmarks(0.0))
    score = scorer.update(make_landmarks(0.0))
    assert score < 0.5


def test_large_shift_gives_high_score():
    scorer = MovementScorer()
    scorer.update(make_landmarks(0.0))
    score = scorer.update(make_landmarks(0.2))
    assert score > 5.0


def test_low_visibility_landmarks_are_ignored():
    scorer = MovementScorer()
    scorer.update(make_landmarks(0.0, visibility=0.1))
    score = scorer.update(make_landmarks(0.5, visibility=0.1))
    # All landmarks below the visibility threshold -> score should hold steady, not spike
    assert score == 0.0 or score < 1.0


def test_missing_landmarks_does_not_crash_and_holds_last_score():
    scorer = MovementScorer()
    scorer.update(make_landmarks(0.0))
    scorer.update(make_landmarks(0.2))
    held = scorer.update(None)
    assert held == scorer.smoothed_score
